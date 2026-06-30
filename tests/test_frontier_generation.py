import json
import sys
import types
from pathlib import Path

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))
sys.modules.setdefault("config", types.SimpleNamespace(build_model=lambda: None))

from agents.memory_manager import MemoryManager  # noqa: E402
from memory.graph import NodeType  # noqa: E402
from tools import graph_tools, research_state  # noqa: E402


class FakeModel:
    def __init__(self, payloads):
        self.payloads = list(payloads)

    def invoke(self, _prompt):
        payload = self.payloads.pop(0)

        class Response:
            content = json.dumps(payload, ensure_ascii=False)

        return Response()


def _manager(model):
    mm = MemoryManager(model=model)
    return mm


def test_assess_query_generates_horizontal_and_vertical_frontiers(monkeypatch):
    mm = _manager(FakeModel([
        {
            "sufficiency_score": 0.7,
            "covered": ["base facts"],
            "filled_slot_keys": ["lead-slot"],
            "remaining_slot_keys": ["history-slot"],
            "horizontal_frontiers": [
                {
                    "description": "missing peer company cluster",
                    "importance": "core",
                    "granularity_level": "entity_cluster",
                    "scope_signature": "peer-cluster",
                    "target_slot_keys": ["history-slot"],
                    "decision_impact": 0.8,
                    "confidence_gain": 0.7,
                    "novelty_score": 0.7,
                    "slot_blocking_score": 0.9,
                    "primary_source_need": 0.1,
                    "estimated_search_rounds": 1,
                    "acceptance_criteria": ["identify at least one uncovered peer cluster"],
                }
            ],
            "vertical_frontiers": [
                {
                    "description": "verify manufacturing timeline",
                    "importance": "core",
                    "granularity_level": "evidence_chain",
                    "scope_signature": "timeline-verify",
                    "target_slot_keys": ["history-slot"],
                    "anchor_claim_ids": ["claim-1"],
                    "anchor_conflict_ids": ["conflict-1"],
                    "anchor_evidence_ids": [],
                    "decision_impact": 0.9,
                    "confidence_gain": 0.9,
                    "novelty_score": 0.6,
                    "slot_blocking_score": 0.8,
                    "primary_source_need": 0.9,
                    "estimated_search_rounds": 1,
                    "acceptance_criteria": ["resolve the timeline conflict"],
                }
            ],
            "dimension_hypotheses": [
                {"dimension_label": "peer clusters", "support_strength": 0.8, "covered_by_scope_signatures": []}
            ],
            "recommendation": "continue",
            "reason": "base answer exists but frontier remains open",
        }
    ]))
    nodes = {
        "goal": {"id": "goal", "type": "UserRequest", "research_state": "RESEARCHING"},
        "query": {
            "id": "query",
            "type": "Query",
            "handle": "q1",
            "text": "humanoid robotics company cluster",
            "status": "assessing",
            "granularity_level": "entity_cluster",
            "scope_signature": "root-cluster",
            "query_role": "seed",
            "target_slot_keys": ["lead-slot", "history-slot"],
            "acceptance_criteria": ["identify the core cluster"],
        },
        "claim-1": {"id": "claim-1", "type": "Claim"},
        "conflict-1": {"id": "conflict-1", "type": "Conflict"},
        "slot-lead": {"id": "slot-lead", "type": "CoverageSlot", "slot_key": "lead-slot", "status": "open"},
        "slot-history": {"id": "slot-history", "type": "CoverageSlot", "slot_key": "history-slot", "status": "open"},
    }
    frontiers = {}
    hypotheses = {}
    frontier_edges = []

    monkeypatch.setattr(research_state, "RESEARCHING", "RESEARCHING")
    monkeypatch.setattr(research_state, "get_status", lambda goal_id=None: {"research_state": "RESEARCHING"})
    monkeypatch.setattr(graph_tools, "get_node", lambda node_id: dict(nodes.get(node_id, frontiers.get(node_id, hypotheses.get(node_id, {})))))
    monkeypatch.setattr(graph_tools, "get_query_evaluation_subgraph", lambda query_id: {"query": nodes["query"], "nodes": []})
    monkeypatch.setattr(graph_tools, "get_task_contract", lambda goal_id: {"required_sections": [], "required_tables": [], "deliverable_type": "research_report"})
    monkeypatch.setattr(graph_tools, "get_coverage_slots", lambda goal_id: [dict(nodes["slot-lead"]), dict(nodes["slot-history"])])
    monkeypatch.setattr(graph_tools, "get_query_parent", lambda query_id: "goal")
    monkeypatch.setattr(graph_tools, "get_frontiers", lambda owner_id=None, statuses=None: [])
    monkeypatch.setattr(graph_tools, "bind_slot_filler", lambda slot_id, evidence_ids=None, claim_ids=None: None)
    monkeypatch.setattr(graph_tools, "search_nodes", lambda kind, _filter=None: [] if kind in {"dimension_hypothesis", "query"} else [])
    monkeypatch.setattr(graph_tools, "transition_query", lambda query_id, status, **attrs: nodes["query"].update({"status": status, **attrs}) or query_id)
    monkeypatch.setattr(graph_tools, "upsert_node", lambda node_type, attrs, dedupe_key=None: nodes.get(dedupe_key, frontiers.get(dedupe_key, hypotheses.get(dedupe_key, {}))).update(attrs) or dedupe_key)
    monkeypatch.setattr(graph_tools, "add_edge", lambda source, target, edge_type, attributes=None: frontier_edges.append((source, target, str(getattr(edge_type, "value", edge_type)))))
    monkeypatch.setattr(graph_tools, "create_frontier", lambda owner_id, frontier_type, description, status="candidate", slot_ids=None, anchor_claim_ids=None, anchor_conflict_ids=None, anchor_evidence_ids=None, **attrs: frontiers.setdefault(f"frontier-{len(frontiers)+1}", {"id": f"frontier-{len(frontiers)+1}", "type": "ResearchFrontier", "frontier_type": frontier_type, "description": description, "status": status, "target_slot_keys": attrs.get("target_slot_keys") or [], "anchor_claim_ids": anchor_claim_ids or [], "anchor_conflict_ids": anchor_conflict_ids or [], **attrs})["id"])
    monkeypatch.setattr(graph_tools, "create_dimension_hypothesis", lambda goal_id, dimension_label, parent_query_id, support_strength=0.0, covered_by_query_ids=None, **attrs: hypotheses.setdefault(f"hyp-{len(hypotheses)+1}", {"id": f"hyp-{len(hypotheses)+1}", "type": "DimensionHypothesis", "dimension_label": dimension_label, "parent_query_id": parent_query_id, "support_strength": support_strength, "covered_by_query_ids": covered_by_query_ids or []})["id"])
    monkeypatch.setattr(mm, "normalize_claims", lambda query_id: {"created_or_updated_claim_ids": ["claim-1"]})
    monkeypatch.setattr(mm, "_task_contract_snapshot", lambda goal_id=None: {"task_contract": {"deliverable_type": "research_report"}, "slot_registry": [{"slot_key": "lead-slot"}, {"slot_key": "history-slot"}]})
    monkeypatch.setattr(mm, "_goal_node", lambda goal_id=None: {"id": "goal"})
    monkeypatch.setattr(mm, "_bump_portfolio_revision", lambda: 2)

    result = mm.assess_query("query")

    assert result["status"] == "sufficient"
    assert len(result["created_horizontal_frontier_ids"]) == 1
    assert len(result["created_vertical_frontier_ids"]) == 1
    assert len(result["created_dimension_hypothesis_ids"]) == 1
    vertical = frontiers[result["created_vertical_frontier_ids"][0]]
    assert vertical["anchor_claim_ids"] == ["claim-1"]
    assert vertical["anchor_conflict_ids"] == ["conflict-1"]
