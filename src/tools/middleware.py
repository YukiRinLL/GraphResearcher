# 参考 /mnt/h/DeepResearch/aiq/src/aiq_agent/agents/deep_researcher/custom_middleware.py 关于中间件的设计和实现
"""System guardrail middleware for GraphResearcher.

Holds agent-level middleware (deepagents / LangChain `AgentMiddleware`). Today
it caps how many times the Orchestrator may dispatch the Searcher in a single
run via `SearchRoundLimitMiddleware`.
"""

import json
import logging
import re
import time

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

logger = logging.getLogger(__name__)

# Maximum number of Searcher dispatches per run; 0 (or less) means no limit.
_MAX_SEARCH_ROUNDS = 0
_search_dispatch_count = 0


def configure(max_search_rounds: int) -> None:
    """Set the search-round budget for the current run.

    Args:
        max_search_rounds: Maximum number of Searcher dispatches; 0 means no
            limit. Resets the dispatch counter so the same process can run
            multiple times.
    """
    global _MAX_SEARCH_ROUNDS, _search_dispatch_count
    _MAX_SEARCH_ROUNDS = max_search_rounds
    _search_dispatch_count = 0


class SearchRoundLimitMiddleware(AgentMiddleware):
    """Caps the number of Searcher dispatches the Orchestrator may make.

    A "search round" is one `task(subagent_type="searcher")` call. Once the
    configured budget is reached, further dispatches are blocked and the
    Orchestrator is told to write the report from the evidence already
    collected. The budget is read from the module-level configuration so the
    Orchestrator graph can be built at import time and the limit injected per
    run via `configure`.
    """

    def __init__(self, subagent_name: str = "searcher"):
        """Initialize the middleware.

        Args:
            subagent_name: The subagent whose dispatches count as search rounds.
        """
        self.subagent_name = subagent_name

    def _intercept(self, tool_call: dict):
        """Return a blocking ToolMessage if the search budget is exhausted, else None.

        Args:
            tool_call: The tool call dict (``name``/``args``/``id``).

        Returns:
            A ``ToolMessage`` to short-circuit the dispatch, or ``None`` to
            allow it.
        """
        global _search_dispatch_count
        if _MAX_SEARCH_ROUNDS <= 0:
            return None
        if tool_call.get("name") != "task" or tool_call.get("args", {}).get("subagent_type") != self.subagent_name:
            return None
        if _search_dispatch_count >= _MAX_SEARCH_ROUNDS:
            logger.info("Search budget exhausted (%d rounds); blocking searcher dispatch.", _MAX_SEARCH_ROUNDS)
            return ToolMessage(
                content=(
                    f"搜索预算已用尽（已达最大搜索轮次 {_MAX_SEARCH_ROUNDS}）。"
                    "请停止派发 searcher，立即基于已收集的证据调用 reporter 生成最终报告。"
                ),
                tool_call_id=tool_call["id"],
                name="task",
                status="error",
            )
        _search_dispatch_count += 1
        return None

    def wrap_tool_call(self, request, handler):
        """Enforce the search-round budget before dispatching the Searcher."""
        blocked = self._intercept(request.tool_call)
        return blocked if blocked is not None else handler(request)

    async def awrap_tool_call(self, request, handler):
        """Async counterpart of :meth:`wrap_tool_call`."""
        blocked = self._intercept(request.tool_call)
        return blocked if blocked is not None else await handler(request)


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
    r"如果你(愿意|需要|想)|我可以(为你|帮你|给出|提供|继续|在下一步|再)|可粘到|"
    r"请确认|请告诉我|如需.*可|would you like me|should i (continue|proceed)|let me know if|shall i"
)


class ReportValidationMiddleware(AgentMiddleware):
    """Forces the Orchestrator's terminal response to be a real report.

    Fires only on terminal responses (no tool calls). If the response offers to
    continue / asks permission, or is very short with no ``##`` sections, it
    nudges the model to deliver the complete report immediately. After
    ``max_retries`` it gives up and returns the latest response.
    """

    _NUDGE = (
        "你正处于无人值守流程，必须立即交付完整最终报告，不得以提议继续、反问或请求确认结束。"
        "请基于已收集的证据直接输出含 `##` 章节标题与编号引用 `[1]` 的完整报告；"
        "证据不足时也要给出带已披露局限的完整报告，而不是停下来询问。"
    )

    def __init__(self, min_length: int = 600, min_sections: int = 1, max_retries: int = 2):
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
        if _OFFER_PATTERN.search(text):
            return True
        if len(text) < self.min_length and text.count("## ") < self.min_sections:
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
