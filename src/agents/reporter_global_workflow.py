"""Single-pass, full-context Reporter workflow with deterministic compilation."""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

import config
from tools import graph_manager_tools, graph_tools, report_tools, research_state
from tools.research_requirements import inspect_delivery_packet

logger = logging.getLogger(__name__)
_MAX_ATTEMPTS = 3
_QUERY_PACKET_SHARE = 1 / 12
_STRUCTURE_HEADING_RE = re.compile(r"(?m)^\s{0,3}(?:#{1,6}\s+)?(?:part|section|chapter|第[一二三四五六七八九十]+部分|[一二三四五六七八九十]+[、.)])\s*(.+?)\s*$", re.IGNORECASE)
_NUMBERED_ITEM_RE = re.compile(r"(?m)^\s*(?:\d+[.)]|[一二三四五六七八九十]+[、.)])\s+(.+?)\s*$")
_TABLE_SIGNAL_RE = re.compile(r"(?:表格|对比表|比较表|summary table|comparison table|table)", re.IGNORECASE)
_NUMBER_SIGNAL_RE = re.compile(r"(?:具体数据|具体数字|数值|百分比|均值|标准差|specific data|exact number|percentage|mean|standard deviation)", re.IGNORECASE)
_TIME_SIGNAL_RE = re.compile(r"(?:截至|截止|时间范围|之前|之后|as of|before|after|between|from .*? to)", re.IGNORECASE)


def _response_text(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, list):
        return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
    return str(content or "")


def _write_artifact(root: Path, name: str, value: Any) -> None:
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _try_write_artifact(root: Path, name: str, value: Any) -> None:
    """Persist diagnostics without making artifact storage a report failure."""
    try:
        _write_artifact(root, name, value)
    except OSError:
        logger.warning(
            "[reporter.global] artifact_write_failed path=%s error_type=%s",
            root / name,
            "OSError",
            exc_info=True,
        )


def _estimate_tokens(value: Any) -> int:
    return max(1, len(json.dumps(value, ensure_ascii=False)) // 4)


def _evidence_key(item: dict[str, Any]) -> str:
    """Return a stable key for duplicate evidence exported by multiple queries."""
    item_id = str(item.get("id") or "").strip()
    if item_id:
        return f"id:{item_id}"
    text = re.sub(r"\s+", " ", str(item.get("text") or "")).strip().casefold()
    return f"text:{text}" if text else ""


def _derive_task_requirements(request: str) -> dict[str, Any]:
    """Extract explicit, surface-level delivery requirements from the request."""
    text = re.sub(r"\s+", " ", str(request or "")).strip()
    headings = [match.group(1).strip(" ：:") for match in _STRUCTURE_HEADING_RE.finditer(request or "")]
    numbered_items = [match.group(1).strip() for match in _NUMBERED_ITEM_RE.finditer(request or "")]
    return {
        "sections": list(dict.fromkeys(headings))[:20],
        "explicit_items": list(dict.fromkeys(numbered_items))[:40],
        "requires_table": bool(_TABLE_SIGNAL_RE.search(text)),
        "requires_exact_values": bool(_NUMBER_SIGNAL_RE.search(text)),
        "has_time_scope": bool(_TIME_SIGNAL_RE.search(text)),
        "language_hint": "zh" if re.search(r"[\u4e00-\u9fff]", text) else "en",
    }


def _build_answer_contract(context: dict[str, Any]) -> dict[str, Any]:
    """Project explicit request requirements into the delivery compiler contract."""
    return report_tools.build_answer_contract(
        str(context.get("user_request") or ""),
        context.get("required_structure") or [],
    )


_NOTE_ID_LIST_FIELDS = ("confirmed_facts", "claim_refs", "source_ids")
_NOTE_ID_LIST_CAP = 100


def _cap_research_notes(notes: list[dict[str, Any]], max_chars: int) -> list[dict[str, Any]]:
    """Bound per-query research notes entering the writer prompt.

    Notes are compact metadata; the only unbounded parts are the
    confirmed-fact / claim / source id lists. Trim those first, then drop
    whole notes when the serialized budget is exceeded (notes are exported in
    query-priority order, so the least important queries are dropped first).
    """
    capped: list[dict[str, Any]] = []
    used_chars = 0
    for raw_note in notes or []:
        note = dict(raw_note)
        for field in _NOTE_ID_LIST_FIELDS:
            values = note.get(field) or []
            if len(values) > _NOTE_ID_LIST_CAP:
                note[field] = values[:_NOTE_ID_LIST_CAP]
                note.setdefault("truncated_fields", {})[field] = len(values)
        note_chars = len(json.dumps(note, ensure_ascii=False))
        if used_chars + note_chars > max_chars:
            continue
        capped.append(note)
        used_chars += note_chars
    return capped


def _build_packet(
    context: dict[str, Any], *, read_view: report_tools.ReportReadView | None = None,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    view_kwargs = {"read_view": read_view} if read_view is not None else {}
    global_budget_full = False
    findings: list[dict[str, Any]] = []
    research_notes: list[dict[str, Any]] = []
    export_errors: list[dict[str, Any]] = []
    used_numbers: set[int] = set()
    budget = config.GR_GLOBAL_PACKET_TOKENS * 4
    query_budget = max(1, int(budget * _QUERY_PACKET_SHARE))
    used_chars = 0
    seen_evidence: set[str] = set()
    objectives = {
        objective.get("objective_key"): objective
        for objective in context.get("objectives") or []
        if objective.get("objective_key")
    }

    def query_priority(query: dict[str, Any]) -> tuple[int, float, str]:
        linked = [objectives[key] for key in query.get("objective_keys") or [] if key in objectives]
        unmet = any(
            objective.get("requirement") == "must"
            and objective.get("status") != "satisfied"
            for objective in linked
        )
        coverage = min((float(objective.get("coverage") or 0.0) for objective in linked), default=1.0)
        return (0 if unmet else 1, coverage, str(query.get("ref") or ""))

    ordered_queries = sorted(context.get("queries") or [], key=query_priority)
    logger.info(
        "[reporter.global] packet_build_started queries=%s budget_tokens=%s",
        len(ordered_queries),
        config.GR_GLOBAL_PACKET_TOKENS,
    )
    for query_index, query in enumerate(ordered_queries, start=1):
        query_ref = str(query.get("ref") or "").strip()
        if not query_ref:
            continue
        query_started_at = time.perf_counter()
        offset = 0
        query_items: list[dict[str, Any]] = []
        query_chars = 0
        query_budget_full = False
        while True:
            page = report_tools.get_report_evidence(query_ref, offset=offset, limit=100, **view_kwargs)
            if page.get("error"):
                error = str(page["error"])
                export_errors.append({"query": query_ref, "offset": offset, "error": error})
                logger.warning(
                    "[reporter.global] evidence_export_failed query=%s offset=%s error=%s",
                    query_ref,
                    offset,
                    error[:500],
                )
                break
            if page.get("research_notes"):
                research_notes.append(page["research_notes"])
            for item in page.get("items") or []:
                compact = {
                    "id": item.get("id"),
                    "type": item.get("type"),
                    "text": item.get("text"),
                    "confidence": item.get("confidence"),
                    "qualifiers": item.get("qualifiers") or [],
                    "limitations": item.get("limitations") or [],
                    "citations": item.get("citations") or [],
                    "sources": item.get("sources") or [],
                    "claim_relations": item.get("claim_relations") or [],
                    "evidence_relations": item.get("evidence_relations") or [],
                    "target_components": query.get("target_components") or [],
                    "target_sections": query.get("target_sections") or [],
                }
                evidence_key = _evidence_key(compact)
                if evidence_key and evidence_key in seen_evidence:
                    continue
                item_chars = len(json.dumps(compact, ensure_ascii=False))
                if used_chars + item_chars > budget:
                    global_budget_full = True
                    break
                if query_chars + item_chars > query_budget:
                    query_budget_full = True
                    break
                query_items.append(compact)
                if evidence_key:
                    seen_evidence.add(evidence_key)
                query_chars += item_chars
                used_chars += item_chars
                used_numbers.update(int(number) for number in compact["citations"])
            if query_budget_full or global_budget_full or query_chars >= query_budget or used_chars >= budget or page.get("next_offset") is None:
                break
            offset = int(page["next_offset"])
        if query_items:
            findings.append({"query": query, "items": query_items})
        logger.info(
            "[reporter.global] packet_query_exported index=%s/%s query=%s items=%s chars=%s elapsed=%.2fs",
            query_index,
            len(ordered_queries),
            query_ref,
            len(query_items),
            query_chars,
            time.perf_counter() - query_started_at,
        )
        if global_budget_full or used_chars >= budget:
            logger.info(
                "[reporter.global] packet_budget_reached query=%s used_chars=%s budget_chars=%s",
                query_ref,
                used_chars,
                budget,
            )
            break

    research_notes = _cap_research_notes(research_notes, config.GR_REPORTER_NOTES_MAX_CHARS)
    ordered_query_refs = [
        str(query.get("ref") or query.get("id") or "").strip()
        for query in ordered_queries
        if str(query.get("ref") or query.get("id") or "").strip()
    ]
    draft_report = report_tools.build_cited_evidence_report(
        str(context.get("user_request") or ""),
        max_chars=config.GR_REPORTER_DRAFT_MAX_CHARS,
        query_order=ordered_query_refs,
        include_references=False,
        **view_kwargs,
    )
    used_numbers.update(
        int(match.group(1))
        for match in re.finditer(r"\[(\d+)\]", draft_report)
    )
    registry = [
        entry for entry in report_tools.build_reference_registry(**view_kwargs)
        if int(entry["n"]) in used_numbers
    ]
    answer_contract = _build_answer_contract(context)
    answer_contract["required_components"] = list(dict.fromkeys(
        component
        for query in context.get("queries") or []
        for component in query.get("target_components") or []
        if str(component).strip()
    ))
    packet = {
        "research_brief": {
            "user_request": context.get("user_request", ""),
            "research_goal": context.get("research_goal") or context.get("user_request", ""),
            "language": context.get("language"),
            "queries": context.get("queries") or [],
            "objectives": context.get("objectives") or [],
            "rubrics": context.get("rubrics") or [],
        },
        "required_data_points": [
            criterion
            for objective in context.get("objectives") or []
            for criterion in objective.get("acceptance_criteria") or []
        ],
        "rubrics": context.get("rubrics") or [],
        "required_structure": context.get("required_structure") or [],
        "task_requirements": _derive_task_requirements(str(context.get("user_request") or "")),
        "answer_contract": answer_contract,
        "findings": findings,
        "research_notes": research_notes,
        "component_buckets": {
            component: [
                group for group in findings
                if component in (group.get("query", {}).get("target_components") or [])
            ]
            for component in sorted({
                component
                for query in context.get("queries") or []
                for component in query.get("target_components") or []
            })
        },
        "draft_report": draft_report,
        "conflicts": context.get("disclosed_conflicts") or [],
        "citation_registry": registry,
        "blocked_sources": context.get("blocked_sources") or [],
        "export_errors": export_errors,
        "budget": {
            "tokens": config.GR_GLOBAL_PACKET_TOKENS,
            "estimated_tokens": _estimate_tokens(findings),
            "query_share": _QUERY_PACKET_SHARE,
            "query_budget_chars": query_budget,
            "deduplicated_items": len(seen_evidence),
            "draft_report_chars": len(draft_report),
            "draft_max_chars": config.GR_REPORTER_DRAFT_MAX_CHARS,
            "research_notes_chars": len(json.dumps(research_notes, ensure_ascii=False)),
        },
    }
    if packet["rubrics"]:
        packet["atomic_diagnostics"] = inspect_delivery_packet(packet)
    logger.info(
        "[reporter.global] packet_built queries=%s findings=%s estimated_tokens=%s "
        "budget_tokens=%s citations=%s export_errors=%s elapsed=%.2fs",
        len(context.get("queries") or []),
        sum(len(group["items"]) for group in findings),
        packet["budget"]["estimated_tokens"],
        config.GR_GLOBAL_PACKET_TOKENS,
        len(registry),
        len(export_errors),
        time.perf_counter() - started_at,
    )
    return packet


def _prompt(packet: dict[str, Any], feedback: str = "") -> str:
    template = config.reporter_global_system_prompt
    replacements = {
        "user_request": packet["research_brief"].get("user_request", ""),
        "research_brief": packet["research_brief"].get("research_goal") or json.dumps(packet["research_brief"], ensure_ascii=False),
        "required_data_points": json.dumps(packet.get("required_data_points") or [], ensure_ascii=False),
        "rubrics": json.dumps(packet.get("rubrics") or [], ensure_ascii=False),
        "required_structure": json.dumps(packet.get("required_structure") or [], ensure_ascii=False),
        "task_requirements": json.dumps(packet.get("task_requirements") or {}, ensure_ascii=False),
        "answer_contract": json.dumps(packet.get("answer_contract") or {}, ensure_ascii=False),
        "findings": json.dumps(packet["findings"], ensure_ascii=False),
        "research_notes": json.dumps(packet.get("research_notes") or [], ensure_ascii=False),
        "component_buckets": json.dumps(packet.get("component_buckets") or {}, ensure_ascii=False),
        "draft_report": packet.get("draft_report", ""),
        "conflicts": json.dumps(packet["conflicts"], ensure_ascii=False),
        "citation_registry": json.dumps(packet["citation_registry"], ensure_ascii=False),
        "atomic_diagnostics": json.dumps(packet.get("atomic_diagnostics") or {}, ensure_ascii=False),
        "retry_feedback": feedback,
    }
    return re.sub(
        r"<(user_request|research_brief|required_data_points|rubrics|atomic_diagnostics|required_structure|task_requirements|answer_contract|findings|research_notes|component_buckets|draft_report|conflicts|citation_registry|retry_feedback)>",
        lambda m: replacements[m.group(1)],
        template,
    )


def _authorize() -> dict[str, Any]:
    goal = research_state.get_goal()
    current = goal.get("research_state")
    if current == research_state.FAILED:
        # A failed run may still contain enough evidence for a bounded report.
        # Do not discard that evidence solely because a later search failed.
        successful_queries = [
            query
            for query in graph_tools.search_nodes("query", {})
            if int(query.get("successful_search_runs") or 0) > 0
        ]
        if not successful_queries:
            return {"error": "Reporter is not authorized from research state 'FAILED' without evidence"}
        research_state.update_goal({
            "research_state": research_state.REPORTING,
            "reporting_from_state": current,
            "report_authorized_reason": "best-effort report from partial research",
        })
        return {"error": "", "user_request": str(goal.get("request") or "")}
    if current not in research_state.REPORT_ALLOWED and current != research_state.REPORTING:
        return {"error": f"Reporter is not authorized from research state {current!r}"}
    if current != research_state.REPORTING:
        research_state.update_goal({"research_state": research_state.REPORTING, "reporting_from_state": current})
    return {"error": "", "user_request": str(goal.get("request") or "")}


def run_global_report_workflow() -> dict[str, Any]:
    """Run global Reporter writing and return a compact delivery result."""
    workflow_started_at = time.perf_counter()
    logger.info("[reporter.global] workflow_started max_attempts=%s", _MAX_ATTEMPTS)
    auth = _authorize()
    if auth.get("error"):
        logger.error("[reporter.global] authorization_failed error=%s", auth["error"])
        return {"success": False, "delivered": False, "validated": False, "error": auth["error"]}
    logger.info("[reporter.global] authorization_succeeded")
    read_view = report_tools.ReportReadView.load()
    context = graph_manager_tools.export_report_context(read_view=read_view)
    logger.info(
        "[reporter.global] context_exported queries=%s objectives=%s rubrics=%s conflicts=%s",
        len(context.get("queries") or []),
        len(context.get("objectives") or []),
        len(context.get("rubrics") or []),
        len(context.get("disclosed_conflicts") or []),
    )
    if not context.get("user_request"):
        logger.error("[reporter.global] context_invalid reason=missing_user_request")
        return {"success": False, "delivered": False, "validated": False, "error": "Reporter context has no user request"}
    packet = _build_packet(context, read_view=read_view)
    logger.info(
        "[reporter.global] packet_ready findings=%s estimated_tokens=%s",
        sum(len(group["items"]) for group in packet.get("findings") or []),
        packet.get("budget", {}).get("estimated_tokens", 0),
    )
    artifact_dir = Path(graph_manager_tools._cache_dir or ".") / ".global_reporter"
    _try_write_artifact(artifact_dir, "packet.json", packet)
    _try_write_artifact(artifact_dir, "answer_contract.json", packet["answer_contract"])
    _try_write_artifact(artifact_dir, "atomic_diagnostics.json", packet.get("atomic_diagnostics") or {})
    outline_path = Path(graph_manager_tools._cache_dir or ".") / ".report_outline.json"
    if not outline_path.exists():
        outline = report_tools.build_default_report_outline(context)
        if outline.get("chapters"):
            report_tools.commit_report_outline(
                graph_manager_tools._cache_dir,
                outline["title"],
                outline["chapters"],
            )
            _try_write_artifact(artifact_dir, "default_outline.json", outline)
    feedback = ""
    last_result: dict[str, Any] = {}
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            logger.info(
                "[reporter.global] writer_attempt_started attempt=%s/%s",
                attempt,
                _MAX_ATTEMPTS,
            )
            graph_manager_tools.increment_reporter_model_call_count()
            model_started_at = time.perf_counter()
            prompt = _prompt(packet, feedback)
            logger.info(
                "[reporter.global] writer_invoke_started attempt=%s prompt_chars=%s feedback_chars=%s max_tokens=%s",
                attempt,
                len(prompt),
                len(feedback),
                config.GR_GLOBAL_WRITER_OUTPUT_TOKENS,
            )
            response = config.reporter_global_model.bind(
                max_tokens=config.GR_GLOBAL_WRITER_OUTPUT_TOKENS
            ).invoke(prompt)
            raw_report = _response_text(response).strip()
            logger.info(
                "[reporter.global] writer_invoke_finished attempt=%s report_chars=%s elapsed=%.2fs",
                attempt,
                len(raw_report),
                time.perf_counter() - model_started_at,
            )
            if attempt == 1:
                _try_write_artifact(artifact_dir, "raw_report.md", raw_report)
            _try_write_artifact(artifact_dir, f"attempt_{attempt}.md", raw_report)
            last_result = graph_manager_tools.deliver_global_report(raw_report, read_view=read_view)
            logger.info(
                "[reporter.global] report_compilation_finished attempt=%s delivered=%s validated=%s hard_issues=%s soft_issues=%s elapsed=%.2fs",
                attempt,
                last_result.get("delivered", False),
                last_result.get("validated", False),
                len(last_result.get("issues") or []),
                len(last_result.get("soft_issues") or []),
                time.perf_counter() - model_started_at,
            )
            _try_write_artifact(artifact_dir, "validation.json", last_result)
            if last_result.get("delivered"):
                logger.info(
                    "[reporter.global] delivered attempt=%s chars=%s citations=%s total_elapsed=%.2fs",
                    attempt,
                    len(last_result.get("report") or ""),
                    len(last_result.get("cited_numbers") or []),
                    time.perf_counter() - workflow_started_at,
                )
                _try_write_artifact(artifact_dir, "compiled_report.md", last_result.get("report", ""))
                return {
                    "success": True,
                    "delivered": True,
                    "validated": bool(last_result.get("validated")),
                    "review_status": "global_compiler",
                    "attempts": attempt,
                    "error": None,
                }
            logger.warning(
                "[reporter.global] compilation_rejected attempt=%s issues=%s",
                attempt,
                len(last_result.get("issues") or []),
            )
            feedback = (
                "Repair the cited Markdown blocks in the previous draft. Every paragraph, "
                "list item, blockquote, table row, equation block, and sentence introducing "
                "a list/table/formula must carry a valid inline citation in that same block. "
                "Do not put a citation only in the following block. Convert any citation "
                "wrapper such as cite[1][2] to plain [1][2]. Specific compiler issues:\n"
                + "\n".join(
                    str(item.get("message") or item) for item in last_result.get("issues") or []
                )
            )[:5000]
            logger.info(
                "[reporter.global] retry_scheduled attempt=%s next_attempt=%s feedback_chars=%s",
                attempt,
                attempt + 1,
                len(feedback),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[reporter.global] attempt_failed attempt=%s error_type=%s error=%s",
                attempt,
                type(exc).__name__,
                str(exc)[:500],
                exc_info=True,
            )
            feedback = f"Writer invocation failed: {exc}"[:2000]
            _try_write_artifact(artifact_dir, f"attempt_{attempt}.error.txt", feedback)
    logger.error(
        "[reporter.global] exhausted_retries attempts=%s last_issues=%s total_elapsed=%.2fs",
        _MAX_ATTEMPTS,
        len(last_result.get("issues") or []),
        time.perf_counter() - workflow_started_at,
    )
    return {
        "success": False,
        "delivered": False,
        "validated": False,
        "review_status": "global_compiler_failed",
        "attempts": _MAX_ATTEMPTS,
        "error": str(last_result.get("issues") or "Global Reporter exhausted retries"),
    }
