"""Standalone checks for final-report consistency and binding repair."""

import sys
from pathlib import Path

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from tools import graph_tools, report_tools, research_state  # noqa: E402


def main():
    nodes = {
        "goal": {"id": "goal", "type": "UserRequest", "time_window": "2018-2024"},
        "s1": {
            "id": "s1", "type": "Source", "title": "Current source",
            "url": "https://example.com/current", "published_at": "2023-06-01",
        },
        "s2": {
            "id": "s2", "type": "Source", "title": "Future source",
            "url": "https://example.com/future", "published_at": "2025-01-01",
        },
        "conflict": {
            "id": "conflict", "type": "Conflict", "resolution_status": "disclosed",
            "description": "Tesla Optimus hand parameter conflict",
        },
        "section": {
            "id": "section", "type": "ReportSection", "title": "Findings",
            "content": "Supported finding. " * 10,
        },
    }
    edges = []
    created_titles = []
    bound_evidence = []

    def search_nodes(kind, filt=None):
        wanted = kind.replace("_", "").lower()
        result = [
            dict(node) for node in nodes.values()
            if str(node.get("type", "")).replace("_", "").lower() == wanted
        ]
        return [node for node in result if all(node.get(k) == v for k, v in (filt or {}).items())]

    def add_edge(source, target, edge_type, attributes=None):
        name = edge_type.value if hasattr(edge_type, "value") else str(edge_type)
        edge = {"source": source, "target": target, "type": name, **(attributes or {})}
        if edge not in edges:
            edges.append(edge)
        return edge

    graph_tools.search_nodes = search_nodes
    graph_tools.get_all_nodes = lambda: [dict(node) for node in nodes.values()]
    graph_tools.get_all_edges = lambda: [dict(edge) for edge in edges]
    graph_tools.get_node = lambda node_id: dict(nodes.get(node_id, {}))
    graph_tools.get_node_edges = lambda node_id, direction="both": [
        dict(edge) for edge in edges
        if (
            direction == "out" and edge["source"] == node_id
            or direction == "in" and edge["target"] == node_id
            or direction == "both" and node_id in {edge["source"], edge["target"]}
        )
    ]
    graph_tools.add_edge = add_edge
    graph_tools.create_report_section = lambda title, content, section_type=None: created_titles.append(title) or "section"
    graph_tools.bind_evidence_to_section = lambda section_id, evidence_ids, claim_ids: bound_evidence.append({
        "section_id": section_id,
        "evidence_ids": list(evidence_ids),
        "claim_ids": list(claim_ids),
    })
    research_state.get_goal = lambda goal_id=None: dict(nodes["goal"])
    edges.append({"source": "conflict", "target": "e1", "type": "HAS_CONFLICT"})
    nodes["e1"] = {"id": "e1", "type": "Evidence", "text": "Tesla Optimus hand parameter conflict"}
    edges.append({"source": "s1", "target": "e1", "type": "SUPPORTED_BY"})

    uncited = "## Findings\n\n" + ("A supported factual sentence. " * 8)
    issues = report_tools.validate_final_report(uncited)
    assert any("no citation" in issue for issue in issues), issues

    out_of_window = (
        "## Findings\n\nTesla Optimus hand parameter conflict. "
        + ("A supported factual sentence. " * 5)
        + "[2]\n\n## References\n\n"
        + "[2] Future source https://example.com/future"
    )
    issues = report_tools.validate_final_report(out_of_window)
    assert any("out-of-window" in issue for issue in issues), issues

    background = out_of_window.replace("## Findings", "## Background")
    issues = report_tools.validate_final_report(background)
    assert not any("out-of-window" in issue for issue in issues), issues

    valid = (
        "## Findings\n\nTesla Optimus hand parameter conflict. "
        + ("A supported factual sentence. " * 5)
        + "[1]\n\n## References\n\n"
        + "[1] Current source https://example.com/current"
    )
    compiled = report_tools.compile_structured_report("具身智能报告", [{
        "title": "Findings",
        "content": (("A supported factual sentence. " * 5) + "[1]").strip(),
        "source_ids": ["s1"],
        "evidence_ids": ["e1"],
    }])
    assert compiled["accepted"] is True, compiled
    assert compiled["auto_appended_conflict_ids"] == ["conflict"], compiled
    assert "## 冲突披露" in compiled["report"], compiled["report"]
    assert bound_evidence == [], bound_evidence
    persisted = report_tools.compile_structured_report("具身智能报告", [{
        "title": "Findings",
        "content": (("A supported factual sentence. " * 5) + "[1]").strip(),
        "source_ids": ["s1"],
        "evidence_ids": ["e1"],
    }], persist=True)
    assert persisted["accepted"] is True, persisted
    assert [item["evidence_ids"] for item in bound_evidence] == [["e1"], ["e1"]], bound_evidence

    nodes["goal"]["request"] = "Write a Wikipedia article about embodied intelligence."
    wikipedia_missing_uncertainty = report_tools.compile_structured_report("具身智能报告", [{
        "title": "Findings",
        "content": (("A supported factual sentence. " * 5) + "[1]").strip(),
        "source_ids": ["s1"],
        "evidence_ids": ["e1"],
        "section_type": "lead",
    }])
    assert wikipedia_missing_uncertainty["accepted"] is False, wikipedia_missing_uncertainty
    assert wikipedia_missing_uncertainty["severity"] == "hard", wikipedia_missing_uncertainty
    assert any(
        issue["code"] == "missing_substantive_uncertainty"
        for issue in wikipedia_missing_uncertainty["issues"]
    ), wikipedia_missing_uncertainty["issues"]
    assert "## 冲突披露" not in (
        wikipedia_missing_uncertainty["report"]
        + wikipedia_missing_uncertainty["salvaged_report"]
    )

    wikipedia_integrated_uncertainty = report_tools.compile_structured_report("具身智能报告", [{
        "title": "Evidence and interpretation",
        "content": (
            "Tesla Optimus hand parameter conflict remains unresolved in the cited sources. "
            + "A supported factual sentence. " * 4
            + "[1]"
        ).strip(),
        "source_ids": ["s1"],
        "evidence_ids": ["e1"],
        "disclosed_conflict_ids": ["conflict"],
        "section_type": "lead",
    }])
    assert wikipedia_integrated_uncertainty["accepted"] is True, wikipedia_integrated_uncertainty
    assert wikipedia_integrated_uncertainty["auto_appended_conflict_ids"] == []
    assert "## 冲突披露" not in wikipedia_integrated_uncertainty["report"]
    nodes["goal"].pop("request")

    conflict_with_unrelated_source = report_tools.compile_structured_report("具身智能报告", [{
        "title": "Evidence disagreement",
        "content": "Tesla Optimus hand parameter conflict remains unresolved.[2]",
        "source_ids": ["s2"],
        "evidence_ids": ["e1"],
        "disclosed_conflict_ids": ["conflict"],
    }])
    assert conflict_with_unrelated_source["accepted"] is False, conflict_with_unrelated_source
    assert any(
        issue["code"] == "invalid_conflict_disclosure_binding"
        for issue in conflict_with_unrelated_source["issues"]
    ), conflict_with_unrelated_source["issues"]

    conflict_without_evidence = report_tools.compile_structured_report("具身智能报告", [{
        "title": "Evidence disagreement",
        "content": "Tesla Optimus hand parameter conflict remains unresolved.[1]",
        "source_ids": ["s1"],
        "evidence_ids": [],
        "disclosed_conflict_ids": ["conflict"],
    }])
    assert conflict_without_evidence["accepted"] is False, conflict_without_evidence
    assert any(
        issue["code"] == "invalid_conflict_disclosure_binding"
        for issue in conflict_without_evidence["issues"]
    ), conflict_without_evidence["issues"]

    conflict_without_description = report_tools.compile_structured_report("具身智能报告", [{
        "title": "Evidence disagreement",
        "content": "The available source supports a generic finding.[1]",
        "source_ids": ["s1"],
        "evidence_ids": ["e1"],
        "disclosed_conflict_ids": ["conflict"],
    }])
    assert conflict_without_description["accepted"] is False, conflict_without_description
    assert any(
        issue["code"] == "invalid_conflict_disclosure_binding"
        for issue in conflict_without_description["issues"]
    ), conflict_without_description["issues"]

    finalized = report_tools.finalize_report(valid)
    assert any(edge["source"] == "section" and edge["target"] == "s1" for edge in edges), edges
    assert not report_tools.validate_final_report(finalized), report_tools.validate_final_report(finalized)

    created_titles.clear()
    report_tools.finalize_report(
        "## Recommendations\n\n"
        + ("Continue targeted research. " * 8)
        + "\n\n## Findings\n\nSupported finding [1].\n\n"
        + "## References\n\n[1] Current source https://example.com/current"
    )
    assert "Recommendations" not in created_titles, created_titles

    internal = valid.replace("A supported factual sentence.", "Research Graph query node.")
    assert any("internal process term" in issue for issue in report_tools.validate_final_report(internal))

    run21_bad = (
        "## Findings\n\n"
        "下面的整理基于截至 2025 年的公开资料，并严格受本次研究图谱覆盖范围约束。\n\n"
        "Supported finding [1].\n\n"
        "如果你接下来希望进一步细化，可以指定维度，我可以帮你补全。\n\n"
        "## References\n\n[1] Current source https://example.com/current"
    )
    sanitized = report_tools.sanitize_report(run21_bad)
    assert "研究图谱" not in sanitized and "如果你接下来希望" not in sanitized
    assert "Supported finding [1]." in sanitized
    assert not report_tools.validate_delivery_invariants(sanitized)

    global_compiled = report_tools.compile_global_writer_report(
        None,
        "## Findings\n\nSupported finding [1] with local marker [e17]."
    )
    assert "Supported finding [1]" in global_compiled["report"]
    assert "[e17]" not in global_compiled["report"]
    assert not global_compiled["hard_issues"]

    no_citation = report_tools.compile_global_writer_report(
        None,
        "## Findings\n\nAn uncited factual claim."
    )
    assert any("no valid inline citations" in issue for issue in no_citation["hard_issues"])

    uncited_unit = valid.replace("[1]", "", 1)
    assert any("uncited factual paragraph" in issue for issue in report_tools.validate_delivery_invariants(uncited_unit))

    for stop_reason in (
        "现有资料仍不完整，因为检索预算耗尽。",
        "The report is limited because targeted recovery failed.",
        "The internal state is LIMITED_REPORT_READY.",
    ):
        leaked_stop_reason = valid.replace(
            "Tesla Optimus hand parameter conflict.",
            stop_reason,
        )
        assert any(
            "forbidden internal-process" in issue
            for issue in report_tools.validate_delivery_invariants(leaked_stop_reason)
        ), stop_reason
    leaked_stop_reason_compilation = report_tools.compile_structured_report("具身智能报告", [{
        "title": "Findings",
        "content": "现有资料仍不完整，因为检索预算耗尽。",
        "source_ids": ["s1"],
        "evidence_ids": ["e1"],
    }])
    assert leaked_stop_reason_compilation["accepted"] is False, leaked_stop_reason_compilation

    for runtime_stop_reason in (
        "report-level objectives reached marginal-utility convergence",
        "bounded research reached best-effort convergence",
        "Exhaustive objective remained open after targeted recovery: core-answer",
    ):
        leaked_runtime_reason = valid.replace(
            "Tesla Optimus hand parameter conflict.",
            runtime_stop_reason,
        )
        assert any(
            "forbidden internal-process" in issue
            for issue in report_tools.validate_delivery_invariants(leaked_runtime_reason)
        ), runtime_stop_reason
        compiled_runtime_reason = report_tools.compile_structured_report("具身智能报告", [{
            "title": "Findings",
            "content": runtime_stop_reason,
            "source_ids": ["s1"],
            "evidence_ids": ["e1"],
        }])
        assert compiled_runtime_reason["accepted"] is False, compiled_runtime_reason

    topic_budget_fact = valid.replace(
        "Tesla Optimus hand parameter conflict.",
        "公开记录显示该项目预算耗尽。",
    )
    assert not report_tools.validate_delivery_invariants(topic_budget_fact)

    legacy = report_tools.compile_structured_report("具身智能报告", [{
        "title": "Legacy",
        "blocks": [{"text": "Old shape", "source_ids": ["s1"]}],
    }])
    assert legacy["accepted"] is False and legacy["severity"] == "hard", legacy
    assert any(issue["code"] == "legacy_block_schema" for issue in legacy["issues"]), legacy["issues"]

    nodes["unmet"] = {
        "id": "unmet",
        "type": "Analysis",
        "analysis_type": "objective",
        "objective_key": "contract-value",
        "requirement": "must",
        "status": "blocked",
        "description": "Determine the undisclosed contract value from primary records.",
        "acceptance_criteria": [
            "The cited source identifies the contract parties.",
            "Document the undisclosed contract value.",
        ],
        "unmet_acceptance_criteria": ["Document the undisclosed contract value."],
    }
    leaked_unmet = report_tools.compile_structured_report("具身智能报告", [{
        "title": "Contract",
        "content": "Determine the undisclosed contract value from primary records.",
        "source_ids": ["s1"],
        "evidence_ids": ["e1"],
    }])
    assert leaked_unmet["accepted"] is False and leaked_unmet["severity"] == "hard", leaked_unmet
    assert any(
        issue["code"] == "internal_unmet_objective_prose"
        for issue in leaked_unmet["issues"]
    ), leaked_unmet["issues"]

    supported_criterion = report_tools.compile_structured_report("具身智能报告", [{
        "title": "Contract parties",
        "content": "The cited source identifies the contract parties.[1]",
        "source_ids": ["s1"],
        "evidence_ids": ["e1"],
    }])
    assert supported_criterion["accepted"] is True, supported_criterion
    print("ALL REPORT VALIDATION CHECKS PASSED")


if __name__ == "__main__":
    main()
