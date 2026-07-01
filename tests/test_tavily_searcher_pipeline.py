"""Standalone checks for the Tavily-only Searcher pipeline.

Run directly: ``uv run python tests/test_tavily_searcher_pipeline.py``
"""

import json
import sys
from pathlib import Path

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from agents import searcher  # noqa: E402


class FakeModel:
    """Return pre-seeded JSON packets from ``invoke``."""

    def __init__(self, payloads):
        self._payloads = list(payloads)

    def invoke(self, _messages):
        payload = self._payloads.pop(0)

        class _R:
            content = json.dumps(payload, ensure_ascii=False)

        return _R()


def main():
    original_search = searcher._TAVILY_SEARCH
    old_default = searcher.config._model_cache.get("default")
    try:
        searcher._TAVILY_SEARCH = lambda **kwargs: {
            "query": kwargs["query"],
            "results": [
                {
                    "url": "https://example.com/a",
                    "title": "Source A",
                    "content": "summary A",
                    "raw_content": "full text A",
                    "published_at": "2025-01-01",
                    "score": 0.9,
                },
                {
                    "url": "https://example.com/drop",
                    "title": "Drop Me",
                    "content": "summary only",
                    "raw_content": "",
                    "score": 0.1,
                },
                {
                    "url": "https://example.com/b",
                    "title": "Source B",
                    "content": "summary B",
                    "raw_content": "full text B",
                    "score": 0.8,
                },
            ],
        }
        searcher.config._model_cache["default"] = FakeModel([
            {
                "source": {"source_type": "report", "published_at": "2025-01-01"},
                "document": {"document_summary": "document summary A"},
                "statements": [
                    {"local_ref": "st1", "text": "statement A", "confidence": "high"},
                ],
                "evidence": [
                    {"local_ref": "e1", "text": "evidence A", "evidence_type": "quote", "confidence": "high"},
                ],
                "conflicts": [],
            },
            {
                "source": {"source_type": "news"},
                "document": {"document_summary": "document summary B"},
                "statements": [
                    {"local_ref": "st1", "text": "statement B", "confidence": "medium"},
                ],
                "evidence": [
                    {"local_ref": "e1", "text": "evidence B1", "evidence_type": "data", "confidence": "medium"},
                    {"local_ref": "e2", "text": "evidence B2", "evidence_type": "data", "confidence": "medium"},
                ],
                "conflicts": [
                    {"local_ref": "x1", "description": "internal mismatch", "evidence_refs": ["e1", "e2"]},
                ],
            },
        ])

        state = {
            "messages": [],
            "query_id": "q1",
            "search_run_id": "run1",
            "query_text": "test query",
        }
        searched = searcher.web_search_node(state)
        assert len(searched["search_results"]["results"]) == 2, searched
        assert searched["search_results"]["dropped_without_raw_content"] == 1, searched

        state.update(searched)
        extracted = searcher.extract_evidence_package_node(state)
        package = extracted["evidence_package"]

        assert len(package["sources"]) == 2, package
        assert len(package["documents"]) == 2, package
        assert package["documents"][0]["raw_content"] == "full text A", package["documents"][0]
        assert package["documents"][1]["raw_content"] == "full text B", package["documents"][1]
        assert {item["document_ref"] for item in package["statements"]} == {"d1", "d2"}, package["statements"]
        assert {item["source_ref"] for item in package["evidence"]} == {"s1", "s2"}, package["evidence"]
        assert package["conflicts"][0]["evidence_refs"] == ["e2", "e3"], package["conflicts"]
    finally:
        searcher._TAVILY_SEARCH = original_search
        if old_default is None:
            searcher.config._model_cache.pop("default", None)
        else:
            searcher.config._model_cache["default"] = old_default

if __name__ == "__main__":
    main()
