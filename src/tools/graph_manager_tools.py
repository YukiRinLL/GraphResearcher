"""State-machine Graph Manager tools exposed to GraphResearcher agents."""

import uuid
from typing import Any, Optional

from langchain_core.tools import tool

from agents.memory_manager import MemoryManager

_manager: Optional[MemoryManager] = None
_cache_dir: Optional[str] = None


def configure(output_dir: Optional[str] = None) -> None:
    """Scope graph storage and rebuild the shared MemoryManager for a run."""
    global _cache_dir, _manager
    _cache_dir = output_dir
    _manager = None
    from tools import convergence, graph_tools

    run_context = f"{output_dir or 'default'}::{uuid.uuid4().hex}"
    graph_tools.set_context(run_context)
    convergence.reset()


def _mm() -> MemoryManager:
    global _manager
    if _manager is None:
        _manager = MemoryManager(cache_dir=_cache_dir)
    return _manager


def prepare_search(query_id: str, source_preferences: Optional[list[str]] = None) -> dict:
    """Prepare an internal structured Searcher dispatch."""
    return _mm().prepare_search(query_id, source_preferences)


def fail_search(search_run_id: str, query_id: str, error: str) -> dict:
    """Record an internal Searcher dispatch failure."""
    return _mm().fail_search(search_run_id, query_id, error)


def set_research_state(state: str, **attributes: Any) -> dict:
    """Update root state for middleware and CLI lifecycle handling."""
    from tools import research_state

    return research_state.update_goal({"research_state": state, **attributes})


@tool
def init_research(user_request: str) -> dict:
    """Initialize a strict Query tree and persistent research state."""
    return _mm().init_research(user_request)


@tool
def get_research_status(goal_id: Optional[str] = None) -> dict:
    """Return persistent system state, budget and unfinished required branches."""
    from tools import research_state

    next_actions = _mm().get_next_actions()
    status = research_state.get_status(goal_id)
    status["tree_validation"] = _mm_validate_tree()
    status["next_actions"] = next_actions
    return status


def _mm_validate_tree() -> dict:
    from tools import graph_tools

    return graph_tools.validate_query_tree()


@tool
def validate_query_tree() -> dict:
    """Validate orphan, multi-parent, cycle and handle invariants."""
    return _mm_validate_tree()


@tool
def get_next_actions(limit: int = 4) -> list:
    """Return ordered assess, expand or search actions from the state machine."""
    return _mm().get_next_actions(limit)


@tool
def assess_query(query_id: str) -> dict:
    """Assess one Query's owned subgraph and automatically advance its state."""
    return _mm().assess_query(query_id)


@tool
def expand_gaps(parent_id: str, gap_ids: Optional[list[str]] = None) -> dict:
    """Create one self-contained child Query for each selected atomic gap."""
    return _mm().expand_gaps(parent_id, gap_ids)


@tool
def assess_convergence(goal_id: Optional[str] = None) -> dict:
    """Authorize reporting only after required tree branches converge or budget expires."""
    return _mm().assess_convergence(goal_id)


@tool
def create_analysis(text: str, query_id: Optional[str] = None) -> dict:
    """Record a typed insight, resolving an optional Query handle safely."""
    return _mm().create_insight(text, query_id)


@tool
def get_query_evaluation_subgraph(query_id: str) -> dict:
    """Read the evidence owned by one Query, excluding parent and sibling evidence."""
    resolved = _mm()._resolve_query_id(query_id)  # central resolver; read-only tool
    if resolved is None:
        return {"error": f"Unknown query reference: {query_id!r}"}
    from tools import graph_tools

    return graph_tools.get_query_evaluation_subgraph(resolved)


@tool
def get_subgraph(node_id: str, depth: int = 2) -> dict:
    """Read a general graph neighborhood for inspection."""
    from tools import graph_tools

    return graph_tools.get_subgraph(node_id, depth)


@tool
def get_node(node_id: str) -> dict:
    """Read one graph node by exact ID."""
    from tools import graph_tools

    return graph_tools.get_node(node_id)


@tool
def submit_search_result(search_run_id: str, query_id: str, evidence_package: dict) -> dict:
    """Write evidence into an existing SearchRun and advance Query state."""
    return _mm().submit_search_result(search_run_id, query_id, evidence_package)


@tool
def export_report_context(goal_id: Optional[str] = None) -> dict:
    """Export report context after the reporter gate has authorized writing."""
    return _mm().export_report_context(goal_id)


@tool
def bind_report_section(
    title: str,
    content: str,
    evidence_ids: Optional[list] = None,
    claim_ids: Optional[list] = None,
    section_type: Optional[str] = None,
) -> str:
    """Create a report section and type-safe evidence/claim bindings."""
    section = {"title": title, "content": content, "section_type": section_type}
    return _mm().bind_report_section(section, claim_ids=claim_ids, evidence_ids=evidence_ids)


ORCHESTRATOR_TOOLS: list[Any] = [
    init_research,
    get_research_status,
    validate_query_tree,
    get_next_actions,
    assess_query,
    expand_gaps,
    assess_convergence,
    create_analysis,
    get_query_evaluation_subgraph,
    get_subgraph,
    get_node,
]

SEARCHER_TOOLS: list[Any] = [submit_search_result]

REPORTER_TOOLS: list[Any] = [
    export_report_context,
    get_subgraph,
    get_node,
    bind_report_section,
]
