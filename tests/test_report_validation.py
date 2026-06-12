"""Standalone checks for final-report consistency and binding repair."""

import sys
from pathlib import Path

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from tools import graph_tools, report_tools, research_state  # noqa: E402


def main():
    nodes = {
        "goal": {"id": "goal", "type": "UserRequest", "time_window": "2018-2024"},
        "s1": {
            "id": "s1", "type": "Source", "title": "Current source",
            "url": "https://example.com/current", "published_at": "2023-06-01",
        },
        "s2": {
            "id": "s2", "type": "Source", "title": "Future source",
            "url": "https://example.com/future", "published_at": "2025-01-01",
        },
        "conflict": {
            "id": "conflict", "type": "Conflict", "resolution_status": "disclosed",
            "description": "Tesla Optimus hand parameter conflict",
        },
        "section": {
            "id": "section", "type": "ReportSection", "title": "Findings",
            "content": "Supported finding. " * 10,
        },
    }
    edges = []

    def search_nodes(kind, filt=None):
        wanted = kind.replace("_", "").lower()
        result = [
            dict(node) for node in nodes.values()
            if str(node.get("type", "")).replace("_", "").lower() == wanted
        ]
        return [node for node in result if all(node.get(k) == v for k, v in (filt or {}).items())]

    def add_edge(source, target, edge_type, attributes=None):
        name = edge_type.value if hasattr(edge_type, "value") else str(edge_type)
        edge = {"source": source, "target": target, "type": name, **(attributes or {})}
        if edge not in edges:
            edges.append(edge)
        return edge

    graph_tools.search_nodes = search_nodes
    graph_tools.get_node_edges = lambda node_id, direction="both": [
        dict(edge) for edge in edges
        if (
            direction == "out" and edge["source"] == node_id
            or direction == "in" and edge["target"] == node_id
            or direction == "both" and node_id in {edge["source"], edge["target"]}
        )
    ]
    graph_tools.add_edge = add_edge
    graph_tools.create_report_section = lambda title, content, section_type=None: "section"
    research_state.get_goal = lambda goal_id=None: dict(nodes["goal"])

    uncited = "## Findings\n\n" + ("A supported factual sentence. " * 8)
    issues = report_tools.validate_final_report(uncited)
    assert any("no citation" in issue for issue in issues), issues
    assert any("disclosed conflict omitted" in issue for issue in issues), issues

    out_of_window = (
        "## Findings\n\nTesla Optimus hand parameter conflict. "
        + ("A supported factual sentence. " * 5)
        + "[2]\n\n## References\n\n"
        + "[2] Future source https://example.com/future"
    )
    issues = report_tools.validate_final_report(out_of_window)
    assert any("out-of-window" in issue for issue in issues), issues

    background = out_of_window.replace("## Findings", "## Background")
    issues = report_tools.validate_final_report(background)
    assert not any("out-of-window" in issue for issue in issues), issues

    valid = (
        "## Findings\n\nTesla Optimus hand parameter conflict. "
        + ("A supported factual sentence. " * 5)
        + "[1]\n\n## References\n\n"
        + "[1] Current source https://example.com/current"
    )
    finalized = report_tools.finalize_report(valid)
    assert any(edge["source"] == "section" and edge["target"] == "s1" for edge in edges), edges
    assert not report_tools.validate_final_report(finalized), report_tools.validate_final_report(finalized)

    internal = valid.replace("A supported factual sentence.", "Research Graph query node.")
    assert any("internal process term" in issue for issue in report_tools.validate_final_report(internal))
    print("ALL REPORT VALIDATION CHECKS PASSED")


if __name__ == "__main__":
    main()
