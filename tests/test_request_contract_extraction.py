"""User Request 显式契约抽取（B3.2）：精确数据点与规定结构。

直接运行：``.venv\\Scripts\\python.exe tests/test_request_contract_extraction.py``。
"""

import sys
from pathlib import Path
from unittest.mock import patch

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from agents.memory_manager import (  # noqa: E402
    MemoryManager,
    _required_data_points,
    _required_structure,
)
from tools import graph_tools, research_state  # noqa: E402


def test_required_data_points_sanitizer():
    raw = [
        "2023 年土地出让收入 5.8 万亿元",
        "  ",
        None,
        "2023 年土地出让收入 5.8 万亿元",
        42,
        "地方政府性基金预算收入",
    ]
    points = _required_data_points(raw)
    assert points == [
        "2023 年土地出让收入 5.8 万亿元",
        "42",
        "地方政府性基金预算收入",
    ], points
    assert _required_data_points("not-a-list") == []
    long_points = [f"数据点 {i} " + "x" * 500 for i in range(80)]
    capped = _required_data_points(long_points)
    assert len(capped) == 60 and len(capped[0]) <= 400, (len(capped), len(capped[0]))


def test_required_structure_sanitizer():
    raw = [
        {"type": "section", "heading": " 第一部分 土地财政概况 "},
        {"type": "table", "heading": "省级财政收入表", "columns": ["省份", "收入", "占比"]},
        {"type": "table", "heading": ""},
        {"type": "chapter", "heading": "非法类型应丢弃"},
        "garbage",
        {"type": "table", "heading": "省级财政收入表", "columns": ["省份", "收入", "占比"]},
        {"type": "section", "heading": "结论", "note": "保留用户附言"},
    ]
    items = _required_structure(raw)
    assert items == [
        {"type": "section", "heading": "第一部分 土地财政概况"},
        {"type": "table", "heading": "省级财政收入表", "columns": ["省份", "收入", "占比"]},
        {"type": "section", "heading": "结论", "note": "保留用户附言"},
    ], items
    assert _required_structure(None) == []


def _init_fakes(parsed):
    request = "请按规定结构写报告，并覆盖 2023 年土地出让收入 5.8 万亿元。"
    nodes = {}
    captured = {}
    seq = {"n": 0}

    def create_user_request(**attributes):
        captured.update(attributes)
        nodes["goal"] = {"id": "goal", "type": "UserRequest", **attributes}
        return "goal"

    def create_analysis(text, query_id=None, **attributes):
        seq["n"] += 1
        node_id = f"analysis-{seq['n']}"
        nodes[node_id] = {"id": node_id, "type": "Analysis", "text": text, **attributes}
        return node_id

    def create_query_child(parent_id, text, **attributes):
        seq["n"] += 1
        node_id = f"query-{seq['n']}"
        nodes[node_id] = {"id": node_id, "type": "Query", "handle": "q1", "text": text, **attributes}
        return node_id

    manager = MemoryManager(model=object(), user_request=request)
    manager._plan_initial_queries = lambda *_args, **_kwargs: parsed
    return manager, nodes, captured, create_user_request, create_analysis, create_query_child


def test_init_persists_contract_and_creates_must_objective():
    parsed = {
        "research_goal": "土地财政研究",
        "language": "zh",
        "scope_mode": "bounded",
        "required_data_points": ["2023 年土地出让收入 5.8 万亿元"],
        "required_structure": [
            {"type": "section", "heading": "第一部分 土地财政概况"},
            {"type": "table", "heading": "省级财政收入表", "columns": ["省份", "收入"]},
        ],
        "objectives": [{
            "objective_key": "overview",
            "description": "梳理土地财政概况",
            "requirement": "must",
            "weight": 1.0,
            "acceptance_criteria": ["梳理概况"],
        }],
        "initial_queries": [{
            "text": "土地财政 2023 政府性基金 收入",
            "objective_keys": ["overview"],
            "acceptance_criteria": [],
        }],
    }
    manager, nodes, captured, create_user_request, create_analysis, create_query_child = _init_fakes(parsed)
    with (
        patch.multiple(
            graph_tools,
            search_nodes=lambda _kind, _filters=None: [],
            create_user_request=create_user_request,
            create_analysis=create_analysis,
            create_query_child=create_query_child,
            get_node=lambda node_id: dict(nodes.get(node_id, {})),
            add_edge=lambda *_args, **_kwargs: {},
        ),
        patch.object(research_state, "update_goal", lambda attributes, goal_id=None: nodes[goal_id].update(attributes)),
    ):
        result = manager.init_research()

    assert result["goal_id"] == "goal", result
    assert captured["required_data_points"] == ["2023 年土地出让收入 5.8 万亿元"], captured
    assert captured["required_structure"] == [
        {"type": "section", "heading": "第一部分 土地财政概况"},
        {"type": "table", "heading": "省级财政收入表", "columns": ["省份", "收入"]},
    ], captured

    objectives = [
        node for node in nodes.values()
        if node.get("type") == "Analysis" and node.get("analysis_type") == "objective"
    ]
    data_objective = next(
        node for node in objectives if node.get("objective_key") == "required-data-points"
    )
    assert data_objective["requirement"] == "must", data_objective
    assert data_objective["acceptance_criteria"] == [
        "2023 年土地出让收入 5.8 万亿元"
    ], data_objective


def test_init_without_contract_creates_no_synthetic_objective():
    parsed = {
        "research_goal": "普通分析",
        "language": "zh",
        "scope_mode": "bounded",
        "required_data_points": [],
        "required_structure": [],
        "objectives": [{
            "objective_key": "topic",
            "description": "回答主题问题",
            "requirement": "must",
            "weight": 1.0,
            "acceptance_criteria": [],
        }],
        "initial_queries": [{"text": "主题 权威资料", "objective_keys": ["topic"], "acceptance_criteria": []}],
    }
    manager, nodes, captured, create_user_request, create_analysis, create_query_child = _init_fakes(parsed)
    with (
        patch.multiple(
            graph_tools,
            search_nodes=lambda _kind, _filters=None: [],
            create_user_request=create_user_request,
            create_analysis=create_analysis,
            create_query_child=create_query_child,
            get_node=lambda node_id: dict(nodes.get(node_id, {})),
            add_edge=lambda *_args, **_kwargs: {},
        ),
        patch.object(research_state, "update_goal", lambda attributes, goal_id=None: nodes[goal_id].update(attributes)),
    ):
        manager.init_research()

    assert captured["required_data_points"] == []
    assert captured["required_structure"] == []
    objective_keys = [
        node.get("objective_key")
        for node in nodes.values()
        if node.get("type") == "Analysis" and node.get("analysis_type") == "objective"
    ]
    assert objective_keys == ["topic"], objective_keys


def main():
    test_required_data_points_sanitizer()
    test_required_structure_sanitizer()
    test_init_persists_contract_and_creates_must_objective()
    test_init_without_contract_creates_no_synthetic_objective()
    print("ALL REQUEST CONTRACT EXTRACTION CHECKS PASSED")


if __name__ == "__main__":
    main()
