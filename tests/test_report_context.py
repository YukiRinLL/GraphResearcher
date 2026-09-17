"""Reporter context Query projection regression checks."""

import sys
from pathlib import Path

repo_dir = Path(__file__).parent.parent
sys.path.insert(0, str(repo_dir / "src"))

from agents.memory_manager import MemoryManager  # noqa: E402
from tools import graph_tools, report_tools  # noqa: E402


def main() -> None:
    goal = {
        "id": "request-1",
        "type": "UserRequest",
        "request": "Write a cited report.",
        "language": "English",
    }
    queries = [
        {
            "id": "query-10",
            "type": "Query",
            "handle": "q2.10",
            "text": "Later child",
            "importance": "core",
            "objective_keys": ["objective-1"],
            "successful_search_runs": 1,
            "covered": "not-a-list",
        },
        {
            "id": "query-blocked",
            "type": "Query",
            "handle": "q3",
            "text": "No valid evidence",
            "importance": "core",
            "successful_search_runs": 0,
            "covered": ["Must not be exposed"],
        },
        {
            "id": "query-2",
            "type": "Query",
            "handle": "q2.2",
            "text": "Earlier child",
            "importance": "supporting",
            "successful_search_runs": 1,
            "covered": [" First topic ", "First topic", "", None, "Second topic"],
        },
        {
            "id": "query-root",
            "type": "Query",
            "handle": "q1",
            "text": "Root topic",
            "importance": "core",
            "successful_search_runs": 1,
            "covered": [],
        },
        {
            "id": "query-legacy",
            "type": "Query",
            "handle": "legacy",
            "text": "Invalid legacy handle",
            "importance": "peripheral",
            "successful_search_runs": 1,
            "covered": ["Legacy topic"],
        },
        {
            "id": "query-missing-marker",
            "type": "Query",
            "handle": "q4",
            "text": "Missing success marker",
            "importance": "core",
            "covered": ["Must not be exposed"],
        },
    ]

    graph_tools.get_node = lambda node_id: dict(goal) if node_id == goal["id"] else {}
    graph_tools.search_nodes = lambda kind, _filters=None: (
        [dict(goal)]
        if kind == "user_request"
        else [dict(query) for query in queries]
        if kind == "query"
        else []
    )
    report_tools.get_disclosed_conflicts = lambda: []

    def unexpected_registry_build():
        raise AssertionError("Outline context must not build the reference registry")

    report_tools.build_reference_registry = unexpected_registry_build

    context = MemoryManager(model=object()).export_report_context()

    assert set(context) == {
        "user_request",
        "research_goal",
        "language",
        "objectives",
        "rubrics",
        "blocked_sources",
        "queries",
        "disclosed_conflicts",
    }
    assert context["research_goal"] == goal["request"]
    assert context["objectives"] == []
    assert context["language"] == goal["language"]
    assert context["user_request"] == goal["request"]
    assert context["rubrics"] == []
    assert context["blocked_sources"] == []
    assert context["queries"] == [
        {
            "ref": "q1",
            "text": "Root topic",
            "supported_topics": [],
            "objective_keys": [],
            "target_components": [],
            "target_sections": [],
            "analysis_mode": "none",
            "required_evidence_types": [],
            "rubric_ids": [],
        },
        {
            "ref": "q2.2",
            "text": "Earlier child",
            "supported_topics": ["First topic", "Second topic"],
            "objective_keys": [],
            "target_components": [],
            "target_sections": [],
            "analysis_mode": "none",
            "required_evidence_types": [],
            "rubric_ids": [],
        },
        {
            "ref": "q2.10",
            "text": "Later child",
            "supported_topics": [],
            "objective_keys": ["objective-1"],
            "target_components": [],
            "target_sections": [],
            "analysis_mode": "none",
            "required_evidence_types": [],
            "rubric_ids": [],
        },
        {
            "ref": "legacy",
            "text": "Invalid legacy handle",
            "supported_topics": ["Legacy topic"],
            "objective_keys": [],
            "target_components": [],
            "target_sections": [],
            "analysis_mode": "none",
            "required_evidence_types": [],
            "rubric_ids": [],
        },
    ]
    assert all(
        set(query) == {
            "ref",
            "text",
            "supported_topics",
            "objective_keys",
            "target_components",
            "target_sections",
            "analysis_mode",
            "required_evidence_types",
            "rubric_ids",
        }
        for query in context["queries"]
    )
    assert "importance" not in str(context)


if __name__ == "__main__":
    main()
