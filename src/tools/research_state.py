"""Persistent research-state helpers stored on the run's UserRequest node."""

from __future__ import annotations

from typing import Any, Optional

from memory.graph import NodeType
from tools import graph_tools

INITIALIZING = "INITIALIZING"
RESEARCHING = "RESEARCHING"
REPORT_READY = "REPORT_READY"
BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
REPORTING = "REPORTING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"

REPORT_ALLOWED = {REPORT_READY, BUDGET_EXHAUSTED, REPORTING, COMPLETED}
TERMINAL_QUERY_STATUSES = {"sufficient", "blocked", "failed", "deferred"}
OPEN_GAP_STATUSES = {"candidate", "selected", "assigned"}
_TRANSITIONS = {
    INITIALIZING: {INITIALIZING, RESEARCHING, FAILED},
    RESEARCHING: {RESEARCHING, REPORT_READY, BUDGET_EXHAUSTED, FAILED},
    REPORT_READY: {REPORT_READY, REPORTING, FAILED},
    BUDGET_EXHAUSTED: {BUDGET_EXHAUSTED, REPORTING, FAILED},
    REPORTING: {REPORTING, COMPLETED, FAILED},
    COMPLETED: {COMPLETED, FAILED},
    FAILED: {FAILED},
}


def get_goal(goal_id: Optional[str] = None) -> dict[str, Any]:
    """Return the current run's unique UserRequest node."""
    node = graph_tools.get_node(goal_id) if goal_id else {}
    if str(node.get("type", "")).replace("_", "").lower() == "userrequest":
        return node
    goals = graph_tools.search_nodes("user_request", {})
    return goals[0] if goals else {}


def update_goal(attributes: dict[str, Any], goal_id: Optional[str] = None) -> dict[str, Any]:
    """Update the current run's root state and return the refreshed node."""
    goal = get_goal(goal_id)
    if not goal:
        return {}
    target_state = attributes.get("research_state")
    current_state = goal.get("research_state")
    if target_state and current_state and target_state not in _TRANSITIONS.get(current_state, set()):
        raise ValueError(f"Invalid research-state transition: {current_state} -> {target_state}")
    graph_tools.upsert_node(NodeType.USER_REQUEST, attributes, goal["id"])
    return graph_tools.get_node(goal["id"])


def remaining_budget(goal_id: Optional[str] = None) -> Optional[int]:
    """Return remaining dispatch capacity, or None for unlimited."""
    goal = get_goal(goal_id)
    maximum = int(goal.get("max_search_rounds") or 0)
    if maximum <= 0:
        return None
    return max(0, maximum - int(goal.get("dispatched_search_rounds") or 0))


def mark_budget_exhausted(goal_id: Optional[str] = None) -> dict[str, Any]:
    """Authorize a limited report and defer every still-open gap."""
    if graph_tools.search_nodes("query", {"status": "searching"}):
        return get_goal(goal_id)
    for gap in graph_tools.search_nodes("analysis", {"analysis_type": "gap"}):
        if gap.get("status") in OPEN_GAP_STATUSES:
            graph_tools.upsert_node(
                NodeType.ANALYSIS,
                {"status": "deferred_budget", "resolution_reason": "search budget exhausted"},
                gap["id"],
            )
    for conflict in graph_tools.search_nodes("conflict", {}):
        if conflict.get("resolution_status") in {"unresolved", "investigating"}:
            graph_tools.upsert_node(
                NodeType.CONFLICT,
                {"resolution_status": "disclosed"},
                conflict["id"],
            )
    return update_goal({
        "research_state": BUDGET_EXHAUSTED,
        "last_convergence_recommendation": "stop",
        "report_authorized_reason": "search budget exhausted",
    }, goal_id)


def is_required_path(query_id: str) -> bool:
    """Return whether every Query on the path to the root is locally required."""
    current = query_id
    while current:
        node = graph_tools.get_node(current)
        if str(node.get("type", "")).lower() != "query":
            return bool(node)
        if not node.get("required_for_parent", True):
            return False
        current = graph_tools.get_query_parent(current)
    return False


def gap_is_required_path(gap_id: str) -> bool:
    """Return whether a required Gap belongs to a globally required Query path."""
    gap = graph_tools.get_node(gap_id)
    if not gap.get("required_for_parent", True):
        return False
    for edge in graph_tools.get_node_edges(gap_id, direction="in"):
        if str(edge.get("type", "")).lower() == "has_gap":
            return is_required_path(edge.get("source"))
    return False


def get_status(goal_id: Optional[str] = None) -> dict[str, Any]:
    """Return a compact persistent state summary."""
    goal = get_goal(goal_id)
    queries = graph_tools.search_nodes("query", {})
    gaps = graph_tools.search_nodes("analysis", {"analysis_type": "gap"})
    objectives = graph_tools.search_nodes("analysis", {"analysis_type": "objective"})
    counts: dict[str, int] = {}
    for query in queries:
        status = query.get("status") or "unknown"
        counts[status] = counts.get(status, 0) + 1
    active_queries = [
        q for q in queries
        if q.get("status") not in TERMINAL_QUERY_STATUSES
    ]
    return {
        "goal_id": goal.get("id"),
        "research_state": goal.get("research_state"),
        "max_search_rounds": goal.get("max_search_rounds", 0),
        "dispatched_search_rounds": goal.get("dispatched_search_rounds", 0),
        "successful_search_rounds": goal.get("successful_search_rounds", 0),
        "remaining_search_rounds": remaining_budget(goal.get("id")),
        "scope_mode": goal.get("scope_mode", "bounded"),
        "portfolio_revision": goal.get("portfolio_revision", 0),
        "evaluated_portfolio_revision": goal.get("evaluated_portfolio_revision", 0),
        "last_max_marginal_utility": goal.get("last_max_marginal_utility", 0.0),
        "report_readiness_score": goal.get("report_readiness_score", 0.0),
        "objectives": [
            {
                "objective_key": objective.get("objective_key"),
                "requirement": objective.get("requirement"),
                "status": objective.get("status"),
                "coverage": objective.get("coverage"),
                "confidence": objective.get("confidence"),
            }
            for objective in objectives
        ],
        "query_status_counts": counts,
        "active_queries": [
            {"id": q.get("id"), "handle": q.get("handle"), "status": q.get("status"), "text": q.get("text")}
            for q in active_queries
        ],
        "selected_gaps": [
            {
                "id": g.get("id"),
                "description": g.get("description") or g.get("text"),
                "status": g.get("status"),
                "marginal_utility": g.get("marginal_utility"),
            }
            for g in gaps
            if g.get("status") in {"selected", "assigned"}
        ],
        "last_convergence_recommendation": goal.get("last_convergence_recommendation"),
        "report_authorized_reason": goal.get("report_authorized_reason"),
        "reporting_from_state": goal.get("reporting_from_state"),
        "report_phase": goal.get("report_phase"),
        "report_revision_attempts": goal.get("report_revision_attempts", 0),
        "report_quality_status": goal.get("report_quality_status"),
        "report_delivery_mode": goal.get("report_delivery_mode"),
        "report_validation_issues": goal.get("report_validation_issues", []),
        "reporter_warnings": goal.get("reporter_warnings", []),
        "last_error": goal.get("last_error"),
    }
