"""State-machine Graph Manager tools exposed to GraphResearcher agents."""

from pathlib import Path
from threading import Lock
from typing import Any, Optional

from langchain_core.tools import tool

from agents.memory_manager import AmbiguousQueryReference, MemoryManager

_manager: Optional[MemoryManager] = None
_cache_dir: Optional[str] = None
_compiled_report: str = ""
_report_lock = Lock()


def configure(output_dir: Optional[str] = None) -> None:
    """Clear and scope graph storage, then rebuild the shared manager for a run."""
    global _cache_dir, _compiled_report, _manager
    _cache_dir = output_dir
    _manager = None
    with _report_lock:
        _compiled_report = ""
        path = _compiled_report_path()
        if path and path.exists():
            path.unlink()
    from tools import convergence, graph_tools

    run_context = output_dir or "default"
    graph_tools.set_context(run_context)
    graph_tools.clear_current_context()
    convergence.reset()


def _mm() -> MemoryManager:
    global _manager
    if _manager is None:
        _manager = MemoryManager(cache_dir=_cache_dir)
    return _manager


def _compiled_report_path() -> Optional[Path]:
    """Return the run-scoped canonical Reporter artifact path."""
    return Path(_cache_dir) / ".compiled_report.md" if _cache_dir else None


def get_compiled_report() -> str:
    """Return the canonical structured Reporter report for the current run."""
    with _report_lock:
        if _compiled_report:
            return _compiled_report
        path = _compiled_report_path()
        return path.read_text(encoding="utf-8") if path and path.exists() else ""


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
    """Return persistent state, Objective coverage, selected work and budget."""
    from tools import research_state

    next_actions = _mm().get_next_actions()
    status = research_state.get_status(goal_id)
    status["tree_validation"] = _mm_validate_tree()
    status["next_actions"] = next_actions
    return status


@tool
def get_research_objectives(goal_id: Optional[str] = None) -> list:
    """Return the report-level research objectives and their current coverage."""
    return _mm().get_research_objectives(goal_id)


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
def evaluate_research_portfolio(goal_id: Optional[str] = None) -> dict:
    """Select globally valuable candidate gaps and defer low-value work."""
    return _mm().evaluate_research_portfolio(goal_id)


@tool
def expand_gaps(parent_id: str, gap_ids: Optional[list[str]] = None) -> dict:
    """Group selected atomic gaps by search subject and create child Queries."""
    return _mm().expand_gaps(parent_id, gap_ids)


@tool
def assess_convergence(goal_id: Optional[str] = None) -> dict:
    """Authorize reporting after Objective convergence or budget exhaustion."""
    return _mm().assess_convergence(goal_id)


@tool
def create_analysis(text: str, query_id: Optional[str] = None) -> dict:
    """Record a typed insight, resolving an optional Query handle safely."""
    return _mm().create_insight(text, query_id)


@tool
def get_query_evaluation_subgraph(query_id: str) -> dict:
    """Read the evidence owned by one Query, excluding parent and sibling evidence."""
    try:
        resolved = _mm()._resolve_query_id(query_id)  # central resolver; read-only tool
    except AmbiguousQueryReference as exc:
        return {"error": str(exc)}
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
    """Export compact report metadata after the reporter gate authorizes writing."""
    return _mm().export_report_context(goal_id)


@tool
def get_report_evidence(query_id: str, offset: int = 0, limit: int = 20) -> dict:
    """Return one compact page of citation-ready Claim/Evidence items."""
    return _mm().get_report_evidence(query_id, offset=offset, limit=limit)


@tool
def get_reference_registry() -> list[dict]:
    """Return the complete stable Source ID, citation number and URL registry."""
    from tools import report_tools

    return report_tools.get_reference_registry()


@tool
def submit_final_report(title: str, sections: list[dict]) -> dict:
    """Validate and compile the canonical report from cited structured blocks.

    Every section requires ``blocks``. Each block requires ``text`` and one or
    more URL-backed ``source_ids``; set ``kind`` to ``list_item`` for bullets.
    """
    global _compiled_report
    from tools import report_tools

    result = report_tools.compile_structured_report(title, sections)
    report = result.pop("report", "") if isinstance(result, dict) else ""
    if not report:
        return result
    with _report_lock:
        _compiled_report = report
        path = _compiled_report_path()
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(report, encoding="utf-8")
    return {"accepted": True, **result}


ORCHESTRATOR_TOOLS: list[Any] = [
    init_research,
    get_research_status,
    get_research_objectives,
    validate_query_tree,
    get_next_actions,
    assess_query,
    evaluate_research_portfolio,
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
    get_report_evidence,
    get_reference_registry,
    submit_final_report,
]
