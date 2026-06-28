"""Standalone checks for marginal-utility portfolio helpers."""

import sys
from pathlib import Path

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from agents.memory_manager import (  # noqa: E402
    MemoryManager,
    _ensure_subject_query_coverage,
    _extract_excluded_domains,
    _is_research_objective,
)
from tools import graph_tools, report_tools, research_state  # noqa: E402


def test_minimum_initial_query_cover():
    objectives = [
        {"objective_key": "a", "requirement": "must"},
        {"objective_key": "b", "requirement": "must"},
        {"objective_key": "c", "requirement": "must"},
    ]
    candidates = [
        {"text": "one broad query", "objective_keys": ["a", "b", "c"]},
        {"text": "only a", "objective_keys": ["a"]},
        {"text": "only b", "objective_keys": ["b"]},
        {"text": "only c", "objective_keys": ["c"]},
    ]
    selected = MemoryManager._select_initial_queries(candidates, objectives)
    assert [item["text"] for item in selected] == ["one broad query"], selected


def test_time_window_filter():
    graph_tools.get_query_evaluation_subgraph = lambda _query_id: {
        "nodes": [{"id": "s1", "type": "Source", "published_at": "2025-01-01"}],
    }
    assert not MemoryManager._query_evidence_within_time_window("q1", "2018-2024")
    assert MemoryManager._query_evidence_within_time_window("q1", None)
    graph_tools.get_query_evaluation_subgraph = lambda _query_id: {
        "nodes": [
            {"id": "s1", "type": "Source", "published_at": "2024-01-01"},
            {"id": "s2", "type": "Source", "published_at": "2025-01-01"},
        ],
    }
    assert not MemoryManager._query_evidence_within_time_window("q1", "2018-2024")


def test_research_objectives_keep_citation_requirements():
    identity_objective = {
        "objective_key": "identity-scope",
        "description": "Establish what the named artifact refers to and resolve ambiguities.",
        "acceptance_criteria": [
            "Provides discovery context with at least one citation.",
            "Clarifies alternate referents with supporting references.",
        ],
    }
    structure_objective = {
        "objective_key": "article-structure-style",
        "description": "Enable construction of a Wikipedia-style article structure with lead, sections, and references.",
        "acceptance_criteria": [
            "Provides enough sourced material for bracketed citations.",
        ],
    }
    assert _is_research_objective(identity_objective)
    assert not _is_research_objective(structure_objective)


def test_named_subject_queries_expand_beyond_one_broad_query():
    objectives = [
        {
            "objective_key": "identity-scope",
            "requirement": "must",
            "description": "Establish what the Ring of Nestor refers to, including discovery and current location.",
            "acceptance_criteria": ["Provides discovery context with at least one citation."],
        },
        {
            "objective_key": "historical-archaeological-context",
            "requirement": "must",
            "description": "Describe the historical and archaeological context of the Ring of Nestor.",
            "acceptance_criteria": ["Situates the object chronologically and culturally."],
        },
        {
            "objective_key": "interpretations-significance",
            "requirement": "must",
            "description": "Summarize major scholarly interpretations and significance of the Ring of Nestor.",
            "acceptance_criteria": [
                "Provides at least two scholarly interpretations.",
                "Notes differing views with supporting references.",
            ],
        },
    ]
    selected = [
        {
            "text": "Ring of Nestor gold ring archaeological artifact Mycenaean discovery site current location",
            "importance": "core",
            "objective_keys": ["identity-scope", "historical-archaeological-context"],
            "acceptance_criteria": ["Directly answer the user request."],
        }
    ]
    expanded = _ensure_subject_query_coverage(
        "Write a Wikipedia-style article about 'Ring of Nestor' with neutral coverage and citations.",
        "English",
        objectives,
        selected,
    )
    assert len(expanded) >= 3, expanded
    assert any(item.get("objective_keys") == ["identity-scope"] for item in expanded), expanded
    assert any(item.get("objective_keys") == ["interpretations-significance"] for item in expanded), expanded


def test_excluded_domains_are_recovered_from_banned_sources_text():
    domains = _extract_excluded_domains(
        "Do not consult any Wikipedia pages or access https://en.wikipedia.org/wiki/Ring_of_Nestor.",
        "Use only non-Wikipedia web sources.",
    )
    assert "wikipedia.org" in domains, domains
    assert "en.wikipedia.org" in domains, domains


def test_report_validation():
    conflict = {
        "id": "c1",
        "type": "Conflict",
        "resolution_status": "disclosed",
        "description": "Optimus hand parameter differs across sources",
    }
    section = {"id": "r1", "type": "ReportSection", "title": "Findings", "content": "fact " * 30}
    graph_tools.search_nodes = lambda kind, _filter: {
        "conflict": [conflict],
        "report_section": [section],
    }.get(kind, [])
    graph_tools.get_node_edges = lambda _node_id, direction="out": []
    issues = report_tools.validate_final_report("Research Graph internal draft")
    assert any("internal process term" in issue for issue in issues), issues
    assert any("no evidence/source binding" in issue for issue in issues), issues

    graph_tools.get_node_edges = lambda _node_id, direction="out": [
        {"source": "r1", "target": "s1", "type": "USES"},
    ]
    clean = report_tools.validate_final_report(
        "Optimus hand parameter differs across sources. This difference remains unresolved."
    )
    assert not clean, clean


def test_identity_objective_stays_open_when_core_identity_conflicts_remain():
    nodes = {
        "goal": {
            "id": "goal",
            "type": "UserRequest",
            "research_state": "RESEARCHING",
            "scope_mode": "bounded",
            "successful_search_rounds": 1,
            "portfolio_revision": 1,
            "evaluated_portfolio_revision": 0,
        },
        "o1": {
            "id": "o1",
            "type": "Analysis",
            "analysis_type": "objective",
            "objective_key": "identity-scope",
            "description": "Clarify what the named artifact refers to and resolve provenance ambiguity.",
            "requirement": "must",
            "weight": 1.0,
            "coverage": 0.0,
            "confidence": 0.0,
            "status": "open",
            "low_gain_streak": 0,
            "last_evaluated_successful_rounds": 0,
        },
        "q1": {
            "id": "q1",
            "type": "Query",
            "handle": "q1",
            "text": "\"Ring of Nestor\" identity scope provenance discovery authenticity",
            "status": "assessing",
            "sufficiency_score": 0.9,
            "objective_keys": ["identity-scope"],
            "covered": ["identity"],
        },
        "c1": {
            "id": "c1",
            "type": "Conflict",
            "description": "Conflicting provenance and authenticity claims leave the artifact's identity unsettled.",
            "conflict_type": "factual",
            "resolution_status": "unresolved",
        },
        "run1": {
            "id": "run1",
            "type": "SearchRun",
            "query_id": "q1",
            "status": "succeeded",
        },
    }
    edges = [
        {"source": "goal", "target": "o1", "type": "HAS_OBJECTIVE"},
        {"source": "goal", "target": "q1", "type": "HAS_QUERY"},
        {"source": "q1", "target": "run1", "type": "SEARCHED_BY"},
        {"source": "run1", "target": "c1", "type": "PRODUCED"},
    ]

    def get_node(node_id):
        return dict(nodes.get(node_id, {}))

    def search_nodes(kind, filt=None):
        wanted = kind.replace("_", "").lower()
        out = [
            dict(node) for node in nodes.values()
            if str(node.get("type", "")).replace("_", "").lower() == wanted
        ]
        return [node for node in out if all(node.get(k) == v for k, v in (filt or {}).items())]

    def get_node_edges(node_id, direction="both"):
        if direction == "out":
            return [dict(edge) for edge in edges if edge["source"] == node_id]
        if direction == "in":
            return [dict(edge) for edge in edges if edge["target"] == node_id]
        return [dict(edge) for edge in edges if node_id in {edge["source"], edge["target"]}]

    def get_query_children(parent_id):
        return [
            edge["target"]
            for edge in edges
            if edge["source"] == parent_id and edge["type"].lower() in {"has_query", "parent_of"}
        ]

    def get_query_parent(query_id):
        return next((
            edge["source"]
            for edge in edges
            if edge["target"] == query_id and edge["type"].lower() in {"has_query", "parent_of"}
        ), None)

    def upsert_node(_kind, attrs, dedupe_key=None):
        nodes[dedupe_key].update(attrs)
        return dedupe_key

    graph_tools.get_node = get_node
    graph_tools.search_nodes = search_nodes
    graph_tools.get_node_edges = get_node_edges
    graph_tools.get_query_children = get_query_children
    graph_tools.get_query_parent = get_query_parent
    graph_tools.upsert_node = upsert_node

    research_state.get_goal = lambda goal_id=None: dict(nodes["goal"])

    class FakeModel:
        def invoke(self, _prompt):
            class R:
                content = (
                    '{"objectives": [{"objective_key": "identity-scope", "coverage": 0.9, '
                    '"confidence": 0.9, "reason": "identity looks covered"}]}'
                )

            return R()

    mm = MemoryManager(model=FakeModel())
    result = mm.evaluate_research_portfolio("goal")
    objective = next(item for item in result["objectives"] if item["objective_key"] == "identity-scope")
    assert objective["status"] == "open", objective
    assert float(objective["confidence"]) < 0.65, objective
    assert "Unresolved provenance/authenticity conflicts" in objective["assessment_reason"], objective


def main():
    test_minimum_initial_query_cover()
    test_time_window_filter()
    test_research_objectives_keep_citation_requirements()
    test_named_subject_queries_expand_beyond_one_broad_query()
    test_excluded_domains_are_recovered_from_banned_sources_text()
    test_report_validation()
    test_identity_objective_stays_open_when_core_identity_conflicts_remain()
    print("ALL MARGINAL PORTFOLIO CHECKS PASSED")


if __name__ == "__main__":
    main()
