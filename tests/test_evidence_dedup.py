"""Standalone checks for Searcher deduplication and salience trimming."""

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
        searcher._PER_SOURCE_STATEMENT_CAP = 4
        searcher._PER_SOURCE_EVIDENCE_CAP = 4
        searcher._PER_QUERY_STATEMENT_CAP = 2
        searcher._PER_QUERY_EVIDENCE_CAP = 1

        search_results = {"results": [{"url": "https://example.com/source", "title": "Source"}]}
        packets = [{
            "source": {"source_type": "report"},
            "document": {"document_summary": "One source"},
            "statements": [
                {"local_ref": "st1", "text": "Warehouse robot financing reached 200 million in 2024."},
                {"local_ref": "st2", "text": "  Warehouse robot financing reached 200 million in 2024.  "},
                {"local_ref": "st3", "text": "The office cafeteria offers coffee."},
            ],
            "evidence": [
                {"local_ref": "e1", "text": "Warehouse robot financing reached 200 million in 2024."},
                {"local_ref": "e2", "text": "Warehouse   robot financing reached 200 million in 2024."},
                {"local_ref": "e3", "text": "The office cafeteria offers coffee."},
            ],
            "conflicts": [{
                "local_ref": "x1",
                "description": "Only retained evidence refs should survive.",
                "evidence_refs": ["e1", "e2", "e3"],
            }],
        }]

        package = searcher._apply_extraction_controls(search_results, packets, "warehouse robot financing")
        assert len(package["statements"]) == 2, package["statements"]
        assert len(package["evidence"]) == 1, package["evidence"]
        assert "financing" in package["evidence"][0]["text"].lower(), package["evidence"]
        assert "coffee" not in package["evidence"][0]["text"].lower(), package["evidence"]
        assert len(package["conflicts"]) == 1, package["conflicts"]
        assert package["conflicts"][0]["evidence_refs"] == [package["evidence"][0]["local_ref"]], package["conflicts"]
    finally:
        for name, value in originals.items():
            setattr(searcher, name, value)

    print("ALL EVIDENCE DEDUP CHECKS PASSED")


if __name__ == "__main__":
    main()
