"""Tavily-only Searcher 管线的独立回归检查。

直接运行：``uv run python tests/test_tavily_searcher_pipeline.py``。
"""

import json
import sys
from pathlib import Path

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from agents import searcher  # noqa: E402
from tools import search_tools  # noqa: E402


class FakeTavilyClient:
    """记录搜索参数并返回预置响应。"""

    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def search(self, query, **kwargs):
        self.calls.append({"query": query, **kwargs})
        if self.error:
            raise self.error
        return self.response


class FakeModel:
    """依次返回预置 source packet，并保留实际输入 prompt。"""

    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.prompts = []

    def invoke(self, messages):
        self.prompts.append(messages[-1].content)
        payload = self.payloads.pop(0)

        class Response:
            content = json.dumps(payload, ensure_ascii=False)

        return Response()


def _test_tavily_tool_contract():
    original_client = search_tools._tavily_client
    try:
        fake = FakeTavilyClient({
            "query": "test query",
            "results": [{
                "url": "https://example.com",
                "raw_content": "x" * 21_000,
            }],
        })
        search_tools._tavily_client = fake
        result = search_tools.tavily_search.invoke({
            "query": "test query",
            "max_results": 3,
            "topic": "news",
        })
        call = fake.calls[0]
        assert call["include_raw_content"] is True, call
        assert call["max_results"] == 3 and call["topic"] == "news", call
        assert "exclude_domains" not in call, call
        assert call["timeout"] == search_tools.SEARCH_TIMEOUT, call
        raw_content = result["results"][0]["raw_content"]
        assert raw_content.startswith("x" * 20_000), len(raw_content)
        assert raw_content.endswith("...(truncated)"), raw_content[-20:]

        search_tools._tavily_client = FakeTavilyClient(error=RuntimeError("offline"))
        failed = search_tools.tavily_search.invoke({"query": "failure"})
        assert failed["results"] == [] and "RuntimeError" in failed["error"], failed
    finally:
        search_tools._tavily_client = original_client


def _test_searcher_pipeline():
    original_search = searcher._TAVILY_SEARCH
    original_model = searcher.config._model_cache.get("default")
    try:
        search_calls = []

        def fake_search(**kwargs):
            search_calls.append(kwargs)
            return {
            "query": kwargs["query"],
            "request_id": "request-1",
            "results": [
                {
                    "url": "HTTPS://Example.COM/article/?utm_source=test&b=2&a=1#fragment",
                    "title": "Source A",
                    "content": "SNIPPET_ONLY_A",
                    "raw_content": "FULL_BODY_A",
                    "published_date": "2025-01-01",
                    "score": 0.9,
                },
                {
                    "url": "https://example.com/article?a=1&b=2",
                    "title": "Duplicate A",
                    "content": "duplicate",
                    "raw_content": "DUPLICATE_BODY",
                },
                {
                    "url": "https://example.net/no-body",
                    "title": "No Body",
                    "content": "snippet only",
                    "raw_content": "",
                },
                {
                    "url": None,
                    "title": "No URL",
                    "raw_content": "body without URL",
                },
                {
                    "url": "https://Example.org/other/?fbclid=tracking",
                    "title": "Source B",
                    "content": "SNIPPET_ONLY_B",
                    "raw_content": "FULL_BODY_B",
                },
                {
                    "url": "https://example.edu/empty-packet",
                    "title": "Source C",
                    "content": "SNIPPET_ONLY_C",
                    "raw_content": "FULL_BODY_C",
                },
                {
                    "url": "https://blocked.example/domain-result",
                    "title": "Forbidden domain",
                    "raw_content": "FORBIDDEN_DOMAIN_BODY",
                },
                {
                    "url": "https://allowed.example/forbidden/?utm_source=test",
                    "title": "Forbidden exact URL",
                    "raw_content": "FORBIDDEN_URL_BODY",
                },
                "invalid result",
            ],
        }
        searcher._TAVILY_SEARCH = fake_search
        model = FakeModel([
            {
                "source": {"source_type": "report", "published_at": "2025-01-01"},
                "document": {"document_summary": "summary A"},
                "statements": [{"local_ref": "st-local", "text": "statement A"}],
                "evidence": [
                    {"local_ref": "first", "text": "evidence A1", "evidence_type": "quote"},
                    {"local_ref": "second", "text": "evidence A2", "evidence_type": "data"},
                ],
                "conflicts": [{
                    "local_ref": "conflict-local",
                    "description": "internal conflict",
                    "evidence_refs": ["first", "second"],
                }],
            },
            {
                "source": {"source_type": "news"},
                "document": {"document_summary": "summary B"},
                "statements": [],
                "evidence": [{"local_ref": "first", "text": "evidence B"}],
                "conflicts": [],
            },
            {
                "source": {"source_type": "other"},
                "document": {"document_summary": ""},
                "statements": [],
                "evidence": [],
                "conflicts": [],
            },
            {
                "source": {"source_type": "other"},
                "document": {"document_summary": ""},
                "statements": [],
                "evidence": [],
                "conflicts": [],
            },
            {
                "source": {"source_type": "other"},
                "document": {"document_summary": ""},
                "statements": [],
                "evidence": [],
                "conflicts": [],
            },
        ])
        searcher.config._model_cache["default"] = model

        state = {
            "messages": [],
            "query_id": "q1",
            "search_run_id": "run1",
            "query_text": "test query",
            "source_preferences": ["official sources"],
        }
        searched = searcher.web_search_node(state)
        results = searched["search_results"]
        assert search_calls[0]["query"] == "test query", search_calls
        assert "exclude_domains" not in search_calls[0], search_calls
        assert results["dropped_duplicates"] == 1, results
        assert results["dropped_without_raw_content"] == 1, results
        assert results["dropped_without_url"] == 1, results
        assert results["dropped_invalid_results"] == 1, results
        assert "dropped_excluded_sources" not in results, results
        assert len(results["results"]) == 5, results
        assert results["results"][0]["url"] == "https://example.com/article?a=1&b=2", results
        assert results["results"][1]["url"] == "https://example.org/other", results
        assert results["results"][3]["url"] == "https://blocked.example/domain-result", results
        assert results["results"][4]["url"] == "https://allowed.example/forbidden", results
        assert "FULL_BODY_A" not in searched["search_output"], searched["search_output"]

        state.update(searched)
        extracted = searcher.extract_evidence_package_node(state)
        package = extracted["evidence_package"]
        assert len(model.prompts) == 5, model.prompts
        assert all("主体匹配硬判定" in prompt for prompt in model.prompts), model.prompts
        assert all(
            '"source": {}, "document": {}, "statements": [], "evidence": [], "conflicts": []'
            in prompt
            for prompt in model.prompts
        ), model.prompts
        assert "FULL_BODY_A" in model.prompts[0] and "FULL_BODY_B" in model.prompts[1]
        assert "FORBIDDEN_DOMAIN_BODY" in model.prompts[3], model.prompts
        assert "FORBIDDEN_URL_BODY" in model.prompts[4], model.prompts
        assert len(package["sources"]) == 2 and len(package["documents"]) == 2, package
        assert all("raw_content" not in document for document in package["documents"]), package
        assert [item["local_ref"] for item in package["statements"]] == ["st1"], package
        assert [item["local_ref"] for item in package["evidence"]] == ["e1", "e2", "e3"], package
        assert package["conflicts"][0]["evidence_refs"] == ["e1", "e2"], package
    finally:
        searcher._TAVILY_SEARCH = original_search
        if original_model is None:
            searcher.config._model_cache.pop("default", None)
        else:
            searcher.config._model_cache["default"] = original_model


def _test_empty_search_results():
    original_search = searcher._TAVILY_SEARCH
    try:
        state = {
            "messages": [],
            "query_id": "q1",
            "search_run_id": "run1",
            "query_text": "empty query",
            "source_preferences": [],
        }
        searcher._TAVILY_SEARCH = lambda **_kwargs: {"error": "offline", "results": []}
        searched = searcher.web_search_node(state)
        state.update(searched)
        extracted = searcher.extract_evidence_package_node(state)
        assert extracted["evidence_package"] == searcher._empty_package(), extracted

        searcher._TAVILY_SEARCH = lambda **_kwargs: "invalid"
        invalid = searcher.web_search_node(state)
        assert invalid["search_results"]["results"] == [], invalid
        assert "non-dict" in invalid["search_results"]["error"], invalid
    finally:
        searcher._TAVILY_SEARCH = original_search


def main():
    """运行全部 Tavily-only 管线检查。"""
    _test_tavily_tool_contract()
    _test_searcher_pipeline()
    _test_empty_search_results()
    print("ALL TAVILY SEARCHER PIPELINE CHECKS PASSED")  # noqa: T201


if __name__ == "__main__":
    main()
