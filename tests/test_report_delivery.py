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
        "s2": {
            "id": "s2",
            "type": "Source",
            "title": "Weak social source",
            "url": "https://facebook.com/company/post",
        },
        "e1": {
            "id": "e1",
            "type": "Evidence",
            "claim": "公司未公开具体融资金额。",
        },
        "e2": {
            "id": "e2",
            "type": "Evidence",
            "claim": "Popular accounts on social media often summarize the company as a warehouse robotics startup.",
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
        {"source": "run1", "target": "s2", "type": "FOUND_SOURCE"},
        {"source": "run1", "target": "e1", "type": "PRODUCED"},
        {"source": "run1", "target": "e2", "type": "PRODUCED"},
        {"source": "run1", "target": "c1", "type": "PRODUCED"},
        {"source": "s1", "target": "e1", "type": "SUPPORTED_BY"},
        {"source": "s2", "target": "e1", "type": "SUPPORTED_BY"},
        {"source": "s2", "target": "e2", "type": "SUPPORTED_BY"},
        {"source": "s1", "target": "c1", "type": "SUPPORTED_BY"},
        {"source": "s2", "target": "c1", "type": "SUPPORTED_BY"},
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
            "get_query_children",
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
        "nodes": [dict(nodes["e1"]), dict(nodes["e2"]), dict(nodes["c1"])],
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
    graph_tools.get_query_children = lambda node_id: [
        edge["target"]
        for edge in edges + created_edges
        if edge["source"] == node_id and str(edge["type"]).lower() in {"has_query", "parent_of"}
    ]
    graph_tools.clear_current_context = lambda: None

    try:
        mm = MemoryManager(model=object())
        context = mm.export_report_context()
        assert "subgraph" not in context and "evidence" not in context and "research_status" not in context
        assert context["reference_registry"][0]["source_id"] == "s1"
        assert len(str(context)) < 5000
        assert context["disclosed_conflicts"] == []

        first_page = mm.get_report_evidence("q1", offset=0, limit=1)
        second_page = mm.get_report_evidence("q1", offset=1, limit=2)
        assert first_page["total"] == 3 and first_page["next_offset"] == 1
        assert second_page["next_offset"] is None
        assert all(item["source_ids"] == ["s1"] and item["citations"] == [1] for item in (
            first_page["items"][:1] + second_page["items"][:1]
        ))
        ordered_page = mm.get_report_evidence("q1", offset=0, limit=3)
        ordered_texts = [item["text"] for item in ordered_page["items"]]
        assert ordered_texts[0] != "Popular accounts on social media often summarize the company as a warehouse robotics startup.", ordered_texts
        assert ordered_texts[-1].startswith("Popular accounts on social media"), ordered_texts

        compiled = report_tools.compile_structured_report("机器人公司研究", [{
            "title": "公司与融资",
            "blocks": [
                {"text": "公司未公开具体融资金额。", "source_ids": ["s1"]},
                {"text": "该公司开发仓储机器人。", "source_ids": ["s1"], "kind": "list_item"},
            ],
        }])
        assert compiled["accepted"] is True and compiled["revision_requested"] is False, compiled
        assert "公司未公开具体融资金额" in compiled["report"]
        assert not report_tools.validate_delivery_invariants(compiled["report"])

        intro_compiled = report_tools.compile_structured_report("机器人公司研究", [
            {
                "title": "Lead",
                "section_type": "intro",
                "blocks": [{
                    "text": "该公司开发仓储机器人并服务仓储场景。",
                    "source_ids": ["s1", "s2"],
                }],
            },
            {
                "title": "公司与融资",
                "blocks": [{"text": "公司未公开具体融资金额。", "source_ids": ["s1", "s2"]}],
            },
        ])
        assert intro_compiled["accepted"] is True and intro_compiled["revision_requested"] is False, intro_compiled
        assert "\n## Lead\n" not in intro_compiled["report"], intro_compiled["report"]
        assert intro_compiled["report"].startswith("# 机器人公司研究\n\n该公司开发仓储机器人并服务仓储场景。 [1]"), intro_compiled["report"]
        assert "facebook.com/company/post" not in intro_compiled["report"], intro_compiled["report"]

        compat_intro = report_tools.compile_structured_report("机器人公司研究", [
            {
                "title": "Lead",
                "section_type": "section",
                "blocks": [{
                    "text": "该公司是一家仓储机器人企业。",
                    "source_ids": ["s1", "s2"],
                }],
            },
            {
                "title": "公司与融资",
                "blocks": [{"text": "公司未公开具体融资金额。", "source_ids": ["s1"]}],
            },
        ])
        assert compat_intro["accepted"] is True and compat_intro["revision_requested"] is False, compat_intro
        assert "\n## Lead\n" not in compat_intro["report"], compat_intro["report"]
        assert compat_intro["report"].startswith("# 机器人公司研究\n\n该公司是一家仓储机器人企业。 [1]"), compat_intro["report"]

        mixed_source_intro = report_tools.compile_structured_report("机器人公司研究", [
            {
                "title": "Lead",
                "section_type": "intro",
                "blocks": [{
                    "text": "该公司是一家仓储机器人企业。",
                    "source_ids": ["missing-source", "s1"],
                }],
            },
            {
                "title": "公司与融资",
                "blocks": [{"text": "公司未公开具体融资金额。", "source_ids": ["s1"]}],
            },
        ])
        assert mixed_source_intro["accepted"] is True, mixed_source_intro
        repaired_text = mixed_source_intro["report"] or mixed_source_intro["salvaged_report"]
        assert repaired_text.startswith("# 机器人公司研究\n\n该公司是一家仓储机器人企业。 [1]"), repaired_text
        assert any(
            issue["code"] == "invalid_source_ids" and issue["section_title"] == "Lead"
            for issue in mixed_source_intro["issues"]
        ), mixed_source_intro["issues"]

        weak_reception = report_tools.compile_structured_report("机器人公司研究", [{
            "title": "公司与融资",
            "blocks": [
                {
                    "text": "Popular accounts on social media often summarize the company as a warehouse robotics startup.",
                    "source_ids": ["s2"],
                },
                {"text": "该公司开发仓储机器人。", "source_ids": ["s1"]},
            ],
        }])
        assert weak_reception["accepted"] is True and weak_reception["revision_requested"] is True, weak_reception
        assert "Popular accounts on social media" not in weak_reception["salvaged_report"]
        assert "该公司开发仓储机器人" in weak_reception["salvaged_report"]
        assert any(issue["code"] == "weak_reception_block" for issue in weak_reception["issues"])

        allowed_reception = report_tools.compile_structured_report("机器人公司研究", [{
            "title": "Public reception",
            "blocks": [
                {
                    "text": "Popular accounts on social media often summarize the company as a warehouse robotics startup.",
                    "source_ids": ["s2"],
                },
            ],
        }])
        assert allowed_reception["accepted"] is True, allowed_reception
        assert "Popular accounts on social media" in (allowed_reception["report"] or allowed_reception["salvaged_report"])

        soft_compiled = report_tools.compile_structured_report("机器人公司研究", [{
            "title": "公司与融资",
            "blocks": [
                {"text": "公司未公开具体融资金额。", "source_ids": ["s1"]},
                {"text": "本次图谱证据更多集中在融资公开口径。", "source_ids": ["s1"]},
            ],
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
        assert "## 研究范围与局限" in context_only
        assert "公司未公开具体融资金额" in context_only
        assert not report_tools.validate_delivery_invariants(context_only)

        with TemporaryDirectory() as temp_dir:
            graph_manager_tools.configure(temp_dir)
            result = graph_manager_tools.submit_final_report.invoke({
                "title": "机器人公司研究",
                "sections": [{
                    "title": "公司与融资",
                    "blocks": [{"text": "公司未公开具体融资金额。", "source_ids": ["s1"]}],
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
                    "blocks": [
                        {"text": "公司未公开具体融资金额。", "source_ids": ["s1"]},
                        {"text": "本次图谱证据更多集中在融资公开口径。", "source_ids": ["s1"]},
                    ],
                }],
            })
            assert soft_result["accepted"] is True and soft_result["revision_requested"] is True
            assert Path(temp_dir, ".salvaged_report.md").exists()
            assert Path(temp_dir, ".best_report.md").exists()
            assert Path(temp_dir, ".report_attempt.json").exists()
            assert graph_manager_tools.get_last_report_attempt()["revision_requested"] is True
            assert "公司未公开具体融资金额" in graph_manager_tools.get_best_report()
    finally:
        for name, original in originals.items():
            setattr(graph_tools, name, original)

    print("ALL REPORT DELIVERY CHECKS PASSED")


if __name__ == "__main__":
    main()
