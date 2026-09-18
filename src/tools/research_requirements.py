"""Pure helpers for inspecting reporter delivery packets."""

from __future__ import annotations

from typing import Any


def inspect_delivery_packet(packet: dict[str, Any]) -> dict[str, Any]:
    """Report delivery gaps without calling the graph, web, or an LLM."""
    objectives = packet.get("research_brief", {}).get("objectives") or []
    findings = packet.get("findings") or []
    notes = packet.get("research_notes") or []
    covered_objectives = {
        key
        for group in findings
        for key in group.get("query", {}).get("objective_keys") or []
    }
    required_components = {
        component
        for component in packet.get("answer_contract", {}).get("required_sections") or []
    }
    targeted_components = {
        component
        for query in packet.get("research_brief", {}).get("queries") or []
        for component in query.get("target_components") or []
    }
    return {
        "uncovered_must_objectives": [
            objective.get("objective_key")
            for objective in objectives
            if objective.get("requirement") == "must"
            and objective.get("objective_key") not in covered_objectives
        ],
        "untargeted_required_sections": sorted(required_components - targeted_components),
        "queries_without_research_notes": sorted({
            str(group.get("query", {}).get("ref") or "")
            for group in findings
            if group.get("query", {}).get("ref")
            and str(group.get("query", {}).get("ref")) not in {
                str(note.get("query_ref")) for note in notes
            }
        }),
        "research_note_gaps": [
            note.get("query_ref")
            for note in notes
            if note.get("gaps")
        ],
        "finding_count": sum(len(group.get("items") or []) for group in findings),
        "research_note_count": len(notes),
    }
