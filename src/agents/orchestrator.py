"""Orchestrator agent — the main deep agent driving the research loop.

Built with `create_deep_agent` and defined purely by `prompts/orchestrator.md`.
It owns the Orchestrator-facing Graph Manager tools, dispatches the Searcher
through the structured `dispatch_searcher` tool (query_id travels as a typed
argument, not free text), and delegates report writing to the `reporter`
`SubAgent` spec via the built-in `task` tool.
"""

from deepagents import create_deep_agent
from langchain.agents.middleware import ModelRetryMiddleware
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

import config
from agents.reporter import reporter
from agents.searcher import searcher
from tools.graph_manager_tools import ORCHESTRATOR_TOOLS
from tools.middleware import (
    EmptyResponseRetryMiddleware,
    ReportValidationMiddleware,
    SearchRoundLimitMiddleware,
    SensitiveWordsRetryMiddleware,
)


@tool
def dispatch_searcher(query_id: str, instructions: str) -> str:
    """Dispatch the Searcher to collect evidence for one query node into the graph.

    ``query_id`` is injected into the Searcher's state directly (not parsed from
    free text), so the query node ID can never be lost in transit.

    Args:
        query_id: The **exact** query node ID returned by ``init_research`` /
            ``get_next_queries`` / ``expand_query``; never truncate or rewrite it.
        instructions: The search task — key points, acceptance criteria, time
            window and source preferences.

    Returns:
        The Searcher's final report text, including the ``submit_search_result``
        write counts (sources/documents/evidence) and ``search_run_id`` so the
        Orchestrator can verify the evidence actually landed in the graph.
    """
    result = searcher.invoke({
        "query_id": query_id,
        "query_text": instructions,
        "messages": [HumanMessage(content=instructions)],
    })
    for message in reversed(result.get("messages", [])):
        content = getattr(message, "content", None)
        if content:
            return content if isinstance(content, str) else str(content)
    return ""


orchestrator = create_deep_agent(
    model=config.orchestrator_model,
    system_prompt=config.orchestrator_system_prompt,
    tools=[*ORCHESTRATOR_TOOLS, dispatch_searcher],
    subagents=[reporter],
    middleware=[
        SearchRoundLimitMiddleware(),
        ReportValidationMiddleware(),
        EmptyResponseRetryMiddleware(),
        SensitiveWordsRetryMiddleware(),
        ModelRetryMiddleware(),
    ],
)
