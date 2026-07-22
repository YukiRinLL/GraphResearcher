"""State Contract v2 的报告授权回归检查。

直接运行：``uv run python tests/test_state_contract_v2.py``。
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))
repo_dir = src_dir.parent

from agents.memory_manager import MemoryManager  # noqa: E402
from tools import graph_tools, research_state  # noqa: E402
from tools.middleware import ResearchStateMiddleware  # noqa: E402


class VerdictModel:
    def __init__(self, fatal=None):
        self.fatal = fatal or []

    def invoke(self, _prompt):
        fatal = self.fatal

        class Response:
            content = json.dumps({"fatal_unresolved_conflicts": fatal, "reason": "done"})

        return Response()


def _assess(
    *,
    must_status: str,
    query_status: str = "sufficient",
    maximum: int = 20,
    dispatched: int = 8,
    should_status: str | None = None,
    selected_gap: bool = False,
    fatal_conflict: bool = False,
    scope_mode: str = "bounded",
    prior_recovery: bool = False,
    completed_recovery: bool = False,
    active_query: bool = False,
    assigned_gap: bool = False,
    schedule_only: bool = False,
):
    nodes = {
        "goal": {
            "id": "goal",
            "type": "UserRequest",
            "state_contract_version": 4,
            "research_state": research_state.RESEARCHING,
            "max_search_rounds": maximum,
            "dispatched_search_rounds": dispatched,
            "scope_mode": scope_mode,
            "portfolio_revision": 1,
            "evaluated_portfolio_revision": 1,
        },
        "must": {
            "id": "must",
            "type": "Analysis",
            "analysis_type": "objective",
            "objective_key": "core-answer",
            "requirement": "must",
            "weight": 1.0,
            "status": must_status,
        },
        "query": {
            "id": "query",
            "type": "Query",
            "handle": "q1",
            "text": "core answer",
            "status": query_status,
            "objective_keys": ["core-answer"],
            "sufficiency_score": 0.8,
        },
    }
    if should_status is not None:
        nodes["should"] = {
            "id": "should",
            "type": "Analysis",
            "analysis_type": "objective",
            "objective_key": "supporting-detail",
            "requirement": "should",
            "weight": 0.5,
            "status": should_status,
        }
        nodes["query"]["objective_keys"].append("supporting-detail")
    if selected_gap:
        nodes["gap"] = {
            "id": "gap",
            "type": "Analysis",
            "analysis_type": "gap",
            "status": "selected",
            "expansion_parent_id": "goal",
        }
    if active_query:
        nodes["active-query"] = {
            "id": "active-query",
            "type": "Query",
            "handle": "q2",
            "text": "active core search",
            "status": "searching",
            "objective_keys": ["core-answer"],
            "sufficiency_score": 0.0,
        }
    if assigned_gap:
        nodes["assigned-gap"] = {
            "id": "assigned-gap",
            "type": "Analysis",
            "analysis_type": "gap",
            "status": "assigned",
            "expansion_parent_id": "goal",
        }
    if fatal_conflict:
        nodes["conflict"] = {
            "id": "conflict",
            "type": "Conflict",
            "description": "core sources irreconcilably disagree",
            "resolution_status": "unresolved",
        }
    edges = []
    if prior_recovery:
        nodes["recovery-gap"] = {
            "id": "recovery-gap",
            "type": "Analysis",
            "analysis_type": "gap",
            "status": "resolved",
            "recovery_objective_key": "core-answer",
        }
        edges.append({"source": "goal", "target": "recovery-gap", "type": "HAS_GAP"})
        if completed_recovery:
            edges.append({
                "source": "query",
                "target": "recovery-gap",
                "type": "ADDRESSES_GAP",
            })

    def get_node(node_id):
        return dict(nodes.get(node_id, {}))

    def search_nodes(node_type, filters=None):
        normalized = node_type.replace("_", "").lower()
        matches = [
            dict(node)
            for node in nodes.values()
            if str(node.get("type", "")).replace("_", "").lower() == normalized
        ]
        return [
            node
            for node in matches
            if all(node.get(key) == value for key, value in (filters or {}).items())
        ]

    def upsert_node(_node_type, attributes, dedupe_key=None):
        nodes[dedupe_key].update(attributes)
        return dedupe_key

    def transition_query(query_id, status, **_kwargs):
        nodes[query_id]["status"] = status
        return dict(nodes[query_id])

    def get_node_edges(node_id, direction="both"):
        return [
            edge
            for edge in edges
            if direction == "both"
            or (direction == "out" and edge["source"] == node_id)
            or (direction == "in" and edge["target"] == node_id)
        ]

    with patch.multiple(
        graph_tools,
        get_node=get_node,
        search_nodes=search_nodes,
        upsert_node=upsert_node,
        transition_query=transition_query,
        get_query_parent=lambda query_id: (
            "goal" if nodes.get(query_id, {}).get("type") == "Query" else None
        ),
        get_query_children=lambda _query_id: [],
        get_node_edges=get_node_edges,
        validate_query_tree=lambda: {"valid": True},
    ):
        fatal = [nodes["conflict"]["description"]] if fatal_conflict else []
        manager = MemoryManager(model=VerdictModel(fatal))
        result = manager.get_next_actions() if schedule_only else manager.assess_convergence("goal")
    return result, nodes


def test_satisfied_must_objectives_win_over_zero_budget():
    result, _ = _assess(must_status="satisfied", maximum=8, dispatched=8)
    assert result["research_state"] == research_state.REPORT_READY, result


def test_exhaustive_run_defers_only_pending_work_after_must_objectives_are_satisfied():
    for maximum, dispatched in ((20, 8), (8, 8)):
        result, nodes = _assess(
            must_status="satisfied",
            query_status="pending",
            maximum=maximum,
            dispatched=dispatched,
            scope_mode="exhaustive",
        )
        assert result["research_state"] == research_state.REPORT_READY, result
        assert nodes["query"]["status"] == "deferred", nodes["query"]


def test_scheduler_preserves_complete_report_precedence_at_zero_budget():
    actions, nodes = _assess(
        must_status="satisfied",
        query_status="pending",
        maximum=8,
        dispatched=8,
        should_status="open",
        schedule_only=True,
    )
    assert actions and actions[0]["action"] == "assess_convergence", actions
    assert nodes["goal"]["research_state"] == research_state.RESEARCHING, nodes["goal"]


def test_exhaustive_scheduler_assesses_convergence_before_optional_pending_work():
    actions, nodes = _assess(
        must_status="satisfied",
        query_status="pending",
        maximum=20,
        dispatched=8,
        scope_mode="exhaustive",
        schedule_only=True,
    )
    assert actions and actions[0]["action"] == "assess_convergence", actions
    assert nodes["query"]["status"] == "pending", nodes["query"]


def test_exhaustive_scheduler_preserves_in_flight_work_before_optional_pending_work():
    for boundary in ({"active_query": True}, {"assigned_gap": True}):
        actions, _ = _assess(
            must_status="satisfied",
            query_status="pending",
            maximum=20,
            dispatched=8,
            scope_mode="exhaustive",
            schedule_only=True,
            **boundary,
        )
        assert actions and actions[0]["action"] == "dispatch_searcher", (boundary, actions)


def test_unmet_must_objectives_with_zero_budget_are_budget_exhausted():
    result, _ = _assess(must_status="open", maximum=8, dispatched=8)
    assert result["research_state"] == research_state.BUDGET_EXHAUSTED, result


def test_active_query_blocks_report_authorization():
    result, _ = _assess(must_status="satisfied", query_status="searching")
    assert result["research_state"] == research_state.RESEARCHING, result


def test_waiting_children_query_blocks_complete_report_authorization():
    result, nodes = _assess(must_status="satisfied", query_status="waiting_children")
    assert result["research_state"] == research_state.RESEARCHING, result
    assert nodes["query"]["status"] == "waiting_children", nodes["query"]


def test_waiting_children_query_blocks_limited_report_authorization():
    result, nodes = _assess(must_status="blocked", query_status="waiting_children")
    assert result["research_state"] == research_state.RESEARCHING, result
    assert nodes["query"]["status"] == "waiting_children", nodes["query"]


def test_needs_expansion_query_blocks_limited_report_authorization():
    result, nodes = _assess(must_status="blocked", query_status="needs_expansion")
    assert result["research_state"] == research_state.RESEARCHING, result
    assert nodes["query"]["status"] == "needs_expansion", nodes["query"]


def test_zero_budget_searching_query_keeps_researching_state():
    result, nodes = _assess(
        must_status="satisfied",
        query_status="searching",
        maximum=8,
        dispatched=8,
    )
    assert result["converged"] is False, result
    assert result["research_state"] == research_state.RESEARCHING, result
    assert nodes["goal"]["research_state"] == research_state.RESEARCHING, nodes["goal"]


def test_zero_budget_assessing_query_keeps_researching_state():
    result, nodes = _assess(
        must_status="satisfied",
        query_status="assessing",
        maximum=8,
        dispatched=8,
    )
    assert result["converged"] is False, result
    assert result["research_state"] == research_state.RESEARCHING, result
    assert nodes["goal"]["research_state"] == research_state.RESEARCHING, nodes["goal"]


def test_pending_query_blocks_limited_report_authorization():
    result, nodes = _assess(must_status="blocked", query_status="pending")
    assert result["research_state"] == research_state.RESEARCHING, result
    assert nodes["query"]["status"] == "pending", nodes["query"]


def test_selected_gap_blocks_report_authorization():
    result, _ = _assess(must_status="satisfied", selected_gap=True)
    assert result["research_state"] == research_state.RESEARCHING, result


def test_fatal_conflict_blocks_report_authorization():
    result, _ = _assess(must_status="satisfied", fatal_conflict=True)
    assert result["research_state"] == research_state.RESEARCHING, result


def test_recovery_gap_without_completed_query_does_not_fail_exhaustive_run():
    actions, nodes = _assess(
        must_status="open",
        scope_mode="exhaustive",
        prior_recovery=True,
        schedule_only=True,
    )
    assert actions and actions[0]["action"] == "evaluate_research_portfolio", actions
    assert nodes["goal"]["research_state"] == research_state.RESEARCHING, nodes["goal"]
    assert nodes["must"]["status"] == "open", nodes["must"]
    assert nodes["recovery-gap"]["status"] == "candidate", nodes["recovery-gap"]


def test_completed_failed_recovery_fails_exhaustive_run():
    actions, nodes = _assess(
        must_status="open",
        query_status="sufficient",
        scope_mode="exhaustive",
        prior_recovery=True,
        completed_recovery=True,
        schedule_only=True,
    )
    assert actions == [], actions
    assert nodes["goal"]["research_state"] == research_state.FAILED, nodes["goal"]


def test_limited_report_ready_authorizes_reporter():
    call = {
        "name": "task",
        "id": "reporter",
        "args": {
            "subagent_type": "reporter",
            "description": "错误事实摘要和章节建议",
        },
    }
    with (
        patch.object(
            research_state,
            "get_status",
            return_value={"research_state": research_state.LIMITED_REPORT_READY},
        ),
        patch.object(research_state, "update_goal") as update_goal,
        patch.object(graph_tools, "validate_query_tree", return_value={"valid": True}),
    ):
        blocked = ResearchStateMiddleware()._gate_reporter(call)
    assert blocked is None, blocked
    assert call["args"]["description"] == ResearchStateMiddleware._REPORTER_HANDOFF
    assert "错误事实摘要" not in call["args"]["description"]
    update_goal.assert_called_once_with({
        "research_state": research_state.REPORTING,
        "reporting_from_state": research_state.LIMITED_REPORT_READY,
    })


def test_agent_prompts_enforce_report_visibility_contract():
    orchestrator = (repo_dir / "src/prompts/orchestrator.md").read_text(encoding="utf-8")
    reporter = (repo_dir / "src/prompts/reporter.md").read_text(encoding="utf-8")
    assert "LIMITED_REPORT_READY" in orchestrator
    assert "LIMITED_REPORT_READY" in reporter
    assert "不得在同一个模型回合中并行调用" in orchestrator
    assert "只有当它明确返回 `assess_convergence`" in orchestrator
    assert "unmet_objectives" not in reporter
    assert "原始 User Request" in reporter
    assert "无参数的 `submit_final_report()`" in reporter
    assert "substantive_uncertainties" in reporter
    assert "不自动创建局限章节" in reporter


def test_idle_should_objective_is_deferred_before_complete_report():
    result, nodes = _assess(
        must_status="satisfied",
        query_status="pending",
        should_status="open",
    )
    assert result["research_state"] == research_state.REPORT_READY, result
    assert nodes["query"]["status"] == "deferred", nodes["query"]
    assert nodes["should"]["status"] == "deferred", nodes["should"]


if __name__ == "__main__":
    test_satisfied_must_objectives_win_over_zero_budget()
    test_exhaustive_run_defers_only_pending_work_after_must_objectives_are_satisfied()
    test_scheduler_preserves_complete_report_precedence_at_zero_budget()
    test_exhaustive_scheduler_assesses_convergence_before_optional_pending_work()
    test_exhaustive_scheduler_preserves_in_flight_work_before_optional_pending_work()
    test_unmet_must_objectives_with_zero_budget_are_budget_exhausted()
    test_active_query_blocks_report_authorization()
    test_waiting_children_query_blocks_complete_report_authorization()
    test_waiting_children_query_blocks_limited_report_authorization()
    test_needs_expansion_query_blocks_limited_report_authorization()
    test_zero_budget_searching_query_keeps_researching_state()
    test_zero_budget_assessing_query_keeps_researching_state()
    test_pending_query_blocks_limited_report_authorization()
    test_selected_gap_blocks_report_authorization()
    test_fatal_conflict_blocks_report_authorization()
    test_recovery_gap_without_completed_query_does_not_fail_exhaustive_run()
    test_completed_failed_recovery_fails_exhaustive_run()
    test_limited_report_ready_authorizes_reporter()
    test_agent_prompts_enforce_report_visibility_contract()
    test_idle_should_objective_is_deferred_before_complete_report()
