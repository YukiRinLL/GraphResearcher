"""Offline checks for the my_agent-style global Reporter input contract."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch


SRC_DIR = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from agents import reporter_global_workflow as workflow  # noqa: E402


def test_prompt_contains_my_agent_final_writer_inputs() -> None:
    packet = {
        "research_brief": {"user_request": "original request", "research_goal": "research brief"},
        "required_data_points": ["data point"],
        "required_structure": ["comparison"],
        "findings": [{"query": {"ref": "q1"}, "items": [{"text": "finding"}]}],
        "draft_report": "# Draft\n\nDraft answer.",
        "conflicts": [{"description": "conflict"}],
        "citation_registry": [{"n": 1, "title": "Source", "url": "https://example.com"}],
    }

    prompt = workflow._prompt(packet)

    assert "research brief" in prompt
    assert "finding" in prompt
    assert "# Draft" in prompt
    assert "data point" in prompt
    assert "comparison" in prompt
    assert "https://example.com" in prompt


def test_task_requirements_extract_explicit_structure() -> None:
    requirements = workflow._derive_task_requirements(
        "请分两部分回答：1. 分析机制；2. 给出具体数据。请制作一个对比表，截至2024年。"
    )

    assert requirements["requires_table"] is True
    assert requirements["requires_exact_values"] is True
    assert requirements["has_time_scope"] is True
    assert len(requirements["explicit_items"]) >= 2
    assert requirements["language_hint"] == "zh"


def test_draft_citations_are_added_to_global_registry() -> None:
    context = {
        "user_request": "request",
        "research_goal": "brief",
        "language": "en",
        "queries": [],
        "objectives": [],
        "disclosed_conflicts": [],
    }
    evidence = {
        "q": {
            "items": [
                {
                    "id": "e1",
                    "type": "Evidence",
                    "text": "Finding",
                    "citations": [1],
                    "sources": [],
                }
            ],
            "next_offset": None,
        }
    }

    with (
        patch.object(workflow.report_tools, "get_report_evidence", return_value={"items": [], "next_offset": None}),
        patch.object(workflow.report_tools, "build_cited_evidence_report", return_value="Draft claim.[2]"),
        patch.object(
            workflow.report_tools,
            "build_reference_registry",
            return_value=[
                {"n": 1, "source_id": "s1", "title": "One", "url": "https://one.example"},
                {"n": 2, "source_id": "s2", "title": "Two", "url": "https://two.example"},
            ],
        ),
    ):
        packet = workflow._build_packet(context)

    assert packet["draft_report"] == "Draft claim.[2]"
    assert packet["task_requirements"]["language_hint"] == "en"
    assert [entry["n"] for entry in packet["citation_registry"]] == [2]
    del evidence


def test_packet_prioritizes_unmet_objective_queries() -> None:
    context = {
        "user_request": "request",
        "research_goal": "brief",
        "queries": [
            {"ref": "q1", "objective_keys": ["covered"]},
            {"ref": "q2", "objective_keys": ["unmet"]},
        ],
        "objectives": [
            {"objective_key": "covered", "requirement": "must", "status": "satisfied", "coverage": 1.0},
            {"objective_key": "unmet", "requirement": "must", "status": "blocked", "coverage": 0.1},
        ],
        "disclosed_conflicts": [],
    }

    with (
        patch.object(workflow.report_tools, "get_report_evidence", return_value={"items": [], "next_offset": None}),
        patch.object(workflow.report_tools, "build_cited_evidence_report", return_value=""),
        patch.object(workflow.report_tools, "build_reference_registry", return_value=[]),
    ):
        packet = workflow._build_packet(context)

    assert packet["findings"] == []


def test_packet_deduplicates_evidence_and_limits_each_query() -> None:
    context = {
        "user_request": "request",
        "research_goal": "brief",
        "queries": [
            {"ref": "q1", "objective_keys": []},
            {"ref": "q2", "objective_keys": []},
        ],
        "objectives": [],
        "disclosed_conflicts": [],
    }
    pages = {
        "q1": {
            "items": [
                {"id": "e1", "type": "Evidence", "text": "same claim", "citations": [1]},
                {"id": "e2", "type": "Evidence", "text": "x" * 2000, "citations": [2]},
            ],
            "next_offset": None,
        },
        "q2": {
            "items": [
                {"id": "e1", "type": "Evidence", "text": "same claim", "citations": [1]},
                {"id": "e3", "type": "Evidence", "text": "unique claim", "citations": [3]},
            ],
            "next_offset": None,
        },
    }

    with (
        patch.object(workflow.report_tools, "get_report_evidence", side_effect=lambda ref, **_: pages[ref]),
        patch.object(workflow.report_tools, "build_cited_evidence_report", return_value=""),
        patch.object(workflow.report_tools, "build_reference_registry", return_value=[]),
        patch.object(workflow.config, "GR_GLOBAL_PACKET_TOKENS", 1_000),
    ):
        packet = workflow._build_packet(context)

    ids = [item["id"] for group in packet["findings"] for item in group["items"]]
    assert ids.count("e1") == 1
    assert "e3" in ids
    assert packet["budget"]["deduplicated_items"] == len(set(ids))


def test_failed_run_with_evidence_is_authorized_for_best_effort_report() -> None:
    goal = {"research_state": workflow.research_state.FAILED, "request": "request"}
    with (
        patch.object(workflow.research_state, "get_goal", return_value=goal),
        patch.object(workflow.graph_tools, "search_nodes", return_value=[{"successful_search_runs": 1}]),
        patch.object(workflow.research_state, "update_goal") as update_goal,
    ):
        result = workflow._authorize()

    assert result["error"] == ""
    update_goal.assert_called_once_with({
        "research_state": workflow.research_state.REPORTING,
        "reporting_from_state": workflow.research_state.FAILED,
        "report_authorized_reason": "best-effort report from partial research",
    })


def test_failed_run_without_evidence_is_not_authorized() -> None:
    goal = {"research_state": workflow.research_state.FAILED, "request": "request"}
    with (
        patch.object(workflow.research_state, "get_goal", return_value=goal),
        patch.object(workflow.graph_tools, "search_nodes", return_value=[]),
    ):
        result = workflow._authorize()

    assert "without evidence" in result["error"]


def test_failed_run_can_transition_to_reporting_for_best_effort_delivery() -> None:
    goal = {"id": "goal", "research_state": workflow.research_state.FAILED}
    updated = {}

    with (
        patch.object(workflow.research_state, "get_goal", return_value=goal),
        patch.object(workflow.graph_tools, "upsert_node", side_effect=lambda _type, attrs, _id: updated.update(attrs)),
        patch.object(workflow.graph_tools, "get_node", side_effect=lambda _id: {**goal, **updated}),
    ):
        result = workflow.research_state.update_goal({
            "research_state": workflow.research_state.REPORTING,
            "reporting_from_state": workflow.research_state.FAILED,
        })

    assert result["research_state"] == workflow.research_state.REPORTING


if __name__ == "__main__":
    test_prompt_contains_my_agent_final_writer_inputs()
    test_draft_citations_are_added_to_global_registry()
    print("test_reporter_global_workflow: PASS")
