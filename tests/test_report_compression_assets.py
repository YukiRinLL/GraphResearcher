"""Standalone checks for Reporter compression assets."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

repo_dir = Path(__file__).parent.parent
sys.path.insert(0, str(repo_dir))
sys.path.insert(0, str(repo_dir / "src"))

from tools import graph_tools, report_tools  # noqa: E402


def main():
    nodes = {
        "goal": {
            "id": "goal",
            "type": "UserRequest",
            "request": "机器人公司比较",
            "research_goal": "比较机器人公司",
            "language": "zh",
        },
        "q1": {
            "id": "q1",
            "type": "Query",
            "handle": "q1",
            "text": "公司 A 融资",
            "importance": "core",
            "source_count_snapshot": 1,
            "top_evidence_ids": ["e1"],
            "evidence_digest": ["公司 A 完成新一轮融资。"],
            "search_subject_key": "company-a",
        },
        "q2": {
            "id": "q2",
            "type": "Query",
            "handle": "q2",
            "text": "公司 B 产品部署",
            "importance": "supporting",
            "source_count_snapshot": 1,
            "top_evidence_ids": ["e2"],
            "evidence_digest": ["公司 B 已部署仓储机器人。"],
        },
        "s1": {"id": "s1", "type": "Source", "title": "A", "url": "https://example.com/a"},
        "s2": {"id": "s2", "type": "Source", "title": "B", "url": "https://example.com/b"},
        "e1": {"id": "e1", "type": "Evidence", "claim": "公司 A 完成新一轮融资。"},
        "e2": {"id": "e2", "type": "Evidence", "claim": "公司 B 已部署仓储机器人。"},
    }
    edges = [
        {"source": "goal", "target": "q1", "type": "HAS_QUERY"},
        {"source": "goal", "target": "q2", "type": "HAS_QUERY"},
        {"source": "s1", "target": "e1", "type": "SUPPORTED_BY"},
        {"source": "s2", "target": "e2", "type": "SUPPORTED_BY"},
    ]

    originals = {
        name: getattr(graph_tools, name)
        for name in (
            "get_all_nodes",
            "get_all_edges",
            "get_node",
            "search_nodes",
            "get_query_evaluation_subgraph",
        )
    }

    def search_nodes(kind, filt=None):
        wanted = kind.replace("_", "").lower()
        result = [
            dict(node) for node in nodes.values()
            if str(node.get("type", "")).replace("_", "").lower() == wanted
        ]
        return [node for node in result if all(node.get(key) == value for key, value in (filt or {}).items())]

    graph_tools.get_all_nodes = lambda: [dict(node) for node in nodes.values()]
    graph_tools.get_all_edges = lambda: [dict(edge) for edge in edges]
    graph_tools.get_node = lambda node_id: dict(nodes.get(node_id, {}))
    graph_tools.search_nodes = search_nodes
    graph_tools.get_query_evaluation_subgraph = lambda query_id: {
        "query": dict(nodes[query_id]),
        "nodes": [dict(nodes["e1"])] if query_id == "q1" else [dict(nodes["e2"])],
        "edges": [dict(edge) for edge in edges],
        "children": [],
    }

    try:
        assets = report_tools.build_report_planning_assets(["q1", "q2"])
        assert assets["query_evidence_digests"][0]["query_id"] == "q1", assets
        assert assets["comparison_slots"], assets
        assert assets["entity_profiles"][0]["entity_key"] == "company-a", assets

        no_subject_assets = report_tools.build_report_planning_assets(["q2"])
        assert no_subject_assets["entity_profiles"] == [], no_subject_assets

        with TemporaryDirectory() as temp_dir:
            report_tools.persist_report_planning_assets(temp_dir, assets)
            report_tools.commit_report_outline(temp_dir, "机器人公司比较", [{
                "chapter_id": 1,
                "title": "公司对比",
                "goals": ["比较两家公司融资与部署"],
                "query_ids": ["q1", "q2"],
                "section_plan": "围绕融资与部署做对比",
            }])
            bundle = report_tools.prepare_report_chapter_bundle(temp_dir, 1)
            assert bundle["query_evidence_digests"], bundle
            assert bundle["comparison_slots"], bundle
            assert bundle["entity_profiles"][0]["entity_key"] == "company-a", bundle
            assert bundle["section_brief"]["focus_queries"][0]["query_id"] == "q1", bundle
    finally:
        for name, original in originals.items():
            setattr(graph_tools, name, original)


if __name__ == "__main__":
    main()
