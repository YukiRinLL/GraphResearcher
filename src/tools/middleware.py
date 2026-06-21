# 参考 /mnt/h/DeepResearch/aiq/src/aiq_agent/agents/deep_researcher/custom_middleware.py 关于中间件的设计和实现
"""System guardrail middleware for GraphResearcher.

Holds agent-level middleware (deepagents / LangChain `AgentMiddleware`). Today
it caps how many times the Orchestrator may dispatch the Searcher in a single
run via `SearchRoundLimitMiddleware`. It also checks for graph-based convergence.
"""

import json
import logging
import re
import time

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from tools import workflow_state

logger = logging.getLogger(__name__)


def configure(max_search_rounds: int) -> None:
    """Set the search-round budget for the current run.

    Args:
        max_search_rounds: Maximum number of Searcher dispatches; 0 means no
            limit. Resets the dispatch counter so the same process can run
            multiple times.
    """
    workflow_state.reset(max_search_rounds=max_search_rounds)


def _observe_convergence() -> dict:
    """Advance per-round novelty and return the deterministic convergence signals.

    Called once per Searcher dispatch (the round boundary). Failures degrade to
    an empty dict so the caller falls back to the budget gate alone.

    Returns:
        The convergence metrics dict from ``convergence.observe_round``, or an
        empty dict if the graph is unavailable.
    """
    try:
        from tools import convergence

        return convergence.observe_round()
    except Exception as e:
        logger.warning(f"Error computing convergence signals: {e}")
        return {}


def _tool_key(tool_call: dict) -> str:
    """Return a normalized tool key, including subagent type for ``task``."""
    name = tool_call.get("name") or ""
    if name != "task":
        return name
    subagent = tool_call.get("args", {}).get("subagent_type")
    return f"task:{subagent}" if subagent else name


def _search_query_id(tool_call: dict, subagent_name: str = "searcher") -> str:
    """Return the query_id of a Searcher dispatch, if recoverable."""
    if tool_call.get("name") == "dispatch_searcher":
        return (tool_call.get("args", {}).get("query_id") or "").strip()
    if tool_call.get("name") == "task" and tool_call.get("args", {}).get("subagent_type") == subagent_name:
        description = tool_call.get("args", {}).get("description") or ""
        match = _QID_RE.search(description)
        return (match.group(1) if match else "").strip()
    return ""


def _is_search_dispatch(tool_call: dict, subagent_name: str = "searcher") -> bool:
    """Return whether the tool call dispatches the Searcher."""
    return tool_call.get("name") == "dispatch_searcher" or (
        tool_call.get("name") == "task" and tool_call.get("args", {}).get("subagent_type") == subagent_name
    )


def _make_block(tool_call: dict, content: str) -> ToolMessage:
    """Create a blocking tool error message."""
    return ToolMessage(
        content=content,
        tool_call_id=tool_call["id"],
        name=tool_call.get("name"),
        status="error",
    )


class WorkflowPhaseMiddleware(AgentMiddleware):
    """Restrict tool usage to the current workflow phase."""

    _BUDGET_DRAIN_ALLOWED = {
        "analyze_subgraph",
        "mark_query",
        "assess_convergence",
        "get_subgraph",
        "get_node",
        "write_todos",
    }
    _ALLOWED = {
        "init": {"init_research", "write_todos"},
        "research": {
            "get_next_queries",
            "dispatch_searcher",
            "analyze_subgraph",
            "mark_query",
            "analyze_coverage",
            "expand_query",
            "create_analysis",
            "assess_convergence",
            "get_subgraph",
            "get_node",
            "task:reporter",
            "write_todos",
        },
        "report": {
            "export_report_context",
            "get_subgraph",
            "get_node",
            "assess_convergence",
            "task:reporter",
            "write_todos",
        },
        "done": set(),
    }

    def _intercept(self, tool_call: dict):
        workflow_state.advance_report_phase_if_ready()
        phase = workflow_state.get("phase", "init")
        key = _tool_key(tool_call)
        if (
            phase == "research"
            and workflow_state.get("budget_exhausted")
            and key not in self._BUDGET_DRAIN_ALLOWED
        ):
            return _make_block(
                tool_call,
                "搜索预算已用尽，不能再发起新的检索、扩展或新一轮选题。"
                "请只完成已入图 query 的 analyze_subgraph + mark_query 收尾；"
                "待所有待评审项清空后进入报告阶段。",
            )
        if key in self._ALLOWED.get(phase, set()):
            return None
        if phase == "done":
            return _make_block(tool_call, "最终报告已通过校验，本轮流程已结束，不应再调用工具。")
        return _make_block(
            tool_call,
            f"当前处于 {phase} 阶段，不允许调用 `{key}`。请按 workflow 推进到正确阶段后再调用该工具。",
        )

    def wrap_tool_call(self, request, handler):
        blocked = self._intercept(request.tool_call)
        return blocked if blocked is not None else handler(request)

    async def awrap_tool_call(self, request, handler):
        blocked = self._intercept(request.tool_call)
        return blocked if blocked is not None else await handler(request)


class SearchRoundLimitMiddleware(AgentMiddleware):
    """Caps the number of Searcher dispatches the Orchestrator may make.

    A "search round" is one `task(subagent_type="searcher")` call. Once the
    configured budget is reached OR the graph has converged, further dispatches 
    are blocked and the Orchestrator is told to write the report from the 
    evidence already collected. The budget is read from the module-level 
    configuration so the Orchestrator graph can be built at import time and 
    the limit injected per run via `configure`.
    """

    def __init__(self, subagent_name: str = "searcher"):
        """Initialize the middleware.

        Args:
            subagent_name: The subagent whose dispatches count as search rounds.
        """
        self.subagent_name = subagent_name

    def _intercept(self, tool_call: dict):
        """Return a blocking ToolMessage if the search should be blocked, else None.

        Search is blocked when:
        1. The graph shows a convergence signal — every high-priority query is
           answered at threshold, OR new evidence has stopped arriving — in
           which case the dispatch is routed through ``assess_convergence``; OR
        2. The search budget is exhausted.

        Args:
            tool_call: The tool call dict (``name``/``args``/``id``).

        Returns:
            A ``ToolMessage`` to short-circuit the dispatch, or ``None`` to
            allow it.
        """
        if not _is_search_dispatch(tool_call, self.subagent_name):
            return None

        state = workflow_state.snapshot()
        max_rounds = state.get("max_search_rounds", 0)
        search_rounds = state.get("search_rounds", 0)

        # One round boundary: advance novelty and read the deterministic signals.
        metrics = _observe_convergence()
        priority = metrics.get("priority", {})
        structurally = bool(priority.get("structurally_converged"))
        # Diminishing returns only stop the loop once no high-priority query is
        # still pending (unsearched) — otherwise there is obvious work left, and
        # blocking here would deadlock against assess_convergence's "continue".
        diminishing = bool(metrics.get("novelty", {}).get("diminishing")) and not bool(
            priority.get("pending_high_priority")
        )

        if structurally or diminishing:
            reason = "高优先级查询均已达标" if structurally else "新一轮检索新颖度持续走低"
            logger.info("Graph convergence signal (%s); routing to assess_convergence.", reason)
            return _make_block(
                tool_call,
                (
                    f"图谱已出现收敛信号（{reason}）。请停止派发 searcher，调用 assess_convergence 取裁决："
                    "recommendation=stop 则基于已收集的证据调用 reporter 生成最终报告；"
                    "recommendation=continue 且预算允许时，对其点名的冲突/缺口调用 expand_query 纵向补齐后再行裁决。"
                ),
            )

        # Check search round limit
        if max_rounds > 0 and search_rounds >= max_rounds:
            logger.info("Search budget exhausted (%d rounds); blocking searcher dispatch.", max_rounds)
            workflow_state.mark_budget_exhausted()
            if workflow_state.has_pending_review_work():
                instruction = (
                    "请停止派发 searcher，也不要 expand_query；先对已经完成搜索的 query "
                    "逐个调用 analyze_subgraph + mark_query 完成收尾。收尾完成后会进入报告阶段。"
                )
            else:
                instruction = "请停止派发 searcher，进入报告阶段并基于已收集证据生成最终报告。"
            return _make_block(
                tool_call,
                (
                    f"搜索预算已用尽（已达最大搜索轮次 {max_rounds}）。"
                    f"{instruction}"
                ),
            )

        # The primary path increments the round counter inside dispatch_searcher.
        # Keep the legacy task(searcher) fallback budget-aware too.
        if tool_call.get("name") == "task":
            query_id = _search_query_id(tool_call, self.subagent_name)
            if query_id:
                workflow_state.record_search_dispatch(query_id)
        return None

    def wrap_tool_call(self, request, handler):
        """Enforce the search-round budget and graph convergence before dispatching the Searcher."""
        blocked = self._intercept(request.tool_call)
        return blocked if blocked is not None else handler(request)

    async def awrap_tool_call(self, request, handler):
        """Async counterpart of :meth:`wrap_tool_call`."""
        blocked = self._intercept(request.tool_call)
        return blocked if blocked is not None else await handler(request)


class PendingReviewGateMiddleware(AgentMiddleware):
    """Enforce dispatch/review sequencing for Stage 2."""

    def __init__(self, subagent_name: str = "searcher"):
        self.subagent_name = subagent_name

    def _intercept(self, tool_call: dict):
        state = workflow_state.snapshot()
        pending = state.get("pending_review_query_ids", [])
        last_results = state.get("last_search_results", {})
        analysis_ready = state.get("analysis_ready_query_ids", [])
        key = _tool_key(tool_call)

        if _is_search_dispatch(tool_call, self.subagent_name):
            query_id = _search_query_id(tool_call, self.subagent_name)
            if not pending:
                return None
            if state.get("round_open"):
                return None
            retry_same_query = (
                query_id
                and query_id in pending
                and not bool((last_results.get(query_id) or {}).get("ok"))
            )
            if retry_same_query:
                return None
            return _make_block(
                tool_call,
                "上一轮已派发的 query 尚未全部完成 analyze_subgraph + mark_query。"
                "请先完成当前 pending query 的评分与标记；只有同一 query 上一跳未真正入图时，才允许立即重派该 query。",
            )

        if key == "mark_query":
            query_id = (tool_call.get("args", {}).get("query_id") or "").strip()
            if query_id not in analysis_ready:
                return _make_block(
                    tool_call,
                    "mark_query 之前必须先对同一 query 调用 analyze_subgraph，且只能消费最新一次尚未写回的分析结果。",
                )
        if key == "get_next_queries" and pending:
            return _make_block(
                tool_call,
                "仍有上一轮 query 未完成 analyze_subgraph + mark_query，不能开始新的 get_next_queries 轮次。"
                "请先完成当前 pending query 的评分与标记。",
            )
        return None

    def wrap_tool_call(self, request, handler):
        blocked = self._intercept(request.tool_call)
        return blocked if blocked is not None else handler(request)

    async def awrap_tool_call(self, request, handler):
        blocked = self._intercept(request.tool_call)
        return blocked if blocked is not None else await handler(request)


class ConvergenceGateMiddleware(AgentMiddleware):
    """Block report writing until convergence or budget exhaustion allows it."""

    def _intercept(self, tool_call: dict):
        if _tool_key(tool_call) != "task:reporter":
            return None
        state = workflow_state.snapshot()
        if state.get("pending_review_query_ids") or state.get("analysis_ready_query_ids"):
            return _make_block(
                tool_call,
                "仍有已派发 query 未完成 analyze_subgraph + mark_query，不能进入 reporter。请先完成当前轮次的评分与标记。",
            )
        if not workflow_state.can_enter_report():
            return _make_block(
                tool_call,
                "进入 reporter 之前必须先满足停止条件：要么 assess_convergence 给出 recommendation=stop，"
                "要么搜索预算已耗尽且所有已搜索 query 均已完成评分标记。当前请先调用 assess_convergence 或继续研究。",
            )
        workflow_state.advance_report_phase_if_ready()
        return None

    def wrap_tool_call(self, request, handler):
        blocked = self._intercept(request.tool_call)
        if blocked is not None:
            return blocked
        result = handler(request)
        if _tool_key(request.tool_call) == "task:reporter" and getattr(result, "status", None) != "error":
            workflow_state.mark_reporter_called()
        return result

    async def awrap_tool_call(self, request, handler):
        blocked = self._intercept(request.tool_call)
        if blocked is not None:
            return blocked
        result = await handler(request)
        if _tool_key(request.tool_call) == "task:reporter" and getattr(result, "status", None) != "error":
            workflow_state.mark_reporter_called()
        return result


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


# Regex that extracts a query node ID from a task description — same pattern
# the Searcher's init_node uses for fallback parsing.
_QID_RE = re.compile(r"(?:query_id|Query ID|queryId|qid)[=:]\s*([a-f0-9_]+)", re.IGNORECASE)


class QueryIdValidationMiddleware(AgentMiddleware):
    """Guardrail: blocks ``task(subagent_type="searcher")`` calls that lack a
    valid ``query_id``, and points the Orchestrator to ``dispatch_searcher``.

    The primary dispatch path is ``dispatch_searcher(query_id, description)``
    where ``query_id`` is a required, typed parameter. This middleware is a
    safety net for any remaining raw ``task(searcher)`` calls — it prevents
    the old fragile text-parsing path from creating orphan evidence.
    """

    _BLOCKED = (
        "task(subagent_type=\"searcher\") 已被 dispatch_searcher 替代。"
        "请改用 dispatch_searcher(query_id=<精确query节点ID>, description=...)。"
        "query_id 必须来自 init_research / expand_query 的返回值。"
    )

    def __init__(self, subagent_name: str = "searcher"):
        self.subagent_name = subagent_name

    def _intercept(self, tool_call: dict):
        if tool_call.get("name") != "task":
            return None
        if tool_call.get("args", {}).get("subagent_type") != self.subagent_name:
            return None

        description = tool_call.get("args", {}).get("description") or ""
        if _QID_RE.search(description):
            # Has a query_id pattern — could work via the fallback path.
            # Still warn, but allow it through.
            logger.warning(
                "task(searcher) called with query_id in description; "
                "allowed through fallback path but dispatch_searcher is preferred."
            )
            return None

        logger.warning("task(searcher) blocked: no query_id in description.")
        return ToolMessage(
            content=self._BLOCKED,
            tool_call_id=tool_call["id"],
            name="task",
            status="error",
        )

    def wrap_tool_call(self, request, handler):
        blocked = self._intercept(request.tool_call)
        return blocked if blocked is not None else handler(request)

    async def awrap_tool_call(self, request, handler):
        blocked = self._intercept(request.tool_call)
        return blocked if blocked is not None else await handler(request)


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
    r"如果你(愿意|需要|想)|我可以(为你|帮你|给出|提供|继续|在下一步|再)|可粘到|"
    r"请确认|请告诉我|如需.*可|would you like me|should i (continue|proceed)|let me know if|shall i"
)

_INTERNAL_REPORT_PATTERN = re.compile(
    r"needs_vertical|needs_horizontal|sufficiency_score|graph state|Research Graph|"
    r"\bblocked\b|\bpending\b|\bquery\b|本轮搜索|预算耗尽",
    re.IGNORECASE,
)
_LIMITATION_PATTERN = re.compile(
    r"局限|不足|有限|未能|尚不|不完整|证据.*薄弱|结论边界|阶段性结论|公开信息有限|"
    r"limitation|limited|insufficient|incomplete|uncertain",
    re.IGNORECASE,
)


class ReportValidationMiddleware(AgentMiddleware):
    """Forces the Orchestrator's terminal response to be a real report.

    Fires only on terminal responses (no tool calls). It also checks workflow
    state: the Reporter must have been called and at least one report section
    must have been bound before the Orchestrator is allowed to finish. If the
    response offers to continue / asks permission, or is very short with no
    ``##`` sections, it nudges the model to deliver the complete report
    immediately. After ``max_retries`` it gives up and returns the latest
    response.
    """

    _NUDGE = (
        "你正处于无人值守流程，必须立即交付完整最终报告，不得以提议继续、反问或请求确认结束。"
        "请基于已收集的证据直接输出含 `##` 章节标题与编号引用 `[1]` 的完整报告；"
        "证据不足时也要给出带已披露局限的完整报告，而不是停下来询问。"
        "在结束前，必须确保已经调用 reporter 且至少成功绑定了一个 report_section。"
        "如果证据仍有限，请用面向读者的自然语言说明结论边界，不要暴露内部状态、query、预算或图谱术语。"
    )

    def __init__(self, min_length: int = 600, min_sections: int = 1, max_retries: int = 6):
        """Initialize the middleware.

        Args:
            min_length: Below this length (and lacking sections) counts as incomplete.
            min_sections: Minimum number of ``##`` headings expected.
            max_retries: Maximum nudge retries.
        """
        self.min_length = min_length
        self.min_sections = min_sections
        self.max_retries = max_retries

    def _is_incomplete(self, response) -> bool:
        last = _last_ai_message(response)
        if last is None or last.tool_calls:
            return False  # not a terminal text response
        text = _message_text(last).strip()
        if not text:
            return False  # empty handled by EmptyResponseRetryMiddleware
        state = workflow_state.snapshot()
        if state.get("phase") not in ("report", "done"):
            return True
        if _OFFER_PATTERN.search(text):
            return True
        if _INTERNAL_REPORT_PATTERN.search(text):
            return True
        convergence = state.get("last_convergence") or {}
        if state.get("budget_exhausted") and convergence.get("recommendation") != "stop":
            if not _LIMITATION_PATTERN.search(text):
                return True
        if len(text) < self.min_length and text.count("## ") < self.min_sections:
            return True
        if not state.get("reporter_called"):
            return True
        if state.get("bound_section_count", 0) <= 0:
            return True
        return False

    @staticmethod
    def _is_terminal_text_response(response) -> bool:
        """Return whether ``response`` ends with plain AI text and no tool calls."""
        last = _last_ai_message(response)
        return last is not None and not last.tool_calls

    def wrap_model_call(self, request, handler):
        """Retry incomplete/offer-to-continue terminal responses with a nudge."""
        response = handler(request)
        for _ in range(self.max_retries):
            if not self._is_terminal_text_response(response):
                break
            if not self._is_incomplete(response):
                workflow_state.mark_report_validated(True)
                break
            nudge = HumanMessage(content=self._NUDGE)
            workflow_state.mark_report_validated(False)
            response = handler(request.override(messages=[*request.messages, nudge]))
        if self._is_terminal_text_response(response) and self._is_incomplete(response):
            workflow_state.mark_report_validated(False)
        return response

    async def awrap_model_call(self, request, handler):
        """Async counterpart of :meth:`wrap_model_call`."""
        response = await handler(request)
        for _ in range(self.max_retries):
            if not self._is_terminal_text_response(response):
                break
            if not self._is_incomplete(response):
                workflow_state.mark_report_validated(True)
                break
            nudge = HumanMessage(content=self._NUDGE)
            workflow_state.mark_report_validated(False)
            response = await handler(request.override(messages=[*request.messages, nudge]))
        if self._is_terminal_text_response(response) and self._is_incomplete(response):
            workflow_state.mark_report_validated(False)
        return response
