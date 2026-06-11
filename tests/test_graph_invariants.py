"""Standalone checks for strict Query-tree and typed binding invariants."""

import sys
from pathlib import Path

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from agents.memory_manager import MemoryManager  # noqa: E402
from memory.graph import EdgeType  # noqa: E402
from tools import graph_tools  # noqa: E402


def main():
    nodes = {
        "goal": {"id": "goal", "type": "UserRequest"},
        "q1": {
            "id": "q1",
            "type": "Query",
            "handle": "q1",
            "priority": 1.0,
            "status": "pending",
        },
        "gap": {
            "id": "gap",
            "type": "Analysis",
            "analysis_type": "gap",
            "required_for_parent": True,
            "status": "open",
        },
        "source": {"id": "source", "type": "Source"},
    }
    created = []
    edges = []

    graph_tools.get_node = lambda node_id: dict(nodes.get(node_id, {}))
    graph_tools.get_query_children = lambda _parent_id: []
    graph_tools.add_edge = lambda source, target, edge_type, attributes=None: edges.append(
        {"source": source, "target": target, "type": edge_type.value}
    )
    graph_tools.upsert_node = lambda kind, attrs, dedupe_key=None: nodes[dedupe_key].update(attrs)

    def create_query(**kwargs):
        created.append(kwargs)
        graph_tools.add_edge(kwargs["parent_id"], "new-query", EdgeType.PARENT_OF)
        return "new-query"

    graph_tools._create_query = create_query

    try:
        graph_tools.create_query_child("q1", "bad child", "core", gap_ids=["source"])
    except ValueError:
        pass
    else:
        raise AssertionError("non-gap assignment must be rejected")
    assert not created, "invalid child creation must not leave a Query node"
    try:
        graph_tools.transition_query("q1", "sufficient")
    except ValueError:
        pass
    else:
        raise AssertionError("illegal Query state transitions must be rejected")
    try:
        graph_tools.add_node("query", {})
    except ValueError:
        pass
    else:
        raise AssertionError("generic add_node must not create Query nodes")

    child_id = graph_tools.create_query_child("q1", "valid child", "peripheral", gap_ids=["gap"])
    assert child_id == "new-query" and created[0]["required_for_parent"] is True
    assert edges[0]["type"] == "PARENT_OF" and edges[1]["type"] == "ADDRESSES_GAP"

    graph_tools.get_all_nodes = lambda: [
        {"id": "goal", "type": "UserRequest"},
        {"id": "q1", "type": "Query", "handle": "q1"},
        {"id": "q2", "type": "Query", "handle": "q1.1"},
    ]
    graph_tools.get_all_edges = lambda: [
        {"source": "goal", "target": "q1", "type": "HAS_QUERY"},
        {"source": "q1", "target": "q2", "type": "HAS_QUERY"},
    ]
    validation = graph_tools.validate_query_tree()
    assert not validation["valid"] and validation["invalid_parent_edges"], validation

    graph_tools.get_node = lambda node_id: dict(nodes.get(node_id, {}))
    try:
        graph_tools.create_analysis("orphan", query_id="source")
    except ValueError:
        pass
    else:
        raise AssertionError("Analysis binding to a non-Query must be rejected")

    mm = MemoryManager(model=object())
    try:
        mm.bind_report_section({"title": "bad", "content": "bad"}, evidence_ids=["source"])
    except ValueError:
        pass
    else:
        raise AssertionError("ReportSection binding to a non-Evidence must be rejected")

    assert not hasattr(mm, "mark_query")
    assert not hasattr(mm, "expand_query")
    print("ALL GRAPH INVARIANT CHECKS PASSED")


if __name__ == "__main__":
    main()
