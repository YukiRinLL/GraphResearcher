"""Standalone regression checks for canonical cited report delivery."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

repo_dir = Path(__file__).parent.parent
sys.path.insert(0, str(repo_dir))
sys.path.insert(0, str(repo_dir / "src"))

import main as app_main  # noqa: E402
from agents.memory_manager import MemoryManager  # noqa: E402
from tools import (  # noqa: E402
    graph_manager_tools,
    graph_tools,
    report_tools,
    report_workspace,
)


def main():
    nodes = {
        "goal": {
            "id": "goal",
            "type": "UserRequest",
            "request": "机器人公司研究",
            "research_goal": "比较机器人公司",
            "language": "zh",
            "research_state": "REPORTING",
        },
        "q1": {"id": "q1", "type": "Query", "handle": "q1", "text": "公司与融资"},
        "run1": {"id": "run1", "type": "SearchRun", "status": "succeeded"},
        "s1": {
            "id": "s1",
            "type": "Source",
            "title": "Company source",
            "url": "https://example.com/company",
            "source_tier": "primary",
            "published_at": "2026-01-15",
        },
        "e1": {
            "id": "e1",
            "type": "Evidence",
            "claim": "公司未公开具体融资金额。",
            "confidence": 0.8,
            "time_scope": "2025-2026",
        },
        "c1": {
            "id": "c1",
            "type": "Claim",
            "statement": "该公司开发仓储机器人。",
        },
        "objective": {
            "id": "objective",
            "type": "Analysis",
            "analysis_type": "objective",
            "description": "比较主要公司",
            "requirement": "must",
            "status": "satisfied",
            "objective_key": "companies",
        },
    }
    edges = [
        {"source": "goal", "target": "q1", "type": "HAS_QUERY"},
        {"source": "q1", "target": "run1", "type": "SEARCHED_BY"},
        {"source": "run1", "target": "s1", "type": "FOUND_SOURCE"},
        {"source": "run1", "target": "e1", "type": "PRODUCED"},
        {"source": "run1", "target": "c1", "type": "PRODUCED"},
        {"source": "q1", "target": "objective", "type": "COVERS_OBJECTIVE"},
        {"source": "s1", "target": "e1", "type": "SUPPORTED_BY"},
        {"source": "s1", "target": "c1", "type": "SUPPORTED_BY"},
    ]
    created_sections = []
    created_edges = []

    originals = {
        name: getattr(graph_tools, name)
        for name in (
            "get_all_nodes",
            "get_all_edges",
            "get_node",
            "search_nodes",
            "get_query_evaluation_subgraph",
            "create_report_section",
            "add_edge",
            "get_node_edges",
            "clear_current_context",
            "bind_evidence_to_section",
            "upsert_node",
        )
    }

    def search_nodes(kind, filt=None):
        wanted = kind.replace("_", "").lower()
        return [
            dict(node) for node in nodes.values()
            if str(node.get("type", "")).replace("_", "").lower() == wanted
            and all(node.get(key) == value for key, value in (filt or {}).items())
        ]

    graph_tools.get_all_nodes = lambda: [dict(node) for node in nodes.values()]
    graph_tools.get_all_edges = lambda: [dict(edge) for edge in edges + created_edges]
    graph_tools.get_node = lambda node_id: dict(nodes.get(node_id, {}))
    graph_tools.search_nodes = search_nodes
    graph_tools.get_query_evaluation_subgraph = lambda query_id: {
        "query": dict(nodes[query_id]),
        "nodes": [dict(nodes["e1"]), dict(nodes["c1"])],
        "edges": [dict(edge) for edge in edges],
        "children": [],
    }
    graph_tools.create_report_section = lambda title, content, section_type=None: (
        created_sections.append({"title": title, "content": content, "section_type": section_type})
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
    graph_tools.get_node_edges = lambda node_id, direction="both": [
        edge for edge in created_edges
        if direction == "out" and edge["source"] == node_id
    ]
    graph_tools.bind_evidence_to_section = lambda section_id, evidence_ids, claim_ids=None: [
        created_edges.append({"source": section_id, "target": item_id, "type": "USES"})
        for item_id in [*(evidence_ids or []), *(claim_ids or [])]
    ]
    graph_tools.upsert_node = lambda node_type, attributes, node_id=None: (
        nodes[node_id].update(attributes) or node_id
    )
    graph_tools.clear_current_context = lambda: None

    try:
        mm = MemoryManager(model=object())
        context = mm.export_report_context()
        assert "subgraph" not in context and "evidence" not in context and "research_status" not in context
        assert context["reference_registry"][0]["source_id"] == "s1"
        assert len(str(context)) < 5000

        first_page = mm.get_report_evidence("q1", offset=0, limit=1)
        second_page = mm.get_report_evidence("q1", offset=1, limit=1)
        assert first_page["total"] == 2 and first_page["next_offset"] == 1
        assert second_page["next_offset"] is None
        assert all(item["source_ids"] == ["s1"] and item["citations"] == [1] for item in (
            first_page["items"] + second_page["items"]
        ))
        objective_page = mm.get_report_evidence("objective", offset=0, limit=10)
        assert objective_page["total"] == 2 and objective_page["objective"]["id"] == "objective"
        nodes["sdup"] = {
            "id": "sdup", "type": "Source", "title": "Duplicate source",
            "url": "https://example.com/company",
        }
        nodes["edup"] = {"id": "edup", "type": "Evidence", "claim": "重复 URL 的证据。"}
        edges.append({"source": "sdup", "target": "edup", "type": "SUPPORTED_BY"})
        duplicate = report_tools.compile_bound_blocks([
            {"text": "重复 URL 仍只产生一个引用。", "evidence_ids": ["edup"]},
        ])
        assert duplicate["source_ids"] == ["s1"] and "[1]" in duplicate["content"], duplicate

        compiled = report_tools.compile_structured_report("机器人公司研究", [{
            "title": "公司与融资",
            "objective_ids": ["objective"],
            "blocks": [
                {"text": "公司未公开具体融资金额。", "evidence_ids": ["e1"]},
                {"text": "该公司开发仓储机器人。", "claim_ids": ["c1"], "kind": "list_item"},
            ],
        }])
        assert "error" not in compiled, compiled
        assert "公司未公开具体融资金额" in compiled["report"]
        assert not report_tools.validate_delivery_invariants(compiled["report"])
        missing_binding = report_tools.compile_bound_blocks([{
            "text": "不允许直接绑定来源。",
            "source_ids": ["s1"],
        }])
        assert missing_binding["error"] == "Bound block validation failed"
        wrong_binding_type = report_tools.compile_bound_blocks([{
            "text": "来源节点不能冒充证据。",
            "evidence_ids": ["s1"],
        }])
        assert wrong_binding_type["error"] == "Bound block validation failed"

        nodes["objective_missing"] = {
            "id": "objective_missing",
            "type": "Analysis",
            "analysis_type": "objective",
            "description": "逐家公司给出产品与融资信息",
            "requirement": "must",
            "status": "satisfied",
        }
        omission_issues = report_tools.collect_report_quality_issues(
            compiled["report"],
            covered_objective_ids=["objective"],
        )
        assert any("must objective not covered" in issue for issue in omission_issues), omission_issues
        del nodes["objective_missing"]

        nodes["conflict"] = {
            "id": "conflict",
            "type": "Conflict",
            "resolution_status": "disclosed",
            "description": "融资金额口径存在冲突",
        }
        edges.append({"source": "conflict", "target": "e1", "type": "HAS_CONFLICT"})
        conflict_issues = report_tools.collect_report_quality_issues(
            compiled["report"],
            covered_objective_ids=["objective"],
        )
        assert any("disclosed conflict omitted" in issue for issue in conflict_issues), conflict_issues
        del nodes["conflict"]
        edges.pop()

        orchestrator_rewrite = (
            "下面的整理基于截至 2025 年的公开资料，并严格受本次研究图谱覆盖范围约束。\n\n"
            "由于引用系统限制，正文不逐条打 [1][2]。\n\n"
            "如果你接下来希望进一步细化，可以指定维度，我可以帮你补全。"
        )
        delivered, issues, mode = app_main._prepare_report_for_delivery(
            orchestrator_rewrite,
            "机器人公司研究",
            {"research_state": "REPORTING"},
            compiled_text=compiled["report"],
        )
        assert mode == "compiled_reporter"
        assert "研究图谱" not in delivered and "如果你接下来希望" not in delivered
        assert "公司未公开具体融资金额" in delivered
        assert not report_tools.validate_delivery_invariants(delivered), issues

        fallback, issues, mode = app_main._prepare_report_for_delivery(
            orchestrator_rewrite,
            "机器人公司研究",
            {"research_state": "REPORTING"},
            compiled_text="",
        )
        assert mode == "cited_fallback" and issues
        assert "研究图谱" not in fallback and "如果你接下来希望" not in fallback
        assert "公司未公开具体融资金额" in fallback
        assert not report_tools.validate_delivery_invariants(fallback)

        with TemporaryDirectory() as temp_dir:
            graph_manager_tools.configure(temp_dir)
            incomplete_outline = graph_manager_tools.commit_report_outline.invoke({
                "title": "未完成报告",
                "chapters": [
                    {
                        "title": "第一章",
                        "goals": ["比较主要公司"],
                        "objective_ids": ["objective"],
                        "candidate_item_ids": ["objective"],
                        "sections_description": "已写章节。",
                    },
                    {
                        "title": "第二章",
                        "goals": ["补充公司画像"],
                        "objective_ids": ["objective"],
                        "candidate_item_ids": ["objective"],
                        "sections_description": "未写章节。",
                    },
                ],
            })
            assert incomplete_outline["status"] == "ok", incomplete_outline
            premature = graph_manager_tools.submit_final_report.invoke({
                "title": "未完成报告",
                "sections": [{"title": "第一章", "blocks": [{"text": "该公司开发仓储机器人。", "claim_ids": ["c1"]}]}],
            })
            assert "omits outline chapters" in premature["issues"][0], premature
            undrafted = graph_manager_tools.submit_final_report.invoke({
                "title": "未完成报告",
                "sections": [
                    {"title": "第一章", "blocks": [{"text": "该公司开发仓储机器人。", "claim_ids": ["c1"]}]},
                    {"title": "第二章", "blocks": [{"text": "公司未公开具体融资金额。", "evidence_ids": ["e1"]}]},
                ],
            })
            assert "report chapters are incomplete" in undrafted["issues"][0], undrafted

            graph_manager_tools.configure(temp_dir)
            outline = graph_manager_tools.commit_report_outline.invoke({
                "title": "机器人公司研究",
                "chapters": [{
                    "title": "公司与融资",
                    "goals": ["比较主要公司"],
                    "objective_ids": ["objective"],
                    "candidate_item_ids": ["objective"],
                    "sections_description": "比较公司能力与融资。",
                }],
            })
            assert outline["status"] == "ok", outline
            bundle = graph_manager_tools.prepare_report_chapter_bundle.invoke({
                "chapter_id": 1,
                "relevant_item_ids": [],
            })
            assert bundle["item_count"] == 2, bundle
            evidence_item = next(item for item in bundle["items"] if item["id"] == "e1")
            assert evidence_item["confidence"] == 0.8
            assert evidence_item["time_scope"] == "2025-2026"
            assert evidence_item["sources"][0]["source_tier"] == "primary"
            assert evidence_item["sources"][0]["published_at"] == "2026-01-15"
            chapter = graph_manager_tools.commit_report_chapter.invoke({
                "chapter_id": 1,
                "blocks": [
                    {"text": "公司未公开具体融资金额。", "evidence_ids": ["e1"]},
                    {"text": "该公司开发仓储机器人。", "claim_ids": ["c1"]},
                ],
            })
            assert chapter["status"] == "ok", chapter
            draft = graph_manager_tools.assemble_report_draft.invoke({})
            assert draft["status"] == "ok" and draft["submission_sections"], draft
            result = graph_manager_tools.submit_final_report.invoke({
                "title": "机器人公司研究",
                "sections": draft["submission_sections"],
            })
            assert result["accepted"] is True and result["review_required"] is True
            canonical = graph_manager_tools.get_compiled_report()
            assert "公司未公开具体融资金额" in canonical
            review_bundle = graph_manager_tools.get_report_review_bundle.invoke({"offset": 0, "limit": 10})
            assert review_bundle["total"] == 2 and review_bundle["bound_items"], review_bundle
            assert review_bundle["blocks"][0]["objective_ids"] == ["objective"]
            assert review_bundle["deterministic_audit"]["bound_block_count"] == 2
            review = graph_manager_tools.complete_report_review.invoke({"additional_issues": []})
            assert review["accepted"] is True and review["report_quality_status"] == "passed", review

            nodes["goal"].update({"report_revision_attempts": 0, "report_phase": "reviewing"})
            first_retry = graph_manager_tools.complete_report_review.invoke({
                "additional_issues": ["company-level output missing: company B"],
            })
            pending_bundle = graph_manager_tools.get_report_review_bundle.invoke({"offset": 0, "limit": 10})
            pending_complete = graph_manager_tools.complete_report_review.invoke({"additional_issues": []})
            assert pending_bundle["next_action"] == "dispatch_reporter", pending_bundle
            assert pending_complete["next_action"] == "dispatch_reporter", pending_complete
            nodes["goal"]["report_phase"] = "reviewing"
            second_retry = graph_manager_tools.complete_report_review.invoke({
                "additional_issues": ["company-level output missing: company B"],
            })
            nodes["goal"]["report_phase"] = "reviewing"
            limited = graph_manager_tools.complete_report_review.invoke({
                "additional_issues": ["company-level output missing: company B"],
            })
            assert first_retry["next_action"] == "dispatch_reporter"
            assert second_retry["next_action"] == "dispatch_reporter"
            assert limited["accepted"] is True and limited["report_quality_status"] == "limited"
            assert Path(temp_dir, "reports/outline.json").exists()
            assert Path(temp_dir, "reports/outline.md").exists()
            assert Path(temp_dir, "reports/chapters/chapter_01.md").exists()
            assert Path(temp_dir, "reports/chapters/chapter_01_meta.json").exists()
            assert Path(temp_dir, "reports/conflicts.json").exists()
            assert Path(temp_dir, "reports/draft.md").exists()
            assert Path(temp_dir, "reports/candidates/report_r01.md").exists()
            assert Path(temp_dir, "reports/candidates/report_r01_meta.json").exists()
            assert Path(temp_dir, "reports/report.md").exists()
            assert not Path(temp_dir, ".compiled_report.md").exists()
            report_workspace.configure(temp_dir)
            assert report_workspace.get_status()["candidate_count"] == 1
            Path(temp_dir, ".compiled_report.md").write_text("stale", encoding="utf-8")
            graph_manager_tools.configure(temp_dir)
            assert report_workspace.get_status()["candidate_count"] == 0
            assert not Path(temp_dir, ".compiled_report.md").exists()

        with TemporaryDirectory() as ranking_dir:
            report_workspace.configure(ranking_dir, reset=True)
            base = {"structural_issues": [], "covered_must_objectives": 1, "bound_block_count": 2}
            report_workspace.save_candidate("older warning", {**base, "quality_issues": ["warning"]})
            report_workspace.save_candidate("older clean", {**base, "quality_issues": []})
            latest = report_workspace.save_candidate("latest clean", {**base, "quality_issues": []})
            report_workspace.save_candidate("structurally invalid", {
                "structural_issues": ["invalid"],
                "quality_issues": [],
                "covered_must_objectives": 99,
                "bound_block_count": 99,
            })
            assert latest["best_revision"] == 3
            assert report_workspace.best_report() == "latest clean"
    finally:
        for name, original in originals.items():
            setattr(graph_tools, name, original)

    print("ALL REPORT DELIVERY CHECKS PASSED")


if __name__ == "__main__":
    main()
