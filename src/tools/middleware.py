# 参考/Users/yindq/projects/DeepResearch/aiq/src/aiq_agent/agents/deep_researcher/custom_middleware.py 关于中间件的设计和实现
"""System guardrail middleware for GraphResearcher."""

import logging
import time

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

logger = logging.getLogger(__name__)

# Maximum number of Searcher dispatches per run; 0 (or less) means no limit.
_MAX_SEARCH_ROUNDS = 30


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
