"""Standalone checks for the run-scoped Reporter workflow guard."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from langchain.agents.middleware.types import ModelResponse
from langchain_core.messages import AIMessage, HumanMessage

repo_dir = Path(__file__).parent.parent
sys.path.insert(0, str(repo_dir / "src"))

from tools import graph_manager_tools, graph_tools  # noqa: E402
from tools.middleware import ReporterWorkflowMiddleware  # noqa: E402


class _Request:
    def __init__(self, messages):
        self.messages = messages

    def override(self, messages):
        return _Request(messages)


def _tool_response(name="assemble_report_draft"):
    return ModelResponse(result=[AIMessage(content="", tool_calls=[{
        "name": name,
        "args": {},
        "id": f"call-{name}",
        "type": "tool_call",
    }])])


def main():
    original_clear = graph_tools.clear_current_context
    original_set = graph_tools.set_context
    graph_tools.clear_current_context = lambda: None
    graph_tools.set_context = lambda _context: None
    try:
        with TemporaryDirectory() as temp_dir:
            graph_manager_tools.configure(temp_dir, user_request="write report")
            middleware = ReporterWorkflowMiddleware(remind_at=2, force_at=3)
            requests = []

            def handler(request):
                requests.append(request)
                return _tool_response()

            request = _Request([HumanMessage(content="write report")])
            first = middleware.wrap_model_call(request, handler)
            assert first.result[-1].tool_calls[0]["name"] == "assemble_report_draft"

            second = middleware.wrap_model_call(request, handler)
            assert second.result[-1].tool_calls[0]["name"] == "assemble_report_draft"
            assert "接近 Reporter 运行上限" in str(requests[-1].messages[-1].content)

            third = middleware.wrap_model_call(request, handler)
            assert third.result[-1].tool_calls[0]["name"] == "submit_final_report"
            assert len(requests) == 2
            assert graph_manager_tools.get_reporter_model_call_count() == 3

            graph_manager_tools.configure(temp_dir, user_request="write report")
            terminal = ReporterWorkflowMiddleware().wrap_model_call(
                request,
                lambda _request: ModelResponse(result=[AIMessage(content="done")]),
            )
            assert terminal.result[-1].tool_calls[0]["name"] == "submit_final_report"

            graph_manager_tools._last_report_attempt = {
                "delivered": True,
                "revision_requested": False,
            }
            handler_called = []
            completed = ReporterWorkflowMiddleware().wrap_model_call(
                request,
                lambda _request: handler_called.append(True),
            )
            assert completed.result[-1].content == "报告已提交。"
            assert not handler_called
    finally:
        graph_tools.clear_current_context = original_clear
        graph_tools.set_context = original_set

    print("ALL REPORTER WORKFLOW MIDDLEWARE CHECKS PASSED")


if __name__ == "__main__":
    main()
