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
        "answer_contract": {"required_sections": ["comparison"]},
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
    assert "required_sections" in prompt
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


def test_answer_contract_extracts_blocked_sources_and_structure() -> None:
    contract = workflow._build_answer_contract({
        "user_request": (
            "请制作一个对比表。禁止引用 https://blocked.example/article。"
            "请分两部分回答：1. 背景；2. 影响。"
        ),
        "required_structure": [{"title": "结论"}],
    })

    assert contract["blocked_sources"] == ["https://blocked.example/article"]
    assert contract["requires_table"] is True
    assert "结论" in contract["required_sections"]


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


if __name__ == "__main__":
    test_prompt_contains_my_agent_final_writer_inputs()
    test_answer_contract_extracts_blocked_sources_and_structure()
    test_draft_citations_are_added_to_global_registry()
    print("test_reporter_global_workflow: PASS")
