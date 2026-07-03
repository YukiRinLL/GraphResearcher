"""Standalone checks for priority-weighted convergence.

Run directly (NOT pytest):  uv run python tests/test_convergence.py

Stubs ``graph_tools`` reads so the deterministic logic is exercised without a
live neo4j backend, and drives ``MemoryManager.assess_convergence`` with a fake
model to check the recommendation is composed correctly.
"""

import json
import sys
from pathlib import Path

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from agents.memory_manager import MemoryManager  # noqa: E402
from tools import convergence, graph_tools, report_tools, research_state  # noqa: E402

# Mutable fake graph the tests drive round by round.
_FAKE = {"query": [], "source": [], "evidence": [], "conflict": [], "analysis": []}
_NODES: dict = {}


def _fake_search_nodes(node_type, _filter):
    return list(_FAKE.get(node_type, []))


def _fake_get_node(node_id):
    return _NODES.get(node_id, {})


graph_tools.search_nodes = _fake_search_nodes
graph_tools.get_node = _fake_get_node
graph_tools.get_query_parent = lambda query_id: "goal" if query_id != "goal" else None


def _set(queries=None, sources=None, evidence=None, conflicts=None, objectives=None):
    _FAKE["query"] = queries or []
    _FAKE["source"] = sources or []
    _FAKE["evidence"] = evidence or []
    _FAKE["conflict"] = conflicts or []
    _FAKE["analysis"] = objectives or []
    for query in _FAKE["query"]:
        _NODES[query["id"]] = query


def ev(node_id, claim):
    return {"id": node_id, "type": "evidence", "claim": claim}


def src(node_id, url):
    return {"id": node_id, "type": "source", "url": url}


def q(node_id, status, score=None, tier=None, priority=None):
    n = {"id": node_id, "type": "query", "status": status, "required_for_parent": True}
    if score is not None:
        n["sufficiency_score"] = score
    if tier is not None:
        n["priority_tier"] = tier
    if priority is not None:
        n["priority"] = priority
    return n


class FakeModel:
    """Returns a fixed JSON payload from ``.invoke`` (the LLM verdict)."""

    def __init__(self, payload):
        self._payload = payload

    def invoke(self, _prompt):
        class _R:
            content = json.dumps(self._payload)

        return _R()


def test_compute_priority():
    convergence.reset()
    _NODES.clear()
    # Initial queries (parent = goal, no priority) -> struct = 1.0.
    _NODES["goal"] = {"id": "goal", "type": "user_request"}
    s_core, t_core, _ = convergence.compute_priority("core", "goal")
    s_sup, t_sup, _ = convergence.compute_priority("supporting", "goal")
    s_per, t_per, _ = convergence.compute_priority("peripheral", "goal")
    assert round(s_core, 2) == 1.00 and t_core == "high", (s_core, t_core)
    assert round(s_sup, 2) == 0.76 and t_sup == "high", (s_sup, t_sup)
    assert round(s_per, 2) == 0.58 and t_per == "low", (s_per, t_per)
    # Missing importance defaults to supporting -> high for an initial query.
    s_def, t_def, _ = convergence.compute_priority(None, "goal")
    assert round(s_def, 2) == 0.76 and t_def == "high"

    # Vertical child of a core query inherits a decayed structural floor.
    _NODES["qcore"] = {"id": "qcore", "type": "query", "priority": 1.0}
    s_child, t_child, _ = convergence.compute_priority("supporting", "qcore")
    assert round(s_child, 2) == 0.70 and t_child == "high", (s_child, t_child)
    # Peripheral detail under a peripheral parent stays low.
    _NODES["qper"] = {"id": "qper", "type": "query", "priority": 0.58}
    s_pp, t_pp, _ = convergence.compute_priority("peripheral", "qper")
    assert t_pp == "low", (s_pp, t_pp)


def test_structurally_converged():
    _NODES.clear()
    _NODES["goal"] = {"id": "goal", "type": "UserRequest"}
    # Every required branch gates convergence regardless of scheduling tier.
    _set(queries=[
        q("h1", "sufficient", 0.8, tier="high"),
        q("h2", "needs_expansion", 0.6, tier="high"),
        q("l1", "needs_expansion", 0.3, tier="low"),
    ])
    assert convergence.structurally_converged() is False
    # High below the score threshold -> not converged.
    _set(queries=[q("h1", "sufficient", 0.65, tier="high")])
    assert convergence.structurally_converged() is False
    # A non-required low-priority detail never gates.
    _set(queries=[
        q("h1", "sufficient", 0.8, tier="high"),
        {**q("l1", "pending", 0.2, tier="low"), "required_for_parent": False},
    ])
    assert convergence.structurally_converged() is True
    # A blocked high counts as best-effort (termination guarantee).
    _set(queries=[q("h1", "blocked", tier="high"), q("h2", "sufficient", 0.9, tier="high")])
    assert convergence.structurally_converged() is True
    # New graphs converge on must Objectives, independent of required-path flags.
    _set(
        queries=[q("h1", "pending", tier="high")],
        objectives=[{
            "id": "o1",
            "type": "analysis",
            "analysis_type": "objective",
            "requirement": "must",
            "status": "satisfied",
        }],
    )
    assert convergence.structurally_converged() is True


def test_novelty_advance_vs_snapshot():
    convergence.reset()
    # Cold start: a round with no evidence yet must NOT register as low novelty.
    _set(evidence=[])
    m = convergence.observe_round()
    assert m["novelty"]["ratio"] is None and m["novelty"]["new_total"] == 0
    m = convergence.observe_round()
    assert m["novelty"]["diminishing"] is False, "empty rounds must not trigger diminishing"

    _set(evidence=[ev("e1", "fact one"), ev("e2", "fact two")])
    m = convergence.observe_round()  # advances
    assert m["novelty"]["new_total"] == 2 and m["novelty"]["new_unique"] == 2
    assert m["novelty"]["ratio"] == 1.0
    # Read-only snapshot does not advance or change history.
    snap = convergence.compute_metrics(advance_novelty=False)
    assert snap["novelty"]["new_total"] is None
    assert snap["novelty"]["ratio"] == 1.0  # last recorded
    # Two duplicate-only rounds -> diminishing.
    _FAKE["evidence"].append(ev("e3", "fact one"))
    convergence.observe_round()
    _FAKE["evidence"].append(ev("e4", "fact two"))
    m = convergence.observe_round()
    assert m["novelty"]["ratio"] == 0.0 and m["novelty"]["diminishing"] is True
    # priority block present in metrics.
    assert "priority" in m and "structurally_converged" in m["priority"]


def test_assembly():
    from tools.graph_manager_tools import ORCHESTRATOR_TOOLS

    names = {t.name for t in ORCHESTRATOR_TOOLS}
    assert {
        "assess_convergence",
        "assess_query",
        "evaluate_research_portfolio",
        "expand_gaps",
        "get_next_actions",
        "get_research_objectives",
    } <= names, names
    assert not {"mark_query", "analyze_subgraph", "expand_query", "export_report_context"} & names, names


def test_delivery_readiness_gate():
    goal = {
        "id": "goal",
        "type": "UserRequest",
        "research_state": "RESEARCHING",
        "scope_mode": "bounded",
        "portfolio_revision": 1,
        "evaluated_portfolio_revision": 1,
        "time_window": "2024-2025",
        "task_archetype": "comparative_matrix",
        "delivery_contract": {
            "report_mode": "comparative_matrix",
            "required_section_types": ["lead", "body", "comparison", "limitations"],
            "required_slot_labels": ["对比矩阵"],
            "comparison_required": True,
            "entity_focus": False,
            "strict_time_window": True,
            "prefer_compression_over_expansion": True,
        },
    }
    query = {
        "id": "q1",
        "type": "Query",
        "status": "sufficient",
        "objective_keys": ["o1"],
        "importance": "core",
        "search_subject_key": "robotics",
        "slot_targets": [],
    }
    objective = {
        "id": "o1",
        "type": "Analysis",
        "analysis_type": "objective",
        "objective_key": "o1",
        "requirement": "must",
        "status": "satisfied",
        "coverage": 0.8,
        "confidence": 0.8,
    }
    _NODES.clear()
    _NODES["goal"] = goal
    _NODES["q1"] = query
    _NODES["o1"] = objective
    _set(queries=[query], objectives=[objective], conflicts=[])

    graph_tools.validate_query_tree = lambda: {"valid": True}
    graph_tools.get_query_evaluation_subgraph = lambda _query_id: {
        "nodes": [{"id": "s1", "type": "Source", "published_at": "2026-01-01"}],
    }
    graph_tools.upsert_node = lambda _kind, attrs, dedupe_key=None: (_NODES[dedupe_key].update(attrs) or dedupe_key)
    graph_tools.search_nodes = _fake_search_nodes
    research_state.get_status = lambda goal_id=None: {"research_state": _NODES["goal"]["research_state"]}
    research_state.get_goal = lambda goal_id=None: dict(_NODES["goal"])
    research_state.remaining_budget = lambda goal_id=None: 2
    research_state.mark_budget_exhausted = lambda goal_id=None: dict(_NODES["goal"])
    research_state.update_goal = lambda attrs, goal_id=None: (_NODES["goal"].update(attrs) or dict(_NODES["goal"]))
    report_tools.build_report_planning_assets = lambda query_ids=None: {
        "query_evidence_digests": [],
        "lead_candidates": [{"text": "lead", "query_ids": ["q1"], "evidence_ids": [], "source_ids": []}],
        "comparison_slots": [],
        "entity_profiles": [],
    }

    mm = MemoryManager(model=FakeModel({"fatal_unresolved_conflicts": [], "reason": "no fatal conflicts"}))
    result = mm.assess_convergence("goal")
    assert result["research_state"] == "RESEARCHING", result
    assert result["recommendation"] == "continue", result
    assert "comparison" in result["missing_contract_slots"], result
    assert "q1" in result["citation_hygiene_query_ids"], result


def test_delivery_readiness_uses_artifact_slot_coverage():
    from tools import report_tools

    goal = {
        "id": "goal",
        "type": "UserRequest",
        "research_state": "RESEARCHING",
        "scope_mode": "bounded",
        "portfolio_revision": 1,
        "evaluated_portfolio_revision": 1,
        "task_archetype": "comparative_matrix",
        "delivery_contract": {
            "report_mode": "comparative_matrix",
            "required_section_types": ["body", "comparison", "limitations"],
            "required_slot_labels": ["跨公司对比矩阵", "团队画像"],
            "comparison_required": True,
            "entity_focus": False,
            "strict_time_window": False,
            "prefer_compression_over_expansion": True,
        },
    }
    query = {
        "id": "q1",
        "type": "Query",
        "status": "sufficient",
        "objective_keys": ["o1"],
        "importance": "core",
        "search_subject_key": "robotics",
        "slot_targets": ["团队画像"],
    }
    objective = {
        "id": "o1",
        "type": "Analysis",
        "analysis_type": "objective",
        "objective_key": "o1",
        "requirement": "must",
        "status": "satisfied",
        "coverage": 0.8,
        "confidence": 0.8,
    }
    _NODES.clear()
    _NODES["goal"] = goal
    _NODES["q1"] = query
    _NODES["o1"] = objective
    _set(queries=[query], objectives=[objective], conflicts=[])

    original_build_assets = report_tools.build_report_planning_assets
    original_infer_slots = report_tools.infer_delivery_slot_coverage
    graph_tools.search_nodes = _fake_search_nodes
    research_state.get_goal = lambda goal_id=None: dict(_NODES["goal"])
    try:
        report_tools.build_report_planning_assets = lambda query_ids=None: {
            "query_evidence_digests": [],
            "lead_candidates": [],
            "comparison_slots": [],
            "entity_profiles": [],
        }
        report_tools.infer_delivery_slot_coverage = lambda output_dir, planning_assets=None: ["comparison"]
        readiness = MemoryManager(model=FakeModel({"fatal_unresolved_conflicts": [], "reason": "ok"}))._compute_delivery_readiness(
            "goal",
            goal=goal,
            queries=[query],
            gaps=[],
        )
        assert readiness["ready"] is True, readiness
        assert readiness["missing_contract_slots"] == [], readiness
        assert set(readiness["slot_coverage"]) == {"comparison", "team_profile"}, readiness
    finally:
        report_tools.build_report_planning_assets = original_build_assets
        report_tools.infer_delivery_slot_coverage = original_infer_slots


def main():
    test_compute_priority()
    test_structurally_converged()
    test_novelty_advance_vs_snapshot()
    test_assembly()
    test_delivery_readiness_gate()
    test_delivery_readiness_uses_artifact_slot_coverage()
if __name__ == "__main__":
    main()
