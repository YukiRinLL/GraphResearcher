"""基于 LangGraph StateGraph 的确定性研究工作流.

用确定性状态图编排完整 DeepResearch 工作流。每个节点直接调用
MemoryManager 的对应方法，无需 LLM 参与调度决策——调度优先级已内置于
``get_next_actions()``。

工作流拓扑::

    init → scheduler ⇄ assess / portfolio / expand / dispatch → convergence
                                       ↑                          ↓
                                       └── continue ─────────────┘
                                       stop/failed → report → END

设计要点:

- ``messages`` 字段使用 ``add_messages`` reducer，保持与 ``main.py`` 流式输出
  兼容（``stream_mode="values"`` 逐 superstep 快照打印新消息）。
- 每个节点 append 一条 ``AIMessage`` 摘要，便于 CLI 侧观察进度。
- ``current_action`` 由 ``scheduler_node`` 写入，各动作节点消费后清空。
- ``report_node`` 用 ``langchain.agents.create_agent`` 构建 reporter 子图，
  挂载 ``ReporterWorkflowMiddleware`` 等 guardrail，行为与原 deepagents
  SubAgent 一致但省去了 ``task`` 工具的 LLM 间接调度。
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Optional, TypedDict

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

import config
from agents.reporter import reporter as _reporter_spec
from agents.searcher import searcher
from tools import graph_manager_tools as gmt
from tools.graph_manager_tools import fail_search, prepare_search
from tools.middleware import (
    EmptyResponseRetryMiddleware,
    ReporterWorkflowMiddleware,
    SensitiveWordsRetryMiddleware,
)

logger = logging.getLogger(__name__)

# 各动作节点的路由目标名，与 ``get_next_actions`` 返回的 ``action`` 字段对齐。
_ACTION_NODES = {
    "assess_query": "assess",
    "evaluate_research_portfolio": "portfolio",
    "expand_gaps": "expand",
    "dispatch_searcher": "dispatch",
    "assess_convergence": "convergence",
}


class WorkflowState(TypedDict):
    """工作流运行状态.

    ``messages`` 使用 ``add_messages`` reducer，兼容 ``main.py`` 的
    ``stream_mode="values"`` 流式输出——每个 superstep 快照打印新增消息。
    """

    messages: Annotated[list, add_messages]
    user_request: str
    current_action: Optional[dict]
    step_count: int
    consecutive_idle: int  # 连续无进展动作数（dispatch 成功或 expand created>0 时重置）
    forced_convergence_count: int  # 连续强制收敛次数（正常收敛或成功搜索时重置）
    error: Optional[str]


def _extract_user_request(state: dict) -> str:
    """从初始 ``messages`` 中提取用户请求文本."""
    if state.get("user_request"):
        return str(state["user_request"])
    for message in state.get("messages") or []:
        content = getattr(message, "content", message)
        if isinstance(content, dict):
            content = content.get("content", "")
        if isinstance(content, str) and content.strip():
            return content.strip()
    return ""


def _action_summary(action: dict) -> str:
    """生成单条动作的可读摘要."""
    name = action.get("action", "unknown")
    query_handle = action.get("query_handle") or action.get("query_id") or ""
    reason = action.get("reason", "")
    parts = [f"action={name}"]
    if query_handle:
        parts.append(f"query={query_handle}")
    if reason:
        parts.append(f"reason={reason}")
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# 节点实现
# ---------------------------------------------------------------------------


def init_node(state: dict) -> dict:
    """初始化研究图谱：解析用户请求，创建 UserRequest 节点和初始 Query 树."""
    user_request = _extract_user_request(state)
    result = gmt.init_research.func()
    if result.get("error"):
        return {
            "messages": [AIMessage(content=f"[init_research] ERROR: {result['error']}")],
            "error": result["error"],
            "user_request": user_request,
        }
    goal_id = result.get("goal_id", "")
    query_count = len(result.get("queries", []))
    objective_count = len(result.get("objectives", []))
    summary = (
        f"[init_research] goal_id={goal_id}, "
        f"queries={query_count}, objectives={objective_count}, "
        f"scope={result.get('scope_mode', 'bounded')}"
    )
    return {
        "messages": [AIMessage(content=summary)],
        "user_request": user_request,
        "step_count": 0,
        "consecutive_idle": 0,
        "forced_convergence_count": 0,
    }


# 连续无进展动作的熔断阈值：超过此值后强制路由到 convergence。
# 正常流程中两次 dispatch_searcher 之间最多有 ~4 次非搜索动作
# (assess + portfolio + expand + portfolio)，阈值 6 容容一轮半空转。
_MAX_CONSECUTIVE_IDLE = 6

# 递归预算安全阈值：当 scheduler 调用次数（step_count）达到此值时，
# 无论 consecutive_idle 是否达标，强制路由到 convergence。
# 每个 scheduler→action 周期消耗 ~2-6 递归步；recursion_limit=400 时，
# 阈值 150 消耗 ~300 递归步，为 convergence + report 子图保留 ~100 步。
# 这防止系统在"成功"搜索/gap 扩展之间循环而始终不收敛——
# consecutive_idle 被每次成功搜索重置，无法触发原有的空转熔断。
_STEP_BUDGET_FOR_CONVERGENCE = 150


def scheduler_node(state: dict) -> dict:
    """从状态机获取最高优先级动作，写入 ``current_action`` 供下游节点消费.

    连续无进展熔断：当连续 ``_MAX_CONSECUTIVE_IDLE`` 次动作既不是成功的
    dispatch_searcher 也不是产生子查询的 expand_gaps 时，跳过正常调度
    直接路由到 convergence，避免 expand_gaps(created=0) /
    evaluate_portfolio(selected=0) 之间的空转循环。

    递归预算安全熔断：当 ``step_count`` 达到 ``_STEP_BUDGET_FOR_CONVERGENCE``
    时，无论 consecutive_idle 是否达标，强制路由到 convergence。这防止系统
    在"成功"搜索之间循环而始终不收敛——每次成功搜索都重置 consecutive_idle，
    导致原空转熔断无法触发，最终耗尽 LangGraph 递归预算。
    """
    step_count = int(state.get("step_count") or 0) + 1
    consecutive_idle = int(state.get("consecutive_idle") or 0)
    forced_count = int(state.get("forced_convergence_count") or 0)

    actions = gmt.get_next_actions.func(limit=1)
    if not actions:
        return {
            "current_action": None,
            "step_count": step_count,
            "consecutive_idle": consecutive_idle,
            "forced_convergence_count": forced_count,
            "messages": [AIMessage(content="[scheduler] no actions, routing to convergence")],
        }
    action = actions[0]

    # 递归预算安全熔断：step_count 接近递归限制时强制收敛。
    # 此检查必须在 consecutive_idle 熔断之前——consecutive_idle 被成功
    # 搜索不断重置，无法在预算耗尽前触发收敛。
    if step_count >= _STEP_BUDGET_FOR_CONVERGENCE:
        summary = (
            f"[scheduler] FORCED CONVERGENCE "
            f"(step={step_count} >= {_STEP_BUDGET_FOR_CONVERGENCE}, "
            f"forced_count={forced_count + 1}): recursion budget near limit"
        )
        return {
            "current_action": {
                "action": "assess_convergence",
                "query_id": None,
                "goal_id": action.get("goal_id"),
                "query_handle": None,
                "reason": f"forced convergence: step budget near limit (step={step_count})",
            },
            "step_count": step_count,
            "consecutive_idle": consecutive_idle,
            "forced_convergence_count": forced_count + 1,
            "messages": [AIMessage(content=summary)],
        }

    # 熔断：连续无进展超过阈值时，将 expand_gaps/evaluate_research_portfolio
    # 替换为 assess_convergence，强制进入收敛裁决。
    if consecutive_idle >= _MAX_CONSECUTIVE_IDLE and action.get("action") in {
        "expand_gaps",
        "evaluate_research_portfolio",
    }:
        action = {
            "action": "assess_convergence",
            "query_id": None,
            "goal_id": action.get("goal_id"),
            "query_handle": None,
            "reason": f"forced convergence after {consecutive_idle} consecutive idle actions",
        }
        summary = f"[scheduler] FORCED CONVERGENCE (idle={consecutive_idle}, forced_count={forced_count + 1}): {_action_summary(action)}"
        return {
            "current_action": action,
            "step_count": step_count,
            "consecutive_idle": consecutive_idle,
            "forced_convergence_count": forced_count + 1,
            "messages": [AIMessage(content=summary)],
        }

    summary = f"[scheduler] {_action_summary(action)}"
    return {
        "current_action": action,
        "step_count": step_count,
        "consecutive_idle": consecutive_idle,
        "forced_convergence_count": forced_count,
        "messages": [AIMessage(content=summary)],
    }


def assess_node(state: dict) -> dict:
    """评估单个 Query 的证据充分性并推进其状态."""
    action = state.get("current_action") or {}
    query_id = action.get("query_id")
    forced_count = int(state.get("forced_convergence_count") or 0)
    if not query_id:
        return {"current_action": None, "forced_convergence_count": forced_count, "messages": [AIMessage(content="[assess_query] no query_id")]}

    result = gmt.assess_query.func(query_id)
    idle = int(state.get("consecutive_idle") or 0) + 1  # assess 不直接产生搜索进展
    if result.get("error"):
        summary = f"[assess_query] {action.get('query_handle', query_id)} ERROR: {result['error']}"
    else:
        summary = (
            f"[assess_query] {action.get('query_handle', query_id)}: "
            f"status={result.get('status', '?')}, "
            f"sufficient_score={result.get('sufficiency_score', '?')}"
        )
    return {"current_action": None, "consecutive_idle": idle, "forced_convergence_count": forced_count, "messages": [AIMessage(content=summary)]}


def portfolio_node(state: dict) -> dict:
    """全局评估目标覆盖率，选择高价值 gap 并延迟低价值工作."""
    action = state.get("current_action") or {}
    goal_id = action.get("goal_id")
    # 记录调用前 portfolio_revision，用于检测 evaluate_research_portfolio 是否
    # 真的改变了 portfolio 状态。仅看 selected > 0 不够——_recover_unactionable_research
    # 会反复重置同一个 Gap 并 bump revision，使 selected 永远 > 0 但实际无进展
    prior_revision = 0
    if goal_id:
        try:
            from tools import graph_tools
            prior_node = graph_tools.get_node(goal_id)
            prior_revision = int(prior_node.get("portfolio_revision") or 0)
        except Exception:
            prior_revision = 0
    result = gmt.evaluate_research_portfolio.func(goal_id)
    if result.get("error"):
        summary = f"[evaluate_portfolio] ERROR: {result['error']}"
        idle = int(state.get("consecutive_idle") or 0) + 1
        forced_count = int(state.get("forced_convergence_count") or 0)
    else:
        selected = len(result.get("selected_gap_ids", []))
        deferred = len(result.get("deferred_gap_ids", []))
        coverage = result.get("report_completeness_score", 0.0)
        summary = (
            f"[evaluate_portfolio] selected={selected}, deferred={deferred}, "
            f"coverage={coverage:.2f}"
        )
        # 真进展 = selected > 0 且 portfolio_revision 在这次调用后确实增长了。
        # 若 selected > 0 但 revision 没变（或反而降低），说明 selector 选的还是
        # 同一批 Gap、没有任何新 Graph 变化——视为空转，递增 idle。
        post_revision = prior_revision
        try:
            if goal_id:
                from tools import graph_tools
                post_node = graph_tools.get_node(goal_id)
                post_revision = int(post_node.get("portfolio_revision") or 0)
        except Exception:
            post_revision = prior_revision
        made_progress = selected > 0 and post_revision > prior_revision
        idle = 0 if made_progress else int(state.get("consecutive_idle") or 0) + 1
        # 有进展时一并重置强制收敛计数
        forced_count = 0 if made_progress else int(state.get("forced_convergence_count") or 0)
    return {"current_action": None, "consecutive_idle": idle, "forced_convergence_count": forced_count, "messages": [AIMessage(content=summary)]}


def expand_node(state: dict) -> dict:
    """将选定的 gap 分组并创建满足严格树约束的子 Query."""
    action = state.get("current_action") or {}
    parent_id = action.get("parent_id")
    gap_ids = action.get("gap_ids")
    if not parent_id:
        return {"current_action": None, "consecutive_idle": int(state.get("consecutive_idle") or 0) + 1, "forced_convergence_count": int(state.get("forced_convergence_count") or 0), "messages": [AIMessage(content="[expand_gaps] no parent_id")]}

    result = gmt.expand_gaps.func(parent_id, gap_ids)
    if result.get("error"):
        summary = f"[expand_gaps] parent={action.get('query_handle', parent_id)} ERROR: {result['error']}"
        idle = int(state.get("consecutive_idle") or 0) + 1
        forced_count = int(state.get("forced_convergence_count") or 0)
    else:
        created = len(result.get("created", []))
        summary = (
            f"[expand_gaps] parent={action.get('query_handle', parent_id)}, "
            f"created={created} child queries"
        )
        # created > 0 表示产生了新子查询（有进展），重置计数；否则递增
        idle = 0 if created > 0 else int(state.get("consecutive_idle") or 0) + 1
        # 有进展时一并重置强制收敛计数
        forced_count = 0 if created > 0 else int(state.get("forced_convergence_count") or 0)
    return {"current_action": None, "consecutive_idle": idle, "forced_convergence_count": forced_count, "messages": [AIMessage(content=summary)]}


def dispatch_node(state: dict) -> dict:
    """准备搜索上下文并调用 Searcher 子图收集证据."""
    action = state.get("current_action") or {}
    query_id = action.get("query_id")
    if not query_id:
        return {"current_action": None, "consecutive_idle": int(state.get("consecutive_idle") or 0) + 1, "forced_convergence_count": int(state.get("forced_convergence_count") or 0), "messages": [AIMessage(content="[dispatch_searcher] no query_id")]}

    source_preferences = action.get("source_preferences")
    prepared = prepare_search(query_id, source_preferences)
    if prepared.get("error"):
        return {
            "current_action": None,
            "consecutive_idle": int(state.get("consecutive_idle") or 0) + 1,
            "forced_convergence_count": int(state.get("forced_convergence_count") or 0),
            "messages": [AIMessage(
                content=f"[dispatch_searcher] {action.get('query_handle', query_id)} prepare ERROR: {prepared['error']}"
            )],
        }

    try:
        result = searcher.invoke({
            "search_run_id": prepared["search_run_id"],
            "query_id": prepared["query_id"],
            "query_text": prepared["query_text"],
            "query_role": prepared.get("query_role") or "evidence_gap",
            "acceptance_criteria": prepared.get("acceptance_criteria", []),
            "research_context": prepared.get("research_context", {}),
            "source_preferences": prepared.get("source_preferences", []),
            "search_mode": prepared.get("search_mode") or "general",
            "messages": [HumanMessage(content=prepared["query_text"])],
        })
    except Exception as exc:  # noqa: BLE001 — Searcher 异常不应中断整个工作流
        fail_search(prepared["search_run_id"], prepared["query_id"], str(exc))
        return {
            "current_action": None,
            "consecutive_idle": int(state.get("consecutive_idle") or 0) + 1,
            "forced_convergence_count": int(state.get("forced_convergence_count") or 0),
            "messages": [AIMessage(
                content=f"[dispatch_searcher] {action.get('query_handle', query_id)} FAILED: {exc}"
            )],
        }

    submit_result = result.get("submit_result")
    if isinstance(submit_result, dict):
        written = submit_result.get("written") or {}
        sources = written.get("sources", "?")
        documents = written.get("documents", "?")
        evidence = written.get("evidence", "?")
        status = submit_result.get("status", "?")
        summary = (
            f"[dispatch_searcher] {action.get('query_handle', query_id)}: "
            f"status={status}, sources={sources}, documents={documents}, evidence={evidence}"
        )
        # 成功的搜索产生新证据，重置空转计数与强制收敛计数
        if status == "succeeded":
            idle = 0
            forced_count = 0
        else:
            idle = int(state.get("consecutive_idle") or 0) + 1
            forced_count = int(state.get("forced_convergence_count") or 0)
    else:
        fail_search(
            prepared["search_run_id"],
            prepared["query_id"],
            "Searcher returned no submit result",
        )
        summary = (
            f"[dispatch_searcher] {action.get('query_handle', query_id)}: "
            f"no submit result (recorded as failure)"
        )
        idle = int(state.get("consecutive_idle") or 0) + 1
        forced_count = int(state.get("forced_convergence_count") or 0)
    return {"current_action": None, "consecutive_idle": idle, "forced_convergence_count": forced_count, "messages": [AIMessage(content=summary)]}


def convergence_node(state: dict) -> dict:
    """裁决收敛：检查目标覆盖、致命冲突和预算，决定继续还是授权报告.

    正常的收敛裁决完全委托 ``memory_manager.assess_convergence``，后者基于
    ``get_next_actions`` 的"单源 actionability 定义"判断是否还有可推进的
    工作。只要 ``get_next_actions`` 能排出任何非 assess_convergence 的动
    作就 ``continue``，否则 ``LIMITED_REPORT_READY``。

    ``forced_convergence_count`` 和 LangGraph ``_STEP_BUDGET_FOR_CONVERGENCE``
    仅在 assess_convergence 被异常
    绕过、或发生了不可预期调度故障时，作为最后一道系统级界限。
    """
    from tools import research_state

    action = state.get("current_action") or {}
    goal_id = action.get("goal_id")
    is_forced = "forced convergence" in (action.get("reason") or "")
    forced_count = int(state.get("forced_convergence_count") or 0)

    result = gmt.assess_convergence.func(goal_id)
    if result.get("error"):
        summary = f"[assess_convergence] ERROR: {result['error']}"
    else:
        recommendation = result.get("recommendation", "?")
        converged = result.get("converged", False)
        fatal = len(result.get("fatal_unresolved_conflicts", []))
        active = len(result.get("active_queries", []))
        summary = (
            f"[assess_convergence] recommendation={recommendation}, "
            f"converged={converged}, fatal_conflicts={fatal}, active_queries={active}"
        )
        # 递归预算安全网：step 熔断触发时 assess_convergence 仍 say continue，
        # 说明调度/收敛逻辑出现了未覆盖的异常分支。此时仍要从 RESEARCHING 迁
        # 移到 LIMITED_REPORT_READY，避免 LangGraph 直接把整个 graph 抛
        # RecursionError。这是系统层保留的硬界限，不再承载"打破乒乓"语义。
        if is_forced and recommendation == "continue":
            try:
                research_state.update_goal({
                    "research_state": research_state.LIMITED_REPORT_READY,
                })
                summary += (
                    f" -> RECURSION BUDGET GUARD: step budget forced "
                    f"convergence override to LIMITED_REPORT_READY "
                    f"(forced_count={forced_count})"
                )
            except ValueError as exc:  # 状态迁移不合法——说明已进入可报告状态
                summary += f" -> recursion guard override skipped (transition invalid: {exc})"

    # 收敛节点始终重置 consecutive_idle，避免 scheduler 立即再次触发
    # consecutive_idle 分支。forced_convergence_count 同理：正常裁决重置，
    # 递归熔断时保留计数以方便事后统计故障频次。
    new_forced_count = forced_count if is_forced else 0
    return {
        "current_action": None,
        "consecutive_idle": 0,
        "forced_convergence_count": new_forced_count,
        "messages": [AIMessage(content=summary)],
    }


# ---------------------------------------------------------------------------
# Reporter agent 构建（延迟初始化，避免 import 时需要 API credentials）
# ---------------------------------------------------------------------------

_reporter_agent: Any = None


def _get_reporter_agent() -> Any:
    """构建并缓存 reporter agent.

    使用 ``langchain.agents.create_agent`` 构建，与 deepagents 对 SubAgent 的
    编译方式一致（``create_agent(model, system_prompt, tools, middleware)``）。
    reporter 继承默认 model（与原 SubAgent spec 行为一致）。
    """
    global _reporter_agent
    if _reporter_agent is not None:
        return _reporter_agent

    _reporter_agent = create_agent(
        model=config.default_model,
        system_prompt=config.reporter_system_prompt,
        tools=list(_reporter_spec["tools"]),
        middleware=[
            ReporterWorkflowMiddleware(),
            SensitiveWordsRetryMiddleware(),
            EmptyResponseRetryMiddleware(),
        ],
    )
    return _reporter_agent


def report_node(state: dict) -> dict:
    """授权并执行 Reporter 子图，从研究图谱生成结构化报告.

    复刻 ``ResearchStateMiddleware._gate_reporter`` 的前置检查：
    1. 确认研究状态允许报告（REPORT_READY / LIMITED_REPORT_READY / BUDGET_EXHAUSTED）
    2. 验证 Query 树完整性
    3. 注入 User Request handoff 文本
    4. 状态迁移至 REPORTING
    """
    from tools import graph_tools, research_state

    status = research_state.get_status()
    current_state = status.get("research_state")

    # FAILED 状态直接结束，不进入 Reporter
    if current_state == research_state.FAILED:
        return {
            "messages": [AIMessage(
                content=f"[reporter] skipped: research FAILED — {status.get('last_error', '')}"
            )],
        }

    # 不在允许报告的状态——标记异常并结束
    if current_state not in {
        research_state.REPORT_READY,
        research_state.LIMITED_REPORT_READY,
        research_state.BUDGET_EXHAUSTED,
    }:
        return {
            "messages": [AIMessage(
                content=f"[reporter] skipped: state={current_state} not in REPORT_ALLOWED"
            )],
        }

    # 验证 Query 树
    tree = graph_tools.validate_query_tree()
    if not tree.get("valid"):
        research_state.update_goal({
            "reporter_warnings": ["Query tree validation failed before Reporter authorization"],
        })

    # 注入 User Request handoff（与 ResearchStateMiddleware._REPORTER_HANDOFF 一致）
    requests = graph_tools.search_nodes("user_request", {})
    user_request_text = requests[0].get("request", "") if requests else ""
    handoff = (
        "以下是原始 User Request（逐字保存），你必须严格遵循其中的所有写作规范和要求：\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{user_request_text}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "请基于上述 User Request 和 export_report_context 中的报告材料，按 Reporter 工作流完成报告。"
    )

    # 状态迁移至 REPORTING
    research_state.update_goal({
        "research_state": research_state.REPORTING,
        "reporting_from_state": current_state,
    })

    # 执行 Reporter agent
    agent = _get_reporter_agent()
    try:
        result = agent.invoke({"messages": [HumanMessage(content=handoff)]})
    except Exception as exc:  # noqa: BLE001 — Reporter 异常不应导致无输出
        logger.exception("Reporter agent invocation failed")
        return {
            "messages": [AIMessage(content=f"[reporter] FAILED: {exc}")],
        }

    # 提取最终报告摘要
    compiled_report = gmt.get_compiled_report()
    attempt = gmt.get_last_report_attempt()
    report_len = len(compiled_report) if compiled_report else 0
    review_status = attempt.get("review_status", "?")
    revision = attempt.get("revision_requested", False)
    summary = (
        f"[reporter] report submitted: {report_len} chars, "
        f"review={review_status}, revision_requested={revision}"
    )
    # 把 reporter 的消息也追加到工作流状态，保持流式输出连续性
    reporter_messages = result.get("messages", []) if isinstance(result, dict) else []
    return {
        "messages": [AIMessage(content=summary), *reporter_messages],
    }


# ---------------------------------------------------------------------------
# 条件路由
# ---------------------------------------------------------------------------


def _route_after_init(state: dict) -> str:
    """Init 成功 → scheduler；init 失败 → END."""
    if state.get("error"):
        return END
    return "scheduler"


def _route_after_scheduler(state: dict) -> str:
    """根据 ``current_action`` 的动作类型路由到对应节点.

    无动作时路由到 ``convergence``（可能状态已变为 REPORT_READY 或 FAILED，
    由 ``assess_convergence`` 统一裁决）。
    """
    action = state.get("current_action")
    if not action:
        return "convergence"
    action_name = action.get("action")
    return _ACTION_NODES.get(action_name, "convergence")


def _route_after_convergence(state: dict) -> str:
    """Convergence 的 recommendation: continue → scheduler, stop/failed → report."""
    from tools import research_state

    # 从持久化状态读取 recommendation（assess_convergence 已写入 goal 节点）
    status = research_state.get_status()
    current_state = status.get("research_state")
    recommendation = status.get("last_convergence_recommendation")

    # 状态已允许报告或已失败 → 进入 report
    if current_state in research_state.REPORT_ALLOWED or current_state == research_state.FAILED:
        return "report"
    # recommendation 为 continue 或 None → 回 scheduler 继续
    if recommendation == "stop":
        return "report"
    return "scheduler"


# ---------------------------------------------------------------------------
# 工作流构建
# ---------------------------------------------------------------------------


def _build_workflow():
    """构建并编译工作流状态图."""
    graph = StateGraph(WorkflowState)

    graph.add_node("init", init_node)
    graph.add_node("scheduler", scheduler_node)
    graph.add_node("assess", assess_node)
    graph.add_node("portfolio", portfolio_node)
    graph.add_node("expand", expand_node)
    graph.add_node("dispatch", dispatch_node)
    graph.add_node("convergence", convergence_node)
    graph.add_node("report", report_node)

    graph.set_entry_point("init")
    graph.add_conditional_edges("init", _route_after_init, {
        "scheduler": "scheduler",
        END: END,
    })
    graph.add_conditional_edges("scheduler", _route_after_scheduler, {
        "assess": "assess",
        "portfolio": "portfolio",
        "expand": "expand",
        "dispatch": "dispatch",
        "convergence": "convergence",
    })
    # 所有动作节点完成后回到 scheduler
    graph.add_edge("assess", "scheduler")
    graph.add_edge("portfolio", "scheduler")
    graph.add_edge("expand", "scheduler")
    graph.add_edge("dispatch", "scheduler")
    graph.add_conditional_edges("convergence", _route_after_convergence, {
        "scheduler": "scheduler",
        "report": "report",
    })
    graph.add_edge("report", END)

    return graph.compile()


# 编译好的工作流图，供 ``main.py`` 等入口 ``.stream()`` / ``.invoke()`` 使用。
workflow = _build_workflow()
