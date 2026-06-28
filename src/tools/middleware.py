# 参考 /mnt/h/DeepResearch/aiq/src/aiq_agent/agents/deep_researcher/custom_middleware.py 关于中间件的设计和实现
"""System guardrail middleware for GraphResearcher."""

import json
import logging
import re
import threading
import time
from typing import Optional

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

logger = logging.getLogger(__name__)

# Maximum number of Searcher dispatches per run; 0 (or less) means no limit.
_MAX_SEARCH_ROUNDS = 0


def configure(max_search_rounds: int) -> None:
    """Set the search-round budget for the current run.

    Args:
        max_search_rounds: Maximum number of Searcher dispatches; 0 means no
            limit. Resets the dispatch counter so the same process can run
            multiple times.
    """
    global _MAX_SEARCH_ROUNDS
    _MAX_SEARCH_ROUNDS = max_search_rounds


def get_max_search_rounds() -> int:
    """Return the configured persistent search budget for a new run."""
    return _MAX_SEARCH_ROUNDS


class ResearchStateMiddleware(AgentMiddleware):
    """Enforce the persistent research-state gate around Reporter and terminal text."""

    _RESEARCH_NUDGE = (
        "研究状态仍为 RESEARCHING，禁止生成最终报告或结束流程。"
        "请调用 get_next_actions，并严格执行返回的 assess_query、evaluate_research_portfolio、"
        "expand_gaps、dispatch_searcher 或 assess_convergence；"
        "完成动作后调用 assess_convergence。"
    )
    _REPORTER_NUDGE = (
        "研究状态已经允许生成最终报告，但规范报告必须由 reporter 子代理通过 "
        "submit_final_report 提交。禁止直接输出报告正文、摘要、表格或结论。"
        "请立即调用 task(subagent_type=\"reporter\", ...)；只向 reporter 传递用户研究目标。"
    )

    def __init__(self, max_repeated_failures: int = 3, max_reporter_nudges: int = 2):
        """Initialize the repeated state-changing failure breaker."""
        self.max_repeated_failures = max_repeated_failures
        self.max_reporter_nudges = max_reporter_nudges
        self._failure_lock = threading.Lock()
        self._last_failure_signature: Optional[str] = None
        self._repeated_failures = 0

    @staticmethod
    def _reporter_call(tool_call: dict) -> bool:
        return tool_call.get("name") == "task" and tool_call.get("args", {}).get("subagent_type") == "reporter"

    def _gate_reporter(self, tool_call: dict):
        if tool_call.get("name") != "task":
            return None
        if not self._reporter_call(tool_call):
            return ToolMessage(
                content=json.dumps({
                    "error": "Only the reporter subagent is allowed in this research workflow",
                }, ensure_ascii=False),
                tool_call_id=tool_call["id"],
                name="task",
                status="error",
            )
        from tools import research_state

        status = research_state.get_status()
        state = status.get("research_state")
        if state not in {research_state.REPORT_READY, research_state.BUDGET_EXHAUSTED}:
            return ToolMessage(
                content=json.dumps({
                    "error": "Reporter is not authorized while research is incomplete",
                    **status,
                }, ensure_ascii=False),
                tool_call_id=tool_call["id"],
                name="task",
                status="error",
            )
        from tools import graph_tools

        tree = graph_tools.validate_query_tree()
        if not tree.get("valid"):
            warning = "Query tree validation failed before Reporter authorization"
            logger.warning("%s: %s", warning, tree)
            research_state.update_goal({
                "reporter_warnings": [warning],
            })
        research_state.update_goal({
            "research_state": research_state.REPORTING,
            "reporting_from_state": state,
        })
        return None

    def _record_tool_result(self, tool_call: dict, result: object) -> object:
        """Fail the run after the same state-changing tool error repeats."""
        if tool_call.get("name") not in {
            "task",
            "init_research",
            "dispatch_searcher",
            "assess_query",
            "evaluate_research_portfolio",
            "expand_gaps",
            "assess_convergence",
        }:
            return result
        text = _message_text(result)
        try:
            payload = json.loads(text) if text else {}
        except (json.JSONDecodeError, ValueError):
            payload = {}
        error = payload.get("error") if isinstance(payload, dict) else None
        with self._failure_lock:
            if not error:
                self._last_failure_signature = None
                self._repeated_failures = 0
                return result
            signature = json.dumps({
                "name": tool_call.get("name"),
                "args": tool_call.get("args", {}),
                "error": error,
            }, ensure_ascii=False, sort_keys=True)
            if signature == self._last_failure_signature:
                self._repeated_failures += 1
            else:
                self._last_failure_signature = signature
                self._repeated_failures = 1
            if self._repeated_failures < self.max_repeated_failures:
                return result
        from tools import research_state

        research_state.update_goal({
            "research_state": research_state.FAILED,
            "last_error": f"Repeated identical failed tool action: {signature}",
        })
        return result

    def wrap_tool_call(self, request, handler):
        """Gate Reporter tool calls using the persistent research state."""
        blocked = self._gate_reporter(request.tool_call)
        result = blocked if blocked is not None else handler(request)
        return self._record_tool_result(request.tool_call, result)

    async def awrap_tool_call(self, request, handler):
        """Gate Reporter tool calls asynchronously."""
        blocked = self._gate_reporter(request.tool_call)
        result = blocked if blocked is not None else await handler(request)
        return self._record_tool_result(request.tool_call, result)

    @staticmethod
    def _researching_terminal(response) -> bool:
        last = _last_ai_message(response)
        if last is None or last.tool_calls:
            return False
        from tools import research_state

        return research_state.get_status().get("research_state") == research_state.RESEARCHING

    @staticmethod
    def _report_ready_terminal_without_report(response) -> bool:
        last = _last_ai_message(response)
        if last is None or last.tool_calls:
            return False
        from tools import graph_manager_tools, research_state

        state = research_state.get_status().get("research_state")
        if state not in {research_state.REPORT_READY, research_state.BUDGET_EXHAUSTED}:
            return False
        return not graph_manager_tools.get_compiled_report().strip()

    def wrap_model_call(self, request, handler):
        """Prevent terminal Orchestrator text before canonical report handoff."""
        response = handler(request)
        if self._researching_terminal(response):
            response = handler(request.override(messages=[*request.messages, HumanMessage(content=self._RESEARCH_NUDGE)]))
        for _ in range(self.max_reporter_nudges):
            if not self._report_ready_terminal_without_report(response):
                break
            response = handler(request.override(messages=[*request.messages, HumanMessage(content=self._REPORTER_NUDGE)]))
        return response

    async def awrap_model_call(self, request, handler):
        """Async counterpart of :meth:`wrap_model_call`."""
        response = await handler(request)
        if self._researching_terminal(response):
            response = await handler(request.override(messages=[*request.messages, HumanMessage(content=self._RESEARCH_NUDGE)]))
        for _ in range(self.max_reporter_nudges):
            if not self._report_ready_terminal_without_report(response):
                break
            response = await handler(request.override(messages=[*request.messages, HumanMessage(content=self._REPORTER_NUDGE)]))
        return response


def _message_text(message: object) -> str:
    """Extract plain text from a message's ``content`` (string or content blocks)."""
    content = getattr(message, "content", "")
    if isinstance(content, list):
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return content or ""


def _last_ai_message(response) -> object | None:
    """Return the last message of a ModelResponse, if it is an AIMessage."""
    result = getattr(response, "result", None) or []
    if not result:
        return None
    last = result[-1]
    return last if isinstance(last, AIMessage) else None


# Search tools that can substitute for each other when one returns an error.
_SEARCH_FALLBACK = {"serper_search": "tavily_search", "tavily_search": "serper_search"}


class SearchFallbackMiddleware(AgentMiddleware):
    """Transparently retries a failed web search with the alternate engine.

    Web-search tools return a dict containing an ``error`` key on failure
    (rate limit, no credits, network) instead of raising. When `serper_search`
    or `tavily_search` returns such a result, this middleware re-runs the same
    query through the other engine once, so a single dead engine does not waste
    the agent's turn. Falls back at most once per call (no loop).
    """

    @staticmethod
    def _is_error_result(result: object) -> bool:
        """Return True if a tool result (ToolMessage) carries an ``error`` key."""
        text = _message_text(result)
        if '"error"' not in text:
            return False
        try:
            data = json.loads(text)
            return isinstance(data, dict) and "error" in data
        except (json.JSONDecodeError, ValueError):
            return '"error"' in text

    def _alternate(self, tool_call: dict, result: object):
        """Run the alternate search engine if the primary result is an error.

        Returns:
            A replacement ``ToolMessage`` from the alternate engine, or ``None``.
        """
        name = tool_call.get("name")
        alt_name = _SEARCH_FALLBACK.get(name)
        if alt_name is None or not self._is_error_result(result):
            return None
        from tools import search_tools

        alt_tool = getattr(search_tools, alt_name)
        logger.info("Search engine %s failed; falling back to %s.", name, alt_name)
        try:
            alt_output = alt_tool.invoke(dict(tool_call.get("args", {})))
        except Exception as e:  # noqa: BLE001 — keep the original error result on fallback failure
            logger.warning("Fallback search %s also failed: %s", alt_name, e)
            return None
        content = alt_output if isinstance(alt_output, str) else json.dumps(alt_output, ensure_ascii=False)
        return ToolMessage(content=content, tool_call_id=tool_call["id"], name=name)

    def wrap_tool_call(self, request, handler):
        """Run the search tool, retrying with the alternate engine on error."""
        result = handler(request)
        return self._alternate(request.tool_call, result) or result

    async def awrap_tool_call(self, request, handler):
        """Async counterpart of :meth:`wrap_tool_call`."""
        result = await handler(request)
        return self._alternate(request.tool_call, result) or result


class EmptyResponseRetryMiddleware(AgentMiddleware):
    """Retries when the model returns an empty terminal response.

    Some models occasionally emit an ``AIMessage`` with no content and no tool
    calls, which would end the agent loop prematurely. This nudges the model to
    either continue with tool calls or produce a substantive answer.
    """

    _NUDGE = (
        "你上一条回复为空（没有内容也没有工具调用）。请继续推进：要么调用工具收集更多信息，"
        "要么直接输出完整、详实的结果。"
    )

    def __init__(self, min_content_length: int = 1, max_retries: int = 2):
        """Initialize the middleware.

        Args:
            min_content_length: Minimum non-whitespace length to count as non-empty.
            max_retries: Maximum nudge retries.
        """
        self.min_content_length = min_content_length
        self.max_retries = max_retries

    def _is_empty(self, response) -> bool:
        last = _last_ai_message(response)
        if last is None:
            return False
        if last.tool_calls:
            return False
        return len(_message_text(last).strip()) < self.min_content_length

    def wrap_model_call(self, request, handler):
        """Retry empty terminal responses with a nudge."""
        response = handler(request)
        for _ in range(self.max_retries):
            if not self._is_empty(response):
                break
            nudge = HumanMessage(content=self._NUDGE)
            response = handler(request.override(messages=[*request.messages, nudge]))
        return response

    async def awrap_model_call(self, request, handler):
        """Async counterpart of :meth:`wrap_model_call`."""
        response = await handler(request)
        for _ in range(self.max_retries):
            if not self._is_empty(response):
                break
            nudge = HumanMessage(content=self._NUDGE)
            response = await handler(request.override(messages=[*request.messages, nudge]))
        return response


class SensitiveWordsRetryMiddleware(AgentMiddleware):
    """Keeps the run alive when the model endpoint content-filters a request.

    The OpenAI-compatible proxy occasionally returns HTTP 500 with a
    ``sensitive_words`` code for an otherwise valid request. The OpenAI SDK
    cannot recover (retrying identical content fails again), and an uncaught
    error tears down the whole agent graph. On such an error this middleware:
    retries once after a short backoff (covers genuinely transient proxy 500s);
    then retries with the largest recent tool message clipped (the raw web dump
    is the usual trigger); and finally returns a short degraded response so the
    loop continues instead of crashing.
    """

    _DEGRADED = (
        "（系统提示：上游模型接口对本次请求触发了内容安全过滤，已跳过该步骤。"
        "请基于已收集并入图的证据继续推进；如需检索可换用更简短或不同措辞的查询。）"
    )

    def __init__(self, backoff_seconds: float = 2.0, clip_limit: int = 2000):
        """Initialize the middleware.

        Args:
            backoff_seconds: Wait before the first plain retry.
            clip_limit: Length to clip the largest tool message to on the
                second retry.
        """
        self.backoff_seconds = backoff_seconds
        self.clip_limit = clip_limit

    @staticmethod
    def _is_sensitive_error(exc: Exception) -> bool:
        """Return True if ``exc`` looks like a content-filter rejection."""
        return "sensitive" in str(exc).lower()

    def _clip_largest_tool_message(self, messages: list) -> list | None:
        """Return a copy of ``messages`` with the largest tool message clipped.

        Returns ``None`` when there is nothing worth clipping (no tool message
        longer than ``clip_limit``).
        """
        msgs = list(messages)
        idx, longest = None, -1
        for i, message in enumerate(msgs):
            if isinstance(message, ToolMessage):
                length = len(_message_text(message))
                if length > longest:
                    longest, idx = length, i
        if idx is None or longest <= self.clip_limit:
            return None
        original = msgs[idx]
        msgs[idx] = ToolMessage(
            content=_message_text(original)[: self.clip_limit] + "…（内容过长已截断以规避内容过滤）",
            tool_call_id=original.tool_call_id,
            name=getattr(original, "name", None),
        )
        return msgs

    def wrap_model_call(self, request, handler):
        """Recover from content-filter 500s; degrade gracefully if they persist."""
        try:
            return handler(request)
        except Exception as e:  # noqa: BLE001 — only content-filter errors are swallowed
            if not self._is_sensitive_error(e):
                raise
            logger.warning("Model call hit content filter: %s", e)
        time.sleep(self.backoff_seconds)
        try:
            return handler(request)
        except Exception as e:  # noqa: BLE001
            if not self._is_sensitive_error(e):
                raise
        clipped = self._clip_largest_tool_message(request.messages)
        if clipped is not None:
            try:
                return handler(request.override(messages=clipped))
            except Exception as e:  # noqa: BLE001
                if not self._is_sensitive_error(e):
                    raise
        logger.warning("Content filter persisted; returning degraded response to keep the run alive.")
        return AIMessage(content=self._DEGRADED)

    async def awrap_model_call(self, request, handler):
        """Async counterpart of :meth:`wrap_model_call`."""
        try:
            return await handler(request)
        except Exception as e:  # noqa: BLE001
            if not self._is_sensitive_error(e):
                raise
            logger.warning("Model call hit content filter: %s", e)
        time.sleep(self.backoff_seconds)
        try:
            return await handler(request)
        except Exception as e:  # noqa: BLE001
            if not self._is_sensitive_error(e):
                raise
        clipped = self._clip_largest_tool_message(request.messages)
        if clipped is not None:
            try:
                return await handler(request.override(messages=clipped))
            except Exception as e:  # noqa: BLE001
                if not self._is_sensitive_error(e):
                    raise
        logger.warning("Content filter persisted; returning degraded response to keep the run alive.")
        return AIMessage(content=self._DEGRADED)


# Phrases that signal the model is offering to continue or asking permission
# instead of delivering the report.
_OFFER_PATTERN = re.compile(
    r"我也可以|需要我|要不要我|是否(要我|需要|继续)|要我继续|可以继续|继续深挖|继续(为你|帮你)|"
    r"如果你(愿意|需要|想|后续希望|接下来希望)|可以指定维度|可直接进\s*ppt|帮你补全|"
    r"我可以(为你|帮你|给出|提供|继续|在下一步|再)|可粘到|"
    r"请确认|请告诉我|如需.*可|would you like me|should i (continue|proceed)|let me know if|shall i"
)


class ReportValidationMiddleware(AgentMiddleware):
    """Prevents incomplete terminal text during Reporter handoff.

    Fires only on terminal responses (no tool calls). If the response offers to
    continue / asks permission while reporting, it nudges the model to finish
    the Reporter handoff instead of writing or extending report prose itself.
    After ``max_retries`` it gives up and returns the latest response.
    """

    _NUDGE = (
        "你正处于无人值守流程，不得以提议继续、反问或请求确认结束。"
        "最终报告正文必须来自 reporter 的 submit_final_report；"
        "如果 reporter 已提交，只需简短确认，不要输出或改写报告正文。"
    )

    def __init__(self, max_retries: int = 2):
        """Initialize the middleware.

        Args:
            max_retries: Maximum nudge retries.
        """
        self.max_retries = max_retries

    def _is_incomplete(self, response) -> bool:
        from tools import research_state

        if research_state.get_status().get("research_state") != research_state.REPORTING:
            return False
        last = _last_ai_message(response)
        if last is None or last.tool_calls:
            return False  # not a terminal text response
        text = _message_text(last).strip()
        if not text:
            return False  # empty handled by EmptyResponseRetryMiddleware
        if _OFFER_PATTERN.search(text):
            return True
        return False

    def wrap_model_call(self, request, handler):
        """Retry incomplete/offer-to-continue terminal responses with a nudge."""
        response = handler(request)
        for _ in range(self.max_retries):
            if not self._is_incomplete(response):
                break
            nudge = HumanMessage(content=self._NUDGE)
            response = handler(request.override(messages=[*request.messages, nudge]))
        return response

    async def awrap_model_call(self, request, handler):
        """Async counterpart of :meth:`wrap_model_call`."""
        response = await handler(request)
        for _ in range(self.max_retries):
            if not self._is_incomplete(response):
                break
            nudge = HumanMessage(content=self._NUDGE)
            response = await handler(request.override(messages=[*request.messages, nudge]))
        return response


class ReporterRevisionMiddleware(AgentMiddleware):
    """Force the Reporter subagent to repair and resubmit failed report attempts."""

    def __init__(self, max_retries: int = 2):
        self.max_retries = max_retries
        self._retries_used = 0

    @staticmethod
    def _latest_attempt() -> dict:
        from tools import graph_manager_tools

        return graph_manager_tools.get_last_report_attempt()

    @staticmethod
    def _needs_revision(response) -> bool:
        last = _last_ai_message(response)
        if last is None or last.tool_calls:
            return False
        attempt = ReporterRevisionMiddleware._latest_attempt()
        if not attempt:
            return True
        return (not bool(attempt.get("accepted"))) or bool(attempt.get("revision_requested"))

    @staticmethod
    def _build_prompt(attempt: dict) -> str:
        if not attempt:
            return (
                "你尚未成功调用 submit_final_report。请立即读取已收集的证据并提交结构化报告；"
                "不要直接结束，也不要输出报告正文。"
            )

        submitted_sections = int(attempt.get("submitted_sections") or 0)
        dropped_sections = int(attempt.get("dropped_sections") or 0)
        allow_rewrite = (
            not str(attempt.get("salvaged_report") or "").strip()
            or attempt.get("severity") == "hard"
            or (submitted_sections > 0 and dropped_sections * 2 > submitted_sections)
        )
        action = (
            "仅在没有可保留的 prose 报告、受影响 section 超过一半、或错误属于全局硬错误时，才允许较大范围重写。"
            if allow_rewrite else
            "默认保留已通过的 section 与 block，只修复被点名的问题，不要从头重写整篇。"
        )
        lines = [
            "submit_final_report 尚未达到可结束状态，请继续修订并重新提交。",
            f"- accepted={bool(attempt.get('accepted'))}",
            f"- revision_requested={bool(attempt.get('revision_requested'))}",
            f"- severity={attempt.get('severity') or 'unknown'}",
            f"- retention_ratio={attempt.get('retention_ratio')}",
            f"- kept_blocks={attempt.get('kept_blocks')} / submitted_blocks={attempt.get('submitted_blocks')}",
            action,
            "- blocks[].source_ids 只能填写 URL-backed Source ID：优先直接复用 get_report_evidence 返回的 items[].source_ids，或 get_reference_registry()[].source_id；不要填 items[].id / claim id / evidence id / conflict id。",
            "- 如果首段是 lead，仍然给该 section 一个正常标题；不要提交空 title。",
            "按以下问题定点修复：",
        ]
        for issue in attempt.get("issues", [])[:8]:
            if not isinstance(issue, dict):
                lines.append(f"- {issue}")
                continue
            location = []
            if issue.get("section_title"):
                location.append(f"section={issue['section_title']}")
            if issue.get("block_index"):
                location.append(f"block={issue['block_index']}")
            location_text = f" ({', '.join(location)})" if location else ""
            lines.append(
                f"- [{issue.get('severity', 'soft')}] {issue.get('code', 'issue')}{location_text}: "
                f"{issue.get('message')} 修复建议：{issue.get('repair_hint')}"
            )
        lines.append("修复后再次调用 submit_final_report；如果仍需修订，继续迭代，不要直接结束。")
        return "\n".join(lines)

    def wrap_model_call(self, request, handler):
        """Retry terminal Reporter responses until the structured submit passes or retries are exhausted."""
        response = handler(request)
        while self._retries_used < self.max_retries and self._needs_revision(response):
            prompt = HumanMessage(content=self._build_prompt(self._latest_attempt()))
            self._retries_used += 1
            response = handler(request.override(messages=[*request.messages, prompt]))
        return response

    async def awrap_model_call(self, request, handler):
        """Async counterpart of :meth:`wrap_model_call`."""
        response = await handler(request)
        while self._retries_used < self.max_retries and self._needs_revision(response):
            prompt = HumanMessage(content=self._build_prompt(self._latest_attempt()))
            self._retries_used += 1
            response = await handler(request.override(messages=[*request.messages, prompt]))
        return response
