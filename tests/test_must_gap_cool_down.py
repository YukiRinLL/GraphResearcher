"""must objective 恢复 gap 不被组合冷却饿死（B3.1）。

复现 DRB-17：delivery_requirement gap 的 owner 是 UserRequest 本身，
而分支白名单只覆盖 Query owner，goal 被默认 cool_down，导致 must
objective 的恢复 gap 连续多轮 deferred_branch_cool_down，最终
objective 被 blocked、报告 PATH EXHAUSTED。

直接运行：``.venv\\Scripts\\python.exe tests/test_must_gap_cool_down.py``。
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
    """返回组合评估 verdict（objective 打分 + branch_decisions）。"""

    def __init__(self, payload):
        self.payload = payload

    def invoke(self, _prompt):
        class Response:
            content = json.dumps(self.payload, ensure_ascii=False)

        return Response()


def _base_goal():
    return {
        "id": "goal",
        "type": "UserRequest",
        "research_state": research_state.RESEARCHING,
        "scope_mode": "bounded",
        "max_search_rounds": 30,
        "dispatched_search_rounds": 10,
        "successful_search_rounds": 10,
        "portfolio_revision": 1,
        "evaluated_portfolio_revision": 1,
    }


def _objective(node_id, key, requirement="must"):
    return {
        "id": node_id,
        "type": "Analysis",
        "analysis_type": "objective",
        "objective_key": key,
        "requirement": requirement,
        "weight": 1.0,
        "acceptance_criteria": [],
        "coverage": 0.0,
        "confidence": 0.0,
        "status": "open",
        "last_evaluated_successful_rounds": 10,
    }


def _gap(node_id, key, owner_id, subject=None, category="missing_core_evidence"):
    return {
        "id": node_id,
        "type": "Analysis",
        "analysis_type": "gap",
        "text": f"Missing evidence for {key}",
        "status": "candidate",
        "gap_category": category,
        "objective_keys": [key],
        "search_subject_key": subject or f"objective-{key}",
        "gap_key": f"gap-{key}-{node_id}",
        "decision_impact": 1.0,
        "confidence_gain": 1.0,
        "estimated_search_rounds": 1,
        "expansion_mode": "horizontal",
        "expansion_parent_id": owner_id,
        "trigger_type": "delivery_requirement",
    }


def _run_portfolio(nodes, verdict, gap_owner_pairs):
    """用内存假图执行一次 evaluate_research_portfolio。"""

    def get_node(node_id):
        node = nodes.get(node_id)
        return dict(node) if node else {}

    def search_nodes(node_type, filters=None):
        normalized = node_type.replace("_", "").lower()
        return [
            dict(node)
            for node in nodes.values()
            if str(node.get("type", "")).replace("_", "").lower() == normalized
            and all(node.get(key) == value for key, value in (filters or {}).items())
        ]

    def upsert_node(_node_type, attributes, dedupe_key=None):
        nodes.setdefault(dedupe_key, {}).update(attributes)
        return dedupe_key

    owner_of = dict(gap_owner_pairs)

    def get_node_edges(node_id, direction="both"):
        owner_id = owner_of.get(node_id)
        if owner_id is not None:
            return [{"source": owner_id, "target": node_id, "type": "HAS_GAP"}]
        return []

    def get_query_parent(query_id):
        node = nodes.get(query_id, {})
        return node.get("_parent")

    with patch.multiple(
        graph_tools,
        get_node=get_node,
        search_nodes=search_nodes,
        upsert_node=upsert_node,
        get_node_edges=get_node_edges,
        get_query_parent=get_query_parent,
        get_query_children=lambda _query_id: [],
        get_query_evaluation_subgraph=lambda query_id: {
            "query": get_node(query_id),
            "nodes": [],
            "edges": [],
            "children": [],
        },
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
        manager = MemoryManager(model=FakeModel(verdict))
        result = manager.evaluate_research_portfolio("goal")
    return result


def _verdict(key, branch_decisions=None, coverage=0.1, confidence=0.1):
    return {
        "objectives": [{
            "objective_key": key,
            "coverage": coverage,
            "confidence": confidence,
            "supported_boundary": "",
            "unmet_acceptance_criteria": [],
            "reason": "no evidence yet",
        }],
        "branch_decisions": branch_decisions or [],
    }


def test_goal_owned_must_gap_bypasses_default_cool_down():
    """delivery_requirement gap 挂在 UserRequest 下也必须被 selected。"""
    key = "maintenance_cost"
    nodes = {
        "goal": _base_goal(),
        "obj": _objective("obj", key),
        "gap": _gap("gap", key, "goal"),
    }
    result = _run_portfolio(nodes, _verdict(key), [("gap", "goal")])
    assert result["selected_gap_ids"] == ["gap"], result
    assert nodes["gap"]["status"] == "selected", nodes["gap"]
    assert nodes["gap"]["expansion_parent_id"] == "goal", nodes["gap"]
    assert nodes["gap"]["resolution_reason"] is None, nodes["gap"]


def test_cooled_query_owner_must_gap_is_force_expanded():
    """owner 查询本轮被 LLM 冷却时，must gap 仍换角度扩展。"""
    key = "stakeholder_perspectives"
    nodes = {
        "goal": _base_goal(),
        "obj": _objective("obj", key),
        "q1": {
            "id": "q1",
            "type": "Query",
            "handle": "q1",
            "text": "stakeholder views",
            "status": "needs_expansion",
            "objective_keys": [key],
            "_parent": "goal",
        },
        "gap": _gap("gap", key, "q1"),
    }
    verdict = _verdict(key, branch_decisions=[{
        "owner_id": "q1",
        "action": "cool_down",
        "reason": "branch parked this round",
    }])
    result = _run_portfolio(nodes, verdict, [("gap", "q1")])
    assert result["selected_gap_ids"] == ["gap"], result
    assert nodes["gap"]["status"] == "selected", nodes["gap"]
    assert nodes["gap"]["expansion_parent_id"] == "q1", nodes["gap"]
    # 被 force-expand 的 owner 查询不应被收尾为 sufficient
    assert nodes["q1"]["status"] == "needs_expansion", nodes["q1"]


def test_should_only_gap_still_cools_down():
    """纯 should gap 行为不变：冷却 owner 时继续 defer。"""
    key = "nice_to_have"
    nodes = {
        "goal": _base_goal(),
        "obj": _objective("obj", key, requirement="should"),
        "gap": _gap("gap", key, "goal"),
    }
    result = _run_portfolio(nodes, _verdict(key), [("gap", "goal")])
    assert result["selected_gap_ids"] == [], result
    assert nodes["gap"]["status"] == "deferred_branch_cool_down", nodes["gap"]
    assert nodes["gap"]["expansion_parent_id"] is None, nodes["gap"]


def test_force_expand_dedupes_per_must_key():
    """同一 must key 每轮只允许一条 gap 借道 force-expand。"""
    key = "maintenance_cost"
    nodes = {
        "goal": _base_goal(),
        "obj": _objective("obj", key),
        "gap1": _gap("gap1", key, "goal", subject="objective-maintenance_cost"),
        "gap2": _gap("gap2", key, "goal", subject="alternative-angles"),
    }
    verdict = _verdict(key)
    result = _run_portfolio(nodes, verdict, [("gap1", "goal"), ("gap2", "goal")])
    assert result["selected_gap_ids"] == ["gap1"], result
    assert nodes["gap1"]["status"] == "selected", nodes["gap1"]
    assert nodes["gap2"]["status"] == "deferred_branch_cool_down", nodes["gap2"]


def main():
    test_goal_owned_must_gap_bypasses_default_cool_down()
    test_cooled_query_owner_must_gap_is_force_expanded()
    test_should_only_gap_still_cools_down()
    test_force_expand_dedupes_per_must_key()
    print("ALL MUST-GAP COOL-DOWN CHECKS PASSED")


if __name__ == "__main__":
    main()
