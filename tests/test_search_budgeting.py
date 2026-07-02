"""Standalone checks for Searcher extraction budgeting."""

import sys
from pathlib import Path

repo_dir = Path(__file__).parent.parent
sys.path.insert(0, str(repo_dir))
sys.path.insert(0, str(repo_dir / "src"))

from agents import searcher  # noqa: E402


def main():
    originals = {
        "_PER_SOURCE_STATEMENT_CAP": searcher._PER_SOURCE_STATEMENT_CAP,
        "_PER_SOURCE_EVIDENCE_CAP": searcher._PER_SOURCE_EVIDENCE_CAP,
        "_PER_QUERY_STATEMENT_CAP": searcher._PER_QUERY_STATEMENT_CAP,
        "_PER_QUERY_EVIDENCE_CAP": searcher._PER_QUERY_EVIDENCE_CAP,
    }
    try:
        searcher._PER_SOURCE_STATEMENT_CAP = 2
        searcher._PER_SOURCE_EVIDENCE_CAP = 2
        searcher._PER_QUERY_STATEMENT_CAP = 3
        searcher._PER_QUERY_EVIDENCE_CAP = 3

        search_results = {
            "results": [
                {"url": "https://example.com/a", "title": "A"},
                {"url": "https://example.com/b", "title": "B"},
            ]
        }
        packets = [
            {
                "source": {"source_type": "report"},
                "document": {"document_summary": "A summary"},
                "statements": [
                    {"local_ref": "st1", "text": "Warehouse robot financing reached 200 million in 2024."},
                    {"local_ref": "st2", "text": "Warehouse robot financing reached 200 million in 2024. "},
                    {"local_ref": "st3", "text": "The warehouse robot launched in 2023."},
                ],
                "evidence": [
                    {"local_ref": "e1", "text": "The funding round totaled 200 million dollars in 2024."},
                    {"local_ref": "e2", "text": "Revenue was 50 million dollars."},
                    {"local_ref": "e3", "text": "The company logo is blue."},
                ],
                "conflicts": [],
            },
            {
                "source": {"source_type": "news"},
                "document": {"document_summary": "B summary"},
                "statements": [
                    {"local_ref": "st1", "text": "The startup builds warehouse robots for logistics."},
                    {"local_ref": "st2", "text": "It also pilots humanoid robots."},
                    {"local_ref": "st3", "text": "An unrelated anecdote about office snacks."},
                ],
                "evidence": [
                    {"local_ref": "e1", "text": "The logistics robot fleet expanded to 300 sites."},
                    {"local_ref": "e2", "text": "The firm signed a financing term sheet in 2024."},
                    {"local_ref": "e3", "text": "The office has a mural."},
                ],
                "conflicts": [],
            },
        ]

        package = searcher._apply_extraction_controls(search_results, packets, "warehouse robot financing 2024")
        assert len(package["statements"]) == 3, package
        assert len(package["evidence"]) == 3, package
        assert len(package["documents"]) <= 2 and len(package["sources"]) <= 2, package
        assert all(item["text"].strip() for item in package["statements"]), package["statements"]
        assert all(item["text"].strip() for item in package["evidence"]), package["evidence"]
    finally:
        for name, value in originals.items():
            setattr(searcher, name, value)

    print("ALL SEARCH BUDGETING CHECKS PASSED")


if __name__ == "__main__":
    main()
