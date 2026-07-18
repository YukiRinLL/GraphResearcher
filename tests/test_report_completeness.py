"""验证 Report Completeness 的 must Objective 加权语义。

直接运行：``uv run python tests/test_report_completeness.py``。
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from agents.memory_manager import MemoryManager  # noqa: E402
from tools import graph_tools, research_state  # noqa: E402


class PortfolioModel:
    """返回一次固定的组合评估结果。"""

    def __init__(self, objectives):
        self.objectives = objectives

    def invoke(self, _prompt):
        payload = {"objectives": self.objectives}

        class Response:
            content = json.dumps(payload)

        return Response()


def _evaluate_completeness(objectives, verdict):
    nodes = {
        "goal": {
            "id": "goal",
            "type": "UserRequest",
            "research_state": research_state.RESEARCHING,
            "portfolio_revision": 1,
            "evaluated_portfolio_revision": 0,
            "successful_search_rounds": 0,
        },
        **{objective["id"]: dict(objective) for objective in objectives},
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

    with (
        patch.multiple(
            graph_tools,
            get_node=get_node,
            search_nodes=search_nodes,
            upsert_node=upsert_node,
            get_node_edges=lambda _node_id, direction="both": [],
        ),
        patch.object(research_state, "get_goal", side_effect=lambda goal_id=None: get_node(goal_id or "goal")),
    ):
        result = MemoryManager(model=PortfolioModel(verdict)).evaluate_research_portfolio("goal")
    return result["report_completeness_score"]


def _objective(objective_id, weight):
    return {
        "id": objective_id,
        "type": "Analysis",
        "analysis_type": "objective",
        "objective_key": objective_id,
        "requirement": "must",
        "weight": weight,
        "coverage": 0.0,
        "confidence": 0.0,
        "status": "open",
        "low_gain_streak": 0,
        "last_evaluated_successful_rounds": 0,
    }


def test_zero_weight_objective_does_not_dilute_weighted_completeness():
    completeness = _evaluate_completeness(
        [_objective("ignored", 0.0), _objective("counted", 1.0)],
        [
            {"objective_key": "ignored", "coverage": 0.0, "confidence": 0.0},
            {"objective_key": "counted", "coverage": 0.8, "confidence": 0.75},
        ],
    )
    assert completeness == 1.0, completeness


def test_all_zero_weight_must_objectives_have_zero_completeness():
    completeness = _evaluate_completeness(
        [_objective("first", 0.0), _objective("second", 0.0)],
        [
            {"objective_key": "first", "coverage": 0.8, "confidence": 0.75},
            {"objective_key": "second", "coverage": 0.0, "confidence": 0.0},
        ],
    )
    assert completeness == 0.0, completeness


if __name__ == "__main__":
    test_zero_weight_objective_does_not_dilute_weighted_completeness()
    test_all_zero_weight_must_objectives_have_zero_completeness()
    print("ALL REPORT COMPLETENESS CHECKS PASSED")
