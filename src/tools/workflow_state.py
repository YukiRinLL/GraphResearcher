"""Shared runtime workflow state for the current GraphResearcher run.

The Orchestrator prompt describes the desired workflow, but middleware and
tools need explicit state to enforce it. This module keeps a minimal
process-local state bag for the current run only.
"""

from copy import deepcopy
from typing import Any


def _default_state() -> dict[str, Any]:
    return {
        "phase": "init",
        "goal_id": None,
        "max_search_rounds": 0,
        "search_rounds": 0,
        "budget_exhausted": False,
        "round_open": False,
        "pending_review_query_ids": [],
        "analysis_ready_query_ids": [],
        "last_search_results": {},
        "last_subgraph_analysis": {},
        "last_marked_queries": {},
        "last_convergence": None,
        "reporter_called": False,
        "bound_section_count": 0,
        "report_validated": False,
    }


_STATE = _default_state()


def reset(max_search_rounds: int = 0) -> None:
    """Reset per-run workflow state."""
    global _STATE
    _STATE = _default_state()
    _STATE["max_search_rounds"] = max_search_rounds


def snapshot() -> dict[str, Any]:
    """Return a defensive copy of the current state."""
    return deepcopy(_STATE)


def get(key: str, default: Any = None) -> Any:
    """Return one state field."""
    return _STATE.get(key, default)


def set_phase(phase: str) -> None:
    """Set the current workflow phase."""
    _STATE["phase"] = phase


def set_goal_id(goal_id: str | None) -> None:
    """Remember the current research-goal node ID."""
    _STATE["goal_id"] = goal_id


def has_pending_review_work() -> bool:
    """Return whether dispatched or analyzed queries still need review closure."""
    return bool(_STATE["pending_review_query_ids"] or _STATE["analysis_ready_query_ids"])


def can_enter_report() -> bool:
    """Return whether the workflow is allowed to enter the report phase."""
    convergence = _STATE.get("last_convergence") or {}
    stop_recommended = convergence.get("recommendation") == "stop"
    budget_done = bool(_STATE.get("budget_exhausted"))
    return not has_pending_review_work() and (stop_recommended or budget_done)


def advance_report_phase_if_ready() -> None:
    """Move to report phase only when runtime stop conditions are satisfied."""
    if can_enter_report():
        _STATE["phase"] = "report"


def mark_budget_exhausted() -> None:
    """Mark the search budget exhausted without skipping pending review work."""
    _STATE["budget_exhausted"] = True
    advance_report_phase_if_ready()


def record_search_dispatch(query_id: str) -> None:
    """Record one Searcher dispatch and mark the query pending review."""
    _STATE["search_rounds"] += 1
    if query_id not in _STATE["pending_review_query_ids"]:
        _STATE["pending_review_query_ids"].append(query_id)
    if query_id in _STATE["analysis_ready_query_ids"]:
        _STATE["analysis_ready_query_ids"].remove(query_id)
    _STATE["phase"] = "research"


def open_research_round() -> None:
    """Allow a batch of Searcher dispatches for the next research round."""
    _STATE["round_open"] = True
    _STATE["phase"] = "research"


def close_research_round() -> None:
    """Close the current dispatch batch once review starts."""
    _STATE["round_open"] = False


def record_search_result(query_id: str, result: dict[str, Any]) -> None:
    """Store the last structured Searcher result for a query."""
    _STATE["last_search_results"][query_id] = result


def record_subgraph_analysis(query_id: str, analysis: dict[str, Any]) -> None:
    """Store analyze_subgraph output and mark the query ready for mark_query."""
    _STATE["round_open"] = False
    _STATE["last_subgraph_analysis"][query_id] = analysis
    if query_id not in _STATE["analysis_ready_query_ids"]:
        _STATE["analysis_ready_query_ids"].append(query_id)


def consume_mark_query(query_id: str, status: str, sufficiency_score: float | None) -> None:
    """Record a query status update and clear its pending-review bookkeeping."""
    _STATE["last_marked_queries"][query_id] = {
        "status": status,
        "sufficiency_score": sufficiency_score,
    }
    if query_id in _STATE["pending_review_query_ids"]:
        _STATE["pending_review_query_ids"].remove(query_id)
    if query_id in _STATE["analysis_ready_query_ids"]:
        _STATE["analysis_ready_query_ids"].remove(query_id)
    if not _STATE["pending_review_query_ids"]:
        _STATE["round_open"] = False
    advance_report_phase_if_ready()


def record_convergence(result: dict[str, Any]) -> None:
    """Store the latest convergence verdict and advance phase on stop."""
    _STATE["last_convergence"] = result
    if can_enter_report():
        _STATE["phase"] = "report"
    else:
        _STATE["phase"] = "research"


def mark_reporter_called() -> None:
    """Record that the Reporter subagent has been dispatched."""
    _STATE["reporter_called"] = True
    _STATE["phase"] = "report"


def record_bound_section() -> None:
    """Increment the number of successfully bound report sections."""
    _STATE["bound_section_count"] += 1


def mark_report_validated(validated: bool = True) -> None:
    """Store whether the final report passed terminal validation."""
    _STATE["report_validated"] = validated
    if validated:
        _STATE["phase"] = "done"
