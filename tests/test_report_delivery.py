"""Standalone regression checks for canonical cited report delivery."""

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
    assert app_main._delivery_contract_mode({
        "research_state": "REPORTING",
        "reporting_from_state": "REPORT_READY",
    }) == "complete"
    assert app_main._delivery_contract_mode({
        "research_state": "REPORTING",
        "reporting_from_state": "LIMITED_REPORT_READY",
    }) == "limited"
    assert app_main._delivery_contract_mode({
        "research_state": "BUDGET_EXHAUSTED",
    }) == "limited"

    nodes = {
        "goal": {
            "id": "goal",
            "type": "UserRequest",
            "request": "机器人公司研究",
            "research_goal": "比较机器人公司",
            "language": "zh",
        },
        "q1": {"id": "q1", "type": "Query", "handle": "q1", "text": "公司与融资"},
        "run1": {"id": "run1", "type": "SearchRun", "status": "succeeded"},
        "s1": {
            "id": "s1",
            "type": "Source",
            "title": "Company source",
            "url": "https://example.com/company",
        },
        "e1": {
            "id": "e1",
            "type": "Evidence",
            "claim": "公司未公开具体融资金额。",
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
        },
    }
    edges = [
        {"source": "goal", "target": "q1", "type": "HAS_QUERY"},
        {"source": "q1", "target": "run1", "type": "SEARCHED_BY"},
        {"source": "run1", "target": "s1", "type": "FOUND_SOURCE"},
        {"source": "run1", "target": "e1", "type": "PRODUCED"},
        {"source": "run1", "target": "c1", "type": "PRODUCED"},
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
    graph_tools.clear_current_context = lambda: None

    try:
        mm = MemoryManager(model=object())
        context = mm.export_report_context()
        assert "subgraph" not in context and "evidence" not in context and "research_status" not in context
        assert context["reference_registry"][0]["source_id"] == "s1"
        assert len(str(context)) < 5000
        assert context["disclosed_conflicts"] == []

        nodes["goal"]["request"] = "请撰写一篇关于机器人公司的维基百科条目。"
        wikipedia_context = mm.export_report_context()
        assert wikipedia_context["writing_hints"]["task_style"] == "wikipedia_article", wikipedia_context
        nodes["goal"]["request"] = "机器人公司研究"

        nodes["goal"].update({
            "research_state": "REPORTING",
            "reporting_from_state": "LIMITED_REPORT_READY",
            "report_authorized_reason": "bounded recovery was exhausted",
        })
        nodes["objective"].update({
            "objective_key": "company-comparison",
            "acceptance_criteria": [
                "identify the product scope",
                "identify the undisclosed funding amount",
            ],
            "unmet_acceptance_criteria": ["identify the undisclosed funding amount"],
            "supported_boundary": "Public sources establish product scope but not funding amount.",
            "status": "blocked",
        })
        nodes["q1"]["objective_keys"] = ["company-comparison"]
        nodes["conflict"] = {
            "id": "conflict",
            "type": "Conflict",
            "description": "Public sources disagree on the announced deployment date.",
            "conflict_type": "date_disagreement",
            "resolution_status": "disclosed",
        }
        nodes["unsupported-evidence"] = {
            "id": "unsupported-evidence",
            "type": "Evidence",
            "claim": "An unsupported uncertainty must remain internal.",
        }
        nodes["unsupported-conflict"] = {
            "id": "unsupported-conflict",
            "type": "Conflict",
            "description": "A claim lacks a URL-backed source.",
            "conflict_type": "unsupported_claim",
            "resolution_status": "disclosed",
        }
        edges.append({"source": "conflict", "target": "e1", "type": "HAS_CONFLICT"})
        edges.append({
            "source": "unsupported-conflict",
            "target": "unsupported-evidence",
            "type": "HAS_CONFLICT",
        })
        limited_context = mm.export_report_context()
        assert limited_context["delivery_mode"] == "limited", limited_context
        assert limited_context["unmet_objectives"] == [{
            "objective_key": "company-comparison",
            "unmet_acceptance_criteria": ["identify the undisclosed funding amount"],
            "supported_boundary": "Public sources establish product scope but not funding amount.",
            "related_query_ids": ["q1"],
        }], limited_context
        assert limited_context["substantive_uncertainties"] == [{
            "reader_facing_topic": "date_disagreement",
            "neutral_description": "Public sources disagree on the announced deployment date.",
            "evidence_ids": ["e1"],
            "source_ids": ["s1"],
        }], limited_context
        assert "limitations" not in limited_context
        assert "bounded recovery was exhausted" not in str(limited_context)
        nodes["goal"]["request"] = "Write a Wikipedia article about robot companies."
        wikipedia_fallback = report_tools.build_context_fallback_report()
        assert "Public sources disagree on the announced deployment date" in wikipedia_fallback
        assert "A claim lacks a URL-backed source" not in wikipedia_fallback
        assert "## Disclosed Conflicts" not in wikipedia_fallback
        assert "## 冲突披露" not in wikipedia_fallback
        nodes["goal"]["request"] = "机器人公司研究"
        fallback_with_unsupported_conflict = report_tools.build_context_fallback_report(
            "机器人公司研究"
        )
        assert "A claim lacks a URL-backed source" not in fallback_with_unsupported_conflict
        edges.pop()
        edges.pop()
        nodes.pop("unsupported-conflict")
        nodes.pop("unsupported-evidence")
        nodes.pop("conflict")
        nodes["objective"]["status"] = "satisfied"

        first_page = mm.get_report_evidence("q1", offset=0, limit=1)
        second_page = mm.get_report_evidence("q1", offset=1, limit=1)
        assert first_page["total"] == 2 and first_page["next_offset"] == 1
        assert second_page["next_offset"] is None
        assert all(item["source_ids"] == ["s1"] and item["citations"] == [1] for item in (
            first_page["items"] + second_page["items"]
        ))

        compiled = report_tools.compile_structured_report("机器人公司研究", [{
            "title": "公司与融资",
            "content": "公司未公开具体融资金额。\n\n该公司开发仓储机器人。",
            "source_ids": ["s1"],
            "evidence_ids": ["e1", "c1"],
        }])
        assert compiled["accepted"] is True and compiled["revision_requested"] is False, compiled
        assert "公司未公开具体融资金额" in compiled["report"]
        assert not report_tools.validate_delivery_invariants(compiled["report"])

        soft_compiled = report_tools.compile_structured_report("机器人公司研究", [{
            "title": "公司与融资",
            "content": "公司未公开具体融资金额。\n\n本次图谱证据更多集中在融资公开口径。",
            "source_ids": ["s1"],
            "evidence_ids": ["e1"],
        }])
        assert soft_compiled["accepted"] is True and soft_compiled["revision_requested"] is True, soft_compiled
        assert soft_compiled["severity"] == "soft"
        assert soft_compiled["report"] == ""
        assert "公司未公开具体融资金额" in soft_compiled["salvaged_report"]
        assert "本次图谱" not in soft_compiled["salvaged_report"]
        assert any(issue["code"] == "forbidden_meta_prose" for issue in soft_compiled["issues"])

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
            salvaged_text=soft_compiled["salvaged_report"],
            attempt_summary=soft_compiled,
        )
        assert mode == "salvaged_reporter", (mode, issues)
        assert "公司未公开具体融资金额" in fallback
        assert not report_tools.validate_delivery_invariants(fallback)

        context_only, issues, mode = app_main._prepare_report_for_delivery(
            orchestrator_rewrite,
            "机器人公司研究",
            {"research_state": "REPORTING"},
            compiled_text="",
            salvaged_text="",
            attempt_summary={"accepted": False, "issues": [{"message": "no valid sections"}]},
        )
        assert mode == "context_fallback", (mode, issues)
        assert "## 融资与资本进展" in context_only
        assert "## 研究范围与局限" not in context_only
        assert "本轮" not in context_only and "无法进一步核实" not in context_only
        assert "公司未公开具体融资金额" in context_only
        assert not report_tools.validate_delivery_invariants(context_only)

        with TemporaryDirectory() as temp_dir:
            graph_manager_tools.configure(temp_dir)
            outline = graph_manager_tools.commit_report_outline.invoke({
                "title": "机器人公司研究",
                "chapters": [{
                    "chapter_id": 1,
                    "title": "公司与融资",
                    "goals": ["概述公司能力与资本公开信息"],
                    "query_ids": ["q1"],
                    "section_plan": "1. 公司能力\n2. 资本公开信息",
                }],
            })
            assert outline["status"] == "ok"
            bundle = graph_manager_tools.prepare_report_chapter_bundle.invoke({"chapter_id": 1})
            assert bundle["status"] == "ok" and bundle["chapter_title"] == "公司与融资"
            assert {item["id"] for item in bundle["evidence_items"]} == {"e1", "c1"}
            chapter = graph_manager_tools.commit_report_chapter.invoke({
                "chapter_id": 1,
                "title": "公司与融资",
                "content": "公司未公开具体融资金额。\n\n该公司开发仓储机器人。",
                "source_ids": ["s1"],
                "evidence_ids": ["e1", "c1"],
            })
            assert chapter["status"] == "ok"
            draft = graph_manager_tools.assemble_report_draft.invoke({})
            assert draft["status"] == "ok"
            assert "公司未公开具体融资金额" in draft["draft"]
            assert Path(temp_dir, ".report_outline.json").exists()
            assert Path(temp_dir, ".report_chapters", "chapter_01.md").exists()
            assert Path(temp_dir, ".report_draft.md").exists()

            result = graph_manager_tools.submit_final_report.invoke({
                "title": "机器人公司研究",
                "sections": [{
                    "title": "公司与融资",
                    "content": "公司未公开具体融资金额。",
                    "source_ids": ["s1"],
                    "evidence_ids": ["e1"],
                }],
            })
            assert result["accepted"] is True and result["revision_requested"] is False
            canonical = graph_manager_tools.get_compiled_report()
            assert "公司未公开具体融资金额" in canonical
            assert Path(temp_dir, ".compiled_report.md").exists()

            soft_result = graph_manager_tools.submit_final_report.invoke({
                "title": "机器人公司研究",
                "sections": [{
                    "title": "公司与融资",
                    "content": "公司未公开具体融资金额。\n\n本次图谱证据更多集中在融资公开口径。",
                    "source_ids": ["s1"],
                    "evidence_ids": ["e1"],
                }],
            })
            assert soft_result["accepted"] is True and soft_result["revision_requested"] is True
            assert Path(temp_dir, ".salvaged_report.md").exists()
            assert Path(temp_dir, ".best_report.md").exists()
            assert Path(temp_dir, ".report_attempt.json").exists()
            assert graph_manager_tools.get_last_report_attempt()["revision_requested"] is True
            assert "公司未公开具体融资金额" in graph_manager_tools.get_best_report()

            legacy = graph_manager_tools.submit_final_report.invoke({
                "title": "机器人公司研究",
                "sections": [{
                    "title": "公司与融资",
                    "blocks": [{"text": "公司未公开具体融资金额。", "source_ids": ["s1"]}],
                }],
            })
            assert legacy["accepted"] is False and legacy["severity"] == "hard", legacy
            assert any(issue["code"] == "legacy_block_schema" for issue in legacy["issues"])
    finally:
        for name, original in originals.items():
            setattr(graph_tools, name, original)

    print("ALL REPORT DELIVERY CHECKS PASSED")


if __name__ == "__main__":
    main()
