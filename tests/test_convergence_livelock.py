"""Regression check for stale-portfolio convergence livelock."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from agents.memory_manager import MemoryManager  # noqa: E402
from tools import graph_tools, research_state  # noqa: E402


class FakeModel:
    """Return the portfolio verdict (fatality classification now lives there)."""

    def __init__(self):
        self.payloads = [
            {
                "objectives": [{
                    "objective_key": "core-answer",
                    "coverage": 0.35,
                    "confidence": 0.4,
                    "supported_boundary": "The available source establishes only a narrow boundary.",
                    "unmet_acceptance_criteria": [],
                    "reason": "The objective remains blocked after targeted recovery.",
                }],
                "fatal_unresolved_conflicts": [],
            },
        ]
        self.calls = 0

    def invoke(self, _prompt):
        payload = self.payloads.pop(0)
        self.calls += 1

        class Response:
            content = json.dumps(payload)

        return Response()


def test_stale_portfolio_is_evaluated_before_convergence():
    nodes = {
        "goal": {
            "id": "goal",
            "type": "UserRequest",
            "research_state": research_state.RESEARCHING,
            "scope_mode": "bounded",
            "max_search_rounds": 20,
            "dispatched_search_rounds": 10,
            "successful_search_rounds": 10,
            "portfolio_revision": 2,
            "evaluated_portfolio_revision": 1,
        },
        "objective": {
            "id": "objective",
            "type": "Analysis",
            "analysis_type": "objective",
            "objective_key": "core-answer",
            "requirement": "must",
            "weight": 1.0,
            "acceptance_criteria": [],
            "coverage": 0.2,
            "confidence": 0.2,
            "status": "blocked",
            "low_gain_streak": 3,
            "last_evaluated_successful_rounds": 10,
        },
        "query": {
            "id": "query",
            "type": "Query",
            "handle": "q1",
            "text": "core answer",
            "status": "blocked",
            "objective_keys": ["core-answer"],
            "acceptance_criteria": [],
            "criterion_results": [],
            "sufficiency_score": 0.2,
            "portfolio_revision_at_assessment": 2,
        },
    }

    def get_node(node_id):
        return dict(nodes.get(node_id, {}))

    def search_nodes(node_type, filters=None):
        normalized = node_type.replace("_", "").lower()
        return [
            dict(node)
            for node in nodes.values()
            if str(node.get("type", "")).replace("_", "").lower() == normalized
            and all(node.get(key) == value for key, value in (filters or {}).items())
        ]

    def upsert_node(_node_type, attributes, dedupe_key=None):
        nodes[dedupe_key].update(attributes)
        return dedupe_key

    model = FakeModel()
    with patch.multiple(
        graph_tools,
        get_node=get_node,
        search_nodes=search_nodes,
        upsert_node=upsert_node,
        get_query_evaluation_subgraph=lambda query_id: {
            "query": get_node(query_id),
            "nodes": [],
            "edges": [],
            "children": [],
        },
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
        result = MemoryManager(model=model).assess_convergence("goal")
        nodes["goal"].update({
            "research_state": research_state.RESEARCHING,
            "portfolio_revision": 2,
            "evaluated_portfolio_revision": 2,
        })
        current_model = FakeModel()
        current_model.payloads = []
        current_result = MemoryManager(model=current_model).assess_convergence("goal")

    assert result["research_state"] == research_state.LIMITED_REPORT_READY, result
    assert result["portfolio_current"] is True, result
    assert nodes["goal"]["evaluated_portfolio_revision"] == 2, nodes["goal"]
    # Stale convergence triggers exactly ONE LLM call (portfolio, which now
    # also classifies fatal conflicts); a current convergence triggers none.
    assert model.calls == 1
    assert current_result["research_state"] == research_state.LIMITED_REPORT_READY
    assert current_model.calls == 0


if __name__ == "__main__":
    test_stale_portfolio_is_evaluated_before_convergence()
    print("ALL CONVERGENCE LIVELOCK CHECKS PASSED")
