import json
import sys
import types
from pathlib import Path

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))
sys.modules.setdefault("config", types.SimpleNamespace(build_model=lambda: None))

from agents.memory_manager import MemoryManager  # noqa: E402
from tools import graph_tools, research_state  # noqa: E402
from tools.graph_manager_tools import ORCHESTRATOR_TOOLS  # noqa: E402


def _manager():
    mm = object.__new__(MemoryManager)
    mm.cache_dir = None
    mm.model = None
    return mm


def test_orchestrator_tool_assembly():
    names = {tool.name for tool in ORCHESTRATOR_TOOLS}
    assert "expand_horizontally" in names
    assert "expand_vertically" in names
    assert "expand_gaps" not in names


def test_assess_convergence_rejects_open_horizontal_space(monkeypatch):
    mm = _manager()
    monkeypatch.setattr(research_state, "REPORT_READY", "REPORT_READY")
    monkeypatch.setattr(research_state, "BUDGET_EXHAUSTED", "BUDGET_EXHAUSTED")
    monkeypatch.setattr(research_state, "RESEARCHING", "RESEARCHING")
    monkeypatch.setattr(research_state, "REPORT_ALLOWED", {"REPORT_READY", "BUDGET_EXHAUSTED"})
    monkeypatch.setattr(research_state, "get_status", lambda goal_id=None: {"research_state": "RESEARCHING"})
    monkeypatch.setattr(research_state, "get_goal", lambda goal_id=None: {"id": "goal", "research_state": "RESEARCHING"})
    updates = []
    monkeypatch.setattr(research_state, "update_goal", lambda attrs, goal_id=None: updates.append(attrs) or attrs)
    monkeypatch.setattr(research_state, "remaining_budget", lambda goal_id=None: 5)
    monkeypatch.setattr(research_state, "mark_budget_exhausted", lambda goal_id=None: {"research_state": "BUDGET_EXHAUSTED"})
    monkeypatch.setattr(graph_tools, "validate_query_tree", lambda: {"valid": True})
    monkeypatch.setattr(graph_tools, "search_nodes", lambda kind, _filter=None: [{"id": "q1", "type": "Query", "status": "sufficient"}] if kind == "query" else [])
    monkeypatch.setattr(graph_tools, "get_frontiers", lambda owner_id=None, statuses=None: [])
    monkeypatch.setattr(graph_tools, "upsert_node", lambda node_type, attrs, dedupe_key=None: dedupe_key)
    monkeypatch.setattr(
        mm,
        "_compute_research_metrics",
        lambda goal_id: {
            "horizontal_closure_score": 0.4,
            "slot_completion_score": 0.95,
            "core_claim_support_score": 0.9,
            "selected_frontier_backlog": 0,
            "delivery_readiness_score": 0.8,
            "delivery_ready": False,
            "slot_completion_threshold": 0.75,
        },
    )
    monkeypatch.setattr(mm, "_task_contract_snapshot", lambda goal_id=None: {"task_contract": {"deliverable_type": "research_report"}})
    monkeypatch.setattr(mm, "_all_remaining_frontiers_low_value", lambda: False)
    monkeypatch.setattr(mm, "_invoke_json", lambda prompt: {"delivery_ready": False, "reason": "horizontal space still open"})
    monkeypatch.setattr(mm, "get_next_actions", lambda limit=4: [{"action": "expand_horizontally"}])

    result = mm.assess_convergence("goal")

    assert result["converged"] is False
    assert result["research_state"] == "RESEARCHING"
    assert result["horizontal_closure_score"] == 0.4
    assert updates[-1]["research_state"] == "RESEARCHING"


def test_assess_convergence_requires_zero_selected_frontier_backlog(monkeypatch):
    mm = _manager()
    monkeypatch.setattr(research_state, "REPORT_READY", "REPORT_READY")
    monkeypatch.setattr(research_state, "BUDGET_EXHAUSTED", "BUDGET_EXHAUSTED")
    monkeypatch.setattr(research_state, "RESEARCHING", "RESEARCHING")
    monkeypatch.setattr(research_state, "REPORT_ALLOWED", {"REPORT_READY", "BUDGET_EXHAUSTED"})
    monkeypatch.setattr(research_state, "get_status", lambda goal_id=None: {"research_state": "RESEARCHING"})
    monkeypatch.setattr(research_state, "get_goal", lambda goal_id=None: {"id": "goal", "research_state": "RESEARCHING"})
    updates = []
    monkeypatch.setattr(research_state, "update_goal", lambda attrs, goal_id=None: updates.append(attrs) or attrs)
    monkeypatch.setattr(research_state, "remaining_budget", lambda goal_id=None: 5)
    monkeypatch.setattr(research_state, "mark_budget_exhausted", lambda goal_id=None: {"research_state": "BUDGET_EXHAUSTED"})
    monkeypatch.setattr(graph_tools, "validate_query_tree", lambda: {"valid": True})
    monkeypatch.setattr(graph_tools, "search_nodes", lambda kind, _filter=None: [{"id": "q1", "type": "Query", "status": "sufficient"}] if kind == "query" else [])
    monkeypatch.setattr(graph_tools, "get_frontiers", lambda owner_id=None, statuses=None: [{"id": "f1"}] if statuses == {"selected"} else [])
    monkeypatch.setattr(graph_tools, "upsert_node", lambda node_type, attrs, dedupe_key=None: dedupe_key)
    monkeypatch.setattr(
        mm,
        "_compute_research_metrics",
        lambda goal_id: {
            "horizontal_closure_score": 0.95,
            "slot_completion_score": 0.95,
            "core_claim_support_score": 0.9,
            "selected_frontier_backlog": 1,
            "delivery_readiness_score": 0.8,
            "delivery_ready": False,
            "slot_completion_threshold": 0.75,
        },
    )
    monkeypatch.setattr(mm, "_task_contract_snapshot", lambda goal_id=None: {"task_contract": {"deliverable_type": "research_report"}})
    monkeypatch.setattr(mm, "_all_remaining_frontiers_low_value", lambda: False)
    monkeypatch.setattr(mm, "_invoke_json", lambda prompt: {"delivery_ready": True, "reason": "selected backlog remains"})
    monkeypatch.setattr(mm, "get_next_actions", lambda limit=4: [{"action": "expand_vertically"}])

    result = mm.assess_convergence("goal")

    assert result["converged"] is False
    assert result["selected_frontier_backlog"] == 1
    assert updates[-1]["research_state"] == "RESEARCHING"


def test_assess_convergence_allows_reporting_when_slots_and_frontiers_close(monkeypatch):
    mm = _manager()
    monkeypatch.setattr(research_state, "REPORT_READY", "REPORT_READY")
    monkeypatch.setattr(research_state, "BUDGET_EXHAUSTED", "BUDGET_EXHAUSTED")
    monkeypatch.setattr(research_state, "RESEARCHING", "RESEARCHING")
    monkeypatch.setattr(research_state, "REPORT_ALLOWED", {"REPORT_READY", "BUDGET_EXHAUSTED"})
    monkeypatch.setattr(research_state, "get_status", lambda goal_id=None: {"research_state": "RESEARCHING"})
    monkeypatch.setattr(research_state, "get_goal", lambda goal_id=None: {"id": "goal", "research_state": "RESEARCHING"})
    updates = []
    monkeypatch.setattr(research_state, "update_goal", lambda attrs, goal_id=None: updates.append(attrs) or attrs)
    monkeypatch.setattr(research_state, "remaining_budget", lambda goal_id=None: 5)
    monkeypatch.setattr(research_state, "mark_budget_exhausted", lambda goal_id=None: {"research_state": "BUDGET_EXHAUSTED"})
    monkeypatch.setattr(graph_tools, "validate_query_tree", lambda: {"valid": True})
    monkeypatch.setattr(graph_tools, "search_nodes", lambda kind, _filter=None: [{"id": "q1", "type": "Query", "status": "sufficient"}] if kind == "query" else [])
    monkeypatch.setattr(graph_tools, "get_frontiers", lambda owner_id=None, statuses=None: [])
    monkeypatch.setattr(graph_tools, "upsert_node", lambda node_type, attrs, dedupe_key=None: dedupe_key)
    monkeypatch.setattr(
        mm,
        "_compute_research_metrics",
        lambda goal_id: {
            "horizontal_closure_score": 0.95,
            "slot_completion_score": 0.92,
            "core_claim_support_score": 0.85,
            "selected_frontier_backlog": 0,
            "delivery_readiness_score": 0.88,
            "delivery_ready": True,
            "slot_completion_threshold": 0.75,
        },
    )
    monkeypatch.setattr(mm, "_task_contract_snapshot", lambda goal_id=None: {"task_contract": {"deliverable_type": "research_report"}})
    monkeypatch.setattr(mm, "_all_remaining_frontiers_low_value", lambda: True)
    monkeypatch.setattr(mm, "_invoke_json", lambda prompt: {"delivery_ready": True, "slot_completion_score": 0.92, "reason": "ready"})
    monkeypatch.setattr(mm, "get_next_actions", lambda limit=4: [])

    result = mm.assess_convergence("goal")

    assert result["converged"] is True
    assert result["research_state"] == "REPORT_READY"
    assert updates[-1]["research_state"] == "REPORT_READY"
