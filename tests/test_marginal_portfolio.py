"""Standalone checks for marginal-utility portfolio helpers."""

import sys
from pathlib import Path

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from agents.memory_manager import MemoryManager  # noqa: E402
from tools import graph_tools, report_tools  # noqa: E402


def test_minimum_initial_query_cover():
    objectives = [
        {"objective_key": "a", "requirement": "must"},
        {"objective_key": "b", "requirement": "must"},
        {"objective_key": "c", "requirement": "must"},
    ]
    candidates = [
        {"text": "one broad query", "objective_keys": ["a", "b", "c"]},
        {"text": "only a", "objective_keys": ["a"]},
        {"text": "only b", "objective_keys": ["b"]},
        {"text": "only c", "objective_keys": ["c"]},
    ]
    selected = MemoryManager._select_initial_queries(candidates, objectives)
    assert [item["text"] for item in selected] == ["one broad query"], selected


def test_time_window_filter():
    graph_tools.get_query_evaluation_subgraph = lambda _query_id: {
        "nodes": [{"id": "s1", "type": "Source", "published_at": "2025-01-01"}],
    }
    assert not MemoryManager._query_evidence_within_time_window("q1", "2018-2024")
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
    test_minimum_initial_query_cover()
    test_time_window_filter()
    test_report_validation()
    print("ALL MARGINAL PORTFOLIO CHECKS PASSED")


if __name__ == "__main__":
    main()
