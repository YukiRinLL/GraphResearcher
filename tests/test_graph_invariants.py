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
            "required_for_parent": False,
            "status": "candidate",
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
    assert child_id == "new-query" and created[0]["required_for_parent"] is False
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

    graph_tools.get_all_nodes = lambda: [
        {"id": "goal", "type": "UserRequest"},
        {"id": "goal2", "type": "UserRequest"},
        {"id": "q1", "type": "Query", "handle": "q1"},
        {"id": "q2", "type": "Query", "handle": "q1"},
    ]
    graph_tools.get_all_edges = lambda: [
        {"source": "goal", "target": "q1", "type": "HAS_QUERY"},
        {"source": "goal2", "target": "q2", "type": "HAS_QUERY"},
    ]
    validation = graph_tools.validate_query_tree()
    assert not validation["valid"] and validation["duplicate_handles"] and validation["multiple_goals"], validation

    graph_tools.get_node = lambda node_id: dict(nodes.get(node_id, {}))
    try:
        graph_tools.create_analysis("orphan", query_id="source")
    except ValueError:
        pass
    else:
        raise AssertionError("Analysis binding to a non-Query must be rejected")

    mm = MemoryManager(model=object())
    selected = mm._select_initial_queries(
        [
            {"text": "covers a and b", "objective_keys": ["a", "b"]},
            {"text": "covers a", "objective_keys": ["a"]},
            {"text": "covers c", "objective_keys": ["c"]},
        ],
        [
            {"objective_key": "a", "requirement": "must", "description": "a"},
            {"objective_key": "b", "requirement": "must", "description": "b"},
            {"objective_key": "c", "requirement": "must", "description": "c"},
        ],
    )
    assert len(selected) == 1
    assert selected[0]["text"] == "covers a and b"
    assert set(selected[0]["objective_keys"]) == {"a", "b"}
    complex_selected = mm._select_initial_queries(
        [
            {"text": "probe one", "objective_keys": ["a"]},
            {"text": "probe two", "objective_keys": ["b"]},
            {"text": "probe three", "objective_keys": []},
            {"text": "probe four", "objective_keys": ["c"]},
        ],
        [],
        complexity="complex",
    )
    assert [item["text"] for item in complex_selected] == ["probe one", "probe two", "probe three"]
    fallback = mm._select_initial_queries(
        [{"text": "unmapped candidate", "objective_keys": []}],
        [{"objective_key": "a", "requirement": "must", "description": "objective a"}],
    )
    assert fallback == [{
        "text": "unmapped candidate",
        "importance": "supporting",
        "objective_keys": [],
        "acceptance_criteria": [],
    }]
    created_sections = []
    bound_sections = []

    def create_report_section(title, content, section_type=None):
        section_id = f"section-{len(created_sections) + 1}"
        created_sections.append({
            "id": section_id,
            "title": title,
            "content": content,
            "section_type": section_type,
        })
        return section_id

    graph_tools.create_report_section = create_report_section
    graph_tools.bind_evidence_to_section = lambda section_id, evidence_ids, claim_ids=None: bound_sections.append({
        "section_id": section_id,
        "evidence_ids": list(evidence_ids),
        "claim_ids": list(claim_ids or []),
    })
    bad_binding = mm.bind_report_section({"title": "bad", "content": "bad"}, evidence_ids=["source"])
    unbound = mm.bind_report_section({"title": "unbound", "content": "fact " * 30})
    assert bad_binding == "section-1" and unbound == "section-2"
    assert bound_sections == [
        {"section_id": "section-1", "evidence_ids": [], "claim_ids": []},
        {"section_id": "section-2", "evidence_ids": [], "claim_ids": []},
    ]

    assert not hasattr(mm, "mark_query")
    assert not hasattr(mm, "expand_query")
    print("ALL GRAPH INVARIANT CHECKS PASSED")


if __name__ == "__main__":
    main()
