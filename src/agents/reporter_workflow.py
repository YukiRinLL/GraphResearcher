"""以证据绑定为前提的确定性 LangGraph 报告工作流.

模型只生成大纲和章节 JSON 候选。本模块负责报告授权、工具调用顺序、
有界重试、一次审校与最多一次修订，因此模型不参与流程调度。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field, ValidationError

import config
from tools import graph_manager_tools, report_tools, research_state

logger = logging.getLogger(__name__)

_MAX_OUTLINE_ATTEMPTS = 3
_MAX_CHAPTER_ATTEMPTS = 3
_REPORTER_RECURSION_LIMIT = 200


class OutlineChapter(BaseModel):
    """模型为大纲规划的一章."""

    title: str = Field(min_length=1)
    goals: list[str] = Field(default_factory=list)
    query_refs: list[str] = Field(min_length=1)
    section_plan: str = ""
    section_type: Literal["lead", "body"] | None = None


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


class ChapterBatchCandidate(BaseModel):
    """章节写作阶段接受的模型输出."""

    chapters: list[ChapterCandidate] = Field(min_length=1, max_length=3)


class ReporterWorkflowState(TypedDict, total=False):
    """Reporter 的临时编排状态；报告事实仍由现有存储负责."""

    user_request: str
    report_context: dict[str, Any]
    outline: dict[str, Any]
    chapter_ids: list[int]
    next_chapter_index: int
    current_bundles: list[dict[str, Any]]
    outline_attempts: int
    chapter_attempts: int
    revision_started: bool
    revision_feedback: list[dict[str, Any]]
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


def _parse_json_object(text: str) -> dict[str, Any]:
    """解析单个 JSON 对象，并兼容模型附加的 Markdown 围栏."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3]
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Reporter returned invalid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ValueError("Reporter JSON must be an object")
    return value


def _invoke_reporter_json(prompt: str) -> dict[str, Any]:
    """调用低温 Reporter 模型并解析 JSON 响应."""
    graph_manager_tools.increment_reporter_model_call_count()
    return _parse_json_object(_response_text(config.reporter_model.invoke(prompt)))


def _outline_prompt(context: dict[str, Any], feedback: str = "") -> str:
    """构造只承担大纲规划的 prompt."""
    retry_feedback = (
        "上一版大纲未通过校验。请仅修复以下问题后重新输出完整 JSON：\n" + feedback
        if feedback
        else ""
    )
    return config.reporter_outline_prompt.replace(
        "<report_context>", json.dumps(context, ensure_ascii=False)
    ).replace("<retry_feedback>", retry_feedback)


def _chapter_prompt(
    context: dict[str, Any],
    bundles: list[dict[str, Any]],
    feedback: list[dict[str, Any]],
    revision_started: bool,
    retry_error: str = "",
) -> str:
    """构造只承担一个已准备章节批次的写作 prompt."""
    instruction = (
        "这是唯一一轮定点修订。根据审校问题重写本批章节，并继续遵守各章节 bundle 的局部引用范围。"
        if revision_started
        else "为本批每个章节撰写完整候选正文。"
    )
    retry_feedback = (
        "上一版章节 JSON 或引用绑定未通过校验。请修复以下问题：\n" + retry_error
        if retry_error
        else ""
    )
    return "\n\n".join(
        [
            config.reporter_system_prompt,
            instruction,
            "Report Context:\n" + json.dumps(context, ensure_ascii=False),
            "Prepared chapter bundles:\n" + json.dumps(bundles, ensure_ascii=False),
            "Revision feedback:\n" + json.dumps(feedback, ensure_ascii=False),
            retry_feedback,
        ]
    ).strip()


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
    if not context.get("goal", {}).get("request") or not context.get("delivery_mode"):
        return {
            "error": "Reporter context is missing an authorized request or delivery mode"
        }
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
        chapters = [
            {
                "chapter_id": index,
                "title": chapter.title,
                "goals": chapter.goals,
                "query_refs": list(dict.fromkeys(chapter.query_refs)),
                "section_plan": chapter.section_plan,
                "section_type": chapter.section_type,
            }
            for index, chapter in enumerate(candidate.chapters, start=1)
        ]
        committed = graph_manager_tools.commit_report_outline(
            title=candidate.title,
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
        "outline": {"title": candidate.title, "chapters": chapters},
        "chapter_ids": [chapter["chapter_id"] for chapter in chapters],
        "next_chapter_index": 0,
        "error": "",
    }


def route_outline(state: ReporterWorkflowState) -> str:
    """在有限次数内重试不合格的大纲."""
    if state.get("chapter_ids"):
        return "prepare_chapter_batch"
    if int(state.get("outline_attempts", 0)) < _MAX_OUTLINE_ATTEMPTS:
        return "plan_outline"
    return "finalize_best_effort"


def prepare_chapter_batch_node(state: ReporterWorkflowState) -> dict[str, Any]:
    """加载下一批一到三章的章节局部证据包."""
    start = int(state.get("next_chapter_index", 0))
    selected = state["chapter_ids"][start : start + 3]
    try:
        prepared = graph_manager_tools.prepare_report_chapter_batch(
            chapters=[{"chapter_id": chapter_id} for chapter_id in selected],
        )
    except Exception as exc:  # noqa: BLE001 - 准备失败不能由模型修复
        return {"error": f"Could not prepare report chapter batch: {exc}"}
    if prepared.get("status") != "ok":
        return {
            "error": (
                "Could not prepare report chapter batch: "
                f"{prepared.get('errors') or prepared.get('message')}"
            ),
        }
    bundles = prepared.get("chapters") or []
    if len(bundles) != len(selected) or any(
        bundle.get("status") != "ok" for bundle in bundles
    ):
        return {"error": "Prepared report chapter batch is incomplete"}
    return {"current_bundles": bundles, "chapter_attempts": 0, "error": ""}


def draft_chapter_batch_node(state: ReporterWorkflowState) -> dict[str, Any]:
    """生成并提交一个已准备章节批次."""
    attempt = int(state.get("chapter_attempts", 0)) + 1
    bundles = state["current_bundles"]
    expected_ids = {int(bundle["chapter_id"]) for bundle in bundles}
    try:
        candidate = ChapterBatchCandidate.model_validate(
            _invoke_reporter_json(
                _chapter_prompt(
                    state["report_context"],
                    bundles,
                    state.get("revision_feedback", []),
                    bool(state.get("revision_started")),
                    state.get("error", ""),
                )
            )
        )
        by_id = {chapter.chapter_id: chapter for chapter in candidate.chapters}
        if set(by_id) != expected_ids or len(by_id) != len(candidate.chapters):
            raise ValueError(
                f"Chapter IDs must exactly match the prepared batch: {sorted(expected_ids)}"
            )
        tokens = {
            int(bundle["chapter_id"]): str(bundle["bundle_token"]) for bundle in bundles
        }
        committed = graph_manager_tools.commit_report_chapter_batch(
            chapters=[
                {
                    "chapter_id": chapter.chapter_id,
                    "bundle_token": tokens[chapter.chapter_id],
                    "content": chapter.content,
                    "evidence_refs": chapter.evidence_refs,
                    "disclosed_conflict_refs": chapter.disclosed_conflict_refs,
                }
                for chapter in candidate.chapters
            ],
        )
        if not committed.get("validated"):
            raise ValueError(
                json.dumps(committed.get("chapters") or committed, ensure_ascii=False)
            )
    except (ValidationError, ValueError, TypeError) as exc:
        return {
            "chapter_attempts": attempt,
            "error": f"Chapter attempt {attempt} failed: {exc}",
        }
    except Exception as exc:  # noqa: BLE001 - provider 失败使用相同的有界重试
        return {
            "chapter_attempts": attempt,
            "error": f"Chapter attempt {attempt} failed: {exc}",
        }
    return {
        "chapter_attempts": attempt,
        "next_chapter_index": (int(state.get("next_chapter_index", 0)) + len(bundles)),
        "current_bundles": [],
        "error": "",
    }


def route_chapter_batch(state: ReporterWorkflowState) -> str:
    """合格后继续下一批或提交，否则重试当前批次."""
    if (
        state.get("error")
        and int(state.get("chapter_attempts", 0)) < _MAX_CHAPTER_ATTEMPTS
    ):
        return "draft_chapter_batch"
    if state.get("error"):
        return "finalize_best_effort"
    if int(state["next_chapter_index"]) < len(state["chapter_ids"]):
        return "prepare_chapter_batch"
    return "submit"


def _quality_feedback(result: dict[str, Any]) -> list[dict[str, Any]]:
    """把现有全文质量检查结果转换为章节修订反馈."""
    report = str(result.get("report") or result.get("salvaged_report") or "")
    return [
        {
            "code": "report_workflow_quality_issue",
            "severity": "soft",
            "section_title": "",
            "block_index": None,
            "message": issue,
            "repair_hint": "在受影响章节中修复该问题。",
        }
        for issue in report_tools.check_report_quality(report)
    ]


def submit_node(state: ReporterWorkflowState) -> dict[str, Any]:
    """执行现有的一次 Review、一次修订提交契约."""
    try:
        result = graph_manager_tools.submit_final_report()
    except Exception as exc:  # noqa: BLE001 - 交由失败节点记录
        return {"error": f"Final report submission failed: {exc}"}

    if result.get("revision_requested") and not state.get("revision_started"):
        feedback = [*list(result.get("issues") or []), *_quality_feedback(result)]
        return {
            "revision_started": True,
            "revision_feedback": feedback,
            "next_chapter_index": 0,
            "current_bundles": [],
            "error": "",
        }
    if result.get("delivered"):
        return {
            "final_result": {
                "success": True,
                "delivered": True,
                "validated": bool(result.get("validated")),
                "review_status": result.get("review_status"),
                "result": result,
            },
            "error": "",
        }
    return {"error": f"Final report delivery failed: {result.get('issues') or result}"}


def route_submit(state: ReporterWorkflowState) -> str:
    """需要修订时返回章节循环，否则结束."""
    if state.get("final_result", {}).get("success"):
        return END
    if state.get("revision_started") and not state.get("error"):
        return "prepare_chapter_batch"
    return "fail"


def finalize_best_effort_node(state: ReporterWorkflowState) -> dict[str, Any]:
    """重试耗尽后通过现有提交工具确定性地产生最佳完整报告."""
    reason = state.get("error") or "Reporter workflow exhausted its retry budget"
    try:
        result = graph_manager_tools.submit_final_report()
        if result.get("revision_requested"):
            result = graph_manager_tools.submit_final_report()
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
    graph.add_node("prepare_chapter_batch", prepare_chapter_batch_node)
    graph.add_node("draft_chapter_batch", draft_chapter_batch_node)
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
    graph.add_conditional_edges(
        "prepare_chapter_batch",
        lambda state: route_after_guard(state, "draft_chapter_batch"),
    )
    graph.add_conditional_edges("draft_chapter_batch", route_chapter_batch)
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
