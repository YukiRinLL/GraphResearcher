"""Standalone checks for ReporterRevisionMiddleware retry behavior."""

import sys
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

repo_dir = Path(__file__).parent.parent
sys.path.insert(0, str(repo_dir / "src"))

from tools import graph_manager_tools  # noqa: E402
from tools.middleware import ReporterRevisionMiddleware  # noqa: E402


class _Response:
    def __init__(self, message):
        self.result = [message]


class _Request:
    def __init__(self, messages):
        self.messages = messages

    def override(self, messages):
        return _Request(messages)


def main():
    original = graph_manager_tools.get_last_report_attempt
    try:
        attempt = {
            "accepted": True,
            "revision_requested": True,
            "severity": "soft",
            "retention_ratio": 0.5,
            "submitted_sections": 2,
            "dropped_sections": 0,
            "submitted_paragraphs": 4,
            "kept_paragraphs": 2,
            "salvaged_report": "# Report\n\n## Section\n\nFact [1]\n\n## References\n\n[1] https://example.com\n",
            "issues": [{
                "code": "forbidden_meta_prose",
                "severity": "soft",
                "section_title": "Section A",
                "block_index": 2,
                "message": "meta prose leaked into one block",
                "repair_hint": "delete the meta sentence and resubmit",
            }],
        }
        graph_manager_tools.get_last_report_attempt = lambda: attempt

        calls = []

        def handler(request):
            calls.append(request)
            last = request.messages[-1]
            if isinstance(last, HumanMessage) and "submit_final_report 尚未达到可结束状态" in str(last.content):
                graph_manager_tools.get_last_report_attempt = lambda: {
                    **attempt,
                    "revision_requested": False,
                    "severity": "clean",
                    "issues": [],
                }
                return _Response(AIMessage(content="已重新提交"))
            return _Response(AIMessage(content="报告已生成"))

        middleware = ReporterRevisionMiddleware(max_retries=2)
        response = middleware.wrap_model_call(_Request([HumanMessage(content="write report")]), handler)
        assert response.result[-1].content == "已重新提交"
        assert len(calls) == 2
        assert isinstance(calls[-1].messages[-1], HumanMessage)
        prompt = str(calls[-1].messages[-1].content)
        assert "Section A" in prompt
        assert "kept_paragraphs=2 / submitted_paragraphs=4" in prompt
    finally:
        graph_manager_tools.get_last_report_attempt = original

    print("ALL REPORTER REVISION MIDDLEWARE CHECKS PASSED")


if __name__ == "__main__":
    main()
