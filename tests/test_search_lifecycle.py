"""Standalone checks for SearchRun lifecycle, retries, budget, and state gates."""

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
        "id": "goal",
        "type": "UserRequest",
        "research_state": "RESEARCHING",
        "max_search_rounds": 10,
        "dispatched_search_rounds": 0,
        "successful_search_rounds": 0,
    },
    "q1": {
        "id": "q1",
        "type": "Query",
        "handle": "q1",
        "text": "successful query",
        "status": "pending",
        "search_attempts": 0,
        "successful_search_runs": 0,
        "required_for_parent": True,
    },
    "q2": {
        "id": "q2",
        "type": "Query",
        "handle": "q2",
        "text": "empty query",
        "status": "pending",
        "search_attempts": 0,
        "successful_search_runs": 0,
        "required_for_parent": True,
    },
}
EDGES = [
    {"source": "goal", "target": "q1", "type": "HAS_QUERY"},
    {"source": "goal", "target": "q2", "type": "HAS_QUERY"},
]
SEQ = 0


def _type_name(value):
    return value.value if hasattr(value, "value") else str(value)


def install_fakes():
    def get_node(node_id):
        return dict(NODES.get(node_id, {}))

    def search_nodes(kind, filt=None):
        wanted = _type_name(kind).replace("_", "").lower()
        nodes = [
            dict(node)
            for node in NODES.values()
            if str(node.get("type", "")).replace("_", "").lower() == wanted
        ]
        return [node for node in nodes if all(node.get(k) == v for k, v in (filt or {}).items())]

    def upsert(kind, attrs, dedupe_key=None):
        NODES[dedupe_key].update(attrs)
        return dedupe_key

    def add_edge(source, target, edge_type, attributes=None):
        edge = {
            "source": source,
            "target": target,
            "type": _type_name(edge_type),
            **(attributes or {}),
        }
        if edge not in EDGES:
            EDGES.append(edge)
        return f"{source}-{edge['type']}-{target}"

    def node_edges(node_id, direction="both"):
        if direction == "out":
            return [dict(edge) for edge in EDGES if edge["source"] == node_id]
        if direction == "in":
            return [dict(edge) for edge in EDGES if edge["target"] == node_id]
        return [
            dict(edge)
            for edge in EDGES
            if edge["source"] == node_id or edge["target"] == node_id
        ]

    def parent(query_id):
        return next((
            edge["source"]
            for edge in EDGES
            if edge["target"] == query_id and edge["type"].lower() in {"has_query", "parent_of"}
        ), None)

    def claim(query_id, goal_id):
        global SEQ
        query = NODES[query_id]
        goal = NODES[goal_id]
        maximum = goal["max_search_rounds"]
        if (
            query["status"] != "pending"
            or query.get("successful_search_runs", 0)
            or (maximum > 0 and goal["dispatched_search_rounds"] >= maximum)
        ):
            return {}
        SEQ += 1
        run_id = f"run{SEQ}"
        query["status"] = "searching"
        query["search_attempts"] = query.get("search_attempts", 0) + 1
        goal["dispatched_search_rounds"] += 1
        NODES[run_id] = {
            "id": run_id,
            "type": "SearchRun",
            "query_id": query_id,
            "status": "running",
            "attempt": query["search_attempts"],
        }
        add_edge(query_id, run_id, EdgeType.SEARCHED_BY)
        return {"search_run_id": run_id, "attempt": query["search_attempts"]}

    def add_typed(kind, attrs):
        global SEQ
        SEQ += 1
        node_id = f"node{SEQ}"
        NODES[node_id] = {"id": node_id, "type": _type_name(kind), **attrs}
        return node_id

    graph_tools.get_node = get_node
    graph_tools.search_nodes = search_nodes
    graph_tools.upsert_node = upsert
    graph_tools.add_edge = add_edge
    graph_tools.get_node_edges = node_edges
    graph_tools.get_query_parent = parent
    graph_tools.get_all_nodes = lambda: [dict(node) for node in NODES.values()]
    graph_tools.get_all_edges = lambda: [dict(edge) for edge in EDGES]
    graph_tools.claim_query_search = claim
    graph_tools.increment_successful_search_rounds = lambda goal_id: NODES[goal_id].update({
        "successful_search_rounds": NODES[goal_id].get("successful_search_rounds", 0) + 1,
    })
    graph_tools.save_graph = lambda: None
    graph_tools.create_source = lambda url, title=None, source_type=None, **attrs: add_typed(
        "Source", {"url": url, "title": title, "source_type": source_type, **attrs}
    )
    graph_tools.create_document = lambda text, source_id=None: add_typed(
        "Document", {"text": text, "source_id": source_id}
    )
    graph_tools.create_claim = lambda statement, document_id=None, source_id=None: add_typed(
        "Claim", {"statement": statement}
    )
    graph_tools.create_evidence = lambda claim, document_id=None, source_id=None, supports_claim_id=None: add_typed(
        "Evidence", {"claim": claim}
    )
    graph_tools.create_conflict = lambda description, evidence_ids, conflict_type="factual", resolution_status="unresolved": add_typed(
        "Conflict",
        {
            "description": description,
            "conflict_type": conflict_type,
            "resolution_status": resolution_status,
        },
    )


def main():
    install_fakes()
    mm = MemoryManager(model=object())

    first = mm.prepare_search("q1")
    assert first.get("search_run_id"), first
    duplicate_claim = mm.prepare_search("q1")
    assert duplicate_claim.get("error") and NODES["goal"]["dispatched_search_rounds"] == 1

    result = mm.submit_search_result(first["search_run_id"], "q1", {
        "sources": [
            {"local_ref": "s1", "url": "https://example.com/valid"},
            {"local_ref": "invalid"},
        ],
        "documents": [
            {"local_ref": "d1", "document_summary": "valid document", "source_ref": "s1"},
        ],
        "claims": [
            {"local_ref": "c1", "statement": "valid claim", "document_ref": "d1", "source_ref": "s1"},
        ],
        "evidence": [
            {
                "statement": "valid evidence",
                "document_ref": "d1",
                "source_ref": "s1",
                "supports_or_contradicts": "c1",
            },
        ],
    })
    assert result["status"] == "succeeded" and result["written"]["sources"] == 1, result
    assert result["written"]["evidence"] == 1 and NODES["q1"]["status"] == "assessing", result
    repeated_submit = mm.submit_search_result(first["search_run_id"], "q1", {})
    assert repeated_submit.get("error"), repeated_submit
    assert mm.prepare_search("q1").get("error")

    for expected_status in ("pending", "pending", "blocked"):
        prepared = mm.prepare_search("q2")
        assert prepared.get("search_run_id"), prepared
        empty = mm.submit_search_result(prepared["search_run_id"], "q2", {})
        assert empty["status"] == "empty" and empty["query_status"] == expected_status, empty
    assert mm.prepare_search("q2").get("error")

    NODES["qbad"] = {
        "id": "qbad",
        "type": "Query",
        "handle": "q3",
        "text": "malformed package",
        "status": "pending",
        "search_attempts": 0,
        "successful_search_runs": 0,
        "required_for_parent": True,
    }
    EDGES.append({"source": "goal", "target": "qbad", "type": "HAS_QUERY"})
    malformed_run = mm.prepare_search("qbad")
    malformed = mm.submit_search_result(malformed_run["search_run_id"], "qbad", {
        "evidence": [{"statement": "untraceable evidence"}],
    })
    assert malformed.get("error") and NODES["qbad"]["status"] == "pending", malformed
    assert NODES[malformed_run["search_run_id"]]["status"] == "failed"

    NODES["q3"] = {
        "id": "q3",
        "type": "Query",
        "handle": "q4",
        "text": "budget query",
        "status": "pending",
        "search_attempts": 0,
        "successful_search_runs": 0,
        "required_for_parent": True,
    }
    NODES["gap"] = {
        "id": "gap",
        "type": "Analysis",
        "analysis_type": "gap",
        "status": "candidate",
        "required_for_parent": False,
    }
    NODES["conflict"] = {
        "id": "conflict",
        "type": "Conflict",
        "resolution_status": "unresolved",
    }
    EDGES.extend([
        {"source": "goal", "target": "q3", "type": "HAS_QUERY"},
        {"source": "q3", "target": "gap", "type": "HAS_GAP"},
    ])
    NODES["goal"]["max_search_rounds"] = NODES["goal"]["dispatched_search_rounds"]
    exhausted = mm.prepare_search("q3")
    assert exhausted.get("research_state") == "BUDGET_EXHAUSTED", exhausted
    assert NODES["gap"]["status"] == "deferred_budget"
    assert NODES["conflict"]["resolution_status"] == "disclosed"
    try:
        research_state.update_goal({"research_state": "RESEARCHING"})
    except ValueError:
        pass
    else:
        raise AssertionError("BUDGET_EXHAUSTED -> RESEARCHING must be rejected")
    allowed = ResearchStateMiddleware()._gate_reporter({
        "name": "task",
        "id": "budget-report",
        "args": {"subagent_type": "reporter"},
    })
    assert allowed is None and NODES["goal"]["reporting_from_state"] == "BUDGET_EXHAUSTED"

    print("ALL SEARCH LIFECYCLE CHECKS PASSED")


if __name__ == "__main__":
    main()
