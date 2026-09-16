"""Standalone regression checks for the v4 candidate-report contract."""

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

repo_dir = Path(__file__).parent.parent
sys.path.insert(0, str(repo_dir))
sys.path.insert(0, str(repo_dir / "src"))

import main as app_main  # noqa: E402
from agents.memory_manager import MemoryManager  # noqa: E402
from tools import graph_manager_tools, graph_tools, report_tools  # noqa: E402


def main():
    query_id = "20260721093000123456_a1b2c3d4"
    request = "请按 Wikipedia 风格撰写机器人公司条目，并在每个事实段落就地引用。"
    nodes = {
        "goal": {
            "id": "goal",
            "type": "UserRequest",
            "request": request,
            "language": "简体中文",
            "research_state": "REPORTING",
            "reporting_from_state": "REPORT_READY",
        },
        query_id: {
            "id": query_id,
            "type": "Query",
            "handle": "q1",
            "text": "机器人公司的产品与融资",
            "status": "sufficient",
            "importance": "core",
            "successful_search_runs": 1,
            "covered": ["仓储机器人", "融资进展", "仓储机器人", ""],
        },
        "empty-query": {
            "id": "empty-query",
            "type": "Query",
            "handle": "q2",
            "text": "没有证据的查询",
            "status": "blocked",
            "importance": "supporting",
            "successful_search_runs": 0,
            "covered": [],
        },
        "s1": {
            "id": "s1",
            "type": "Source",
            "title": "产品公告",
            "url": "https://example.com/product",
        },
        "s2": {
            "id": "s2",
            "type": "Source",
            "title": "融资公告",
            "url": "https://example.com/funding",
        },
        "e1": {
            "id": "e1",
            "type": "Evidence",
            "claim": "该公司开发仓储机器人。",
            "confidence": 0.91,
            "qualifiers": ["面向仓储场景"],
            "limitations": ["公告未披露部署数量"],
            "locator": "第 2 段",
        },
        "e2": {
            "id": "e2",
            "type": "Evidence",
            "claim": "该公司未公开具体融资金额。",
            "confidence": 0.84,
            "qualifiers": [],
            "limitations": ["仅确认金额未公开"],
            "locator": "FAQ",
        },
        "c1": {
            "id": "c1",
            "type": "Claim",
            "statement": "该公司开发面向仓储的机器人。",
            "confidence": 0.88,
            "qualifiers": ["仓储"],
            "limitations": [],
        },
    }
    edges = [
        {"source": "goal", "target": query_id, "type": "HAS_QUERY"},
        {"source": "goal", "target": "empty-query", "type": "HAS_QUERY"},
        {"source": "s1", "target": "e1", "type": "SUPPORTED_BY"},
        {"source": "s2", "target": "e2", "type": "SUPPORTED_BY"},
        {"source": "e1", "target": "c1", "type": "SUPPORTED_BY"},
    ]
    created_sections = []
    created_edges = []

    names = (
        "get_all_nodes",
        "get_all_edges",
        "get_node",
        "search_nodes",
        "get_query_evaluation_subgraph",
        "create_report_section",
        "add_edge",
        "clear_current_context",
        "set_context",
        "bind_evidence_to_section",
    )
    originals = {name: getattr(graph_tools, name) for name in names}
    original_review = graph_manager_tools._review_report_once

    def search_nodes(kind, filters=None):
        wanted = kind.replace("_", "").lower()
        return [
            dict(node)
            for node in nodes.values()
            if str(node.get("type", "")).replace("_", "").lower() == wanted
            and all(node.get(key) == value for key, value in (filters or {}).items())
        ]

    graph_tools.get_all_nodes = lambda: [dict(node) for node in nodes.values()]
    graph_tools.get_all_edges = lambda: [dict(edge) for edge in edges + created_edges]
    graph_tools.get_node = lambda node_id: dict(nodes[node_id]) if node_id in nodes else {}
    graph_tools.search_nodes = search_nodes
    graph_tools.get_query_evaluation_subgraph = lambda resolved: {
        "query": dict(nodes[resolved]),
        "nodes": [
            dict(nodes[item_id])
            for item_id in (() if resolved == "empty-query" else ("e1", "e2", "c1"))
        ],
        "edges": [dict(edge) for edge in edges],
        "children": [],
    }
    graph_tools.create_report_section = lambda title, content, section_type=None: (
        created_sections.append({
            "title": title,
            "content": content,
            "section_type": section_type,
        })
        or f"section-{len(created_sections)}"
    )
    graph_tools.add_edge = lambda source, target, edge_type, attributes=None: (
        created_edges.append({
            "source": source,
            "target": target,
            "type": edge_type.value if hasattr(edge_type, "value") else str(edge_type),
        })
        or created_edges[-1]
    )
    graph_tools.clear_current_context = lambda: None
    graph_tools.set_context = lambda context: None
    graph_tools.bind_evidence_to_section = lambda *_args, **_kwargs: None

    try:
        context = MemoryManager(model=object(), user_request=request).export_report_context()
        assert context["user_request"] == request
        assert context["language"] == "简体中文"
        assert set(context) == {
            "user_request",
            "research_goal",
            "language",
            "objectives",
            "queries",
            "disclosed_conflicts",
        }
        assert context["queries"] == [
            {
                "ref": "q1",
                "text": "机器人公司的产品与融资",
                "supported_topics": ["仓储机器人", "融资进展"],
                "objective_keys": [],
                "target_components": [],
                "target_sections": [],
                "analysis_mode": "none",
                "required_evidence_types": [],
            }
        ]
        assert "status" not in context["queries"][0]
        assert not any(
            key in str(context)
            for key in ("importance", "unmet_objectives", "budget")
        )

        evidence = report_tools.get_report_evidence("q1", limit=10)
        assert evidence["query"]["id"] == query_id
        by_id = {item["id"]: item for item in evidence["items"]}
        assert by_id["e1"]["confidence"] == 0.91
        assert by_id["e1"]["qualifiers"] == ["面向仓储场景"]
        assert by_id["e1"]["limitations"] == ["公告未披露部署数量"]
        assert by_id["e1"]["locator"] == "第 2 段"
        assert by_id["e1"]["claim_relations"] == [{"claim_id": "c1", "stance": "supports"}]
        assert by_id["c1"]["evidence_relations"] == [{"evidence_id": "e1", "stance": "supports"}]

        assert callable(graph_manager_tools.commit_report_chapter_batch)
        assert not hasattr(graph_manager_tools.commit_report_chapter_batch, "invoke")
        assert callable(graph_manager_tools.submit_final_report)
        assert hasattr(graph_manager_tools.run_analysis_pass, "invoke")

        with TemporaryDirectory() as temp_dir:
            graph_manager_tools.configure(temp_dir, user_request=request)
            outline = graph_manager_tools.commit_report_outline(
                title="机器人公司",
                chapters=[
                    {
                        "chapter_id": 1,
                        "title": "导言",
                        "goals": ["概述公司产品"],
                        "query_refs": ["q1"],
                        "section_plan": "概述产品定位",
                        "section_type": "lead",
                    },
                    {
                        "chapter_id": 2,
                        "title": "融资",
                        "goals": ["说明公开融资信息"],
                        "query_refs": ["q1"],
                        "section_plan": "说明披露边界",
                        "section_type": "body",
                    },
                ],
            )
            assert outline["status"] == "ok"
            stored_outline = json.loads(Path(temp_dir, ".report_outline.json").read_text(encoding="utf-8"))
            assert stored_outline["chapters"][0]["query_refs"] == ["q1"]

            prepared = graph_manager_tools.prepare_report_chapter_batch(
                chapters=[{"chapter_id": 1}, {"chapter_id": 2}],
            )
            assert prepared["status"] == "ok", prepared
            lead_bundle, body_bundle = prepared["chapters"]
            assert lead_bundle["query_refs"] == ["q1"]
            assert lead_bundle["section_type"] == "lead"
            assert body_bundle["section_type"] == "body"
            assert {item["ref"] for item in lead_bundle["evidence_items"]} == {"e1", "e2", "c1"}
            assert "reference_registry_subset" not in lead_bundle
            assert all(
                item.get("source_numbers") and "sources" not in item
                for item in lead_bundle["evidence_items"]
            )

            rejected = graph_manager_tools.commit_report_chapter_batch(
                chapters=[{
                    "chapter_id": 1,
                    "bundle_token": lead_bundle["bundle_token"],
                    "title": "导言",
                    "content": "无效选择。[1]",
                    "evidence_refs": ["missing"],
                    "section_type": "lead",
                }],
            )
            assert rejected["chapters"][0]["candidate_saved"]
            assert not rejected["chapters"][0]["validated"]

            committed = graph_manager_tools.commit_report_chapter_batch(
                chapters=[
                    {
                        "chapter_id": 1,
                        "bundle_token": lead_bundle["bundle_token"],
                        "title": "导言",
                        "content": "该公司开发仓储机器人。[1]",
                        "evidence_refs": ["e1"],
                        "section_type": "lead",
                    },
                    {
                        "chapter_id": 2,
                        "bundle_token": body_bundle["bundle_token"],
                        "title": "融资",
                        "content": "该公司未公开具体融资金额。[2]",
                        "evidence_refs": ["e2"],
                        "section_type": "body",
                    },
                ],
            )
            assert committed["validated"], committed
            assert "analysis_refs" in committed["chapters"][0]
            lead_meta = json.loads(Path(temp_dir, ".report_chapters", "chapter_01.meta.json").read_text(encoding="utf-8"))
            assert lead_meta["source_ids"] == ["s1"]

            reviews = []
            graph_manager_tools._review_report_once = lambda report: reviews.append(report) or []
            final = graph_manager_tools.submit_final_report()
            assert final["delivered"] and final["validated"] and not final["revision_requested"], final
            assert final["review_status"] == "passed" and len(reviews) == 1
            assert "该公司开发仓储机器人。[1]" in final["report"]
            assert "该公司未公开具体融资金额。[2]" in final["report"]
            assert "## Lead" not in final["report"] and "## 导言" not in final["report"]
            assert final["report"].index("该公司开发") < final["report"].index("## 融资")
            assert final["report"].count("## 参考文献") == 1
            assert final["commit_proof"]["validated"] is True
            proof = json.loads(Path(temp_dir, ".report_commit_proof.json").read_text(encoding="utf-8"))
            assert proof["report_sha256"] == final["commit_proof"]["report_sha256"]
            assert len(created_sections) == 2
            assert created_sections[0]["content"] == "该公司开发仓储机器人。[1]"
            assert final["report"].rstrip().endswith("https://example.com/funding")
            delivered, issues, mode = app_main._prepare_report_for_delivery(
                "Orchestrator summary",
                request,
                {"research_state": "REPORTING"},
                compiled_text=final["report"],
                attempt_summary=final,
            )
            assert mode == "compiled_reporter_validated" and not issues
            assert delivered == final["report"]
            assert len(created_sections) == 2
            unvalidated, unvalidated_issues, unvalidated_mode = app_main._prepare_report_for_delivery(
                "Orchestrator summary",
                request,
                {"research_state": "REPORTING"},
                compiled_text=final["report"],
                attempt_summary={"validated": False},
            )
            assert unvalidated == final["report"]
            assert unvalidated_mode == "compiled_reporter_unvalidated"
            assert isinstance(unvalidated_issues, list)
            missing, missing_issues, missing_mode = app_main._prepare_report_for_delivery(
                "Orchestrator summary",
                request,
                {"research_state": "REPORTING"},
            )
            assert missing and missing_mode == "evidence_fallback"
            assert missing_issues

        with TemporaryDirectory() as empty_dir:
            empty_outline = report_tools.commit_report_outline(empty_dir, "空包", [{
                "chapter_id": 1,
                "title": "空包",
                "query_refs": ["q2"],
            }])
            assert empty_outline["status"] == "ok"
            empty_bundle = report_tools.prepare_report_chapter_batch(
                empty_dir,
                [{"chapter_id": 1}],
            )["chapters"][0]
            assert empty_bundle["status"] == "error" and "no URL-backed" in empty_bundle["message"]
            unknown_outline = report_tools.commit_report_outline(empty_dir, "未知", [{
                "chapter_id": 1,
                "title": "未知",
                "query_refs": ["q404"],
            }])
            assert unknown_outline["status"] == "error"
    finally:
        graph_manager_tools._review_report_once = original_review
        for name, original in originals.items():
            setattr(graph_tools, name, original)

    print("ALL V4 REPORT DELIVERY CHECKS PASSED")


if __name__ == "__main__":
    main()
