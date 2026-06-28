"""State-machine Graph Manager tools exposed to GraphResearcher agents."""

import json
from pathlib import Path
from threading import Lock
from typing import Any, Optional

from langchain_core.tools import tool

from agents.memory_manager import AmbiguousQueryReference, MemoryManager

_manager: Optional[MemoryManager] = None
_cache_dir: Optional[str] = None
_compiled_report: str = ""
_salvaged_report: str = ""
_best_report: str = ""
_last_report_attempt: dict[str, Any] = {}
_report_lock = Lock()


def configure(output_dir: Optional[str] = None) -> None:
    """Clear and scope graph storage, then rebuild the shared manager for a run."""
    global _best_report, _cache_dir, _compiled_report, _last_report_attempt, _manager, _salvaged_report
    _cache_dir = output_dir
    _manager = None
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
        for relative in (".report_outline.json", ".report_outline.md", ".report_draft.md"):
            path = Path(_cache_dir) / relative if _cache_dir else None
            if path and path.exists():
                path.unlink()
        chapter_dir = Path(_cache_dir) / ".report_chapters" if _cache_dir else None
        if chapter_dir and chapter_dir.exists():
            for child in chapter_dir.iterdir():
                if child.is_file():
                    child.unlink()
            chapter_dir.rmdir()
    from tools import convergence, graph_tools

    run_context = output_dir or "default"
    graph_tools.set_context(run_context)
    graph_tools.clear_current_context()
    convergence.reset()


def _mm() -> MemoryManager:
    global _manager
    if _manager is None:
        _manager = MemoryManager(cache_dir=_cache_dir)
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
def init_research(user_request: str) -> dict:
    """Initialize a strict Query tree and persistent research state."""
    return _mm().init_research(user_request)


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
    """Group selected atomic gaps by search subject and create child Queries."""
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
    try:
        resolved = _mm()._resolve_query_id(query_id)  # central resolver; read-only tool
    except AmbiguousQueryReference as exc:
        return {"error": str(exc)}
    if resolved is None:
        return {"error": f"Unknown query reference: {query_id!r}"}
    from tools import graph_tools

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


@tool
def export_report_context(goal_id: Optional[str] = None) -> dict:
    """Export compact report metadata after the reporter gate authorizes writing."""
    return _mm().export_report_context(goal_id)


@tool
def get_report_evidence(query_id: str, offset: int = 0, limit: int = 20) -> dict:
    """Return one compact page of citation-ready Claim/Evidence items."""
    return _mm().get_report_evidence(query_id, offset=offset, limit=limit)


@tool
def get_reference_registry() -> list[dict]:
    """Return the complete stable Source ID, citation number and URL registry."""
    from tools import report_tools

    return report_tools.get_reference_registry()


@tool
def commit_report_outline(title: str, chapters: list[dict]) -> dict:
    """Persist the reporter's chapter-level outline for the current run."""
    from tools import report_tools

    return report_tools.commit_report_outline(_cache_dir, title, chapters)


@tool
def prepare_report_chapter_bundle(chapter_id: int, extra_query_ids: Optional[list[str]] = None) -> dict:
    """Load one chapter plan together with its evidence bundle."""
    from tools import report_tools

    return report_tools.prepare_report_chapter_bundle(_cache_dir, chapter_id, extra_query_ids)


@tool
def commit_report_chapter(
    chapter_id: int,
    title: str,
    content: str,
    source_ids: list[str],
    evidence_ids: Optional[list[str]] = None,
    disclosed_conflict_ids: Optional[list[str]] = None,
    section_type: Optional[str] = None,
) -> dict:
    """Persist one chapter draft and its source/evidence bindings."""
    from tools import report_tools

    return report_tools.commit_report_chapter(
        _cache_dir,
        chapter_id,
        title,
        content,
        source_ids,
        evidence_ids=evidence_ids,
        disclosed_conflict_ids=disclosed_conflict_ids,
        section_type=section_type,
    )


@tool
def assemble_report_draft() -> dict:
    """Assemble completed chapter drafts into one provisional report draft."""
    from tools import report_tools

    return report_tools.assemble_report_draft(_cache_dir)


@tool
def submit_final_report(title: str, sections: list[dict]) -> dict:
    """Validate and compile the canonical report from cited chapter sections.

    Every section requires ``title``, prose ``content``, and URL-backed
    ``source_ids``. Optional ``evidence_ids`` and ``disclosed_conflict_ids``
    preserve graph traceability. ``section_type="conflict_disclosure"`` marks
    a dedicated conflict section.
    """
    global _best_report, _compiled_report, _last_report_attempt, _salvaged_report
    from tools import report_tools

    result = report_tools.compile_structured_report(title, sections)
    with _report_lock:
        _compiled_report = str(result.get("report") or "")
        _salvaged_report = str(result.get("salvaged_report") or "")
        _best_report = _compiled_report or _salvaged_report
        _last_report_attempt = dict(result)

        _write_optional_text(_compiled_report_path(), _compiled_report)
        _write_optional_text(_salvaged_report_path(), _salvaged_report)
        _write_optional_text(_best_report_path(), _best_report)

        path = _report_attempt_path()
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


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

REPORTER_TOOLS: list[Any] = [
    export_report_context,
    get_report_evidence,
    get_reference_registry,
    commit_report_outline,
    prepare_report_chapter_bundle,
    commit_report_chapter,
    assemble_report_draft,
    submit_final_report,
]
