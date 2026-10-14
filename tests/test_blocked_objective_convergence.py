"""复现低覆盖 Objective 被提前授权报告的问题。

直接运行：``uv run python tests/test_blocked_objective_convergence.py``。
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from agents.memory_manager import MemoryManager  # noqa: E402
from tools import graph_tools, research_state  # noqa: E402


class FakeModel:
    """返回组合评估裁决（致命冲突分类已并入 portfolio）。"""

    def __init__(self):
        self.payloads = [
            {
                "objectives": [{
                    "objective_key": "discovery-provenance",
                    "coverage": 0.35,
                    "confidence": 0.8,
                    "reason": "The required museum and provenance facts remain missing.",
                    "supported_boundary": "Museum records establish the material but not the transfer history.",
                    "unmet_acceptance_criteria": ["Document the transfer history."],
                }],
                "fatal_unresolved_conflicts": [],
            },
        ]

    def invoke(self, _prompt):
        payload = self.payloads.pop(0)

        class Response:
            content = json.dumps(payload)

        return Response()


def test_blocked_objective_with_budget_authorizes_limited_report():
    nodes = {
        "goal": {
            "id": "goal",
            "type": "UserRequest",
            "state_contract_version": 4,
            "research_state": research_state.RESEARCHING,
            "max_search_rounds": 20,
            "dispatched_search_rounds": 8,
            "successful_search_rounds": 8,
            "scope_mode": "bounded",
            "portfolio_revision": 1,
            "evaluated_portfolio_revision": 1,
        },
        "objective": {
            "id": "objective",
            "type": "Analysis",
            "analysis_type": "objective",
            "objective_key": "discovery-provenance",
            "requirement": "must",
            "weight": 1.0,
            "acceptance_criteria": [
                "Identify the material from a museum record.",
                "Document the transfer history.",
            ],
            "coverage": 0.35,
            "confidence": 0.8,
            "status": "blocked",
            "low_gain_streak": 3,
            "last_evaluated_successful_rounds": 8,
        },
        "optional-objective": {
            "id": "optional-objective",
            "type": "Analysis",
            "analysis_type": "objective",
            "objective_key": "optional-context",
            "requirement": "should",
            "weight": 100.0,
            "coverage": 0.0,
            "confidence": 0.0,
            "status": "open",
        },
        "query": {
            "id": "query",
            "type": "Query",
            "handle": "q1",
            "text": "Ring of Nestor museum provenance",
            "status": "blocked",
            "objective_keys": ["discovery-provenance"],
            "sufficiency_score": 0.2,
        },
    }

    def get_node(node_id):
        return dict(nodes.get(node_id, {}))

    def search_nodes(node_type, filters=None):
        normalized = node_type.replace("_", "").lower()
        matches = [
            dict(node)
            for node in nodes.values()
            if str(node.get("type", "")).replace("_", "").lower() == normalized
        ]
        return [
            node
            for node in matches
            if all(node.get(key) == value for key, value in (filters or {}).items())
        ]

    def upsert_node(_node_type, attributes, dedupe_key=None):
        nodes[dedupe_key].update(attributes)
        return dedupe_key

    with patch.multiple(
        graph_tools,
        get_node=get_node,
        search_nodes=search_nodes,
        upsert_node=upsert_node,
        get_query_evaluation_subgraph=lambda query_id: {
            "query": get_node(query_id),
            "nodes": [],
            "edges": [],
        },
        get_query_parent=lambda query_id: "goal" if query_id == "query" else None,
        get_query_children=lambda _parent_id: [],
        get_node_edges=lambda _node_id, direction="both": [],
        validate_query_tree=lambda: {
            "valid": True,
            "orphans": [],
            "multi_parent_queries": [],
            "cycles": [],
            "invalid_handles": [],
            "duplicate_handles": [],
            "multiple_goals": [],
            "invalid_parent_edges": [],
        },
    ):
        manager = MemoryManager(model=FakeModel())
        portfolio = manager.evaluate_research_portfolio("goal")
        convergence = manager.assess_convergence("goal")
        repeated_convergence = manager.assess_convergence("goal")
        observed = {
            "report_completeness_score": round(portfolio["report_completeness_score"], 4),
            "research_state": convergence["research_state"],
            "repeated_converged": repeated_convergence["converged"],
            "supported_boundary": nodes["objective"].get("supported_boundary"),
            "unmet_acceptance_criteria": nodes["objective"].get("unmet_acceptance_criteria"),
            "remaining_search_rounds": research_state.remaining_budget("goal"),
        }

    assert observed["remaining_search_rounds"] == 12, observed
    # coverage/confidence 比值 0.5833（0.35/0.60；confidence 0.8/0.5
    # 非限制项），再乘验收标准满足率：2 条中 1 条未满足 → 0.5。
    assert observed["report_completeness_score"] == 0.2917, observed
    assert observed["research_state"] == research_state.LIMITED_REPORT_READY, observed
    assert observed["repeated_converged"] is True, observed
    assert observed["supported_boundary"] == (
        "Museum records establish the material but not the transfer history."
    ), observed
    assert observed["unmet_acceptance_criteria"] == ["Document the transfer history."], observed


if __name__ == "__main__":
    test_blocked_objective_with_budget_authorizes_limited_report()
