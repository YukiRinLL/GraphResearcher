"""Standalone checks for marginal-utility portfolio helpers."""

import json
import sys
from pathlib import Path

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from agents.memory_manager import MemoryManager  # noqa: E402
from tools import graph_tools, report_tools  # noqa: E402


class FakeModel:
    def __init__(self, payloads):
        self.payloads = list(payloads)

    def invoke(self, _prompt):
        payload = self.payloads.pop(0)

        class Response:
            content = json.dumps(payload, ensure_ascii=False)

        return Response()


def test_exploratory_initial_query_selection():
    objectives = [
        {"objective_key": "a", "requirement": "must"},
        {"objective_key": "b", "requirement": "must"},
        {"objective_key": "c", "requirement": "must"},
    ]
    candidates = [
        {"text": "first exploratory query", "objective_keys": ["a"]},
        {"text": "only a", "objective_keys": ["a"]},
        {"text": "only b", "objective_keys": ["b"]},
        {"text": "only c", "objective_keys": ["c"]},
    ]
    selected = MemoryManager._select_initial_queries(candidates, objectives)
    assert [item["text"] for item in selected] == ["first exploratory query"], selected
    complex_selected = MemoryManager._select_initial_queries(
        candidates,
        objectives,
        complexity="complex",
        excluded_domains=["en.wikipedia.org"],
    )
    assert len(complex_selected) == 3, complex_selected
    assert all(item["text"].endswith("-site:en.wikipedia.org") for item in complex_selected)
    assert {key for item in complex_selected for key in item["objective_keys"]} == {"a", "b"}
    invalid = MemoryManager._select_initial_queries(
        [{"text": "请调研上述公司的报告"}, {"text": "Write a Wikipedia-style article about X"}],
        objectives,
        complexity="complex",
    )
    assert invalid == [], invalid


def test_time_window_filter():
    graph_tools.get_query_evaluation_subgraph = lambda _query_id: {
        "nodes": [{"id": "s1", "type": "Source", "published_at": "2025-01-01"}],
    }
    assert not MemoryManager._query_evidence_within_time_window("q1", "2018-2024")


def test_followup_query_validation_and_constraints():
    mm = MemoryManager(model=FakeModel([
        {"queries": [{"text": "Write a Wikipedia-style article about Japan"}]},
        {"queries": [{"text": "日本 国家数字战略 1960 2022 政策 年份 核心目标"}]},
    ]))
    queries = mm._plan_followup_queries(
        research_goal="日本数字战略历史",
        parent_text="日本数字战略",
        research_constraints={
            "time_window": "1960-2022",
            "region_scope": "日本",
            "excluded_domains": ["en.wikipedia.org"],
            "excluded_urls": ["https://en.wikipedia.org/wiki/Japan"],
        },
        existing_query_texts=["日本 数字政府 2022"],
        gaps=[{"description": "缺少政策时间线"}],
        reason="vertical evidence gap",
    )
    assert queries == [{
        "text": "日本 国家数字战略 1960 2022 政策 年份 核心目标 -site:en.wikipedia.org",
        "importance": None,
        "acceptance_criteria": [],
        "objective_keys": [],
    }], queries
    assert MemoryManager._query_evidence_within_time_window("q1", None)
    graph_tools.get_query_evaluation_subgraph = lambda _query_id: {
        "nodes": [
            {"id": "s1", "type": "Source", "published_at": "2024-01-01"},
            {"id": "s2", "type": "Source", "published_at": "2025-01-01"},
        ],
    }
    assert not MemoryManager._query_evidence_within_time_window("q1", "2018-2024")


def test_report_validation():
    conflict = {
        "id": "c1",
        "type": "Conflict",
        "resolution_status": "disclosed",
        "description": "Optimus hand parameter differs across sources",
    }
    section = {"id": "r1", "type": "ReportSection", "title": "Findings", "content": "fact " * 30}
    graph_tools.search_nodes = lambda kind, _filter: {
        "conflict": [conflict],
        "report_section": [section],
    }.get(kind, [])
    graph_tools.get_node_edges = lambda _node_id, direction="out": []
    issues = report_tools.validate_final_report("Research Graph internal draft")
    assert any("internal process term" in issue for issue in issues), issues
    assert any("no evidence/source binding" in issue for issue in issues), issues

    graph_tools.get_node_edges = lambda _node_id, direction="out": [
        {"source": "r1", "target": "s1", "type": "USES"},
    ]
    clean = report_tools.validate_final_report(
        "Optimus hand parameter differs across sources. This difference remains unresolved."
    )
    assert not clean, clean


def main():
    test_exploratory_initial_query_selection()
    test_time_window_filter()
    test_followup_query_validation_and_constraints()
    test_report_validation()
    print("ALL MARGINAL PORTFOLIO CHECKS PASSED")


if __name__ == "__main__":
    main()
