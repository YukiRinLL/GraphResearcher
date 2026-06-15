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

        first_page = mm.get_report_evidence("q1", offset=0, limit=1)
        second_page = mm.get_report_evidence("q1", offset=1, limit=1)
        assert first_page["total"] == 2 and first_page["next_offset"] == 1
        assert second_page["next_offset"] is None
        assert all(item["source_ids"] == ["s1"] and item["citations"] == [1] for item in (
            first_page["items"] + second_page["items"]
        ))

        compiled = report_tools.compile_structured_report("机器人公司研究", [{
            "title": "公司与融资",
            "blocks": [
                {"text": "公司未公开具体融资金额。", "source_ids": ["s1"]},
                {"text": "该公司开发仓储机器人。", "source_ids": ["s1"], "kind": "list_item"},
            ],
        }])
        assert "error" not in compiled, compiled
        assert "公司未公开具体融资金额" in compiled["report"]
        assert not report_tools.validate_delivery_invariants(compiled["report"])

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
            result = graph_manager_tools.submit_final_report.invoke({
                "title": "机器人公司研究",
                "sections": [{
                    "title": "公司与融资",
                    "blocks": [{"text": "公司未公开具体融资金额。", "source_ids": ["s1"]}],
                }],
            })
            assert result["accepted"] is True
            canonical = graph_manager_tools.get_compiled_report()
            assert "公司未公开具体融资金额" in canonical
            assert Path(temp_dir, ".compiled_report.md").exists()
    finally:
        for name, original in originals.items():
            setattr(graph_tools, name, original)

    print("ALL REPORT DELIVERY CHECKS PASSED")


if __name__ == "__main__":
    main()
