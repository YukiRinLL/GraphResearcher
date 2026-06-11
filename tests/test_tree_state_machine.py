"""Standalone end-to-end checks for the strict Query-tree state machine."""

import json
import sys
from pathlib import Path

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from agents.memory_manager import MemoryManager  # noqa: E402
from memory.graph import EdgeType  # noqa: E402
from tools import graph_tools, research_state  # noqa: E402
from tools.middleware import ResearchStateMiddleware  # noqa: E402

NODES = {
    "goal": {
        "id": "goal", "type": "UserRequest", "research_state": "RESEARCHING",
        "max_search_rounds": 20, "dispatched_search_rounds": 2, "successful_search_rounds": 2,
    },
    "q1": {
        "id": "q1", "type": "Query", "handle": "q1", "text": "core route", "status": "assessing",
        "priority": 1.0, "sem": 1.0, "required_for_parent": True, "acceptance_criteria": [],
    },
    "q2": {
        "id": "q2", "type": "Query", "handle": "q2", "text": "sibling route", "status": "pending",
        "priority": 0.76, "sem": 0.6, "required_for_parent": True, "acceptance_criteria": [],
    },
    "r1": {"id": "r1", "type": "SearchRun", "query_id": "q1", "status": "succeeded"},
    "r2": {"id": "r2", "type": "SearchRun", "query_id": "q2", "status": "succeeded"},
    "shared": {"id": "shared", "type": "Source", "url": "https://example.com"},
    "e1": {"id": "e1", "type": "Evidence", "claim": "owned evidence"},
    "e2": {"id": "e2", "type": "Evidence", "claim": "sibling evidence"},
}
EDGES = [
    {"source": "goal", "target": "q1", "type": "HAS_QUERY"},
    {"source": "goal", "target": "q2", "type": "HAS_QUERY"},
    {"source": "q1", "target": "r1", "type": "SEARCHED_BY"},
    {"source": "q2", "target": "r2", "type": "SEARCHED_BY"},
    {"source": "r1", "target": "shared", "type": "FOUND_SOURCE"},
    {"source": "r2", "target": "shared", "type": "FOUND_SOURCE"},
    {"source": "r1", "target": "e1", "type": "PRODUCED"},
    {"source": "r2", "target": "e2", "type": "PRODUCED"},
]
SEQ = 0


def install_fakes():
    def get_node(node_id):
        return dict(NODES.get(node_id, {}))

    def search_nodes(kind, filt=None):
        wanted = kind.replace("_", "").lower()
        out = [dict(n) for n in NODES.values() if str(n.get("type", "")).replace("_", "").lower() == wanted]
        return [n for n in out if all(n.get(k) == v for k, v in (filt or {}).items())]

    def upsert(kind, attrs, dedupe_key=None):
        NODES[dedupe_key].update(attrs)
        return dedupe_key

    def add_edge(source, target, edge_type, attributes=None):
        name = edge_type.value if hasattr(edge_type, "value") else str(edge_type)
        edge = {"source": source, "target": target, "type": name, **(attributes or {})}
        if edge not in EDGES:
            EDGES.append(edge)
        return f"{source}_{name}_{target}"

    def node_edges(node_id, direction="both"):
        if direction == "out":
            return [dict(e) for e in EDGES if e["source"] == node_id]
        if direction == "in":
            return [dict(e) for e in EDGES if e["target"] == node_id]
        return [dict(e) for e in EDGES if e["source"] == node_id or e["target"] == node_id]

    def children(parent_id):
        return [
            e["target"] for e in EDGES
            if e["source"] == parent_id and e["type"].lower() in {"has_query", "parent_of"}
        ]

    def parent(query_id):
        return next((
            e["source"] for e in EDGES
            if e["target"] == query_id and e["type"].lower() in {"has_query", "parent_of"}
        ), None)

    def create_analysis(text, query_id=None, analysis_type="insight", **attrs):
        global SEQ
        SEQ += 1
        node_id = f"a{SEQ}"
        NODES[node_id] = {"id": node_id, "type": "Analysis", "text": text, "analysis_type": analysis_type, **attrs}
        if query_id:
            add_edge(query_id, node_id, EdgeType.HAS_GAP if analysis_type == "gap" else EdgeType.HAS_ANALYSIS)
        return node_id

    def create_query_child(parent_id, text, importance, acceptance_criteria=None, gap_ids=None, **attrs):
        global SEQ
        SEQ += 1
        node_id = f"child{SEQ}"
        parent_node = NODES[parent_id]
        handle = f"{parent_node['handle']}.{len(children(parent_id)) + 1}"
        NODES[node_id] = {
            "id": node_id, "type": "Query", "handle": handle, "text": text, "status": "pending",
            "priority": parent_node["priority"] * 0.85, "sem": 0.6, "required_for_parent": importance != "peripheral",
            "acceptance_criteria": acceptance_criteria or [],
        }
        add_edge(parent_id, node_id, EdgeType.PARENT_OF)
        for gap_id in gap_ids or []:
            add_edge(node_id, gap_id, EdgeType.ADDRESSES_GAP)
            NODES[gap_id]["status"] = "assigned"
        return node_id

    graph_tools.get_node = get_node
    graph_tools.search_nodes = search_nodes
    graph_tools.upsert_node = upsert
    graph_tools.add_edge = add_edge
    graph_tools.get_node_edges = node_edges
    graph_tools.get_query_children = children
    graph_tools.get_query_parent = parent
    graph_tools.get_all_nodes = lambda: [dict(n) for n in NODES.values()]
    graph_tools.get_all_edges = lambda: [dict(e) for e in EDGES]
    graph_tools.create_analysis = create_analysis
    graph_tools.create_query_child = create_query_child


class FakeModel:
    def __init__(self, payloads):
        self.payloads = list(payloads)

    def invoke(self, _prompt):
        payload = self.payloads.pop(0)

        class R:
            content = json.dumps(payload)

        return R()


def main():
    install_fakes()
    evaluation = graph_tools.get_query_evaluation_subgraph("q1")
    ids = {n["id"] for n in evaluation["nodes"]}
    assert "e1" in ids and "e2" not in ids, ids
    assert graph_tools.validate_query_tree()["valid"]

    mm = MemoryManager(model=FakeModel([
        {
            "sufficiency_score": 0.5,
            "covered": ["base"],
            "gaps": [
                {"description": "gap one", "importance": "core", "acceptance_criteria": ["one"]},
                {"description": "gap two", "importance": "supporting", "acceptance_criteria": ["two"]},
            ],
            "recommendation": "needs_expansion",
            "reason": "two gaps",
        },
        {"queries": [{"text": "child query one", "importance": "core", "acceptance_criteria": ["one"]}]},
        {"queries": [{"text": "child query two", "importance": "supporting", "acceptance_criteria": ["two"]}]},
        {"sufficiency_score": 0.4, "covered": [], "gaps": [{"description": "repeat"}], "recommendation": "needs_expansion"},
        {"fatal_unresolved_conflicts": [], "core_threatening_gaps": [], "reason": "done"},
    ]))
    actions = mm.get_next_actions()
    assert actions[0]["action"] == "assess_query", actions
    assessed = mm.assess_query("q1")
    assert assessed["status"] == "needs_expansion" and len(assessed["created_gaps"]) == 2, assessed
    expanded = mm.expand_gaps("q1")
    assert len(expanded["created"]) == 2 and NODES["q1"]["status"] == "waiting_children", expanded
    assert all(NODES[c["id"]]["priority"] < NODES["q1"]["priority"] for c in expanded["created"])

    NODES["qlow"] = {
        "id": "qlow", "type": "Query", "handle": "q3", "text": "repeated branch", "status": "assessing",
        "priority": 0.5, "sem": 0.6, "required_for_parent": True, "low_novelty_streak": 2,
    }
    EDGES.append({"source": "goal", "target": "qlow", "type": "HAS_QUERY"})
    low = mm.assess_query("qlow")
    assert low["status"] == "blocked" and not low["created_gaps"], low

    NODES["qopt"] = {
        "id": "qopt", "type": "Query", "handle": "q4", "status": "waiting_children",
        "required_for_parent": False,
    }
    NODES["qoptc"] = {
        "id": "qoptc", "type": "Query", "handle": "q4.1", "status": "pending",
        "required_for_parent": True,
    }
    EDGES.extend([
        {"source": "goal", "target": "qopt", "type": "HAS_QUERY"},
        {"source": "qopt", "target": "qoptc", "type": "PARENT_OF"},
    ])
    assert research_state.is_required_path("qoptc") is False

    blocked = ResearchStateMiddleware()._gate_reporter({
        "name": "task", "id": "call1", "args": {"subagent_type": "reporter"},
    })
    assert blocked is not None

    for node in NODES.values():
        if node.get("type") == "Query":
            node["status"] = "sufficient"
            node["sufficiency_score"] = 0.8
    for node in NODES.values():
        if node.get("analysis_type") == "gap":
            node["status"] = "resolved"
    converged = mm.assess_convergence("goal")
    assert converged["research_state"] == "REPORT_READY", converged
    allowed = ResearchStateMiddleware()._gate_reporter({
        "name": "task", "id": "call2", "args": {"subagent_type": "reporter"},
    })
    assert allowed is None and NODES["goal"]["research_state"] == "REPORTING"
    print("ALL TREE STATE-MACHINE CHECKS PASSED")


if __name__ == "__main__":
    main()
