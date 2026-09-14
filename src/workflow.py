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
- ``report_node`` 调用嵌套的确定性 Reporter StateGraph。模型只生成受 schema
  约束的大纲和章节候选，不参与报告工具调度。
"""

from __future__ import annotations

import logging
from typing import Annotated, Optional, TypedDict

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.config import get_config
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

import config
from agents.reporter_workflow import run_report_workflow
from agents.reporter_global_workflow import run_global_report_workflow
from agents.searcher import searcher
from tools import graph_manager_tools as gmt
from tools.graph_manager_tools import fail_search, prepare_search

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
    current_action_batch: Optional[list]  # parallel dispatch_searcher actions
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


# 递归预算安全阈值：当 scheduler 调用次数（step_count）达到此值时，
# 无论可操作路径检查结果如何，强制路由到 convergence。
# 每个 scheduler→action 周期消耗 ~2-6 递归步；recursion_limit=400 时，
# 阈值 150 消耗 ~300 递归步，为 convergence + report 子图保留 ~100 步。
# 这防止系统在"成功"搜索之间循环而始终不收敛——
# 这是系统层保留的硬界限，不再承载"打破乒乓"语义。
_STEP_BUDGET_FOR_CONVERGENCE = 150


def _has_actionable_paths() -> bool:
    """检查图谱中是否还有可操作的搜索/扩展路径。

    返回 True 如果存在以下任一情况：
    - pending 查询（可以被 dispatch_searcher 搜索）
    - selected gaps（可以被 expand_gaps 扩展）
    - candidate gaps 且 parent 状态为 needs_expansion（可被 portfolio 选中）
    - assessing / waiting_children 查询（评估后可能产生新 gap）

    返回 False 表示所有搜索路径已穷尽，应正常收敛。
    """
    from tools import graph_tools

    # 1. Pending 查询（待搜索）
    if graph_tools.get_pending_queries():
        return True

    # 2. Selected gaps（待扩展）
    selected = graph_tools.search_nodes("analysis", {"analysis_type": "gap", "status": "selected"})
    if selected:
        return True

    # 3. Candidate gaps 且 parent 是 needs_expansion（可被 portfolio 选中）
    candidates = graph_tools.search_nodes("analysis", {"analysis_type": "gap", "status": "candidate"})
    for gap in candidates:
        parent_id = gap.get("expansion_parent_id")
        if parent_id:
            parent = graph_tools.get_node(parent_id)
            if parent and parent.get("status") == "needs_expansion":
                return True

    # 4. Assessing / waiting_children 查询（评估后可能产生新 gap）
    assessing = graph_tools.search_nodes("query", {"status": "assessing"})
    if assessing:
        return True
    waiting = graph_tools.search_nodes("query", {"status": "waiting_children"})
    if waiting:
        return True

    # 5. portfolio 需要重新评估（evaluated 落后于当前 revision）
    from tools import research_state
    goal = research_state.get_goal()
    if int(goal.get("evaluated_portfolio_revision") or 0) < int(goal.get("portfolio_revision") or 0):
        return True

    # 6. 有未满足的 must objective（不应提前收敛）
    objectives = graph_tools.search_nodes("analysis", {"analysis_type": "objective"})
    if any(
        obj.get("requirement") == "must"
        and obj.get("status") not in {"satisfied", "blocked"}
        for obj in objectives
    ):
        return True

    return False


def scheduler_node(state: dict) -> dict:
    """从状态机获取最高优先级动作，写入 ``current_action`` 供下游节点消费.

    可操作路径检查：当图谱中没有 pending 查询、selected gaps、candidate gaps
    （parent=needs_expansion）或 assessing/waiting_children 查询时，直接路由到
    convergence，不再等待空转计数。这比固定阈值更精确——只在真正没有可操作
    路径时才收敛，而不会在有活可干时因阈值到期而强制停机。

    递归预算安全熔断：当 ``step_count`` 达到 ``_STEP_BUDGET_FOR_CONVERGENCE``
    时，无论路径检查结果如何，强制路由到 convergence。这是系统层保留的硬界限，
    防止意外情况下耗尽 LangGraph 递归预算。
    """
    step_count = int(state.get("step_count") or 0) + 1
    consecutive_idle = int(state.get("consecutive_idle") or 0)
    forced_count = int(state.get("forced_convergence_count") or 0)

    actions = gmt.get_next_actions.func(limit=1)
    if not actions:
        return {
            "current_action": None,
            "current_action_batch": None,
            "step_count": step_count,
            "consecutive_idle": consecutive_idle,
            "forced_convergence_count": forced_count,
            "messages": [AIMessage(content="[scheduler] no actions, routing to convergence")],
        }
    action = actions[0]

    # Parallel dispatch: when the top action is dispatch_searcher, grab
    # additional pending dispatch actions (up to SEARCH_DISPATCH_CONCURRENCY)
    # so dispatch_node can run them concurrently via ThreadPoolExecutor.
    # Parallel assess: when the top action is assess_query, grab all pending
    # assess actions so assess_node can run them concurrently via
    # ThreadPoolExecutor. assess_query calls are independent — each only
    # reads its own query's evidence subgraph and the LLM call dominates.
    from config import SEARCH_DISPATCH_CONCURRENCY, ASSESS_QUERY_CONCURRENCY
    action_batch = None
    if action.get("action") == "dispatch_searcher":
        all_actions = gmt.get_next_actions.func(limit=SEARCH_DISPATCH_CONCURRENCY)
        dispatch_actions = [a for a in all_actions if a.get("action") == "dispatch_searcher"]
        if len(dispatch_actions) > 1:
            action_batch = dispatch_actions
            action = dispatch_actions[0]
    elif action.get("action") == "assess_query":
        all_actions = gmt.get_next_actions.func(limit=ASSESS_QUERY_CONCURRENCY)
        assess_actions = [a for a in all_actions if a.get("action") == "assess_query"]
        if len(assess_actions) > 1:
            action_batch = assess_actions
            action = assess_actions[0]

    # 递归预算安全熔断：step_count 接近递归限制时强制收敛。
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
                "reason": "forced convergence: step budget near limit",
            },
            "current_action_batch": None,
            "step_count": step_count,
            "consecutive_idle": consecutive_idle,
            "forced_convergence_count": forced_count + 1,
            "messages": [AIMessage(content=summary)],
        }

    # 可操作路径检查：当图谱中没有 pending/selected/candidate/assessing 路径时，
    # 直接路由到 convergence，不再等待空转计数。expand_gaps hard-brake 会把
    # gap 标为 blocked，所以路径检查会在 1-2 轮内正确收敛。
    if not _has_actionable_paths():
        action = {
            "action": "assess_convergence",
            "query_id": None,
            "goal_id": action.get("goal_id"),
            "query_handle": None,
            "reason": "no actionable paths remain",
        }
        summary = f"[scheduler] PATH EXHAUSTED: no actionable search/expansion paths remain, routing to convergence"
        return {
            "current_action": action,
            "current_action_batch": None,
            "step_count": step_count,
            "consecutive_idle": consecutive_idle,
            "forced_convergence_count": forced_count + 1,
            "messages": [AIMessage(content=summary)],
        }

    summary = f"[scheduler] {_action_summary(action)}"
    if action_batch:
        handles = [a.get("query_handle", a.get("query_id")) for a in action_batch]
        summary += f" (parallel batch: {handles})"
    return {
        "current_action": action,
        "current_action_batch": action_batch,
        "step_count": step_count,
        "consecutive_idle": consecutive_idle,
        "forced_convergence_count": forced_count,
        "messages": [AIMessage(content=summary)],
    }


def _run_single_assess(action: dict) -> tuple[str, bool, str]:
    """Run one assess_query call and return (handle, succeeded, summary)."""
    query_id = action.get("query_id")
    handle = action.get("query_handle", query_id)
    if not query_id:
        return handle or "?", False, f"[assess_query] {handle or '?'}: no query_id"
    try:
        result = gmt.assess_query.func(query_id)
    except Exception as exc:  # noqa: BLE001
        return handle, False, f"[assess_query] {handle} FAILED: {exc}"
    if result.get("error"):
        return handle, False, f"[assess_query] {handle} ERROR: {result['error']}"
    status = result.get("status", "?")
    score = result.get("sufficiency_score", "?")
    return handle, True, f"[assess_query] {handle}: status={status}, sufficient_score={score}"


def assess_node(state: dict) -> dict:
    """评估 Query 的证据充分性并推进其状态.

    当 ``current_action_batch`` 包含多个 assess_query 动作时，使用
    ThreadPoolExecutor 并行执行。assess_query 只读取各自 query 的证据
    子图，LLM 调用（``_invoke_json``）在 ``_state_lock`` 外完成，因此
    并行安全；图写入由 ``MemoryManager._state_lock`` 串行化。
    """
    action = state.get("current_action") or {}
    query_id = action.get("query_id")
    forced_count = int(state.get("forced_convergence_count") or 0)
    if not query_id:
        return {"current_action": None, "current_action_batch": None, "forced_convergence_count": forced_count, "messages": [AIMessage(content="[assess_query] no query_id")]}

    batch = state.get("current_action_batch")

    if batch and len(batch) > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from config import ASSESS_QUERY_CONCURRENCY

        summaries: list[str] = []
        any_succeeded = False
        with ThreadPoolExecutor(max_workers=ASSESS_QUERY_CONCURRENCY) as pool:
            futures = {pool.submit(_run_single_assess, a): a for a in batch}
            for fut in as_completed(futures):
                handle, succeeded, summary = fut.result()
                summaries.append(summary)
                if succeeded:
                    any_succeeded = True

        combined = "; ".join(summaries)
        idle = 0 if any_succeeded else int(state.get("consecutive_idle") or 0) + len(batch)
        return {"current_action": None, "current_action_batch": None, "consecutive_idle": idle, "forced_convergence_count": forced_count, "messages": [AIMessage(content=combined)]}

    # Serial path (single assess or no batch)
    handle, succeeded, summary = _run_single_assess(action)
    idle = 0 if succeeded else int(state.get("consecutive_idle") or 0) + 1
    return {"current_action": None, "current_action_batch": None, "consecutive_idle": idle, "forced_convergence_count": forced_count, "messages": [AIMessage(content=summary)]}


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
    return {"current_action": None, "current_action_batch": None, "consecutive_idle": idle, "forced_convergence_count": forced_count, "messages": [AIMessage(content=summary)]}


def expand_node(state: dict) -> dict:
    """将选定的 gap 分组并创建满足严格树约束的子 Query."""
    action = state.get("current_action") or {}
    parent_id = action.get("parent_id")
    gap_ids = action.get("gap_ids")
    if not parent_id:
        return {"current_action": None, "current_action_batch": None, "consecutive_idle": int(state.get("consecutive_idle") or 0) + 1, "forced_convergence_count": int(state.get("forced_convergence_count") or 0), "messages": [AIMessage(content="[expand_gaps] no parent_id")]}

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
    return {"current_action": None, "current_action_batch": None, "consecutive_idle": idle, "forced_convergence_count": forced_count, "messages": [AIMessage(content=summary)]}


def _run_single_search(action: dict) -> tuple[str, bool, str]:
    """Execute one searcher dispatch and return (handle, succeeded, summary).

    Encapsulates the prepare→invoke→summarise pipeline so it can be called
    from both the serial path and a ThreadPoolExecutor.
    """
    query_id = action.get("query_id")
    handle = action.get("query_handle", query_id)
    source_preferences = action.get("source_preferences")

    prepared = prepare_search(query_id, source_preferences)
    if prepared.get("error"):
        return handle, False, f"[dispatch_searcher] {handle} prepare ERROR: {prepared['error']}"

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
        return handle, False, f"[dispatch_searcher] {handle} FAILED: {exc}"

    submit_result = result.get("submit_result")
    if isinstance(submit_result, dict):
        written = submit_result.get("written") or {}
        sources = written.get("sources", "?")
        documents = written.get("documents", "?")
        evidence = written.get("evidence", "?")
        status = submit_result.get("status", "?")
        summary = (
            f"[dispatch_searcher] {handle}: "
            f"status={status}, sources={sources}, documents={documents}, evidence={evidence}"
        )
        return handle, status == "succeeded", summary
    else:
        fail_search(
            prepared["search_run_id"],
            prepared["query_id"],
            "Searcher returned no submit result",
        )
        return handle, False, f"[dispatch_searcher] {handle}: no submit result (recorded as failure)"


def dispatch_node(state: dict) -> dict:
    """准备搜索上下文并调用 Searcher 子图收集证据.

    When ``current_action_batch`` is set (multiple dispatch_searcher actions
    queued by the scheduler), runs them concurrently via ThreadPoolExecutor.
    Graph writes inside ``submit_search_result`` are serialised by
    ``MemoryManager._state_lock``, so only the I/O-bound search and analysis
    work is parallelised.
    """
    action = state.get("current_action") or {}
    query_id = action.get("query_id")
    if not query_id:
        return {"current_action": None, "current_action_batch": None, "consecutive_idle": int(state.get("consecutive_idle") or 0) + 1, "forced_convergence_count": int(state.get("forced_convergence_count") or 0), "messages": [AIMessage(content="[dispatch_searcher] no query_id")]}

    batch = state.get("current_action_batch")

    if batch and len(batch) > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from config import SEARCH_DISPATCH_CONCURRENCY

        summaries: list[str] = []
        any_succeeded = False
        with ThreadPoolExecutor(max_workers=SEARCH_DISPATCH_CONCURRENCY) as pool:
            futures = {pool.submit(_run_single_search, a): a for a in batch}
            for fut in as_completed(futures):
                handle, succeeded, summary = fut.result()
                summaries.append(summary)
                if succeeded:
                    any_succeeded = True

        combined = "; ".join(summaries)
        idle = 0 if any_succeeded else int(state.get("consecutive_idle") or 0) + len(batch)
        forced_count = 0 if any_succeeded else int(state.get("forced_convergence_count") or 0)
        return {"current_action": None, "current_action_batch": None, "consecutive_idle": idle, "forced_convergence_count": forced_count, "messages": [AIMessage(content=combined)]}

    # Serial path (single dispatch or no batch)
    handle, succeeded, summary = _run_single_search(action)
    if succeeded:
        idle = 0
        forced_count = 0
    else:
        idle = int(state.get("consecutive_idle") or 0) + 1
        forced_count = int(state.get("forced_convergence_count") or 0)
    return {"current_action": None, "current_action_batch": None, "consecutive_idle": idle, "forced_convergence_count": forced_count, "messages": [AIMessage(content=summary)]}


def convergence_node(state: dict) -> dict:
    """裁决收敛：检查目标覆盖、致命冲突和预算，决定继续还是授权报告.

    正常的收敛裁决完全委托 ``memory_manager.assess_convergence``，后者基于
    ``get_next_actions`` 的"单源 actionability 定义"判断是否还有可推进的
    工作。

    可操作路径穷尽时使用 ``REPORT_READY``（正常交付），不降级为 limited。
    步预算安全网触发时（不可预期的调度故障）使用 ``LIMITED_REPORT_READY``。
    """
    from tools import research_state

    action = state.get("current_action") or {}
    goal_id = action.get("goal_id")
    reason = action.get("reason") or ""
    is_path_exhausted = "no actionable paths" in reason
    is_step_budget = "step budget" in reason
    is_forced = is_path_exhausted or is_step_budget
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
        # 当路径检查或步预算触发时 assess_convergence 仍 say continue，
        # 说明 assess_convergence 看到了 evaluate_research_portfolio 等
        # 非直接搜索动作。路径穷尽时正常交付（REPORT_READY），
        # 步预算耗尽时降级交付（LIMITED_REPORT_READY）作为安全网。
        if is_forced and recommendation == "continue":
            target_state = (
                research_state.REPORT_READY
                if is_path_exhausted
                else research_state.LIMITED_REPORT_READY
            )
            label = (
                "PATH EXHAUSTED -> REPORT_READY"
                if is_path_exhausted
                else "RECURSION BUDGET GUARD -> LIMITED_REPORT_READY"
            )
            try:
                research_state.update_goal({
                    "research_state": target_state,
                })
                summary += (
                    f" -> {label} "
                    f"(forced_count={forced_count})"
                )
            except ValueError as exc:
                summary += f" -> override skipped (transition invalid: {exc})"

    new_forced_count = forced_count if is_forced else 0
    return {
        "current_action": None,
        "consecutive_idle": 0,
        "forced_convergence_count": new_forced_count,
        "current_action_batch": None,
        "messages": [AIMessage(content=summary)],
    }


def report_node(state: dict) -> dict:
    """执行嵌套的确定性 Reporter workflow."""
    del state
    try:
        if config.reporter_mode() == "global":
            result = run_global_report_workflow()
            if not result.get("success") and config.GR_REPORTER_FALLBACK:
                logger.warning(
                    "[reporter.fallback] global_failed attempts=%s error=%s",
                    result.get("attempts"),
                    str(result.get("error"))[:500],
                )
                fallback_result = run_report_workflow(runnable_config=get_config())
                logger.info(
                    "[reporter.fallback] chapter_completed success=%s validated=%s",
                    fallback_result.get("success"),
                    fallback_result.get("validated"),
                )
                # Never treat an unvalidated chapter artifact as a successful
                # replacement for the global report. It may remain available as
                # a diagnostic salvage artifact, but must not enter benchmark output.
                if fallback_result.get("success") and fallback_result.get("validated"):
                    result = fallback_result
                    result["fallback_reason"] = "global Reporter failed"
                else:
                    result["fallback_reason"] = "global Reporter failed; chapter fallback was not validated"
        else:
            result = run_report_workflow(runnable_config=get_config())
    except Exception as exc:  # noqa: BLE001 — Reporter 异常不应导致无输出
        logger.exception("Reporter workflow invocation failed")
        return {
            "messages": [AIMessage(content=f"[reporter] FAILED: {exc}")],
        }

    compiled_report = gmt.get_compiled_report()
    report_len = len(compiled_report) if compiled_report else 0
    status = "submitted" if result.get("success") else "failed"
    summary = (
        f"[reporter] workflow {status}: {report_len} chars, "
        f"validated={result.get('validated', False)}, "
        f"review={result.get('review_status') or '?'}"
    )
    if result.get("error"):
        summary += f", error={result['error']}"
    if result.get("fallback_reason"):
        summary += f", fallback={result['fallback_reason']}"
    return {"messages": [AIMessage(content=summary)]}


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
