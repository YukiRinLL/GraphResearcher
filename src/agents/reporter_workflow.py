"""以证据绑定为前提的确定性 LangGraph 报告工作流.

模型生成大纲、章节 JSON 候选和一次全文润色候选。本模块负责报告授权、
工具调用顺序、章节结构错误的有界重试和最终交付，因此模型不参与流程调度。
"""

from __future__ import annotations

import json
import logging
import operator
import re
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from langgraph.types import Send
from pydantic import BaseModel, ConfigDict, Field, ValidationError

import config
from tools import graph_manager_tools, report_source_context, research_state

logger = logging.getLogger(__name__)

_MAX_OUTLINE_ATTEMPTS = 3
_MAX_CHAPTER_ATTEMPTS = 3
_REPORTER_RECURSION_LIMIT = 200


class OutlineChapter(BaseModel):
    """模型为大纲规划的一章."""

    title: str = Field(min_length=1)
    goals: list[str] = Field(min_length=1)
    query_refs: list[str] = Field(min_length=1)
    section_plan: str = Field(min_length=1)
    section_type: Literal["lead", "body"]


class OutlineCandidate(BaseModel):
    """大纲规划阶段接受的模型输出."""

    title: str = Field(min_length=1)
    chapters: list[OutlineChapter] = Field(min_length=1)


class ChapterCandidate(BaseModel):
    """与一个已准备证据包绑定的章节候选."""

    chapter_id: int = Field(gt=0)
    content: str = Field(min_length=1)
    evidence_refs: list[str] = Field(min_length=1)
    disclosed_conflict_refs: list[str] = Field(default_factory=list)


class ChapterDraftCandidate(BaseModel):
    """章节写作阶段接受的单章模型输出."""

    chapters: list[ChapterCandidate] = Field(min_length=1, max_length=1)


class ReadRequest(BaseModel):
    """章节一次回读中的有界请求，引用合法性在读取边界逐项处理."""

    model_config = ConfigDict(extra="forbid", strict=True)
    evidence_ref: str = Field(max_length=100)
    block_refs: list[Annotated[str, Field(max_length=120)]] = Field(default_factory=list, max_length=4)
    purpose: str = Field(min_length=1, max_length=200)


class ChapterReadCandidate(BaseModel):
    """与最终章节互斥的回读分支."""

    model_config = ConfigDict(extra="forbid", strict=True)
    read_requests: list[ReadRequest] = Field(min_length=1, max_length=4)


class PolishedReportCandidate(BaseModel):
    """全文润色阶段接受的模型输出."""

    report: str = Field(min_length=1)


class ChapterResult(TypedDict):
    """一个章节分支结束时写回主图的运行时结果."""

    chapter_id: int
    success: bool
    attempts: int
    error: str


class ChapterTaskState(TypedDict):
    """通过 Send 传给一个章节写作分支的隔离输入."""

    report_context: dict[str, Any]
    outline: dict[str, Any]
    chapter_bundle: dict[str, Any]


class ReporterWorkflowState(TypedDict, total=False):
    """Reporter 的临时编排状态；报告事实仍由现有存储负责."""

    user_request: str
    report_context: dict[str, Any]
    outline: dict[str, Any]
    chapter_ids: list[int]
    chapter_bundles: list[dict[str, Any]]
    chapter_results: Annotated[list[ChapterResult], operator.add]
    outline_attempts: int
    draft_report: str
    draft_issues: list[dict[str, Any]]
    polished_report: str
    final_result: dict[str, Any]
    error: str


def _response_text(response: Any) -> str:
    """从模型响应中提取纯文本."""
    content = getattr(response, "content", response)
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return str(content or "")


def _strip_code_fence(text: str) -> str:
    """剥离模型可能附加的 ```json ... ``` 围栏（容忍首尾解释文字）."""
    stripped = text.strip()
    fence = stripped.find("```")
    if fence != -1:
        after_open = stripped.find("\n", fence)
        if after_open != -1:
            close = stripped.rfind("```")
            if close > after_open:
                return stripped[after_open + 1:close].strip()
    return stripped


def _salvage_json_object(text: str) -> dict[str, Any] | None:
    """JSON 直接解析失败时的两级恢复.

    1. 从首个 '{' 起用 raw_decode 解析第一个完整对象（容忍尾随说明文字或
       模型连续输出多个对象导致的 Extra data）；
    2. 仍失败时截取首个 '{' 到末个 '}' 的子串再解析（容忍前后都有散文）。
    """
    start = text.find("{")
    if start == -1:
        return None
    try:
        value, _end = json.JSONDecoder().raw_decode(text[start:])
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    end = text.rfind("}")
    if end > start:
        try:
            value = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None
    return None


def _parse_json_object(text: str) -> dict[str, Any]:
    """解析单个 JSON 对象，兼容 Markdown 围栏、附加说明与轻微格式漂移."""
    stripped = _strip_code_fence(text)
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError as exc:
        salvaged = _salvage_json_object(stripped)
        if salvaged is None:
            raise ValueError(f"Reporter returned invalid JSON: {exc.msg}") from exc
        logger.warning("Reporter JSON 解析失败后通过首尾大括号截取恢复: %s", exc.msg)
        value = salvaged
    if not isinstance(value, dict):
        raise ValueError("Reporter JSON must be an object")
    return value


def _invoke_reporter_json(
    prompt: str,
    *,
    phase: Literal["draft", "chapter", "polish"] = "draft",
) -> dict[str, Any]:
    """调用低温 Reporter 模型并解析 JSON 响应."""
    graph_manager_tools.increment_reporter_model_call_count()
    model = (
        config.reporter_polish_model
        if phase == "polish"
        else config.reporter_model
    )
    if phase == "chapter":
        model = model.bind(max_tokens=config.REPORTER_OUTPUT_TOKENS)
    return _parse_json_object(_response_text(model.invoke(prompt)))


def _outline_prompt(context: dict[str, Any], feedback: str = "") -> str:
    """构造只承担大纲规划的 prompt."""
    retry_feedback = (
        "# Retry Feedback\n\n"
        "上一版大纲未通过校验。请仅修复以下问题后重新输出完整 JSON：\n"
        + feedback
        if feedback
        else ""
    )
    return config.reporter_outline_prompt.replace(
        "<language>", str(context.get("language") or "")
    ).replace("<report_context>", json.dumps(context, ensure_ascii=False)).replace(
        "<retry_feedback>", retry_feedback
    )


def _available_query_refs(context: dict[str, Any]) -> set[str]:
    """返回当前报告上下文公开的非空 Query handle."""
    return {
        str(query.get("ref") or "").strip()
        for query in context.get("queries") or []
        if isinstance(query, dict) and str(query.get("ref") or "").strip()
    }


def _validated_outline(
    candidate: OutlineCandidate,
    context: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    """规范化模型大纲并校验只引用本次上下文公开的 Query."""
    title = candidate.title.strip()
    if not title:
        raise ValueError("Report title must not be blank")

    available_refs = _available_query_refs(context)
    chapters: list[dict[str, Any]] = []
    for index, chapter in enumerate(candidate.chapters, start=1):
        chapter_title = chapter.title.strip()
        goals = [goal.strip() for goal in chapter.goals if goal.strip()]
        query_refs = list(
            dict.fromkeys(ref.strip() for ref in chapter.query_refs if ref.strip())
        )
        section_plan = chapter.section_plan.strip()
        if not chapter_title:
            raise ValueError(f"Chapter {index} title must not be blank")
        if not goals:
            raise ValueError(f"Chapter {index} goals must not be empty")
        if not query_refs:
            raise ValueError(f"Chapter {index} query_refs must not be empty")
        if not section_plan:
            raise ValueError(f"Chapter {index} section_plan must not be blank")
        unavailable_refs = sorted(set(query_refs) - available_refs)
        if unavailable_refs:
            raise ValueError(
                f"Chapter {index} query_refs are not available in Report Context: "
                f"{unavailable_refs}; available refs: {sorted(available_refs)}"
            )
        chapters.append(
            {
                "chapter_id": index,
                "title": chapter_title,
                "goals": goals,
                "query_refs": query_refs,
                "section_plan": section_plan,
                "section_type": chapter.section_type,
            }
        )

    lead_ids = [
        chapter["chapter_id"]
        for chapter in chapters
        if chapter["section_type"] == "lead"
    ]
    if len(lead_ids) > 1:
        raise ValueError("Outline may contain at most one lead chapter")
    if lead_ids and lead_ids[0] != 1:
        raise ValueError("The lead chapter must be the first chapter")
    return title, chapters


def _chapter_prompt(
    user_request: str,
    outline: dict[str, Any],
    bundle: dict[str, Any],
    retry_error: str = "",
    *,
    language: str | None,
) -> str:
    """构造只承担一个已准备章节的写作 prompt."""
    retry_feedback = (
        "# Retry Feedback\n\n"
        "上一版章节 JSON 无法保存。请仅修复以下问题后重新输出当前章节的完整 JSON：\n"
        + retry_error
        + "\n修订时仍输出当前章节的完整候选正文，不输出补丁、解释或问题清单。"
        "chapters 数组必须且只能包含当前这一章，且输出单个 JSON 对象、不要输出多个对象。"
        if retry_error
        else ""
    )
    sections = {
        "language": str(language or ""), "retry_feedback": retry_feedback,
        "current_chapter_bundle": json.dumps(_writer_chapter_bundle(bundle), ensure_ascii=False),
        "report_outline": json.dumps(_writer_report_outline(outline), ensure_ascii=False),
        "user_request": user_request.strip(),
    }
    # 单次替换模板，原文内碰巧出现的占位符保持来源文字本身。
    return re.sub(
        r"<(language|retry_feedback|current_chapter_bundle|report_outline|user_request)>",
        lambda match: sections[match[1]], config.reporter_system_prompt,
    ).strip()


def _polish_prompt(
    user_request: str, draft_report: str, *, language: str | None
) -> str:
    """构造只承担全文行文润色的 prompt."""
    return config.reporter_polish_prompt.replace(
        "<language>", str(language or "")
    ).replace("<user_request>", user_request).replace(
        "<complete_draft>", draft_report
    )


def _writer_report_outline(outline: dict[str, Any]) -> dict[str, Any]:
    """将持久化大纲投影为每次章节写作共用的全文结构."""
    return {
        "title": outline.get("title"),
        "chapters": [
            {
                "chapter_id": chapter.get("chapter_id"),
                "title": chapter.get("title"),
                "goals": chapter.get("goals") or [],
                "section_plan": chapter.get("section_plan") or "",
                "section_type": chapter.get("section_type"),
            }
            for chapter in outline.get("chapters") or []
        ],
    }


def _writer_chapter_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """将内部章节证据包投影为 Reporter 所需的最小写作视图."""
    items = bundle.get("evidence_items") or []
    evidence = [
        {
            "ref": item.get("ref"),
            "text": item.get("text"),
            "citation": "".join(f"[{number}]" for number in item.get("source_numbers") or []),
        }
        for item in items
        if str(item.get("type") or "Evidence").casefold() == "evidence"
    ]
    available_evidence_refs = {
        str(item.get("ref")) for item in evidence if item.get("ref")
    }

    claims = []
    for item in items:
        if str(item.get("type") or "").casefold() != "claim":
            continue
        evidence_refs = [
            {
                "ref": relation.get("target_ref"),
                "stance": relation.get("stance"),
            }
            for relation in item.get("evidence_relations") or []
            if relation.get("target_ref") in available_evidence_refs
        ]
        if not evidence_refs:
            continue
        claims.append(
            {
                "ref": item.get("ref"),
                "text": item.get("text"),
                "confidence": item.get("confidence"),
                "qualifiers": item.get("qualifiers") or [],
                "limitations": item.get("limitations") or [],
                "evidence_refs": evidence_refs,
            }
        )

    conflicts = [
        {
            "ref": conflict.get("ref"),
            "description": conflict.get("description"),
            "conflict_type": conflict.get("conflict_type"),
            "evidence_refs": [
                ref
                for ref in conflict.get("evidence_refs") or []
                if ref in available_evidence_refs
            ],
        }
        for conflict in bundle.get("disclosed_conflicts") or []
    ]
    source_context = bundle.get("_source_context")
    if source_context is not None:
        evidence = [
            {**item, **source_context["evidence_locations"].get(item["ref"], {})}
            for item in evidence
        ]
    return {
        **({key: source_context[key] for key in ("context_blocks", "read_results", "readback_available")}
           if source_context is not None else {}),
        "chapter_id": bundle.get("chapter_id"),
        "chapter_title": bundle.get("chapter_title"),
        "chapter_goals": bundle.get("chapter_goals") or [],
        "section_plan": bundle.get("section_plan") or "",
        "section_type": bundle.get("section_type"),
        "evidence": evidence,
        "claims": claims,
        "disclosed_conflicts": conflicts,
    }


def _mark_failed(message: str) -> dict[str, Any]:
    """记录无法产生任何交付物的 Reporter 失败."""
    logger.error("Reporter workflow failed: %s", message)
    try:
        research_state.update_goal(
            {
                "research_state": research_state.FAILED,
                "last_error": message,
            }
        )
    except Exception:  # noqa: BLE001 - 保留最初的工作流诊断
        logger.exception("Could not mark Reporter workflow as failed")
    return {
        "error": message,
        "final_result": {
            "success": False,
            "delivered": False,
            "validated": False,
            "error": message,
        },
    }


def authorize_node(state: ReporterWorkflowState) -> dict[str, Any]:
    """校验 Reporter 授权、记录树告警并切换到 REPORTING."""
    del state
    from tools import graph_tools

    goal = research_state.get_goal()
    current = goal.get("research_state")
    if current in {
        research_state.REPORT_READY,
        research_state.LIMITED_REPORT_READY,
        research_state.BUDGET_EXHAUSTED,
    }:
        tree = graph_tools.validate_query_tree()
        if not tree.get("valid"):
            warning = "Query tree validation failed before Reporter authorization"
            logger.warning("%s: %s", warning, tree)
            research_state.update_goal({"reporter_warnings": [warning]})
        research_state.update_goal(
            {
                "research_state": research_state.REPORTING,
                "reporting_from_state": current,
            }
        )
    elif current != research_state.REPORTING:
        return {"error": f"Reporter is not authorized from research state {current!r}"}
    return {"user_request": str(goal.get("request") or ""), "error": ""}


def export_context_node(state: ReporterWorkflowState) -> dict[str, Any]:
    """在授权后读取固定的报告上下文."""
    del state
    try:
        context = graph_manager_tools.export_report_context()
    except Exception as exc:  # noqa: BLE001 - 交给确定性终止路径处理
        return {"error": f"Could not export Reporter context: {exc}"}
    if not context.get("user_request"):
        return {"error": "Reporter context is missing the user request"}
    if not _available_query_refs(context):
        return {"error": "Reporter context has no evidence-backed Query handles"}
    return {"report_context": context, "error": ""}


def route_after_guard(state: ReporterWorkflowState, next_node: str) -> str:
    """准备失败时进入 fail-open 终止，否则继续."""
    return "finalize_best_effort" if state.get("error") else next_node


def plan_outline_node(state: ReporterWorkflowState) -> dict[str, Any]:
    """生成、校验并持久化一份报告大纲."""
    attempt = int(state.get("outline_attempts", 0)) + 1
    try:
        candidate = OutlineCandidate.model_validate(
            _invoke_reporter_json(
                _outline_prompt(state["report_context"], state.get("error", ""))
            )
        )
        title, chapters = _validated_outline(candidate, state["report_context"])
        committed = graph_manager_tools.commit_report_outline(
            title=title,
            chapters=chapters,
        )
        if committed.get("status") != "ok":
            raise ValueError(str(committed.get("message") or "Outline was rejected"))
    except (ValidationError, ValueError, TypeError) as exc:
        return {
            "outline_attempts": attempt,
            "error": f"Outline attempt {attempt} failed: {exc}",
        }
    except Exception as exc:  # noqa: BLE001 - provider 失败使用相同的有界重试
        return {
            "outline_attempts": attempt,
            "error": f"Outline attempt {attempt} failed: {exc}",
        }
    return {
        "outline_attempts": attempt,
        "outline": {"title": title, "chapters": chapters},
        "chapter_ids": [chapter["chapter_id"] for chapter in chapters],
        "error": "",
    }


def route_outline(state: ReporterWorkflowState) -> str:
    """在有限次数内重试不合格的大纲."""
    if state.get("chapter_ids"):
        return "prepare_chapters"
    if int(state.get("outline_attempts", 0)) < _MAX_OUTLINE_ATTEMPTS:
        return "plan_outline"
    return "finalize_best_effort"


def prepare_chapters_node(state: ReporterWorkflowState) -> dict[str, Any]:
    """按工具批量上限顺序加载全部章节证据包."""
    bundles: list[dict[str, Any]] = []
    chapter_ids = state["chapter_ids"]
    for start in range(0, len(chapter_ids), 3):
        selected = chapter_ids[start : start + 3]
        try:
            prepared = graph_manager_tools.prepare_report_chapter_batch(
                chapters=[{"chapter_id": chapter_id} for chapter_id in selected],
            )
        except Exception as exc:  # noqa: BLE001 - 单章准备失败留给汇总阶段补齐
            bundles.extend(
                {
                    "status": "error",
                    "chapter_id": chapter_id,
                    "message": f"Could not prepare report chapter: {exc}",
                }
                for chapter_id in selected
            )
            continue

        prepared_by_id = {
            int(bundle.get("chapter_id") or 0): bundle
            for bundle in prepared.get("chapters") or []
        }
        for chapter_id in selected:
            bundle = prepared_by_id.get(chapter_id)
            bundles.append(
                bundle
                or {
                    "status": "error",
                    "chapter_id": chapter_id,
                    "message": "Prepared report chapter is incomplete",
                }
            )
    return {"chapter_bundles": bundles, "error": ""}


def dispatch_chapters(state: ReporterWorkflowState) -> list[Send]:
    """为每个章节创建一个隔离的并行写作任务."""
    return [
        Send(
            "draft_chapter",
            {
                "report_context": state["report_context"],
                "outline": state["outline"],
                "chapter_bundle": bundle,
            },
        )
        for bundle in state["chapter_bundles"]
    ]


def draft_chapter_node(state: ChapterTaskState) -> dict[str, Any]:
    """独立生成、重试并保存一个已准备章节."""
    bundle = state["chapter_bundle"]
    expected_id = int(bundle.get("chapter_id") or 0)
    if bundle.get("status") != "ok":
        return {
            "chapter_results": [
                {
                    "chapter_id": expected_id,
                    "success": False,
                    "attempts": 0,
                    "error": str(bundle.get("message") or "Chapter preparation failed"),
                }
            ]
        }

    retry_error = ""
    invocations = 0
    failures = 0
    readback_used = False
    success = False
    source_context = None
    try:
        source_context = report_source_context.SourceContext(bundle)
        while failures < _MAX_CHAPTER_ATTEMPTS:
            try:
                prompt = source_context.prompt(
                    lambda current: _chapter_prompt(
                        str(state["report_context"]["user_request"]), state["outline"],
                        current, retry_error, language=state["report_context"].get("language"),
                    ),
                    readback_used=readback_used,
                )
                invocations += 1
                response = _invoke_reporter_json(prompt, phase="chapter")
                if set(response) == {"read_requests"}:
                    if readback_used:
                        raise ValueError("Readback already used; return final chapters only")
                    requests = ChapterReadCandidate.model_validate(response)
                    readback_used = True
                    source_context.accept_requests([request.model_dump() for request in requests.read_requests])
                    retry_error = ""
                    continue
                if set(response) != {"chapters"}:
                    raise ValueError("Return exactly one of chapters or read_requests")
                raw_chapters = response.get("chapters")
                if not isinstance(raw_chapters, list) or not raw_chapters:
                    raise ValueError("chapters must be a non-empty list")
                if len(raw_chapters) > 1:
                    # 模型偶尔一次性返回多章；抽取当前目标章而不是整批作废。
                    matched = [
                        item for item in raw_chapters
                        if isinstance(item, dict) and item.get("chapter_id") == expected_id
                    ]
                    if not matched:
                        ids = [
                            item.get("chapter_id") for item in raw_chapters
                            if isinstance(item, dict)
                        ]
                        raise ValueError(
                            f"Return only the current chapter {expected_id}; "
                            f"got chapter ids {ids}"
                        )
                    logger.warning(
                        "章节 %s 模型返回了 %d 章，已抽取目标章继续",
                        expected_id, len(raw_chapters),
                    )
                    response = {"chapters": matched[:1]}
                candidate = ChapterDraftCandidate.model_validate(response)
                chapter = candidate.chapters[0]
                if chapter.chapter_id != expected_id:
                    raise ValueError(f"Chapter ID must match the current chapter: {expected_id}")
                committed = graph_manager_tools.commit_report_chapter_batch(
                    chapters=[{
                        "chapter_id": chapter.chapter_id,
                        "bundle_token": str(bundle["bundle_token"]),
                        "content": chapter.content,
                        "evidence_refs": chapter.evidence_refs,
                        "disclosed_conflict_refs": chapter.disclosed_conflict_refs,
                    }],
                )
                committed_chapters = committed.get("chapters") or []
                saved_ids = {
                    int(item.get("chapter_id") or 0) for item in committed_chapters
                    if item.get("candidate_saved")
                }
                if committed.get("status") != "ok" or saved_ids != {expected_id}:
                    raise ValueError(json.dumps(committed_chapters or committed, ensure_ascii=False))
            except report_source_context.PromptBudgetError:
                raise
            except Exception as exc:  # noqa: BLE001 - 结构、提交与 provider 失败共享有界重试
                failures += 1
                # 不将模型返回的整章原文或无界异常重新放进 prompt。
                detail = (
                    json.dumps(exc.errors(include_input=False, include_url=False), ensure_ascii=False)
                    if isinstance(exc, ValidationError) else str(exc)
                )
                retry_error = f"Chapter attempt {invocations} failed: {detail[:1200]}"
                continue
            success = True
            retry_error = ""
            break
    except report_source_context.PromptBudgetError as exc:
        retry_error = str(exc)
    finally:
        if source_context is not None:
            source_context.audit(
                model_invocations=invocations, failed_attempts=failures,
                readback_used=readback_used, error=retry_error,
            )
        else:
            report_source_context.write_audit(bundle, {
                "model_invocations": invocations, "failed_attempts": failures,
                "readback_used": readback_used, "error": retry_error, "views": [],
            })
    return {"chapter_results": [{
        "chapter_id": expected_id, "success": success,
        "attempts": invocations, "error": retry_error,
    }]}


def _chapter_fallback_reason(state: ReporterWorkflowState) -> str | None:
    """汇总失败章节，供最终交付结果说明降级原因."""
    failed = sorted(
        (
            result
            for result in state.get("chapter_results", [])
            if not result["success"]
        ),
        key=lambda result: result["chapter_id"],
    )
    if not failed:
        return None
    chapter_ids = ", ".join(str(result["chapter_id"]) for result in failed)
    return f"Reporter failed to draft chapters {chapter_ids}; deterministic fallbacks were used"


def assemble_draft_node(state: ReporterWorkflowState) -> dict[str, Any]:
    """在全部章节分支结束后补齐缺章并组装完整草稿."""
    del state
    try:
        result = graph_manager_tools.assemble_report_draft()
    except Exception as exc:  # noqa: BLE001 - 无完整草稿时不能进入润色
        return {"error": f"Report draft assembly failed: {exc}"}
    draft_report = str(result.get("report") or "").strip()
    if not result.get("delivered") or not draft_report:
        return {"error": f"Report draft assembly failed: {result.get('issues') or result}"}
    return {
        "draft_report": draft_report,
        "draft_issues": list(result.get("issues") or []),
        "error": "",
    }


def polish_report_node(state: ReporterWorkflowState) -> dict[str, Any]:
    """恰好调用一次模型润色完整报告草稿."""
    try:
        candidate = PolishedReportCandidate.model_validate(
            _invoke_reporter_json(
                _polish_prompt(
                    str(state["report_context"]["user_request"]),
                    state["draft_report"],
                    language=state["report_context"].get("language"),
                ),
                phase="polish",
            )
        )
        polished_report = candidate.report.strip()
        if not polished_report:
            raise ValueError("Polished report must not be blank")
    except Exception as exc:  # noqa: BLE001 - 状态图会交付已组装的章节草稿
        return {"error": f"Report polishing failed: {exc}"}
    return {"polished_report": polished_report, "error": ""}


def submit_node(state: ReporterWorkflowState) -> dict[str, Any]:
    """将润色后的完整报告写入现有最终交付缓存."""
    try:
        result = graph_manager_tools.deliver_polished_report(
            state["polished_report"],
            issues=state.get("draft_issues") or [],
        )
    except Exception as exc:  # noqa: BLE001 - 交由失败节点记录
        return {"error": f"Final report submission failed: {exc}"}

    if result.get("delivered"):
        return {
            "final_result": {
                "success": True,
                "delivered": True,
                "validated": bool(result.get("validated")),
                "review_status": result.get("review_status"),
                "fallback_reason": _chapter_fallback_reason(state),
                "result": result,
            },
            "error": "",
        }
    return {"error": f"Final report delivery failed: {result.get('issues') or result}"}


def route_submit(state: ReporterWorkflowState) -> str:
    """直接交付成功后结束，否则进入失败节点."""
    if state.get("final_result", {}).get("success"):
        return END
    return "fail"


def finalize_best_effort_node(state: ReporterWorkflowState) -> dict[str, Any]:
    """重试耗尽后直接交付当前最佳完整报告."""
    reason = state.get("error") or "Reporter workflow exhausted its retry budget"
    try:
        result = graph_manager_tools.deliver_final_report()
    except Exception as exc:  # noqa: BLE001 - 只有此时才无法交付
        return _mark_failed(f"{reason}; best-effort submission failed: {exc}")
    if not result.get("delivered"):
        return _mark_failed(
            f"{reason}; final submission produced no deliverable report: "
            f"{result.get('issues') or result}"
        )
    return {
        "final_result": {
            "success": True,
            "delivered": True,
            "validated": bool(result.get("validated")),
            "review_status": result.get("review_status"),
            "fallback_reason": reason,
            "result": result,
        },
        "error": "",
    }


def fail_node(state: ReporterWorkflowState) -> dict[str, Any]:
    """将不可交付的终止结果写入持久状态."""
    return _mark_failed(state.get("error") or "Reporter workflow failed")


def _build_reporter_workflow() -> StateGraph:
    """构建确定性的 Reporter 状态图."""
    graph = StateGraph(ReporterWorkflowState)
    graph.add_node("authorize", authorize_node)
    graph.add_node("export_context", export_context_node)
    graph.add_node("plan_outline", plan_outline_node)
    graph.add_node("prepare_chapters", prepare_chapters_node)
    graph.add_node("draft_chapter", draft_chapter_node)
    graph.add_node("assemble_draft", assemble_draft_node)
    graph.add_node("polish_report", polish_report_node)
    graph.add_node("submit", submit_node)
    graph.add_node("finalize_best_effort", finalize_best_effort_node)
    graph.add_node("fail", fail_node)
    graph.set_entry_point("authorize")
    graph.add_conditional_edges(
        "authorize",
        lambda state: "fail" if state.get("error") else "export_context",
    )
    graph.add_conditional_edges(
        "export_context",
        lambda state: route_after_guard(state, "plan_outline"),
    )
    graph.add_conditional_edges("plan_outline", route_outline)
    graph.add_conditional_edges("prepare_chapters", dispatch_chapters)
    graph.add_edge("draft_chapter", "assemble_draft")
    graph.add_conditional_edges(
        "assemble_draft",
        lambda state: "fail" if state.get("error") else "polish_report",
    )
    graph.add_conditional_edges(
        "polish_report",
        lambda state: "finalize_best_effort" if state.get("error") else "submit",
    )
    graph.add_conditional_edges("submit", route_submit)
    graph.add_edge("finalize_best_effort", END)
    graph.add_edge("fail", END)
    return graph


reporter_workflow = _build_reporter_workflow().compile()


def run_report_workflow(
    *, runnable_config: RunnableConfig | None = None
) -> dict[str, Any]:
    """运行 Reporter workflow，并返回精简的编排结果."""
    invoke_config = {
        **dict(runnable_config or {}),
        "recursion_limit": _REPORTER_RECURSION_LIMIT,
        "max_concurrency": config.REPORTER_CHAPTER_CONCURRENCY,
    }
    result = reporter_workflow.invoke(
        {},
        config=invoke_config,
    )
    final = result.get("final_result") or {}
    if final.get("success"):
        return {
            "success": True,
            "delivered": bool(final.get("delivered")),
            "validated": bool(final.get("validated")),
            "review_status": final.get("review_status"),
            "fallback_reason": final.get("fallback_reason"),
            "error": None,
        }
    return {
        "success": False,
        "delivered": False,
        "validated": False,
        "review_status": None,
        "fallback_reason": None,
        "error": result.get("error", "Reporter workflow failed"),
    }
