"""Run-scoped Graph Manager services and agent-facing research tools."""

import json
import logging
from pathlib import Path
from threading import Lock
from typing import Any, Optional

from langchain_core.tools import tool

from agents.memory_manager import MemoryManager
from tools.graph_tools import AmbiguousQueryReference

_manager: Optional[MemoryManager] = None
_cache_dir: Optional[str] = None
_compiled_report: str = ""
_salvaged_report: str = ""
_best_report: str = ""
_last_report_attempt: dict[str, Any] = {}
_report_lock = Lock()
_user_request: Optional[str] = None
_report_review_completed = False
_report_review_had_issues = False
_report_submit_count = 0
_report_model_call_count = 0

logger = logging.getLogger(__name__)


def _normalize_run_context(output_dir: Optional[str]) -> str:
    """Normalize output_dir into a stable run-context string for Neo4j scoping.

    Historical behavior (V32..V35): always a windows relative form like
    ``outputs\\V33``. Newer callers may pass an absolute path (e.g. from
    Path.resolve()) or posix-style separators. Normalize them so that
    ``WHERE n.context = "outputs\\V36"`` keeps working consistently
    regardless of how the script passes ``-o``.
    """
    if not output_dir:
        return "default"
    p = Path(output_dir)
    try:
        # Prefer a path relative to graphresearcher project root (folder that
        # contains main.py, run_benchmark.ps1, and outputs/).
        from __main__ import __file__ as _entry  # type: ignore[attr-defined]

        project_root = Path(_entry).resolve().parent
    except Exception:
        project_root = Path.cwd()
    try:
        rel = p.resolve().relative_to(project_root.resolve())
    except ValueError:
        # Fall back to the final path components if outside project tree.
        parts = list(p.parts)
        if len(parts) >= 2:
            return "\\".join(parts[-2:]).replace("/", "\\")
        return str(p).replace("/", "\\")
    return str(rel).replace("/", "\\")


def configure(output_dir: Optional[str] = None, user_request: Optional[str] = None) -> None:
    """Clear and scope graph storage, then rebuild the shared manager for a run."""
    global _best_report, _cache_dir, _compiled_report, _last_report_attempt, _manager, _report_model_call_count, _report_review_completed, _report_review_had_issues, _report_submit_count, _salvaged_report, _user_request
    _cache_dir = output_dir
    _user_request = user_request
    _manager = None
    _report_review_completed = False
    _report_review_had_issues = False
    _report_submit_count = 0
    _report_model_call_count = 0
    with _report_lock:
        _compiled_report = ""
        _salvaged_report = ""
        _best_report = ""
        _last_report_attempt = {}
        for path_getter in (
            _compiled_report_path,
            _salvaged_report_path,
            _best_report_path,
            _report_attempt_path,
        ):
            path = path_getter()
            if path and path.exists():
                path.unlink()
        for relative in (".report_outline.json", ".report_outline.md"):
            path = Path(_cache_dir) / relative if _cache_dir else None
            if path and path.exists():
                path.unlink()
        chapter_dir = Path(_cache_dir) / ".report_chapters" if _cache_dir else None
        if chapter_dir and chapter_dir.exists():
            for child in chapter_dir.iterdir():
                if child.is_file():
                    child.unlink()
            chapter_dir.rmdir()
    from memory import source_snapshots
    from tools import convergence, graph_tools

    run_context = _normalize_run_context(output_dir)
    source_snapshots.configure(output_dir, run_context)
    graph_tools.set_context(run_context)
    graph_tools.clear_current_context()
    convergence.reset()


def _mm() -> MemoryManager:
    global _manager
    if _manager is None:
        _manager = MemoryManager(cache_dir=_cache_dir, user_request=_user_request)
    return _manager


def _compiled_report_path() -> Optional[Path]:
    """Return the run-scoped canonical Reporter artifact path."""
    return Path(_cache_dir) / ".compiled_report.md" if _cache_dir else None


def _salvaged_report_path() -> Optional[Path]:
    """Return the run-scoped salvaged Reporter artifact path."""
    return Path(_cache_dir) / ".salvaged_report.md" if _cache_dir else None


def _best_report_path() -> Optional[Path]:
    """Return the run-scoped best-available Reporter artifact path."""
    return Path(_cache_dir) / ".best_report.md" if _cache_dir else None


def _report_attempt_path() -> Optional[Path]:
    """Return the run-scoped JSON summary for the latest report attempt."""
    return Path(_cache_dir) / ".report_attempt.json" if _cache_dir else None


def get_compiled_report() -> str:
    """Return the canonical structured Reporter report for the current run."""
    with _report_lock:
        if _compiled_report:
            return _compiled_report
        path = _compiled_report_path()
        return path.read_text(encoding="utf-8") if path and path.exists() else ""


def get_salvaged_report() -> str:
    """Return the latest salvaged prose report for the current run."""
    with _report_lock:
        if _salvaged_report:
            return _salvaged_report
        path = _salvaged_report_path()
        return path.read_text(encoding="utf-8") if path and path.exists() else ""


def get_best_report() -> str:
    """Return the best available prose report for the current run."""
    with _report_lock:
        if _best_report:
            return _best_report
        path = _best_report_path()
        return path.read_text(encoding="utf-8") if path and path.exists() else ""


def get_last_report_attempt() -> dict[str, Any]:
    """Return the latest structured report-attempt summary."""
    with _report_lock:
        if _last_report_attempt:
            return dict(_last_report_attempt)
        path = _report_attempt_path()
        if path and path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}


def _write_optional_text(path: Optional[Path], text: str) -> None:
    """Persist one report artifact when a path is configured."""
    if path is None:
        return
    if not text:
        if path.exists():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _record_report_result(result: dict[str, Any], *, finalized: bool) -> None:
    """Persist one run-scoped report result without writing graph sections."""
    global _best_report, _compiled_report, _last_report_attempt, _salvaged_report
    with _report_lock:
        report = str(result.get("report") or "")
        salvaged = str(result.get("salvaged_report") or "")
        _compiled_report = report if finalized else ""
        _salvaged_report = "" if finalized else salvaged or report
        _best_report = _compiled_report or _salvaged_report
        _last_report_attempt = dict(result)
        _write_optional_text(_compiled_report_path(), _compiled_report)
        _write_optional_text(_salvaged_report_path(), _salvaged_report)
        _write_optional_text(_best_report_path(), _best_report)
        path = _report_attempt_path()
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_review_issues(content: Any) -> list[str]:
    """Parse the reviewer's deliberately small JSON response."""
    text = str(getattr(content, "content", content) or "").strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Report Review returned no JSON object") from None
        payload = json.loads(text[start : end + 1])
    if not isinstance(payload.get("issues"), list):
        raise ValueError("Report Review returned no issues list")
    if set(payload) != {"issues"}:
        raise ValueError("Report Review returned fields other than issues")
    return [str(item).strip() for item in payload["issues"] if str(item).strip()]


def _review_report_once(report: str) -> list[str]:
    """Invoke the isolated reviewer with only the agreed report context."""
    import config
    from tools import report_tools

    context = report_tools.get_committed_review_context(_cache_dir)
    prompt = (
        config.report_reviewer_system_prompt
        + "\n\nUser Request:\n"
        + str(_user_request or "")
        + "\n\nCandidate report:\n"
        + report
        + "\n\nUsed report material:\n"
        + json.dumps(context, ensure_ascii=False)
    )
    return _parse_review_issues(config.report_reviewer_model.invoke(prompt))


def prepare_search(query_id: str, source_preferences: Optional[list[str]] = None) -> dict:
    """Prepare an internal structured Searcher dispatch."""
    return _mm().prepare_search(query_id, source_preferences)


def fail_search(search_run_id: str, query_id: str, error: str) -> dict:
    """Record an internal Searcher dispatch failure."""
    return _mm().fail_search(search_run_id, query_id, error)


def set_research_state(state: str, **attributes: Any) -> dict:
    """Update root state for middleware and CLI lifecycle handling."""
    from tools import research_state

    return research_state.update_goal({"research_state": state, **attributes})


@tool
def init_research() -> dict:
    """Initialize a strict Query tree and persistent research state."""
    return _mm().init_research()


@tool
def get_research_status(goal_id: Optional[str] = None) -> dict:
    """Return persistent state, Objective coverage, selected work and budget."""
    from tools import research_state

    next_actions = _mm().get_next_actions()
    status = research_state.get_status(goal_id)
    status["tree_validation"] = _mm_validate_tree()
    status["next_actions"] = next_actions
    return status


@tool
def get_research_objectives(goal_id: Optional[str] = None) -> list:
    """Return the report-level research objectives and their current coverage."""
    return _mm().get_research_objectives(goal_id)


def _mm_validate_tree() -> dict:
    from tools import graph_tools

    return graph_tools.validate_query_tree()


@tool
def validate_query_tree() -> dict:
    """Validate orphan, multi-parent, cycle and handle invariants."""
    return _mm_validate_tree()


@tool
def get_next_actions(limit: int = 4) -> list:
    """Return ordered assess, expand or search actions from the state machine."""
    return _mm().get_next_actions(limit)


@tool
def assess_query(query_id: str) -> dict:
    """Assess one Query's owned subgraph and automatically advance its state."""
    return _mm().assess_query(query_id)


@tool
def evaluate_research_portfolio(goal_id: Optional[str] = None) -> dict:
    """Select globally valuable candidate gaps and defer low-value work."""
    return _mm().evaluate_research_portfolio(goal_id)


@tool
def expand_gaps(parent_id: str, gap_ids: Optional[list[str]] = None) -> dict:
    """Group selected gaps by direction/subject and create strict-tree Queries."""
    return _mm().expand_gaps(parent_id, gap_ids)


@tool
def assess_convergence(goal_id: Optional[str] = None) -> dict:
    """Authorize reporting after Objective convergence or budget exhaustion."""
    return _mm().assess_convergence(goal_id)


@tool
def create_analysis(text: str, query_id: Optional[str] = None) -> dict:
    """Record a typed insight, resolving an optional Query handle safely."""
    return _mm().create_insight(text, query_id)


@tool
def get_query_evaluation_subgraph(query_id: str) -> dict:
    """Read the evidence owned by one Query, excluding parent and sibling evidence."""
    from tools import graph_tools

    try:
        resolved = graph_tools.resolve_query_reference(query_id)
    except AmbiguousQueryReference as exc:
        return {"error": str(exc)}
    if resolved is None:
        return {"error": f"Unknown query reference: {query_id!r}"}
    return graph_tools.get_query_evaluation_subgraph(resolved)


@tool
def get_subgraph(node_id: str, depth: int = 2) -> dict:
    """Read a general graph neighborhood for inspection."""
    from tools import graph_tools

    return graph_tools.get_subgraph(node_id, depth)


@tool
def get_node(node_id: str) -> dict:
    """Read one graph node by exact ID."""
    from tools import graph_tools

    return graph_tools.get_node(node_id)


@tool
def submit_search_result(search_run_id: str, query_id: str, evidence_package: dict) -> dict:
    """Write evidence into an existing SearchRun and advance Query state."""
    return _mm().submit_search_result(search_run_id, query_id, evidence_package)


def export_report_context(goal_id: Optional[str] = None) -> dict:
    """Export compact outline metadata after the reporter gate authorizes writing."""
    return _mm().export_report_context(goal_id)


def commit_report_outline(title: str, chapters: list[dict]) -> dict:
    """Persist the reporter's chapter-level outline for the current run.
    
    Args:
        title: Report title string.
        chapters: List of chapter dicts, each must contain:
            - chapter_id (int, REQUIRED): Chapter number starting from 1.
            - title (str, REQUIRED): Chapter title.
            - goals (list[str]): Writing goals for this chapter.
            - query_refs (list[str], REQUIRED): Query handles (e.g. ["q1"]).
            - section_plan (str): Brief plan for this chapter.
            - section_type (str): "lead" or "body".
    
    Example:
        commit_report_outline("Ring of Nestor", [
            {"chapter_id": 1, "title": "Lead", "goals": ["..."], "query_refs": ["q1"], "section_plan": "...", "section_type": "lead"},
            {"chapter_id": 2, "title": "Discovery", "goals": ["..."], "query_refs": ["q1"], "section_plan": "...", "section_type": "body"},
        ])
    """
    from tools import report_tools

    return report_tools.commit_report_outline(_cache_dir, title, chapters)


def prepare_report_chapter_batch(
    chapters: list[dict],
) -> dict:
    """Load one to three chapter plans with chapter-local evidence references.
    
    Args:
        chapters: List of chapter dicts, each MUST contain:
            - chapter_id (int, REQUIRED): Must match the chapter_id from commit_report_outline (e.g. 1, 2, 3).
            - extra_query_refs (list[str]): Additional query handles to load.
    
    Example:
        prepare_report_chapter_batch([
            {"chapter_id": 1, "extra_query_refs": []},
            {"chapter_id": 2, "extra_query_refs": ["q1"]},
        ])
    
    Returns chapter-local refs like e1/e2 (Evidence), c1/c2 (Claims), x1/x2 (Conflicts).
    """
    from tools import report_tools

    return report_tools.prepare_report_chapter_batch(_cache_dir, chapters)


def commit_report_chapter_batch(
    chapters: list[dict],
) -> dict:
    """Save and validate one to three complete chapter candidates.
    
    Args:
        chapters: List of chapter dicts, each MUST contain:
            - chapter_id (int, REQUIRED): Must match the chapter_id from outline.
            - bundle_token (str, REQUIRED): Token from prepare_report_chapter_batch.
            - content (str, REQUIRED): Full chapter text with inline [n] citations.
            - evidence_refs (list[str], REQUIRED): All e*/c* refs used in content.
            - disclosed_conflict_refs (list[str]): x* refs for disclosed conflicts.
    
    Example:
        commit_report_chapter_batch([
            {
                "chapter_id": 1,
                "bundle_token": "token_from_prepare",
                "content": "Full chapter text with [1] citations...",
                "evidence_refs": ["e1", "e2", "c1"],
                "disclosed_conflict_refs": ["x1"]
            },
        ])
    """
    from tools import report_tools

    return report_tools.commit_report_chapter_batch(_cache_dir, chapters)


def submit_final_report() -> dict:
    """Review once, revise once, and always deliver the latest complete report."""
    global _report_review_completed, _report_review_had_issues, _report_submit_count
    from tools import report_tools

    _report_submit_count += 1
    candidate = report_tools.submit_committed_report(_cache_dir)
    if not _report_review_completed:
        _report_review_completed = True
        try:
            review_issues = _review_report_once(candidate["report"])
        except Exception as exc:  # noqa: BLE001 - review is explicitly fail-open
            logger.warning("Report Review failed open: %s", exc)
            final = report_tools.submit_committed_report(_cache_dir, persist=True)
            final["review_status"] = "failed_open"
            final["review_error"] = str(exc)
            final["revision_requested"] = False
            _record_report_result(final, finalized=True)
            return final
        combined_issues = list(candidate.get("issues") or []) + [
            {
                "code": "report_review_issue",
                "severity": "soft",
                "section_title": "",
                "block_index": None,
                "message": issue,
                "repair_hint": "Update the affected chapter candidate, then submit once more.",
            }
            for issue in review_issues
        ]
        # Critical review patterns that must trigger revision even when
        # labeled soft by the reviewer. Pure soft issues (placeholder prose,
        # low retention, single-source reliance, etc.) are recorded but do
        # not consume the single revision slot.
        CRITICAL_REVIEW_PATTERNS = (
            "uncited factual",
            "citation has no URL-backed reference",
            "forbidden internal-process",
            "no valid cited sections",
            "missing_substantive_uncertainty",
        )
        hard_issues = [
            issue for issue in combined_issues
            if issue.get("severity") == "hard"
        ]
        critical_review_issues = [
            issue for issue in combined_issues
            if any(p in str(issue.get("message") or "") for p in CRITICAL_REVIEW_PATTERNS)
        ]
        should_revise = bool(hard_issues or critical_review_issues)
        if combined_issues:
            _report_review_had_issues = should_revise
            result = dict(candidate)
            result.update({
                "revision_requested": should_revise,
                "severity": "hard" if hard_issues else (
                    "soft" if combined_issues else "clean"
                ),
                "review_status": "issues" if should_revise else "soft_only_no_revise",
                "issues": combined_issues,
            })
            _record_report_result(result, finalized=not should_revise)
            return result

    final = report_tools.submit_committed_report(_cache_dir, persist=True)
    final["review_status"] = "revised_once" if _report_review_had_issues else "passed"
    final["revision_requested"] = False
    _record_report_result(final, finalized=True)
    return final


def deliver_final_report() -> dict:
    """Deliver the latest complete report once, without review or persistence."""
    global _report_submit_count
    from tools import report_tools

    _report_submit_count += 1
    final = report_tools.deliver_committed_report(_cache_dir)
    _record_report_result(final, finalized=True)
    return final


def assemble_report_draft() -> dict:
    """组装完整报告草稿，但不将其登记为最终交付物."""
    from tools import report_tools

    return report_tools.assemble_committed_report(_cache_dir)


def deliver_polished_report(
    report: str,
    *,
    issues: Optional[list[dict[str, Any]]] = None,
) -> dict:
    """将润色后的完整 Markdown 登记为当前运行的最终报告."""
    global _report_submit_count

    _report_submit_count += 1
    report_text = str(report or "").strip()
    report_text = f"{report_text}\n" if report_text else ""
    report_issues = list(issues or [])
    severity = (
        "hard"
        if any(item.get("severity") == "hard" for item in report_issues)
        else ("soft" if report_issues else "clean")
    )
    final = {
        "delivered": bool(report_text),
        "validated": False,
        "accepted": False,
        "revision_requested": False,
        "review_status": "skipped",
        "severity": severity,
        "report": report_text,
        "salvaged_report": report_text,
        "graph_persisted": False,
        "issues": report_issues,
    }
    _record_report_result(final, finalized=True)
    return final


def deliver_global_report(
    body: str,
    *,
    issues: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Compile and persist a report produced by the global Reporter writer."""
    global _report_submit_count
    from tools import report_tools

    _report_submit_count += 1
    compiled = report_tools.compile_global_writer_report(_cache_dir, body)
    compiler_issues = [
        {"code": "global_report_validation", "severity": "hard", "message": message}
        for message in compiled.get("hard_issues") or []
    ]
    all_issues = list(issues or []) + compiler_issues
    final = {
        "delivered": bool(compiled.get("report")) and not compiled.get("hard_issues"),
        "validated": not bool(compiled.get("hard_issues")),
        "accepted": not bool(compiled.get("hard_issues")),
        "revision_requested": bool(compiled.get("hard_issues")),
        "review_status": "global_compiler",
        "severity": "hard" if compiled.get("hard_issues") else ("soft" if all_issues else "clean"),
        "report": compiled.get("report", ""),
        "salvaged_report": compiled.get("report", ""),
        "graph_persisted": False,
        "issues": all_issues,
        "cited_numbers": compiled.get("cited_numbers", []),
    }
    if compiled.get("hard_issues"):
        logger.warning(
            "[reporter.global] compilation_rejected issues=%s",
            len(compiled["hard_issues"]),
        )
    else:
        logger.info(
            "[reporter.global] compilation_succeeded chars=%s citations=%s",
            len(final["report"]),
            len(final["cited_numbers"]),
        )
    _record_report_result(final, finalized=bool(final["delivered"]))
    return final


def get_report_submit_count() -> int:
    """Return the run-scoped number of final report submissions."""
    return _report_submit_count


def increment_reporter_model_call_count() -> int:
    """Increment and return the run-scoped Reporter model-call count."""
    global _report_model_call_count
    with _report_lock:
        _report_model_call_count += 1
        return _report_model_call_count


def get_reporter_model_call_count() -> int:
    """Return the run-scoped Reporter model-call count."""
    with _report_lock:
        return _report_model_call_count


ORCHESTRATOR_TOOLS: list[Any] = [
    init_research,
    get_research_status,
    get_research_objectives,
    validate_query_tree,
    get_next_actions,
    assess_query,
    evaluate_research_portfolio,
    expand_gaps,
    assess_convergence,
    create_analysis,
    get_query_evaluation_subgraph,
    get_subgraph,
    get_node,
]

SEARCHER_TOOLS: list[Any] = [submit_search_result]
