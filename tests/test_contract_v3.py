"""Standalone checks for request, criterion, and v4 review contracts."""

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from agents.memory_manager import MemoryManager  # noqa: E402
from tools import (  # noqa: E402
    graph_manager_tools,
    graph_tools,
    report_tools,
    research_state,
)


def test_verbatim_request_initialization():
    request = "请写条目。\n\n必须保留这个完整 rubric：不要使用宣传措辞；使用两个表格。"
    nodes = {}
    captured = {}

    def create_user_request(**attributes):
        captured.update(attributes)
        nodes["goal"] = {"id": "goal", "type": "UserRequest", **attributes}
        return "goal"

    def create_analysis(text, query_id=None, **attributes):
        nodes["objective"] = {
            "id": "objective",
            "type": "Analysis",
            "text": text,
            **attributes,
        }
        return "objective"

    def create_query_child(parent_id, text, **attributes):
        nodes["query"] = {
            "id": "query",
            "type": "Query",
            "handle": "q1",
            "text": text,
            **attributes,
        }
        return "query"

    parsed = {
        "research_goal": "研究一个条目",
        "language": "zh",
        "scope_mode": "bounded",
        "objectives": [{
            "objective_key": "entry",
            "description": "查明条目事实",
            "requirement": "must",
            "weight": 1.0,
            "acceptance_criteria": ["查明条目事实"],
        }],
        "initial_queries": [{
            "text": "条目 权威资料",
            "objective_keys": ["entry"],
            "acceptance_criteria": ["查明条目事实"],
        }],
    }
    manager = MemoryManager(model=object(), user_request=request)
    manager._plan_initial_queries = lambda *_args, **_kwargs: parsed
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
    assert captured["request"] == request
    assert captured["state_contract_version"] == 4
    assert "request_complexity" not in captured
    assert nodes["query"]["importance"] == "core"
    assert nodes["query"]["query_role"] == "discovery"
    assert MemoryManager(model=object()).init_research()["error"]


def test_criterion_validation():
    criterion = "确认融资金额"
    evaluation = {
        "nodes": [
            {"id": "s1", "type": "Source", "url": "https://example.com/a"},
            {"id": "e-miss", "type": "Evidence", "claim": "公告未提及融资金额。"},
            {"id": "e-unknown", "type": "Evidence", "claim": "公司明确表示融资金额未公开。"},
            {"id": "analysis", "type": "Analysis", "text": "模型总结"},
        ],
        "edges": [
            {"source": "s1", "target": "e-miss", "type": "SUPPORTED_BY"},
            {"source": "s1", "target": "e-unknown", "type": "SUPPORTED_BY"},
        ],
    }
    validate = MemoryManager._validate_criterion_results
    missing = validate([criterion], [{
        "criterion": criterion,
        "status": "satisfied",
        "supporting_refs": ["e-miss"],
        "reason": "来源没有提到金额",
    }], evaluation)
    assert missing[0]["status"] == "unmet", missing

    explicit_unknown = validate([criterion], [{
        "criterion": criterion,
        "status": "satisfied",
        "supporting_refs": ["e-unknown"],
        "reason": "来源明确说金额未公开",
    }], evaluation)
    assert explicit_unknown[0]["status"] == "satisfied", explicit_unknown
    assert explicit_unknown[0]["supporting_refs"] == ["e-unknown"]

    invalid = validate([criterion], [{
        "criterion": criterion,
        "status": "satisfied",
        "supporting_refs": ["analysis", "missing"],
        "reason": "间接总结",
    }], evaluation)
    assert invalid[0]["status"] == "unmet" and invalid[0]["supporting_refs"] == []

    queries = [{
        "objective_keys": ["funding"],
        "acceptance_criteria": [criterion],
        "criterion_results": [{"criterion": criterion, "status": "unmet"}],
    }]
    assert not MemoryManager._linked_criteria_complete("funding", queries)
    queries[0]["criterion_results"][0]["status"] = "satisfied"
    assert MemoryManager._linked_criteria_complete("funding", queries)


def test_criterion_assessment_retry_boundary():
    query = {
        "id": "q1",
        "type": "Query",
        "handle": "q1",
        "text": "融资金额",
        "query_role": "discovery",
        "status": "assessing",
        "acceptance_criteria": ["确认融资金额"],
        "objective_keys": [],
    }
    evaluation = {
        "query": query,
        "nodes": [
            {"id": "s1", "type": "Source", "url": "https://example.com/a"},
            {"id": "e1", "type": "Evidence", "claim": "融资金额为一亿元。"},
        ],
        "edges": [{"source": "s1", "target": "e1", "type": "SUPPORTED_BY"}],
    }
    updates = {}
    manager = MemoryManager(model=object())
    manager.normalize_claims = lambda _query_id: {}
    responses = [
        {"sufficiency_score": 0.9, "recommendation": "sufficient", "gaps": []},
        {
            "sufficiency_score": 0.9,
            "recommendation": "sufficient",
            "gaps": [],
            "criteria": [{
                "criterion": "确认融资金额",
                "status": "satisfied",
                "supporting_refs": ["e1"],
                "reason": "来源明确给出金额",
            }],
        },
    ]
    calls = []
    manager._invoke_json = lambda prompt: calls.append(prompt) or responses.pop(0)
    with (
        patch.multiple(
            graph_tools,
            get_node=lambda node_id: dict(query) if node_id == "q1" else {},
            search_nodes=lambda kind, _filters=None: [dict(query)] if kind == "query" else [],
            get_query_evaluation_subgraph=lambda _query_id: evaluation,
            get_query_children=lambda _query_id: [],
            get_query_parent=lambda _query_id: None,
            get_node_edges=lambda _node_id, direction="both": [],
            transition_query=lambda _query_id, status, **attributes: updates.update({
                "status": status,
                **attributes,
            }),
            upsert_node=lambda *_args, **_kwargs: "q1",
        ),
        patch.object(research_state, "get_status", lambda _goal_id=None: {"research_state": research_state.RESEARCHING}),
        patch.object(research_state, "get_goal", lambda _goal_id=None: {"id": "goal", "portfolio_revision": 1}),
    ):
        result = manager.assess_query("q1")
    assert len(calls) == 2
    assert '"query_role": "discovery"' in calls[0]
    assert result["status"] == "sufficient"
    assert updates["criterion_results"][0]["supporting_refs"] == ["e1"]


def test_single_review_and_fail_open():
    original_submit = report_tools.submit_committed_report
    original_review = graph_manager_tools._review_report_once
    clean = {
        "delivered": True,
        "validated": True,
        "accepted": True,
        "revision_requested": False,
        "severity": "clean",
        "report": "# 标题\n\n正文。[1]\n\n## 参考文献\n\n[1] 来源 https://example.com",
        "salvaged_report": "",
        "issues": [],
        "graph_persisted": False,
    }
    try:
        with TemporaryDirectory() as temp_dir:
            graph_manager_tools._cache_dir = temp_dir
            graph_manager_tools._report_review_completed = False
            graph_manager_tools._report_review_had_issues = False
            calls = []
            report_tools.submit_committed_report = lambda _output, persist=False: (
                calls.append(persist) or dict(clean)
            )
            reviews = []
            graph_manager_tools._review_report_once = lambda report: (
                reviews.append(report) or ["导言缺少范围说明"]
            )

            first = graph_manager_tools.submit_final_report()
            assert first["revision_requested"] and first["review_status"] == "issues"
            second = graph_manager_tools.submit_final_report()
            assert second["accepted"] and second["review_status"] == "revised_once"
            assert len(reviews) == 1
            assert calls == [False, False, True], calls

            graph_manager_tools._report_review_completed = False
            graph_manager_tools._report_review_had_issues = False
            graph_manager_tools._review_report_once = lambda _report: (_ for _ in ()).throw(
                TimeoutError("review timed out")
            )
            failed_open = graph_manager_tools.submit_final_report()
            assert failed_open["accepted"] and failed_open["review_status"] == "failed_open"
            artifact = json.loads(Path(temp_dir, ".report_attempt.json").read_text())
            assert artifact["review_status"] == "failed_open"
            assert "timed out" in artifact["review_error"]

            invalid = {
                **clean,
                "delivered": True,
                "validated": False,
                "accepted": False,
                "severity": "hard",
                "graph_persisted": False,
                "issues": [{
                    "code": "unknown_evidence_refs",
                    "severity": "hard",
                    "message": "unknown local evidence ref",
                }],
            }
            graph_manager_tools._report_review_completed = False
            graph_manager_tools._report_review_had_issues = False
            report_tools.submit_committed_report = lambda _output, persist=False: dict(invalid)
            invalid_reviews = []
            graph_manager_tools._review_report_once = lambda report: invalid_reviews.append(report) or []
            first_invalid = graph_manager_tools.submit_final_report()
            second_invalid = graph_manager_tools.submit_final_report()
            assert first_invalid["report"] and first_invalid["revision_requested"]
            assert second_invalid["delivered"] and second_invalid["report"]
            assert not second_invalid["validated"] and not second_invalid["accepted"]
            assert not second_invalid["revision_requested"] and not second_invalid["graph_persisted"]
            assert len(invalid_reviews) == 1
    finally:
        report_tools.submit_committed_report = original_submit
        graph_manager_tools._review_report_once = original_review


def main():
    test_verbatim_request_initialization()
    test_criterion_validation()
    test_criterion_assessment_retry_boundary()
    test_single_review_and_fail_open()
    print("ALL V4 REQUEST/REVIEW CONTRACT CHECKS PASSED")


if __name__ == "__main__":
    main()
