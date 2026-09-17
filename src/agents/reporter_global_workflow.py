"""Single-pass, full-context Reporter workflow with deterministic compilation."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import config
from tools import graph_manager_tools, report_tools, research_state
from tools.drb2_diagnostics import diagnose_packet

logger = logging.getLogger(__name__)
_MAX_ATTEMPTS = 3
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


def _build_packet(context: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    research_notes: list[dict[str, Any]] = []
    export_errors: list[dict[str, Any]] = []
    used_numbers: set[int] = set()
    budget = config.GR_GLOBAL_PACKET_TOKENS * 4
    used_chars = 0
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
    for query in ordered_queries:
        query_ref = str(query.get("ref") or "").strip()
        if not query_ref:
            continue
        offset = 0
        query_items: list[dict[str, Any]] = []
        while True:
            page = report_tools.get_report_evidence(query_ref, offset=offset, limit=100)
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
                item_chars = len(json.dumps(compact, ensure_ascii=False))
                if used_chars + item_chars > budget:
                    break
                query_items.append(compact)
                used_chars += item_chars
                used_numbers.update(int(number) for number in compact["citations"])
            if used_chars >= budget or page.get("next_offset") is None:
                break
            offset = int(page["next_offset"])
        if query_items:
            findings.append({"query": query, "items": query_items})
        if used_chars >= budget:
            break

    draft_report = report_tools.build_cited_evidence_report(
        str(context.get("user_request") or "")
    )
    used_numbers.update(
        int(match.group(1))
        for match in re.finditer(r"\[(\d+)\]", draft_report)
    )
    registry = [
        entry for entry in report_tools.build_reference_registry()
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
            "atomic_rubrics": context.get("atomic_rubrics") or [],
        },
        "required_data_points": [
            criterion
            for objective in context.get("objectives") or []
            for criterion in objective.get("acceptance_criteria") or []
        ],
        "atomic_rubrics": context.get("atomic_rubrics") or [],
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
        "budget": {"tokens": config.GR_GLOBAL_PACKET_TOKENS, "estimated_tokens": _estimate_tokens(findings)},
    }
    if packet["atomic_rubrics"]:
        packet["atomic_diagnostics"] = diagnose_packet(packet)
    logger.info(
        "[reporter.global] packet_built queries=%s findings=%s estimated_tokens=%s "
        "budget_tokens=%s citations=%s export_errors=%s",
        len(context.get("queries") or []),
        sum(len(group["items"]) for group in findings),
        packet["budget"]["estimated_tokens"],
        config.GR_GLOBAL_PACKET_TOKENS,
        len(registry),
        len(export_errors),
    )
    return packet


def _prompt(packet: dict[str, Any], feedback: str = "") -> str:
    template = config.reporter_global_system_prompt
    replacements = {
        "user_request": packet["research_brief"].get("user_request", ""),
        "research_brief": packet["research_brief"].get("research_goal") or json.dumps(packet["research_brief"], ensure_ascii=False),
        "required_data_points": json.dumps(packet.get("required_data_points") or [], ensure_ascii=False),
        "atomic_rubrics": json.dumps(packet.get("atomic_rubrics") or [], ensure_ascii=False),
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
        r"<(user_request|research_brief|required_data_points|atomic_rubrics|atomic_diagnostics|required_structure|task_requirements|answer_contract|findings|research_notes|component_buckets|draft_report|conflicts|citation_registry|retry_feedback)>",
        lambda m: replacements[m.group(1)],
        template,
    )


def _authorize() -> dict[str, Any]:
    goal = research_state.get_goal()
    current = goal.get("research_state")
    if current not in research_state.REPORT_ALLOWED and current != research_state.REPORTING:
        return {"error": f"Reporter is not authorized from research state {current!r}"}
    if current != research_state.REPORTING:
        research_state.update_goal({"research_state": research_state.REPORTING, "reporting_from_state": current})
    return {"error": "", "user_request": str(goal.get("request") or "")}


def run_global_report_workflow() -> dict[str, Any]:
    """Run global Reporter writing and return a compact delivery result."""
    auth = _authorize()
    if auth.get("error"):
        return {"success": False, "delivered": False, "validated": False, "error": auth["error"]}
    context = graph_manager_tools.export_report_context()
    if not context.get("user_request"):
        return {"success": False, "delivered": False, "validated": False, "error": "Reporter context has no user request"}
    packet = _build_packet(context)
    artifact_dir = Path(graph_manager_tools._cache_dir or ".") / ".global_reporter"
    _try_write_artifact(artifact_dir, "packet.json", packet)
    _try_write_artifact(artifact_dir, "answer_contract.json", packet["answer_contract"])
    _try_write_artifact(artifact_dir, "atomic_rubric_diagnostics.json", packet.get("atomic_diagnostics") or {})
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
            response = config.reporter_global_model.bind(
                max_tokens=config.GR_GLOBAL_WRITER_OUTPUT_TOKENS
            ).invoke(_prompt(packet, feedback))
            raw_report = _response_text(response).strip()
            if attempt == 1:
                _try_write_artifact(artifact_dir, "raw_report.md", raw_report)
            _try_write_artifact(artifact_dir, f"attempt_{attempt}.md", raw_report)
            last_result = graph_manager_tools.deliver_global_report(raw_report)
            _try_write_artifact(artifact_dir, "validation.json", last_result)
            if last_result.get("delivered"):
                logger.info(
                    "[reporter.global] delivered attempt=%s chars=%s citations=%s",
                    attempt,
                    len(last_result.get("report") or ""),
                    len(last_result.get("cited_numbers") or []),
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
        "[reporter.global] exhausted_retries attempts=%s last_issues=%s",
        _MAX_ATTEMPTS,
        len(last_result.get("issues") or []),
    )
    return {
        "success": False,
        "delivered": False,
        "validated": False,
        "review_status": "global_compiler_failed",
        "attempts": _MAX_ATTEMPTS,
        "error": str(last_result.get("issues") or "Global Reporter exhausted retries"),
    }
