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
OPEN_FRONTIER_STATUSES = {"candidate", "selected", "expanded"}
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
    """Authorize a limited report and defer every still-open frontier."""
    if graph_tools.search_nodes("query", {"status": "searching"}):
        return get_goal(goal_id)
    for frontier in graph_tools.search_nodes("research_frontier", {}):
        if frontier.get("status") in OPEN_FRONTIER_STATUSES:
            graph_tools.upsert_node(
                NodeType.RESEARCH_FRONTIER,
                {"status": "deferred_budget", "resolution_reason": "search budget exhausted"},
                frontier["id"],
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
    frontiers = graph_tools.search_nodes("research_frontier", {})
    slots = graph_tools.get_coverage_slots(goal.get("id")) if goal else []
    contract = graph_tools.get_task_contract(goal.get("id")) if goal else {}
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
        "deliverable_type": goal.get("deliverable_type") or (contract or {}).get("deliverable_type"),
        "horizontal_closure_score": goal.get("horizontal_closure_score", 0.0),
        "slot_completion_score": goal.get("slot_completion_score", 0.0),
        "delivery_readiness": goal.get("delivery_readiness", False),
        "query_status_counts": counts,
        "active_queries": [
            {"id": q.get("id"), "handle": q.get("handle"), "status": q.get("status"), "text": q.get("text")}
            for q in active_queries
        ],
        "frontier_backlog": [
            {
                "id": f.get("id"),
                "frontier_type": f.get("frontier_type"),
                "description": f.get("description"),
                "status": f.get("status"),
                "marginal_utility": f.get("marginal_utility"),
            }
            for f in frontiers
            if f.get("status") in {"selected", "expanded"}
        ],
        "slot_registry": [
            {
                "id": slot.get("id"),
                "slot_key": slot.get("slot_key"),
                "section": slot.get("section"),
                "status": slot.get("status"),
                "completion_score": slot.get("completion_score"),
            }
            for slot in slots
        ],
        "last_convergence_recommendation": goal.get("last_convergence_recommendation"),
        "report_authorized_reason": goal.get("report_authorized_reason"),
        "reporting_from_state": goal.get("reporting_from_state"),
        "report_delivery_mode": goal.get("report_delivery_mode"),
        "report_validation_issues": goal.get("report_validation_issues", []),
        "report_attempt_summary": goal.get("report_attempt_summary", {}),
        "reporter_warnings": goal.get("reporter_warnings", []),
        "last_error": goal.get("last_error"),
    }
