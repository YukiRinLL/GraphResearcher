"""Run-scoped report workflow artifacts and candidate selection."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from threading import RLock
from typing import Any, Optional

from memory.graph import EdgeType, NodeType
from tools import graph_tools

_output_dir: Optional[Path] = None
_lock = RLock()


def configure(output_dir: Optional[str], reset: bool = False) -> None:
    """Scope report artifacts to one run and optionally clear stale outputs."""
    global _output_dir
    _output_dir = Path(output_dir) if output_dir else None
    if _output_dir:
        if reset:
            shutil.rmtree(_output_dir / "reports", ignore_errors=True)
            for stale_name in ("report.md", ".compiled_report.md"):
                stale_path = _output_dir / stale_name
                if stale_path.exists():
                    stale_path.unlink()
        for path in (_reports_dir(), _chapters_dir(), _candidates_dir()):
            path.mkdir(parents=True, exist_ok=True)
        conflicts_path = _reports_dir() / "conflicts.json"
        if not conflicts_path.exists():
            _write_json(conflicts_path, {"conflicts": []})


def _reports_dir() -> Path:
    if _output_dir is None:
        raise RuntimeError("Report workspace is not configured")
    return _output_dir / "reports"


def _chapters_dir() -> Path:
    return _reports_dir() / "chapters"


def _candidates_dir() -> Path:
    return _reports_dir() / "candidates"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _render_outline(outline: dict) -> str:
    lines = [f"# {outline.get('title') or 'Report Outline'}", ""]
    for chapter in outline.get("chapters", []):
        lines.extend([
            f"## {chapter['chapter_id']}. {chapter['title']} [{chapter.get('status', 'pending')}]",
            "",
        ])
        if chapter.get("goals"):
            lines.append("**Goals**")
            lines.extend(f"- {goal}" for goal in chapter["goals"])
            lines.append("")
        if chapter.get("sections_description"):
            lines.extend(["**Structure**", chapter["sections_description"], ""])
        if chapter.get("objective_ids"):
            lines.extend([
                f"**Objectives:** {', '.join(chapter['objective_ids'])}",
                "",
            ])
    return "\n".join(lines).rstrip() + "\n"


def commit_outline(title: str, chapters: list[dict]) -> dict:
    """Persist a report outline and return non-blocking coverage warnings."""
    objectives = graph_tools.search_nodes("analysis", {"analysis_type": "objective"})
    objective_by_id = {item["id"]: item for item in objectives}
    normalized: list[dict] = []
    mapped: set[str] = set()
    issues: list[str] = []
    for index, raw in enumerate(chapters or [], start=1):
        chapter_title = str(raw.get("title") or "").strip()
        if not chapter_title:
            issues.append(f"chapter {index} has no title")
            continue
        objective_ids = list(dict.fromkeys(raw.get("objective_ids") or []))
        invalid = [item_id for item_id in objective_ids if item_id not in objective_by_id]
        if invalid:
            issues.append(f"chapter {index} has unknown objective_ids: {invalid}")
            objective_ids = [item_id for item_id in objective_ids if item_id in objective_by_id]
        mapped.update(objective_ids)
        normalized.append({
            "chapter_id": len(normalized) + 1,
            "title": chapter_title,
            "goals": [str(item).strip() for item in raw.get("goals") or [] if str(item).strip()],
            "objective_ids": objective_ids,
            "candidate_item_ids": list(dict.fromkeys(raw.get("candidate_item_ids") or [])),
            "sections_description": str(raw.get("sections_description") or "").strip(),
            "status": "pending",
        })
    if not normalized:
        return {"error": "Report outline requires at least one valid chapter", "issues": issues}
    uncovered = [
        item["id"] for item in objectives
        if item.get("requirement") == "must" and item["id"] not in mapped
    ]
    if uncovered:
        issues.append(f"must objectives not mapped to any chapter: {uncovered}")
    outline = {"title": str(title or "Research Report").strip(), "chapters": normalized, "issues": issues}
    with _lock:
        _write_json(_reports_dir() / "outline.json", outline)
        (_reports_dir() / "outline.md").write_text(_render_outline(outline), encoding="utf-8")
    return {
        "status": "ok",
        "chapter_count": len(normalized),
        "uncovered_must_objective_ids": uncovered,
        "issues": issues,
    }


def get_outline() -> dict:
    """Return the persisted report outline."""
    return _read_json(_reports_dir() / "outline.json", {})


def get_chapter(chapter_id: int) -> Optional[dict]:
    """Return one outline chapter by its 1-based ID."""
    for chapter in get_outline().get("chapters", []):
        if chapter.get("chapter_id") == int(chapter_id):
            return chapter
    return None


def update_chapter_status(chapter_id: int, status: str) -> None:
    """Persist one chapter status and refresh the outline render."""
    outline = get_outline()
    for chapter in outline.get("chapters", []):
        if chapter.get("chapter_id") == int(chapter_id):
            chapter["status"] = status
            break
    with _lock:
        _write_json(_reports_dir() / "outline.json", outline)
        (_reports_dir() / "outline.md").write_text(_render_outline(outline), encoding="utf-8")


def save_chapter(chapter_id: int, content: str, metadata: dict) -> dict:
    """Persist one compiled chapter and its traceability metadata."""
    chapter = get_chapter(chapter_id)
    if chapter is None:
        return {"error": f"Unknown report chapter: {chapter_id}"}
    with _lock:
        (_chapters_dir() / f"chapter_{chapter_id:02d}.md").write_text(content, encoding="utf-8")
        _write_json(_chapters_dir() / f"chapter_{chapter_id:02d}_meta.json", metadata)
        update_chapter_status(chapter_id, "completed")
    return {"status": "ok", "chapter_id": chapter_id, "path": f"reports/chapters/chapter_{chapter_id:02d}.md"}


def chapter_metadata(chapter_id: int) -> dict:
    """Return one chapter's persisted metadata."""
    return _read_json(_chapters_dir() / f"chapter_{chapter_id:02d}_meta.json", {})


def chapter_text(chapter_id: int) -> str:
    """Return one chapter's compiled markdown text."""
    path = _chapters_dir() / f"chapter_{chapter_id:02d}.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def save_conflict(entry: dict) -> None:
    """Append a report-stage conflict record."""
    path = _reports_dir() / "conflicts.json"
    data = _read_json(path, {"conflicts": []})
    data.setdefault("conflicts", []).append(entry)
    with _lock:
        _write_json(path, data)


def save_draft(content: str) -> None:
    """Persist the assembled draft."""
    with _lock:
        (_reports_dir() / "draft.md").write_text(content, encoding="utf-8")


def draft_text() -> str:
    """Return the assembled draft text."""
    path = _reports_dir() / "draft.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _candidate_metadata() -> list[dict]:
    result = []
    for path in sorted(_candidates_dir().glob("report_r*_meta.json")):
        data = _read_json(path, {})
        if data:
            result.append(data)
    return result


def _candidate_key(meta: dict) -> tuple:
    return (
        not bool(meta.get("structural_issues")),
        -len(meta.get("quality_issues") or []),
        int(meta.get("covered_must_objectives") or 0),
        int(meta.get("bound_block_count") or 0),
        int(meta.get("revision") or 0),
    )


def save_candidate(report: str, metadata: dict) -> dict:
    """Persist one candidate and promote the best available version."""
    with _lock:
        revision = len(_candidate_metadata()) + 1
        metadata = {**metadata, "revision": revision}
        report_path = _candidates_dir() / f"report_r{revision:02d}.md"
        meta_path = _candidates_dir() / f"report_r{revision:02d}_meta.json"
        report_path.write_text(report, encoding="utf-8")
        metadata["report_path"] = f"reports/candidates/{report_path.name}"
        _write_json(meta_path, metadata)
        candidates = _candidate_metadata()
        best = max(candidates, key=_candidate_key)
        best_path = _output_dir / best["report_path"]  # type: ignore[operator]
        best_report = best_path.read_text(encoding="utf-8")
        (_reports_dir() / "report.md").write_text(best_report, encoding="utf-8")
        _write_json(_reports_dir() / "report_meta.json", best)
    return {"revision": revision, "best_revision": best["revision"], "best_metadata": best}


def best_report() -> str:
    """Return the currently selected best candidate report."""
    if _output_dir is None:
        return ""
    path = _reports_dir() / "report.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def best_metadata() -> dict:
    """Return metadata for the currently selected best candidate."""
    if _output_dir is None:
        return {}
    return _read_json(_reports_dir() / "report_meta.json", {})


def annotate_best_candidate(additional_issues: list[str]) -> dict:
    """Attach parent-review issues to the reviewed candidate and re-rank."""
    with _lock:
        best = best_metadata()
        if not best:
            return {}
        best["quality_issues"] = list(dict.fromkeys([
            *(best.get("quality_issues") or []),
            *(additional_issues or []),
        ]))
        meta_path = _candidates_dir() / f"report_r{int(best['revision']):02d}_meta.json"
        _write_json(meta_path, best)
        candidates = _candidate_metadata()
        selected = max(candidates, key=_candidate_key)
        selected_path = _output_dir / selected["report_path"]  # type: ignore[operator]
        (_reports_dir() / "report.md").write_text(
            selected_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        _write_json(_reports_dir() / "report_meta.json", selected)
        return selected


def candidate_metadata() -> list[dict]:
    """Return all candidate metadata ordered by revision."""
    return _candidate_metadata()


def get_status() -> dict:
    """Return compact report-workspace progress."""
    outline = get_outline()
    best = best_metadata()
    chapters = []
    for chapter in outline.get("chapters", []):
        chapter_id = chapter["chapter_id"]
        chapters.append({
            **chapter,
            "file_exists": (_chapters_dir() / f"chapter_{chapter_id:02d}.md").exists(),
        })
    return {
        "status": "not_started" if not outline else (
            "completed" if chapters and all(item.get("status") == "completed" for item in chapters)
            else "in_progress"
        ),
        "outline_exists": bool(outline),
        "chapters": chapters,
        "draft_exists": (_reports_dir() / "draft.md").exists(),
        "report_exists": (_reports_dir() / "report.md").exists(),
        "candidate_count": len(_candidate_metadata()),
        "best_candidate": {
            key: best.get(key)
            for key in (
                "revision", "quality_issues", "covered_must_objectives",
                "bound_block_count", "report_path",
            )
        } if best else {},
    }


def objective_ids_for_items(item_ids: list[str]) -> set[str]:
    """Return Objectives reachable from Claim/Evidence items through SearchRuns."""
    all_edges = graph_tools.get_all_edges()
    produced_by_runs = {
        edge["source"]
        for edge in all_edges
        if str(edge.get("type", "")).lower() == EdgeType.PRODUCED.value.lower()
        and edge.get("target") in item_ids
    }
    query_ids = {
        edge["source"]
        for edge in all_edges
        if str(edge.get("type", "")).lower() == EdgeType.SEARCHED_BY.value.lower()
        and edge.get("target") in produced_by_runs
    }
    return {
        edge["target"]
        for edge in all_edges
        if str(edge.get("type", "")).lower() == EdgeType.COVERS_OBJECTIVE.value.lower()
        and edge.get("source") in query_ids
        and graph_tools.get_node(edge["target"]).get("type") == NodeType.ANALYSIS.value
    }
