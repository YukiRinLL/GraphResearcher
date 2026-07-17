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
from tools.graph_manager_tools import ORCHESTRATOR_TOOLS, fail_search, prepare_search
from tools.middleware import (
    EmptyResponseRetryMiddleware,
    ReportValidationMiddleware,
    ResearchStateMiddleware,
    SensitiveWordsRetryMiddleware,
)


@tool
def dispatch_searcher(query_id: str, source_preferences: list[str] | None = None) -> dict:
    """Dispatch the Searcher to collect evidence for one query into the graph.

    ``query_id`` is injected into the Searcher's state directly (not parsed from
    free text), so the reference can never be lost in transit.

    Args:
        query_id: The exact Query node ID returned by ``get_next_actions`` or
            ``expand_gaps``. Pass it through unchanged.
        source_preferences: Optional preferred source categories or domains.

    Returns:
        The Searcher's final report text, including the ``submit_search_result``
        write counts (sources/documents/evidence) and ``search_run_id`` so the
        Orchestrator can verify the evidence actually landed in the graph.
    """
    prepared = prepare_search(query_id, source_preferences)
    if prepared.get("error"):
        return prepared
    try:
        result = searcher.invoke({
            "search_run_id": prepared["search_run_id"],
            "query_id": prepared["query_id"],
            "query_text": prepared["query_text"],
            "source_preferences": prepared.get("source_preferences", []),
            "excluded_domains": prepared.get("excluded_domains", []),
            "excluded_urls": prepared.get("excluded_urls", []),
            "messages": [HumanMessage(content=prepared["query_text"])],
        })
    except Exception as exc:
        return fail_search(prepared["search_run_id"], prepared["query_id"], str(exc))
    submit_result = result.get("submit_result")
    if isinstance(submit_result, dict):
        return submit_result
    return fail_search(
        prepared["search_run_id"],
        prepared["query_id"],
        "Searcher returned no submit result",
    )


orchestrator = create_deep_agent(
    model=config.orchestrator_model,
    system_prompt=config.orchestrator_system_prompt,
    tools=[*ORCHESTRATOR_TOOLS, dispatch_searcher],
    subagents=[reporter],
    middleware=[
        ResearchStateMiddleware(),
        ReportValidationMiddleware(),
        EmptyResponseRetryMiddleware(),
        SensitiveWordsRetryMiddleware(),
        ModelRetryMiddleware(),
    ],
)
