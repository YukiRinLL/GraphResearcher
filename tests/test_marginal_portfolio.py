"""Standalone checks for marginal-utility portfolio helpers."""

import json
import sys
from pathlib import Path

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from agents.memory_manager import MemoryManager, _initial_query_limit  # noqa: E402
from tools import graph_tools, report_tools  # noqa: E402


class FakeModel:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        payload = self.payloads.pop(0)

        class Response:
            content = json.dumps(payload, ensure_ascii=False)

        return Response()


def test_exploratory_initial_query_selection():
    candidates = [
        {"text": "first exploratory query", "objective_keys": ["a"]},
        {"text": "only a", "objective_keys": ["a"]},
        {"text": "only b", "objective_keys": ["b"]},
        {"text": "only c", "objective_keys": ["c"]},
    ]
    selected = MemoryManager._select_initial_queries(candidates, limit=1)
    assert [item["text"] for item in selected] == ["first exploratory query"], selected
    budgeted = MemoryManager._select_initial_queries(
        candidates,
        limit=3,
        excluded_domains=["en.wikipedia.org"],
    )
    assert len(budgeted) == 3, budgeted
    assert all(item["text"].endswith("-site:en.wikipedia.org") for item in budgeted)
    assert {key for item in budgeted for key in item["objective_keys"]} == {"a", "b"}
    assert all("importance" not in item for item in budgeted)
    invalid = MemoryManager._select_initial_queries(
        [{"text": "请调研上述公司的报告"}, {"text": "Write a Wikipedia-style article about X"}],
        limit=8,
    )
    assert invalid == [], invalid


def test_initial_query_budget_limit():
    assert _initial_query_limit(1) == 1
    assert _initial_query_limit(4) == 2
    assert _initial_query_limit(12) == 6
    assert _initial_query_limit(20) == 8
    assert _initial_query_limit(0) == 8

    model = FakeModel([{"initial_queries": []}])
    MemoryManager(model=model)._plan_initial_queries("研究对象", initial_query_limit=6)
    assert "最多允许生成 6 条初始 Query" in model.prompts[0]
    assert "研究对象" in model.prompts[0]
    assert "所有禁止 URL 必须完整保留" in model.prompts[0]
    assert "用户明确列出的多个独立对象" in model.prompts[0]
    assert "呈现要求保留在原始 User Request 中" in model.prompts[0]
    assert "事实维度、比较关系、数据范围和评价问题" in model.prompts[0]
    assert "Query 中的 `-site:` 域名集合必须与 `excluded_domains` 完全一致" in model.prompts[0]
    assert "所有自然语言字段是否使用 `language` 指定的报告语言" in model.prompts[0]
    assert "不要提及导言、章节、标题、表格布局" in model.prompts[0]
    assert "request_complexity" not in model.prompts[0]
    assert "importance" not in model.prompts[0]


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
        "acceptance_criteria": [],
        "objective_keys": [],
    }], queries
    assert all("importance" not in prompt for prompt in mm.model.prompts)
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
    test_initial_query_budget_limit()
    test_time_window_filter()
    test_followup_query_validation_and_constraints()
    test_report_validation()
    print("ALL MARGINAL PORTFOLIO CHECKS PASSED")


if __name__ == "__main__":
    main()
