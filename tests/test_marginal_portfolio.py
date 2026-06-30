import sys
import types
from pathlib import Path

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))
sys.modules.setdefault("config", types.SimpleNamespace(build_model=lambda: None))

from agents.memory_manager import MemoryManager  # noqa: E402
from memory.graph import NodeType  # noqa: E402
from tools import graph_tools  # noqa: E402


def _manager():
    mm = object.__new__(MemoryManager)
    mm.cache_dir = None
    mm.model = None
    return mm


def test_horizontal_frontier_selected_when_problem_space_open(monkeypatch):
    mm = _manager()
    goal = {
        "id": "goal",
        "research_state": "RESEARCHING",
        "portfolio_revision": 3,
        "evaluated_portfolio_revision": 2,
        "breadth_budget": 2,
        "breadth_budget_used": 0,
        "depth_budget": 0,
        "depth_budget_used": 0,
        "verification_budget": 0,
        "verification_budget_used": 0,
    }
    nodes = {
        "goal": dict(goal),
        "fh": {
            "id": "fh",
            "type": "ResearchFrontier",
            "frontier_type": "horizontal",
            "status": "candidate",
            "description": "missing company cluster",
            "decision_impact": 0.8,
            "confidence_gain": 0.7,
            "novelty_score": 0.7,
            "slot_blocking_score": 0.9,
            "primary_source_need": 0.2,
            "estimated_search_rounds": 1,
            "dimension": "company_cluster",
        }
    }
    monkeypatch.setattr(graph_tools, "get_frontiers", lambda owner_id=None, statuses=None: [dict(nodes["fh"])] if statuses != {"selected"} else [])
    monkeypatch.setattr(graph_tools, "search_nodes", lambda kind, _filter=None: [] if kind == "dimension_hypothesis" else [])
    monkeypatch.setattr(graph_tools, "upsert_node", lambda node_type, attrs, dedupe_key=None: nodes[dedupe_key].update(attrs) or dedupe_key)
    monkeypatch.setattr(
        mm,
        "_compute_research_metrics",
        lambda goal_id: {
            "horizontal_closure_score": 0.4,
            "slot_completion_score": 0.3,
            "core_claim_support_score": 0.4,
            "selected_frontier_backlog": 0,
            "delivery_readiness_score": 0.0,
            "delivery_ready": False,
            "slot_completion_threshold": 0.75,
        },
    )
    monkeypatch.setattr(mm, "_remaining_frontier_budgets", lambda goal_node: {"breadth": 2, "depth": 0, "verification": 0})
    monkeypatch.setattr(mm, "_frontier_redundancy", lambda frontier: 0.0)
    monkeypatch.setattr(mm, "_is_verification_frontier", lambda frontier: False)

    from tools import research_state

    monkeypatch.setattr(research_state, "get_goal", lambda goal_id=None: dict(goal))
    result = mm.evaluate_research_portfolio("goal")

    assert result["selected_frontier_ids"] == ["fh"]
    assert nodes["fh"]["status"] == "selected"


def test_verification_vertical_frontier_beats_regular_horizontal(monkeypatch):
    mm = _manager()
    goal = {
        "id": "goal",
        "research_state": "RESEARCHING",
        "portfolio_revision": 5,
        "evaluated_portfolio_revision": 4,
        "breadth_budget": 0,
        "breadth_budget_used": 0,
        "depth_budget": 0,
        "depth_budget_used": 0,
        "verification_budget": 1,
        "verification_budget_used": 0,
    }
    nodes = {
        "goal": dict(goal),
        "fh": {
            "id": "fh",
            "type": "ResearchFrontier",
            "frontier_type": "horizontal",
            "status": "candidate",
            "description": "extra vendor cluster",
            "decision_impact": 0.5,
            "confidence_gain": 0.5,
            "novelty_score": 0.5,
            "slot_blocking_score": 0.5,
            "primary_source_need": 0.2,
            "estimated_search_rounds": 1,
        },
        "fv": {
            "id": "fv",
            "type": "ResearchFrontier",
            "frontier_type": "vertical",
            "status": "candidate",
            "description": "resolve conflicting shipment figure",
            "decision_impact": 0.6,
            "confidence_gain": 0.7,
            "novelty_score": 0.4,
            "slot_blocking_score": 0.8,
            "primary_source_need": 0.9,
            "estimated_search_rounds": 1,
            "anchor_conflict_ids": ["conflict-1"],
        },
    }
    monkeypatch.setattr(graph_tools, "get_frontiers", lambda owner_id=None, statuses=None: [dict(nodes["fh"]), dict(nodes["fv"])] if statuses != {"selected"} else [])
    monkeypatch.setattr(graph_tools, "search_nodes", lambda kind, _filter=None: [] if kind == "dimension_hypothesis" else [])
    monkeypatch.setattr(graph_tools, "upsert_node", lambda node_type, attrs, dedupe_key=None: nodes[dedupe_key].update(attrs) or dedupe_key)
    monkeypatch.setattr(
        mm,
        "_compute_research_metrics",
        lambda goal_id: {
            "horizontal_closure_score": 0.95,
            "slot_completion_score": 0.3,
            "core_claim_support_score": 0.4,
            "selected_frontier_backlog": 0,
            "delivery_readiness_score": 0.0,
            "delivery_ready": False,
            "slot_completion_threshold": 0.75,
        },
    )
    monkeypatch.setattr(mm, "_remaining_frontier_budgets", lambda goal_node: {"breadth": 0, "depth": 0, "verification": 1})
    monkeypatch.setattr(mm, "_frontier_redundancy", lambda frontier: 0.0)
    monkeypatch.setattr(mm, "_is_verification_frontier", lambda frontier: frontier["id"] == "fv")

    from tools import research_state

    monkeypatch.setattr(research_state, "get_goal", lambda goal_id=None: dict(goal))
    result = mm.evaluate_research_portfolio("goal")

    assert result["selected_frontier_ids"] == ["fv"]
    assert nodes["fv"]["status"] == "selected"
    assert nodes["fh"]["status"] != "selected"
