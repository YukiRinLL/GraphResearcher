"""Pure, offline diagnostics for DRB II-style report packet coverage."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


_URL_RE = re.compile(r"https?://[^\s<>\"']+")


def project_drb2_task(task: dict[str, Any]) -> dict[str, Any]:
    """Project one DRB II task into generic GraphResearcher delivery metadata."""
    prompt = str(task.get("prompt") or task.get("description") or "")
    content = task.get("content") if isinstance(task.get("content"), dict) else {}
    rubric = content.get("rubric") if isinstance(content.get("rubric"), dict) else task.get("rubric") or {}
    rubric_values = [
        str(item)
        for values in rubric.values()
        for item in (values if isinstance(values, list) else [values])
    ]
    text = " ".join([prompt, *rubric_values])
    analysis_mode = "none"
    if re.search(r"compare|comparison|对比|比较", text, re.IGNORECASE):
        analysis_mode = "compare"
    elif re.search(r"why|cause|causal|原因|机制|影响", text, re.IGNORECASE):
        analysis_mode = "causal"
    elif re.search(r"categor|分类|归类", text, re.IGNORECASE):
        analysis_mode = "classification"
    elif re.search(r"analy|分析|synthesi|综合", text, re.IGNORECASE):
        analysis_mode = "synthesis"
    blocked_sources = []
    for match in _URL_RE.finditer(prompt):
        url = match.group(0).rstrip(".,，。);）")
        if re.search(r"not allowed|do not|ignore|不得|禁止|不能|不允许", prompt[max(0, match.start() - 180): match.end() + 80], re.IGNORECASE):
            if url not in blocked_sources:
                blocked_sources.append(url)
    return {
        "task_id": task.get("id"),
        "language": task.get("language") or ("zh" if re.search(r"[\u4e00-\u9fff]", prompt) else "en"),
        "analysis_mode": analysis_mode,
        "required_components": rubric_values,
        "target_sections": [
            line.strip(" -*#：:")
            for line in prompt.splitlines()
            if re.match(r"^\s*(?:#{1,6}\s+|第[一二三四五六七八九十]+部分|Part\s+\w+)", line, re.IGNORECASE)
        ],
        "blocked_sources": blocked_sources,
        "rubric_dimensions": sorted(rubric),
    }


def load_drb2_tasks(path: str | Path) -> list[dict[str, Any]]:
    """Load and project a JSONL DRB II task file without touching runtime state."""
    tasks = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            tasks.append(project_drb2_task(json.loads(line)))
    return tasks


def build_drb2_research_plan(task: dict[str, Any]) -> dict[str, Any]:
    """Convert a projected task into generic Objective/Query planning metadata."""
    projection = project_drb2_task(task)
    components = projection["required_components"]
    sections = projection["target_sections"] or ["Answer"]
    objectives = [
        {
            "objective_key": f"drb2-{index + 1}",
            "description": component,
            "requirement": "must",
            "weight": 1.0,
            "acceptance_criteria": [component],
        }
        for index, component in enumerate(components)
        if component
    ]
    query_specs = [
        {
            "text": f"{section}: {task.get('description') or task.get('id') or 'research task'}",
            "objective_keys": [objective["objective_key"] for objective in objectives],
            "target_components": components,
            "target_sections": [section],
            "analysis_mode": projection["analysis_mode"],
            "required_evidence_types": ["primary", "secondary"],
        }
        for section in sections
    ]
    return {
        **projection,
        "objectives": objectives,
        "initial_queries": query_specs,
    }


def diagnose_packet(packet: dict[str, Any]) -> dict[str, Any]:
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
