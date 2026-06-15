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
        "scope_mode": "bounded", "portfolio_revision": 1, "evaluated_portfolio_revision": 1,
    },
    "o1": {
        "id": "o1", "type": "Analysis", "analysis_type": "objective",
        "objective_key": "core-answer", "requirement": "must", "weight": 1.0,
        "coverage": 0.0, "confidence": 0.0, "status": "open",
    },
    "q1": {
        "id": "q1", "type": "Query", "handle": "q1", "text": "core route", "status": "assessing",
        "priority": 1.0, "sem": 1.0, "required_for_parent": True, "acceptance_criteria": [],
        "objective_keys": ["core-answer"],
    },
    "q2": {
        "id": "q2", "type": "Query", "handle": "q2", "text": "sibling route", "status": "pending",
        "priority": 0.76, "sem": 0.6, "required_for_parent": True, "acceptance_criteria": [],
        "objective_keys": ["core-answer"],
    },
    "r1": {"id": "r1", "type": "SearchRun", "query_id": "q1", "status": "succeeded"},
    "r2": {"id": "r2", "type": "SearchRun", "query_id": "q2", "status": "succeeded"},
    "shared": {"id": "shared", "type": "Source", "url": "https://example.com"},
    "e1": {"id": "e1", "type": "Evidence", "claim": "owned evidence"},
    "e2": {"id": "e2", "type": "Evidence", "claim": "sibling evidence"},
}
EDGES = [
    {"source": "goal", "target": "o1", "type": "HAS_OBJECTIVE"},
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
        parent_handle = parent_node.get("handle")
        handle = f"{parent_handle}.{len(children(parent_id)) + 1}" if parent_handle else f"q{len(children(parent_id)) + 1}"
        NODES[node_id] = {
            "id": node_id, "type": "Query", "handle": handle, "text": text, "status": "pending",
            "priority": parent_node.get("priority", 1.0) * 0.85, "sem": 0.6,
            "required_for_parent": attrs.get("required_for_parent", False),
            "acceptance_criteria": acceptance_criteria or [],
            "objective_keys": attrs.get("objective_keys") or [],
            "search_subject_key": attrs.get("search_subject_key"),
            "recovery_objective_key": attrs.get("recovery_objective_key"),
        }
        edge_type = EdgeType.HAS_QUERY if parent_node.get("type") == "UserRequest" else EdgeType.PARENT_OF
        add_edge(parent_id, node_id, edge_type)
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
                {
                    "description": "gap one", "importance": "core", "acceptance_criteria": ["one"],
                    "objective_keys": ["core-answer"], "gap_category": "missing_core_evidence",
                    "search_subject_key": "shared-subject", "decision_impact": 1.0, "confidence_gain": 1.0,
                },
                {
                    "description": "gap two", "importance": "supporting", "acceptance_criteria": ["two"],
                    "objective_keys": ["core-answer"], "gap_category": "verification",
                    "search_subject_key": "shared-subject", "decision_impact": 0.8, "confidence_gain": 0.8,
                },
            ],
            "recommendation": "needs_expansion",
            "reason": "two gaps",
        },
        {"objectives": [{"objective_key": "core-answer", "coverage": 0.4, "confidence": 0.4}]},
        {"queries": [{"text": "combined child query", "importance": "core", "acceptance_criteria": ["one", "two"]}]},
        {
            "sufficiency_score": 0.8,
            "covered": ["base"],
            "gaps": [{
                "description": "optional detail", "gap_category": "detail",
                "objective_keys": ["core-answer"], "search_subject_key": "detail",
                "decision_impact": 0.1, "confidence_gain": 0.1,
            }],
            "recommendation": "needs_expansion",
        },
        {"objectives": [{"objective_key": "core-answer", "coverage": 0.8, "confidence": 0.75}]},
        {"objectives": [
            {"objective_key": "core-answer", "coverage": 0.8, "confidence": 0.75},
            {"objective_key": "hard-answer", "coverage": 0.1, "confidence": 0.1},
        ]},
        {"objectives": [
            {"objective_key": "core-answer", "coverage": 0.8, "confidence": 0.75},
            {"objective_key": "hard-answer", "coverage": 0.1, "confidence": 0.1},
        ]},
        {"objectives": [
            {"objective_key": "core-answer", "coverage": 0.8, "confidence": 0.75},
            {"objective_key": "hard-answer", "coverage": 0.1, "confidence": 0.1},
            {"objective_key": "exhaustive-answer", "coverage": 0.1, "confidence": 0.1},
        ]},
        {"objectives": [
            {"objective_key": "core-answer", "coverage": 0.8, "confidence": 0.75},
            {"objective_key": "hard-answer", "coverage": 0.1, "confidence": 0.1},
            {"objective_key": "exhaustive-answer", "coverage": 0.1, "confidence": 0.1},
        ]},
        {"fatal_unresolved_conflicts": [], "reason": "done"},
    ]))
    actions = mm.get_next_actions()
    assert actions[0]["action"] == "assess_query", actions
    assert actions[0]["query_id"] == "q1" and actions[0]["query_handle"] == "q1", actions
    assert "exact_query_id" not in actions[0], actions
    assessed = mm.assess_query("q1")
    assert assessed["status"] == "needs_expansion" and len(assessed["created_gaps"]) == 2, assessed
    portfolio = mm.evaluate_research_portfolio("goal")
    assert len(portfolio["selected_gap_ids"]) == 2, portfolio
    expanded = mm.expand_gaps("q1")
    assert len(expanded["created"]) == 1 and NODES["q1"]["status"] == "waiting_children", expanded
    assert len(expanded["created"][0]["gap_ids"]) == 2, expanded
    assert all(NODES[c["id"]]["priority"] < NODES["q1"]["priority"] for c in expanded["created"])

    NODES["qlow"] = {
        "id": "qlow", "type": "Query", "handle": "q3", "text": "repeated branch", "status": "assessing",
        "priority": 0.5, "sem": 0.6, "required_for_parent": False, "low_novelty_streak": 2,
        "objective_keys": ["core-answer"],
    }
    EDGES.append({"source": "goal", "target": "qlow", "type": "HAS_QUERY"})
    low = mm.assess_query("qlow")
    assert low["status"] == "needs_expansion" and low["created_gaps"], low
    low_portfolio = mm.evaluate_research_portfolio("goal")
    assert low_portfolio["deferred_gap_ids"] and NODES["qlow"]["status"] == "sufficient", low_portfolio

    NODES["ohard"] = {
        "id": "ohard", "type": "Analysis", "analysis_type": "objective",
        "objective_key": "hard-answer", "requirement": "must", "weight": 1.0,
        "coverage": 0.1, "confidence": 0.1, "status": "open",
        "low_gain_streak": 0, "last_evaluated_successful_rounds": 2,
    }
    EDGES.append({"source": "goal", "target": "ohard", "type": "HAS_OBJECTIVE"})
    NODES["goal"]["successful_search_rounds"] = 3
    mm.evaluate_research_portfolio("goal")
    assert NODES["ohard"]["low_gain_streak"] == 1
    NODES["goal"]["successful_search_rounds"] = 4
    mm.evaluate_research_portfolio("goal")
    assert NODES["ohard"]["status"] == "blocked_best_effort"

    NODES["oexhaustive"] = {
        "id": "oexhaustive", "type": "Analysis", "analysis_type": "objective",
        "objective_key": "exhaustive-answer", "requirement": "must", "weight": 1.0,
        "coverage": 0.1, "confidence": 0.1, "status": "open",
        "low_gain_streak": 0, "last_evaluated_successful_rounds": 4,
    }
    EDGES.append({"source": "goal", "target": "oexhaustive", "type": "HAS_OBJECTIVE"})
    NODES["goal"]["scope_mode"] = "exhaustive"
    NODES["goal"]["successful_search_rounds"] = 5
    mm.evaluate_research_portfolio("goal")
    NODES["goal"]["successful_search_rounds"] = 6
    mm.evaluate_research_portfolio("goal")
    assert NODES["oexhaustive"]["low_gain_streak"] >= 2
    assert NODES["oexhaustive"]["status"] == "open"
    NODES["goal"]["scope_mode"] = "bounded"

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
    general_blocked = ResearchStateMiddleware()._gate_reporter({
        "name": "task", "id": "general1", "args": {"subagent_type": "general-purpose"},
    })
    assert general_blocked is not None and general_blocked.status == "error"

    NODES["orecover"] = {
        "id": "orecover", "type": "Analysis", "analysis_type": "objective",
        "objective_key": "recover-answer", "description": "recover missing answer",
        "acceptance_criteria": ["recover"], "requirement": "must", "weight": 1.0,
        "coverage": 0.0, "confidence": 0.0, "status": "open",
    }
    EDGES.append({"source": "goal", "target": "orecover", "type": "HAS_OBJECTIVE"})
    recovery = mm._recover_unactionable_research(NODES["goal"], [
        dict(node) for node in NODES.values() if node.get("type") == "Query"
    ])
    assert recovery["action"] == "dispatch_searcher" and recovery["query_id"].startswith("child"), recovery
    assert "exact_query_id" not in recovery and recovery["query_handle"].startswith("q"), recovery
    NODES["orecover"].update({"coverage": 0.8, "confidence": 0.75, "status": "satisfied"})

    for node in NODES.values():
        if node.get("type") == "Query":
            node["status"] = "sufficient"
            node["sufficiency_score"] = 0.8
    for node in NODES.values():
        if node.get("analysis_type") == "gap":
            node["status"] = "resolved"
    NODES["o1"].update({"coverage": 0.8, "confidence": 0.75, "status": "satisfied"})
    NODES["oexhaustive"].update({"coverage": 0.8, "confidence": 0.75, "status": "satisfied"})
    NODES["goal"]["evaluated_portfolio_revision"] = NODES["goal"]["portfolio_revision"]
    converged = mm.assess_convergence("goal")
    assert converged["research_state"] == "REPORT_READY", converged
    original_validate_query_tree = graph_tools.validate_query_tree
    graph_tools.validate_query_tree = lambda: {"valid": False, "orphans": ["q1"]}
    allowed = ResearchStateMiddleware()._gate_reporter({
        "name": "task", "id": "call2", "args": {"subagent_type": "reporter"},
    })
    assert allowed is None and NODES["goal"]["research_state"] == "REPORTING"
    assert NODES["goal"]["reporter_warnings"] == [
        "Query tree validation failed before Reporter authorization"
    ]
    graph_tools.validate_query_tree = original_validate_query_tree
    loop_guard = ResearchStateMiddleware(max_repeated_failures=3)
    repeated_call = {
        "name": "task",
        "id": "general-loop",
        "args": {"subagent_type": "general-purpose"},
    }
    for _ in range(3):
        blocked_result = loop_guard._gate_reporter(repeated_call)
        loop_guard._record_tool_result(repeated_call, blocked_result)
    assert NODES["goal"]["research_state"] == "FAILED"
    assert "Repeated identical failed tool action" in NODES["goal"]["last_error"]
    print("ALL TREE STATE-MACHINE CHECKS PASSED")


if __name__ == "__main__":
    main()
