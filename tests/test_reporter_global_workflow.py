"""Offline checks for the my_agent-style global Reporter input contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

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


def _draft_with_fake_view(queries, pages, **kwargs):
    rt = workflow.report_tools
    view = MagicMock()
    view.search_nodes.return_value = queries

    def fetch(query_id, **_kwargs):
        return {"items": pages[query_id], "next_offset": None}

    with (
        patch.object(rt, "_report_read_view", return_value=view),
        patch.object(rt, "build_reference_registry", return_value=[]),
        patch.object(rt, "get_report_evidence", side_effect=fetch),
    ):
        return rt.build_cited_evidence_report("Answer this.", read_view=view, **kwargs)


def _draft_items(query_id, count):
    return [
        {"id": f"{query_id}-e{i}", "text": "x" * 150, "citations": [1], "source_ids": ["s1"]}
        for i in range(count)
    ]


def test_cited_draft_caps_bullets_and_respects_priority_order() -> None:
    queries = [
        {"id": "q1", "handle": "a", "text": "Question one"},
        {"id": "q2", "handle": "b", "text": "Question two"},
    ]
    pages = {"q1": _draft_items("q1", 6), "q2": _draft_items("q2", 6)}

    draft = _draft_with_fake_view(
        queries,
        pages,
        max_chars=400,
        query_order=["q2"],
        include_references=False,
    )

    # 每条 bullet 156 字符：400 预算只放得下 q2 的 2 条；q2 段排在 q1 之前。
    assert draft.count("\n- ") == 2, draft
    assert draft.index("## Question two") < draft.index("## Question one")
    assert "omitted" in draft
    assert "## References" not in draft


def test_cited_draft_without_cap_keeps_all_items_and_references() -> None:
    queries = [{"id": "q1", "handle": "a", "text": "Question one"}]
    pages = {"q1": _draft_items("q1", 12)}

    draft = _draft_with_fake_view(queries, pages)

    assert draft.count("\n- ") == 12, draft
    assert "omitted" not in draft
    assert "## References" in draft


def test_cap_research_notes_trims_id_lists_and_drops_overflow() -> None:
    large_note = {
        "query_ref": "q1",
        "confirmed_facts": [f"e{i}" for i in range(130)],
        "claim_refs": [],
        "source_ids": [],
    }
    small_note = {
        "query_ref": "q2",
        "confirmed_facts": ["x"],
        "claim_refs": ["c1"],
        "source_ids": ["s9"],
    }
    third_note = dict(small_note, query_ref="q3")

    trimmed_first = dict(large_note, confirmed_facts=large_note["confirmed_facts"][:100])
    # 截断时 helper 还会写入 truncated_fields 元数据，预留 64 字符余量。
    budget = len(json.dumps(trimmed_first, ensure_ascii=False)) + 64 + len(
        json.dumps(small_note, ensure_ascii=False)
    )
    capped = workflow._cap_research_notes([large_note, small_note, third_note], budget)

    assert [note["query_ref"] for note in capped] == ["q1", "q2"]
    assert len(capped[0]["confirmed_facts"]) == 100
    assert capped[0]["truncated_fields"]["confirmed_facts"] == 130
    # 未超限的字段不被改动。
    assert "truncated_fields" not in capped[1]


def test_research_notes_reach_the_writer_prompt() -> None:
    packet = {
        "research_brief": {"user_request": "request", "research_goal": "brief"},
        "required_data_points": [],
        "required_structure": [],
        "rubrics": [],
        "task_requirements": {},
        "answer_contract": {},
        "findings": [],
        "research_notes": [{
            "query_ref": "q1",
            "gaps": ["No citation-ready evidence was exported for this query."],
        }],
        "draft_report": "",
        "conflicts": [],
        "citation_registry": [],
    }

    prompt = workflow._prompt(packet)

    assert "No citation-ready evidence was exported" in prompt
    assert "<research_notes>" not in prompt


def test_build_packet_caps_draft_and_passes_query_priority() -> None:
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
    captured: dict = {}

    def fake_draft(_request, **kwargs):
        captured.update(kwargs)
        return ""

    with (
        patch.object(workflow.report_tools, "get_report_evidence", return_value={"items": [], "next_offset": None}),
        patch.object(workflow.report_tools, "build_cited_evidence_report", side_effect=fake_draft),
        patch.object(workflow.report_tools, "build_reference_registry", return_value=[]),
    ):
        packet = workflow._build_packet(context)

    assert captured["max_chars"] == workflow.config.GR_REPORTER_DRAFT_MAX_CHARS
    assert captured["include_references"] is False
    # q2 绑定未满足的 must objective，必须排在 draft 预算序列首位。
    assert captured["query_order"][0] == "q2"
    assert packet["budget"]["draft_report_chars"] == 0
    assert packet["budget"]["draft_max_chars"] == workflow.config.GR_REPORTER_DRAFT_MAX_CHARS


if __name__ == "__main__":
    test_prompt_contains_my_agent_final_writer_inputs()
    test_draft_citations_are_added_to_global_registry()
    test_cited_draft_caps_bullets_and_respects_priority_order()
    test_cited_draft_without_cap_keeps_all_items_and_references()
    test_cap_research_notes_trims_id_lists_and_drops_overflow()
    test_research_notes_reach_the_writer_prompt()
    test_build_packet_caps_draft_and_passes_query_priority()
    print("test_reporter_global_workflow: PASS")
