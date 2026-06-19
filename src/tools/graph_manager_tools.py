"""State-machine Graph Manager tools exposed to GraphResearcher agents."""

from threading import Lock
from typing import Any, Optional

from langchain_core.tools import tool

from agents.memory_manager import AmbiguousQueryReference, MemoryManager

_manager: Optional[MemoryManager] = None
_cache_dir: Optional[str] = None
_report_lock = Lock()


def configure(output_dir: Optional[str] = None) -> None:
    """Clear and scope graph storage, then rebuild the shared manager for a run."""
    global _cache_dir, _manager
    _cache_dir = output_dir
    _manager = None
    from tools import convergence, graph_tools, report_workspace

    run_context = output_dir or "default"
    graph_tools.set_context(run_context)
    graph_tools.clear_current_context()
    convergence.reset()
    report_workspace.configure(output_dir, reset=True)


def _mm() -> MemoryManager:
    global _manager
    if _manager is None:
        _manager = MemoryManager(cache_dir=_cache_dir)
    return _manager


def get_compiled_report() -> str:
    """Return the best structured Reporter report for compatibility."""
    from tools import report_workspace

    return report_workspace.best_report()


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
def commit_report_outline(title: str, chapters: list[dict]) -> dict:
    """Persist an evidence-grounded report outline with Objective mappings."""
    from tools import report_workspace, research_state

    result = report_workspace.commit_outline(title, chapters)
    if not result.get("error"):
        research_state.update_goal({
            "report_phase": "drafting",
            "report_validation_issues": result.get("issues") or [],
        })
    return result


@tool
def prepare_report_chapter_bundle(chapter_id: int, relevant_item_ids: Optional[list[str]] = None) -> dict:
    """Load a chapter and expand Query/Objective/item references into evidence."""
    from tools import report_tools, report_workspace

    chapter = report_workspace.get_chapter(chapter_id)
    if chapter is None:
        return {"error": f"Unknown report chapter: {chapter_id}"}
    references = [
        *(chapter.get("candidate_item_ids") or []),
        *(chapter.get("objective_ids") or []),
        *(relevant_item_ids or []),
    ]
    item_ids = report_tools.resolve_report_item_ids(references)
    items = report_tools.get_report_items(item_ids)
    report_workspace.update_chapter_status(chapter_id, "in_progress")
    return {
        "chapter": chapter,
        "items": items,
        "item_count": len(items),
        "unresolved_references": [
            reference for reference in dict.fromkeys(references)
            if reference not in item_ids and not report_tools.resolve_report_item_ids([reference])
        ],
    }


@tool
def commit_report_chapter(chapter_id: int, blocks: list[dict]) -> dict:
    """Compile and persist one chapter from Claim/Evidence-bound blocks."""
    from tools import report_tools, report_workspace

    chapter = report_workspace.get_chapter(chapter_id)
    if chapter is None:
        return {"error": f"Unknown report chapter: {chapter_id}"}
    compiled = report_tools.compile_bound_blocks(blocks)
    if compiled.get("error"):
        return compiled
    metadata = {
        "chapter_id": chapter_id,
        "title": chapter.get("title"),
        "objective_ids": chapter.get("objective_ids") or [],
        "source_ids": compiled["source_ids"],
        "claim_ids": compiled["claim_ids"],
        "evidence_ids": compiled["evidence_ids"],
        "blocks": compiled["blocks"],
        "block_count": compiled["block_count"],
    }
    saved = report_workspace.save_chapter(chapter_id, compiled["content"], metadata)
    return {**saved, **metadata}


@tool
def record_report_conflict(
    description: str,
    evidence_ids: list[str],
    chapter_id: Optional[int] = None,
    resolution: Optional[str] = None,
) -> dict:
    """Record a report-stage evidence conflict in the graph and artifacts."""
    from tools import graph_tools, report_workspace

    try:
        conflict_id = graph_tools.create_conflict(
            description=description,
            evidence_ids=evidence_ids,
            conflict_type="factual",
            resolution_status="disclosed",
        )
    except ValueError as exc:
        return {"error": str(exc)}
    entry = {
        "id": conflict_id,
        "description": description,
        "evidence_ids": evidence_ids,
        "chapter_id": chapter_id,
        "resolution": resolution,
    }
    report_workspace.save_conflict(entry)
    return {"status": "ok", "conflict": entry}


@tool
def assemble_report_draft() -> dict:
    """Assemble all committed chapters into a deterministic cited draft."""
    from tools import report_tools, report_workspace

    outline = report_workspace.get_outline()
    if not outline:
        return {"error": "Report outline has not been committed"}
    missing = [
        chapter["chapter_id"] for chapter in outline.get("chapters", [])
        if not report_workspace.chapter_text(chapter["chapter_id"])
    ]
    if missing:
        return {"error": f"Report chapters are incomplete: {missing}"}
    sections = []
    submission_sections = []
    for chapter in outline["chapters"]:
        metadata = report_workspace.chapter_metadata(chapter["chapter_id"])
        sections.append({
            "title": chapter["title"],
            "content": report_workspace.chapter_text(chapter["chapter_id"]),
            "source_ids": metadata.get("source_ids") or [],
        })
        submission_sections.append({
            "title": chapter["title"],
            "objective_ids": metadata.get("objective_ids") or [],
            "blocks": metadata.get("blocks") or [],
        })
    draft = report_tools.assemble_cited_sections(outline.get("title") or "Research Report", sections)
    report_workspace.save_draft(draft)
    return {
        "status": "ok",
        "draft_path": "reports/draft.md",
        "chapter_count": len(sections),
        "content_length": len(draft),
        "submission_sections": submission_sections,
    }


@tool
def get_report_status() -> dict:
    """Return outline, chapter, draft, candidate, and review progress."""
    from tools import report_workspace, research_state

    return {**report_workspace.get_status(), "review": research_state.get_status()}


@tool
def get_report_review_issues() -> dict:
    """Return the current review issues and requested revision state."""
    from tools import report_workspace, research_state

    status = research_state.get_status()
    return {
        "report_phase": status.get("report_phase"),
        "report_revision_attempts": status.get("report_revision_attempts", 0),
        "report_validation_issues": status.get("report_validation_issues") or [],
        "best_candidate": report_workspace.best_metadata(),
    }


@tool
def get_reference_registry() -> list[dict]:
    """Return the complete stable Source ID, citation number and URL registry."""
    from tools import report_tools

    return report_tools.get_reference_registry()


@tool
def submit_final_report(title: str, sections: list[dict]) -> dict:
    """Validate and compile the canonical report from cited structured blocks.

    Every section requires ``blocks``. Each block requires ``text`` and one or
    more exact ``claim_ids`` or ``evidence_ids``; citations are derived from
    their URL-backed sources.
    """
    from tools import report_tools, report_workspace, research_state

    status = research_state.get_status()
    outline = report_workspace.get_outline()
    if outline:
        expected_count = len(outline.get("chapters") or [])
        submitted_count = len(sections or [])
        if submitted_count < expected_count:
            return {
                "error": "Structured report validation failed",
                "issues": [
                    f"report omits outline chapters: submitted {submitted_count}, expected {expected_count}",
                ],
            }
        if status.get("report_phase") != "revision_requested":
            missing = [
                chapter["chapter_id"] for chapter in outline.get("chapters", [])
                if not report_workspace.chapter_text(chapter["chapter_id"])
            ]
            if missing:
                return {
                    "error": "Structured report validation failed",
                    "issues": [f"report chapters are incomplete: {missing}"],
                }
            if not report_workspace.draft_text().strip():
                return {
                    "error": "Structured report validation failed",
                    "issues": ["report draft has not been assembled"],
                }

    result = report_tools.compile_structured_report(title, sections)
    report = result.get("report", "") if isinstance(result, dict) else ""
    if not report:
        return result
    objective_ids = set(result.get("objective_ids") or [])
    objective_ids.update(report_workspace.objective_ids_for_items([
        *(result.get("claim_ids") or []),
        *(result.get("evidence_ids") or []),
    ]))
    quality_issues = report_tools.collect_report_quality_issues(
        report,
        covered_objective_ids=sorted(objective_ids),
        draft_text=report_workspace.draft_text(),
    )
    must_ids = {
        objective["id"]
        for objective in _mm().get_research_objectives()
        if objective.get("requirement") == "must"
    }
    metadata = {
        "structural_issues": [],
        "quality_issues": quality_issues,
        "covered_objective_ids": sorted(objective_ids),
        "covered_must_objectives": len(must_ids & objective_ids),
        "bound_block_count": result.get("bound_block_count", 0),
        "blocks": result.get("blocks") or [],
        "sections": result.get("sections") or [],
    }
    with _report_lock:
        saved = report_workspace.save_candidate(report, metadata)
    research_state.update_goal({
        "report_phase": "submitted",
        "report_validation_issues": quality_issues,
    })
    return {
        "accepted": True,
        "review_required": True,
        "quality_issues": quality_issues,
        **saved,
        **{key: value for key, value in result.items() if key != "report"},
    }


@tool
def get_report_review_bundle(offset: int = 0, limit: int = 20) -> dict:
    """Return a compact page of candidate blocks with bound evidence for review."""
    from tools import report_tools, report_workspace, research_state

    status = research_state.get_status()
    if status.get("research_state") != research_state.REPORTING:
        return {"error": "Report review is only available while research_state is REPORTING"}
    if status.get("report_phase") == "revision_requested":
        return {
            "status": "revision_requested",
            "next_action": "dispatch_reporter",
            "report_revision_attempts": status.get("report_revision_attempts", 0),
            "issues": status.get("report_validation_issues") or [],
        }
    if status.get("report_phase") not in {"submitted", "reviewing"}:
        return {"error": f"Report review is unavailable during phase {status.get('report_phase')!r}"}
    offset = max(0, int(offset or 0))
    limit = min(100, max(1, int(limit or 20)))
    metadata = report_workspace.best_metadata()
    if not metadata:
        return {"error": "Reporter submitted no valid candidate report"}
    research_state.update_goal({"report_phase": "reviewing"})
    blocks = metadata.get("blocks") or []
    page = blocks[offset : offset + limit]
    item_ids = [
        item_id for block in page
        for item_id in [*(block.get("claim_ids") or []), *(block.get("evidence_ids") or [])]
    ]
    next_offset = offset + len(page)
    return {
        "report_phase": research_state.get_status().get("report_phase"),
        "quality_issues": metadata.get("quality_issues") or [],
        "deterministic_audit": {
            "structural_issues": metadata.get("structural_issues") or [],
            "quality_issues": metadata.get("quality_issues") or [],
            "covered_objective_ids": metadata.get("covered_objective_ids") or [],
            "covered_must_objectives": metadata.get("covered_must_objectives") or 0,
            "bound_block_count": metadata.get("bound_block_count") or 0,
        },
        "blocks": page,
        "bound_items": report_tools.get_report_items(item_ids),
        "objectives": _mm().get_research_objectives(),
        "offset": offset,
        "limit": limit,
        "total": len(blocks),
        "next_offset": next_offset if next_offset < len(blocks) else None,
    }


@tool
def complete_report_review(additional_issues: Optional[list[str]] = None) -> dict:
    """Accept the report or request one of at most two targeted revisions."""
    from tools import report_workspace, research_state

    status = research_state.get_status()
    if status.get("research_state") != research_state.REPORTING:
        return {"error": "Report review is only available while research_state is REPORTING"}
    if status.get("report_phase") == "revision_requested":
        return {
            "accepted": False,
            "next_action": "dispatch_reporter",
            "report_revision_attempts": status.get("report_revision_attempts", 0),
            "issues": status.get("report_validation_issues") or [],
        }
    if status.get("report_phase") != "reviewing":
        return {"error": f"Report review cannot complete during phase {status.get('report_phase')!r}"}
    goal = research_state.get_goal()
    metadata = (
        report_workspace.annotate_best_candidate(additional_issues or [])
        if additional_issues else report_workspace.best_metadata()
    )
    issues = list(dict.fromkeys([
        *(metadata.get("quality_issues") or []),
        *(additional_issues or []),
    ]))
    if not metadata:
        issues.insert(0, "Reporter submitted no valid candidate report")
    attempts = int(goal.get("report_revision_attempts") or 0)
    if issues and attempts < 2:
        attempts += 1
        research_state.update_goal({
            "report_phase": "revision_requested",
            "report_revision_attempts": attempts,
            "report_quality_status": None,
            "report_validation_issues": issues,
        })
        return {
            "accepted": False,
            "next_action": "dispatch_reporter",
            "report_revision_attempts": attempts,
            "issues": issues,
        }
    quality_status = "limited" if issues else "passed"
    research_state.update_goal({
        "report_phase": "accepted",
        "report_quality_status": quality_status,
        "report_validation_issues": issues,
    })
    return {
        "accepted": True,
        "report_quality_status": quality_status,
        "report_revision_attempts": attempts,
        "issues": issues,
    }


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
    get_report_review_bundle,
    complete_report_review,
]

SEARCHER_TOOLS: list[Any] = [submit_search_result]

REPORTER_TOOLS: list[Any] = [
    export_report_context,
    get_report_evidence,
    commit_report_outline,
    prepare_report_chapter_bundle,
    commit_report_chapter,
    record_report_conflict,
    assemble_report_draft,
    get_report_status,
    get_report_review_issues,
    get_reference_registry,
    submit_final_report,
]
