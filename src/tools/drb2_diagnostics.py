"""Pure, offline diagnostics for DRB II-style report packet coverage."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


_URL_RE = re.compile(r"https?://[^\s<>\"']+")

_NUMERIC_RE = re.compile(r"(?<![\w.])\d+(?:[,.]\d+)?\s*(?:%|亿元|万元|万亿元|年|years?|percent)?", re.IGNORECASE)
_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
_TABLE_RE = re.compile(r"(?:表格|对比表|比较表|table|comparison)", re.IGNORECASE)


def _flatten_rubric_values(rubric: Any) -> list[tuple[str, str]]:
    """Return rubric dimension/item pairs while preserving source order."""
    if not isinstance(rubric, dict):
        return []
    values: list[tuple[str, str]] = []
    for dimension, items in rubric.items():
        candidates = items if isinstance(items, list) else [items]
        for item in candidates:
            if isinstance(item, dict):
                text = item.get("statement") or item.get("rubric") or item.get("text")
            else:
                text = item
            if str(text or "").strip():
                values.append((str(dimension), str(text).strip()))
    return values


def _split_atomic_statement(statement: str) -> list[str]:
    """Split only explicit conjunctions; keep each resulting claim independently judgeable."""
    text = re.sub(r"\s+", " ", statement).strip()
    if not text:
        return []
    # DRB rubrics are normally already atomic. Split explicit Chinese/English
    # list conjunctions only when both sides contain a predicate-like phrase.
    parts = re.split(r"(?:；|;|\s+and\s+|\s+以及\s+|\s+同时\s+)", text, flags=re.IGNORECASE)
    return [part.strip(" ，,：:") for part in parts if part.strip(" ，,：:")]


def build_atomic_rubrics(task: dict[str, Any]) -> list[dict[str, Any]]:
    """Build stable, auditable atomic rubric records from one DRB II task."""
    content = task.get("content") if isinstance(task.get("content"), dict) else {}
    rubric = content.get("rubric") if isinstance(content.get("rubric"), dict) else task.get("rubric") or {}
    prompt = str(task.get("prompt") or task.get("description") or "")
    sections = [
        line.strip(" -*#：:")
        for line in prompt.splitlines()
        if re.match(r"^\s*(?:#{1,6}\s+|第[一二三四五六七八九十]+部分|Part\s+\w+)", line, re.IGNORECASE)
    ]
    atomic: list[dict[str, Any]] = []
    for index, (dimension, original) in enumerate(_flatten_rubric_values(rubric), start=1):
        statements = _split_atomic_statement(original)
        for part_index, statement in enumerate(statements, start=1):
            numbers = _NUMERIC_RE.findall(statement)
            years = _YEAR_RE.findall(statement)
            answer_type = "numeric" if numbers or years else "fact"
            if _TABLE_RE.search(statement):
                answer_type = "table"
            elif re.search(r"why|cause|effect|mechanism|原因|机制|影响|后果", statement, re.IGNORECASE):
                answer_type = "analysis"
            elif re.search(r"define|definition|what is|定义|什么是", statement, re.IGNORECASE):
                answer_type = "definition"
            rubric_id = f"drb2-{task.get('idx', task.get('id', 'task'))}-{dimension}-{index:03d}-{part_index:02d}"
            atomic.append({
                "rubric_id": rubric_id,
                "source_dimension": dimension,
                "dimension": {
                    "info_recall": "information_recall",
                    "information_recall": "information_recall",
                    "analysis": "analysis",
                    "presentation": "presentation",
                }.get(dimension, dimension),
                "requirement": "must",
                "statement": statement,
                "source_statement": original,
                "answer_type": answer_type,
                "expected_numbers": numbers,
                "expected_years": years,
                "target_sections": sections or ["Answer"],
                "evidence_requirements": ["direct evidence", "citation"],
                "blocked_source_policy": "reject",
                "weight": 1.0,
                "status": "uncovered",
            })
    return atomic


def project_drb2_task(task: dict[str, Any]) -> dict[str, Any]:
    """Project one DRB II task into generic GraphResearcher delivery metadata."""
    prompt = str(task.get("prompt") or task.get("description") or "")
    content = task.get("content") if isinstance(task.get("content"), dict) else {}
    rubric = content.get("rubric") if isinstance(content.get("rubric"), dict) else task.get("rubric") or {}
    rubric_values = [item[1] for item in _flatten_rubric_values(rubric)]
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
        "atomic_rubrics": build_atomic_rubrics(task),
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
    rubrics = projection["atomic_rubrics"]
    components = [rubric["statement"] for rubric in rubrics]
    sections = projection["target_sections"] or ["Answer"]
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for rubric in rubrics:
        section = (rubric["target_sections"] or sections or ["Answer"])[0]
        key = (section, rubric["answer_type"], rubric["dimension"])
        groups.setdefault(key, []).append(rubric)
    query_specs = []
    for (section, answer_type, _dimension), grouped in groups.items():
        statements = [rubric["statement"] for rubric in grouped]
        query_specs.append({
            "text": f"{section}: " + "; ".join(statements),
            "objective_keys": [rubric["rubric_id"] for rubric in grouped],
            "rubric_ids": [rubric["rubric_id"] for rubric in grouped],
            "acceptance_criteria": [
                criterion
                for rubric in grouped
                for criterion in (rubric["statement"], *rubric["evidence_requirements"])
            ],
            "target_components": statements,
            "target_sections": [section],
            "analysis_mode": projection["analysis_mode"],
            "required_evidence_types": ["primary"] if answer_type == "numeric" else ["primary", "secondary"],
            "search_mode": "finance" if answer_type == "numeric" else "general",
        })
    # Keep the runtime portfolio at query-group granularity. The atomic rubric
    # records remain the fine-grained acceptance contract for the Reporter;
    # creating one graph Objective per rubric overwhelms the existing scheduler.
    objectives = [
        {
            "objective_key": f"drb2-{task.get('idx', task.get('id', 'task'))}-group-{index:03d}",
            "rubric_ids": query["rubric_ids"],
            "description": query["text"],
            "requirement": "must",
            "weight": 1.0,
            "acceptance_criteria": query["acceptance_criteria"],
        }
        for index, query in enumerate(query_specs, start=1)
    ]
    for query, objective in zip(query_specs, objectives):
        query["objective_keys"] = [objective["objective_key"]]
    return {
        **projection,
        "objectives": objectives,
        "initial_queries": query_specs,
        "atomic_rubrics": rubrics,
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
