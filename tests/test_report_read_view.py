"""离线验证 Reporter 的共享读取、投影兼容性及预算停止。"""

from __future__ import annotations

import json
import sys
from collections import Counter
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from agents import reporter_global_workflow as workflow  # noqa: E402
from agents.memory_manager import MemoryManager  # noqa: E402
from tools import graph_manager_tools, graph_tools, report_tools  # noqa: E402


def fixture_graph():
    """覆盖成功和空搜索、子 Query、来源去重及多种证据绑定路径。"""
    nodes = [
        {
            "id": "goal",
            "type": "UserRequest",
            "request": "Write a cited report.",
            "language": "en",
        },
        {
            "id": "query_aaaa",
            "type": "Query",
            "handle": "q1",
            "text": "Research topic",
            "successful_search_runs": 1,
        },
        {
            "id": "child_bbbb",
            "type": "Query",
            "handle": "q1.1",
            "text": "Child topic",
            "status": "blocked",
        },
        {"id": "r1", "type": "SearchRun", "status": "succeeded"},
        {"id": "r2", "type": "SearchRun", "status": "empty"},
        {
            "id": "s1",
            "type": "Source",
            "url": "https://example.com/a",
            "title": "Source A",
        },
        {
            "id": "s2",
            "type": "Source",
            "url": "https://example.com/b",
            "title": "Source B",
        },
        {
            "id": "s3",
            "type": "Source",
            "url": "https://example.com/a",
            "title": "Duplicate A",
        },
        {"id": "ghost", "type": "Source", "url": "https://example.com/ghost"},
        {
            "id": "d1",
            "type": "Document",
            "source_id": "s1",
            "snapshot_id": "snapshot",
            "chunker_version": "v1",
            "capture_id": "capture",
        },
        {"id": "t1", "type": "Statement", "text": "Source statement"},
        {
            "id": "c1",
            "type": "Claim",
            "statement": "Canonical finding",
            "confidence": 0.9,
        },
        {
            "id": "e1",
            "type": "Evidence",
            "text": "Direct finding",
            "document_id": "d1",
            "source_id": "s1",
            "block_refs": ["b1"],
            "location_status": "valid",
            "qualifiers": ["qualified"],
        },
        {"id": "e2", "type": "Evidence", "text": "Second finding"},
        {"id": "e3", "type": "Evidence", "text": "Duplicate-source finding"},
        {"id": "not_owned", "type": "Evidence", "text": "Empty run finding"},
        {
            "id": "x1",
            "type": "Conflict",
            "description": "Disclosed disagreement",
            "resolution_status": "disclosed",
        },
        {"id": "gap", "type": "Analysis", "analysis_type": "gap"},
        {
            "id": "objective",
            "type": "Analysis",
            "analysis_type": "objective",
            "objective_key": "topic",
            "requirement": "must",
            "weight": 1,
        },
    ]
    edges = [
        {"source": a, "target": b, "type": t}
        for a, b, t in [
            ("goal", "query_aaaa", "HAS_QUERY"),
            ("query_aaaa", "child_bbbb", "PARENT_OF"),
            ("query_aaaa", "r1", "SEARCHED_BY"),
            ("query_aaaa", "r2", "SEARCHED_BY"),
            ("r1", "s1", "FOUND_SOURCE"),
            ("s1", "d1", "HAS_DOCUMENT"),
            ("d1", "t1", "EXTRACTED_STATEMENT"),
            ("t1", "c1", "NORMALIZED_TO"),
            ("d1", "e1", "HAS_EVIDENCE"),
            ("s1", "e1", "SUPPORTED_BY"),
            ("s2", "e2", "SUPPORTED_BY"),
            ("s3", "e3", "SUPPORTED_BY"),
            ("e1", "c1", "SUPPORTED_BY"),
            ("e2", "c1", "CONTRADICTED_BY"),
            ("x1", "e2", "HAS_CONFLICT"),
            ("child_bbbb", "gap", "ADDRESSES_GAP"),
            ("r2", "not_owned", "PRODUCED"),
        ]
    ]
    edges.extend(
        {"source": "r1", "target": n, "type": "PRODUCED"}
        for n in ["d1", "t1", "e1", "e2", "e3"]
    )
    return nodes, edges


@contextmanager
def fake_graph(nodes, edges, context="report-test"):
    """替换存储边界，统计真实报告代码发起的读取。"""
    by_id = {n["id"]: n for n in nodes}
    counts = Counter()

    def counted(name, func):
        def call(*args, **kwargs):
            counts[name] += 1
            return func(*args, **kwargs)

        return call

    def node_edges(node_id, direction="both"):
        return [
            e
            for e in edges
            if (direction in {"in", "both"} and e["target"] == node_id)
            or (direction in {"out", "both"} and e["source"] == node_id)
        ]

    def search(kind, filters):
        normalized = str(getattr(kind, "value", kind)).replace("_", "").lower()
        return [
            n
            for n in nodes
            if n["type"].replace("_", "").lower() == normalized
            and all(n.get(k) == v for k, v in filters.items())
        ]

    with ExitStack() as stack:
        stack.enter_context(patch.object(graph_tools, "_context", context))
        for name, func in {
            "get_all_nodes": lambda: nodes,
            "get_all_edges": lambda: edges,
            "get_node": lambda node_id: by_id.get(node_id, {}),
            "get_node_edges": node_edges,
            "search_nodes": search,
            "get_query_children": lambda node_id: [
                e["target"]
                for e in node_edges(node_id, "out")
                if e["type"].lower() in {"has_query", "parent_of"}
            ],
        }.items():
            stack.enter_context(patch.object(graph_tools, name, counted(name, func)))
        yield counts


def capture_outputs(nodes, edges, read_view=None):
    """收集需要保持兼容的完整投影、草稿、上下文与编译结果。"""
    kwargs = {"read_view": read_view} if read_view is not None else {}
    with fake_graph(nodes, edges), patch.object(report_tools, "_persist_sections"):
        result = {
            "registry": report_tools.build_reference_registry(**kwargs),
            "context": MemoryManager(model=object()).export_report_context(**kwargs),
            "pages": {},
            "draft": report_tools.build_cited_evidence_report(
                "Write a cited report.", **kwargs
            ),
            "compiled": report_tools.compile_global_writer_report(
                None, "# Findings\n\nA supported finding.[1][2]", **kwargs
            ),
        }
        for query in (n for n in nodes if n["type"] == "Query"):
            pages = []
            offset = 0
            while True:
                page = report_tools.get_report_evidence(
                    query["id"], offset=offset, limit=100, **kwargs
                )
                pages.append(page)
                if page["next_offset"] is None:
                    break
                offset = page["next_offset"]
            result["pages"][query["id"]] = pages
        return result


def test_projection_matches_original_fixture():
    nodes, edges = fixture_graph()
    expected = json.loads(
        (ROOT / "tests/fixtures/report_read_view_expected.json").read_text()
    )
    with fake_graph(nodes, edges):
        view = report_tools.ReportReadView.load()
        actual = capture_outputs(nodes, edges, view)
    assert actual == expected


def test_shared_reads_and_returned_values_are_isolated():
    nodes, edges = fixture_graph()
    with fake_graph(nodes, edges) as counts:
        view = report_tools.ReportReadView.load()
        with patch.object(
            report_tools,
            "_project_report_evidence",
            wraps=report_tools._project_report_evidence,
        ) as projection:
            first = report_tools.get_report_evidence("q1", limit=1, read_view=view)
            first["items"][0]["sources"][0]["title"] = "mutated"
            first["research_notes"].clear()
            page = report_tools.get_report_evidence(
                "q1", offset=1, limit=1, read_view=view
            )
            assert page["research_notes"] == {}
            packet = workflow._build_packet(
                MemoryManager(model=object()).export_report_context(read_view=view),
                read_view=view,
            )
            assert packet["draft_report"]
            assert projection.call_count == 2  # 草稿还需要空的子 Query 投影。
        clean = report_tools.get_report_evidence("q1", read_view=view)
        assert clean["items"][0]["sources"][0]["title"] == "Source A"
        assert clean["research_notes"]
        registry = report_tools.build_reference_registry(read_view=view)
        registry[0]["title"] = "mutated"
        assert (
            report_tools.build_reference_registry(read_view=view)[0]["title"]
            == "Source A"
        )
        nodes[5]["title"] = "live mutation"
        assert view.get_node("s1")["title"] == "Source A"
        assert (
            report_tools.build_reference_registry(read_view=view)[0]["title"]
            == "Source A"
        )
        assert counts == {"get_all_nodes": 1, "get_all_edges": 1}, counts


def test_context_and_query_reference_isolation():
    nodes, edges = fixture_graph()
    with fake_graph(nodes, edges):
        view = report_tools.ReportReadView.load()
        assert (
            report_tools.get_report_evidence("broken_aaaa", read_view=view)["total"]
            == 3
        )
        assert report_tools.get_report_evidence("missing", read_view=view).get("error")
    with fake_graph(nodes, edges, context="another-run"):
        try:
            report_tools.get_report_evidence("q1", read_view=view)
        except ValueError:
            pass
        else:
            raise AssertionError("不同 context 不得共享读取视图")
        fresh = report_tools.ReportReadView.load()
        assert fresh is not view
    nodes.append({"id": "duplicate", "type": "Query", "handle": "q1"})
    with fake_graph(nodes, edges):
        ambiguous = report_tools.ReportReadView.load()
        assert (
            "Ambiguous"
            in report_tools.get_report_evidence("q1", read_view=ambiguous)["error"]
        )


def _budget_packet(pages, *, share=1 / 12, tokens=1000):
    context = {
        "user_request": "request",
        "queries": [{"ref": q} for q in pages],
        "objectives": [],
    }
    calls = []

    def fetch(query, offset=0, **kwargs):
        calls.append((query, offset))
        return deepcopy(pages[query][offset])

    with (
        patch.object(report_tools, "get_report_evidence", side_effect=fetch),
        patch.object(report_tools, "build_cited_evidence_report", return_value=""),
        patch.object(report_tools, "build_reference_registry", return_value=[]),
        patch.object(workflow.config, "GR_GLOBAL_PACKET_TOKENS", tokens),
        patch.object(workflow, "_QUERY_PACKET_SHARE", share),
    ):
        return workflow._build_packet(context), calls


def test_query_budget_stops_before_next_page():
    pages = {
        "q1": {
            0: {"items": [{"id": "large", "text": "x" * 1000}], "next_offset": 100},
            100: {"items": [{"id": "small", "text": "x"}], "next_offset": None},
        },
        "q2": {0: {"items": [{"id": "other", "text": "y"}], "next_offset": None}},
    }
    packet, calls = _budget_packet(pages)
    assert calls == [("q1", 0), ("q2", 0)], calls
    assert [g["query"]["ref"] for g in packet["findings"]] == ["q2"]


def test_global_budget_stops_before_next_query():
    pages = {
        q: {0: {"items": [{"id": q, "text": "x" * 2600}], "next_offset": None}}
        for q in ["q1", "q2", "q3"]
    }
    packet, calls = _budget_packet(pages, share=1)
    assert calls == [("q1", 0), ("q2", 0)], calls
    assert len(packet["findings"]) == 1


def test_duplicates_and_normal_pagination():
    pages = {
        "q1": {
            0: {"items": [{"id": "same", "text": "x"}], "next_offset": 100},
            100: {
                "items": [{"id": "same", "text": "x"}, {"id": "unique", "text": "y"}],
                "next_offset": None,
            },
        },
        "q2": {0: {"items": [{"id": "same", "text": "x"}], "next_offset": None}},
    }
    packet, calls = _budget_packet(pages, share=1)
    assert calls == [("q1", 0), ("q1", 100), ("q2", 0)]
    assert [i["id"] for g in packet["findings"] for i in g["items"]] == [
        "same",
        "unique",
    ]


def test_exact_query_budget_stops_before_next_page():
    pages = {
        "q1": {
            0: {"items": [{"id": "fits", "text": "exact fit"}], "next_offset": 100},
            100: {"items": [], "next_offset": None},
        }
    }
    packet, _ = _budget_packet(pages, share=1)
    size = len(json.dumps(packet["findings"][0]["items"][0], ensure_ascii=False))
    exact, calls = _budget_packet(pages, share=0.25, tokens=size)
    assert calls == [("q1", 0)], calls
    assert exact["findings"] == packet["findings"]


def test_standalone_calls_reload_graph():
    nodes, edges = fixture_graph()
    with fake_graph(nodes, edges) as counts:
        assert report_tools.build_reference_registry()[0]["title"] == "Source A"
        nodes[5]["title"] = "Updated source"
        assert report_tools.build_reference_registry()[0]["title"] == "Updated source"
        assert counts == {"get_all_nodes": 2, "get_all_edges": 2}


def test_workflow_retry_persistence_and_final_delivery():
    # 使用真实组包、编译与落盘；只替换模型和存储写入边界。
    sys.path.insert(0, str(ROOT))
    import main as app_main

    nodes, edges = fixture_graph()
    nodes[0]["research_state"] = "REPORTING"
    accepted = (
        "# Findings\n\n" + "This source supports a qualified finding. " * 3 + "[1][2]"
    )

    class Writer:
        def __init__(self):
            self.calls = 0

        def bind(self, **kwargs):
            return self

        def invoke(self, prompt):
            self.calls += 1
            return SimpleNamespace(
                content="# Findings\n\nInvalid.[999]" if self.calls == 1 else accepted
            )

    writer = Writer()
    manager = MemoryManager(model=object())
    sections = []

    def create_section(title, content, section_type=None):
        section_id = f"section-{len(sections)}"
        sections.append(section_id)
        nodes.append(
            {
                "id": section_id,
                "type": "ReportSection",
                "title": title,
                "content": content,
            }
        )
        return section_id

    def add_edge(source, target, edge_type):
        edges.append({"source": source, "target": target, "type": str(edge_type)})

    with (
        TemporaryDirectory() as output_dir,
        fake_graph(nodes, edges) as counts,
        ExitStack() as stack,
    ):
        stack.enter_context(
            patch.dict(workflow.config._model_cache, {"reporter_global": writer})
        )
        for name, value in {
            "_manager": manager,
            "_cache_dir": output_dir,
            "_user_request": nodes[0]["request"],
            "_compiled_report": "",
            "_salvaged_report": "",
            "_best_report": "",
            "_last_report_attempt": {},
            "_report_submit_count": 0,
            "_report_model_call_count": 0,
        }.items():
            stack.enter_context(patch.object(graph_manager_tools, name, value))
        stack.enter_context(
            patch.object(
                graph_tools, "create_report_section", side_effect=create_section
            )
        )
        stack.enter_context(patch.object(graph_tools, "add_edge", side_effect=add_edge))
        registry = stack.enter_context(
            patch.object(
                report_tools,
                "_project_reference_registry",
                wraps=report_tools._project_reference_registry,
            )
        )
        result = workflow.run_global_report_workflow()
        assert result["success"] and result["validated"]
        assert writer.calls == 2
        assert registry.call_count == 1
        assert counts["get_all_nodes"] == counts["get_all_edges"] == 1, counts
        # 默认提纲校验保留一次 Query resolver 读取，不属于证据分页。
        assert counts["get_node"] == 1, counts
        assert sections and any(
            e["source"] == sections[0] and e["type"] == "USES" for e in edges
        )
        report = graph_manager_tools.get_compiled_report()
        assert Path(output_dir, ".compiled_report.md").read_text() == report
        assert "[999]" not in report
        delivered, issues, mode = app_main._prepare_report_for_delivery(
            "",
            nodes[0]["request"],
            {},
            compiled_text=report,
            attempt_summary=graph_manager_tools.get_last_report_attempt(),
        )
        assert delivered == report
        assert mode == "compiled_reporter_validated"
        assert not issues, issues


if __name__ == "__main__":
    failures = []
    for name, test in list(globals().items()):
        if name.startswith("test_") and callable(test):
            try:
                test()
                print(f"{name}: PASS")  # noqa: T201
            except (AssertionError, AttributeError, TypeError) as exc:
                failures.append(name)
                print(f"{name}: FAIL: {exc}")  # noqa: T201
    assert not failures, failures
