"""Standalone checks for the v4 Reporter alias and fail-open delivery contract."""

import json
import re
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

repo_dir = Path(__file__).parent.parent
sys.path.insert(0, str(repo_dir / "src"))

from agents.memory_manager import MemoryManager  # noqa: E402
from tools import graph_tools, report_tools  # noqa: E402

GRAPH_ID_RE = re.compile(r"\b\d{20}_[0-9a-f]{8}\b")


def main():
    q1 = "20260721120000000001_a1b2c3d4"
    q2 = "20260721120000000002_b2c3d4e5"
    e1 = "20260721120000000003_c3d4e5f6"
    e2 = "20260721120000000004_d4e5f6a7"
    goal_id = "20260721120000000005_e5f6a7b8"
    nodes = {
        goal_id: {
            "id": goal_id,
            "type": "UserRequest",
            "request": "请撰写机器人公司的 Wikipedia 条目。",
            "research_state": "REPORT_READY",
        },
        q1: {
            "id": q1,
            "type": "Query",
            "handle": "q1",
            "text": "产品",
            "importance": "core",
            "successful_search_runs": 1,
            "covered": ["产品与应用"],
        },
        q2: {
            "id": q2,
            "type": "Query",
            "handle": "q2",
            "text": "融资",
            "importance": "core",
            "successful_search_runs": 1,
            "covered": ["融资进展"],
        },
        e1: {"id": e1, "type": "Evidence", "claim": "公司开发仓储机器人。", "confidence": 0.9},
        e2: {"id": e2, "type": "Evidence", "claim": "公司未公开融资金额。", "confidence": 0.8},
        "source-product": {
            "id": "source-product",
            "type": "Source",
            "title": "产品公告",
            "url": "https://example.com/product",
        },
        "source-funding": {
            "id": "source-funding",
            "type": "Source",
            "title": "融资公告",
            "url": "https://example.com/funding",
        },
    }
    edges = [
        {"source": "source-product", "target": e1, "type": "SUPPORTED_BY"},
        {"source": "source-funding", "target": e2, "type": "SUPPORTED_BY"},
    ]
    originals = {
        name: getattr(graph_tools, name)
        for name in (
            "get_all_nodes",
            "get_all_edges",
            "get_query_evaluation_subgraph",
            "resolve_query_reference",
            "search_nodes",
        )
    }

    graph_tools.get_all_nodes = lambda: [dict(node) for node in nodes.values()]
    graph_tools.get_all_edges = lambda: [dict(edge) for edge in edges]
    graph_tools.resolve_query_reference = lambda ref: {
        "q1": q1,
        "q2": q2,
        q1: q1,
        q2: q2,
    }.get(ref)
    graph_tools.search_nodes = lambda kind, _filters=None: [
        dict(node) for node in nodes.values() if node.get("type", "").lower() == kind.lower()
    ]
    graph_tools.get_query_evaluation_subgraph = lambda query_id: {
        "query": dict(nodes[query_id]),
        "nodes": [dict(nodes[e1 if query_id == q1 else e2])],
        "edges": [dict(edge) for edge in edges],
        "children": [],
    }

    try:
        report_context = MemoryManager(model=object()).export_report_context()
        assert not GRAPH_ID_RE.search(json.dumps(report_context, ensure_ascii=False)), report_context
        assert report_context["queries"] == [
            {"ref": "q1", "text": "产品", "supported_topics": ["产品与应用"]},
            {"ref": "q2", "text": "融资", "supported_topics": ["融资进展"]},
        ]
        with TemporaryDirectory() as temp_dir:
            outline = report_tools.commit_report_outline(temp_dir, "机器人公司", [
                {
                    "chapter_id": 1,
                    "title": "导言",
                    "query_refs": ["q1"],
                    "section_type": "lead",
                },
                {
                    "chapter_id": 2,
                    "title": "融资",
                    "query_refs": ["q2"],
                    "section_type": "body",
                },
            ])
            assert outline["status"] == "ok", outline

            prepared = report_tools.prepare_report_chapter_batch(temp_dir, [
                {"chapter_id": 1},
                {"chapter_id": 2},
            ])
            assert prepared["status"] == "ok", prepared
            assert not GRAPH_ID_RE.search(json.dumps(prepared, ensure_ascii=False)), prepared
            bundles = {item["chapter_id"]: item for item in prepared["chapters"]}
            assert bundles[1]["evidence_items"][0]["ref"] == "e1"
            assert bundles[2]["evidence_items"][0]["ref"] == "e1"
            assert all(
                "reference_registry_subset" not in bundle
                and all(
                    item.get("source_numbers") and "sources" not in item
                    for item in bundle["evidence_items"]
                )
                for bundle in bundles.values()
            )
            too_many = report_tools.prepare_report_chapter_batch(
                temp_dir,
                [{"chapter_id": 1}] * 4,
            )
            assert too_many["status"] == "error"

            invalid = report_tools.commit_report_chapter_batch(temp_dir, [{
                "chapter_id": 1,
                "bundle_token": bundles[1]["bundle_token"],
                "title": "导言",
                "section_type": "lead",
                "content": "公司开发仓储机器人。[1]",
                "evidence_refs": ["e2"],
                "disclosed_conflict_refs": [],
            }])
            assert invalid["chapters"][0]["candidate_saved"] is True
            assert invalid["chapters"][0]["validated"] is False
            assert Path(temp_dir, ".report_chapters", "chapter_01.md").exists()

            valid = report_tools.commit_report_chapter_batch(temp_dir, [{
                "chapter_id": 2,
                "bundle_token": bundles[2]["bundle_token"],
                "title": "融资",
                "section_type": "body",
                "content": (
                    "公司未公开融资金额。"
                    f"[{bundles[2]['evidence_items'][0]['source_numbers'][0]}]"
                ),
                "evidence_refs": ["e1"],
                "disclosed_conflict_refs": [],
            }])
            assert valid["chapters"][0]["validated"] is True, valid

            review_context = report_tools.get_committed_review_context(temp_dir)
            assert not GRAPH_ID_RE.search(json.dumps(review_context, ensure_ascii=False)), review_context

            delivered = report_tools.submit_committed_report(temp_dir)
            assert not GRAPH_ID_RE.search(json.dumps(delivered, ensure_ascii=False)), delivered
            assert delivered["delivered"] is True
            assert delivered["validated"] is False
            assert delivered["accepted"] is False
            assert delivered["report"]
            assert delivered["graph_persisted"] is False

            active_resolver = graph_tools.resolve_query_reference

            def ambiguous_resolver(reference):
                raise graph_tools.AmbiguousQueryReference(reference, [q1, q2])

            graph_tools.resolve_query_reference = ambiguous_resolver
            ambiguous = report_tools.commit_report_outline(temp_dir, "歧义", [{
                "chapter_id": 1,
                "title": "歧义",
                "query_refs": ["q1"],
            }])
            graph_tools.resolve_query_reference = active_resolver
            assert ambiguous["status"] == "error"
            assert not GRAPH_ID_RE.search(json.dumps(ambiguous, ensure_ascii=False)), ambiguous

        with TemporaryDirectory() as fallback_dir:
            fallback_outline = report_tools.commit_report_outline(fallback_dir, "机器人公司", [
                {
                    "chapter_id": 1,
                    "title": "导言",
                    "query_refs": ["q1"],
                    "section_type": "lead",
                },
                {
                    "chapter_id": 2,
                    "title": "融资",
                    "query_refs": ["q2"],
                    "section_type": "body",
                },
            ])
            assert fallback_outline["status"] == "ok"
            fallback = report_tools.submit_committed_report(fallback_dir)
            assert fallback["delivered"] and fallback["report"]
            assert not fallback["validated"] and not fallback["graph_persisted"]
            assert Path(fallback_dir, ".report_chapters", "chapter_01.md").exists()
            assert Path(fallback_dir, ".report_chapters", "chapter_02.md").exists()
            assert not GRAPH_ID_RE.search(json.dumps(fallback, ensure_ascii=False)), fallback
    finally:
        for name, original in originals.items():
            setattr(graph_tools, name, original)

    print("ALL V4 CONTRACT CHECKS PASSED")


if __name__ == "__main__":
    main()
