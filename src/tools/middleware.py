# 参考 /mnt/h/DeepResearch/aiq/src/aiq_agent/agents/deep_researcher/custom_middleware.py 关于中间件的设计和实现
"""System guardrail middleware for GraphResearcher.

Holds agent-level middleware (deepagents / LangChain `AgentMiddleware`). Today
it caps how many times the Orchestrator may dispatch the Searcher in a single
run via `SearchRoundLimitMiddleware`.
"""

import logging

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage

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
