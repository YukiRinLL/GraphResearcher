import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from langchain_core.messages import AIMessage

langchain_module = ModuleType("langchain")
agents_module = ModuleType("langchain.agents")
middleware_module = ModuleType("langchain.agents.middleware")


class AgentMiddleware:
    pass


middleware_module.AgentMiddleware = AgentMiddleware
sys.modules.setdefault("langchain", langchain_module)
sys.modules.setdefault("langchain.agents", agents_module)
sys.modules.setdefault("langchain.agents.middleware", middleware_module)

from tools import workflow_state
from tools.middleware import (
    ConvergenceGateMiddleware,
    PendingReviewGateMiddleware,
    ReportValidationMiddleware,
    WorkflowPhaseMiddleware,
)


def tool_call(name, args=None):
    return {"id": f"call_{name}", "name": name, "args": args or {}}


class WorkflowRuntimeTests(unittest.TestCase):
    def setUp(self):
        workflow_state.reset(max_search_rounds=1)
        workflow_state.set_phase("research")

    def test_budget_exhaustion_keeps_pending_review_open(self):
        workflow_state.record_search_dispatch("q1")
        workflow_state.mark_budget_exhausted()

        state = workflow_state.snapshot()
        self.assertTrue(state["budget_exhausted"])
        self.assertEqual(state["phase"], "research")

        phase_gate = WorkflowPhaseMiddleware()
        self.assertIsNone(phase_gate._intercept(tool_call("analyze_subgraph", {"query_id": "q1"})))
        self.assertIsNone(phase_gate._intercept(tool_call("mark_query", {"query_id": "q1"})))
        self.assertIsNotNone(phase_gate._intercept(tool_call("dispatch_searcher", {"query_id": "q2"})))
        self.assertIsNotNone(phase_gate._intercept(tool_call("expand_query", {"anchor_query_id": "q1"})))

    def test_mark_query_consumes_latest_analysis_and_enters_report_when_budget_done(self):
        workflow_state.record_search_dispatch("q1")
        workflow_state.mark_budget_exhausted()
        workflow_state.record_subgraph_analysis("q1", {"sufficiency_score": 0.7})

        review_gate = PendingReviewGateMiddleware()
        self.assertIsNone(review_gate._intercept(tool_call("mark_query", {"query_id": "q1"})))

        workflow_state.consume_mark_query("q1", "sufficient", 0.7)
        state = workflow_state.snapshot()
        self.assertEqual(state["pending_review_query_ids"], [])
        self.assertEqual(state["analysis_ready_query_ids"], [])
        self.assertEqual(state["phase"], "report")

    def test_reanalyzed_query_can_be_marked_again_after_prior_mark(self):
        workflow_state.record_search_dispatch("q1")
        workflow_state.record_subgraph_analysis("q1", {"sufficiency_score": 0.6})
        workflow_state.consume_mark_query("q1", "needs_vertical", 0.6)

        workflow_state.record_subgraph_analysis("q1", {"sufficiency_score": 0.8})
        review_gate = PendingReviewGateMiddleware()
        self.assertIsNone(review_gate._intercept(tool_call("mark_query", {"query_id": "q1"})))

    def test_continue_without_budget_exhaustion_rejects_terminal_report(self):
        workflow_state.record_convergence({"recommendation": "continue"})
        middleware = ReportValidationMiddleware(min_length=1, min_sections=0)
        response = SimpleNamespace(result=[AIMessage(content="## 报告\n\n正文 [1]")])

        self.assertTrue(middleware._is_incomplete(response))

    def test_reporter_called_only_after_allowed_successful_handler(self):
        gate = ConvergenceGateMiddleware()
        request = SimpleNamespace(tool_call=tool_call("task", {"subagent_type": "reporter"}))

        blocked = gate.wrap_tool_call(request, lambda req: SimpleNamespace(status="ok"))
        self.assertEqual(getattr(blocked, "status", None), "error")
        self.assertFalse(workflow_state.snapshot()["reporter_called"])

        workflow_state.record_convergence({"recommendation": "stop"})
        result = gate.wrap_tool_call(request, lambda req: SimpleNamespace(status="ok"))
        self.assertEqual(result.status, "ok")
        self.assertTrue(workflow_state.snapshot()["reporter_called"])

    def test_terminal_report_rejects_internal_terms(self):
        workflow_state.record_convergence({"recommendation": "stop"})
        workflow_state.mark_reporter_called()
        workflow_state.record_bound_section()
        middleware = ReportValidationMiddleware(min_length=1, min_sections=0)
        response = SimpleNamespace(result=[AIMessage(content="## 报告\n\nneeds_vertical 暴露了内部状态 [1]")])

        self.assertTrue(middleware._is_incomplete(response))

    def test_budget_forced_report_requires_natural_limitations(self):
        workflow_state.mark_budget_exhausted()
        workflow_state.mark_reporter_called()
        workflow_state.record_bound_section()
        middleware = ReportValidationMiddleware(min_length=1, min_sections=0)

        no_limits = SimpleNamespace(result=[AIMessage(content="## 报告\n\n这是完整结论 [1]")])
        with_limits = SimpleNamespace(result=[AIMessage(content="## 报告\n\n公开信息有限，相关判断应视为阶段性结论 [1]")])

        self.assertTrue(middleware._is_incomplete(no_limits))
        self.assertFalse(middleware._is_incomplete(with_limits))


if __name__ == "__main__":
    unittest.main()
