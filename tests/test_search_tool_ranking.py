"""Standalone checks for search-result quality reranking."""

import sys
from pathlib import Path

repo_dir = Path(__file__).parent.parent
sys.path.insert(0, str(repo_dir / "src"))

from tools import search_tools  # noqa: E402


def main():
    results = [
        {"url": "https://www.facebook.com/example/post", "title": "Facebook", "content": ""},
        {"url": "https://www.cambridge.org/core/journals/example", "title": "Cambridge", "content": ""},
        {"url": "https://archive.example.com/page", "title": "Archive", "content": ""},
        {"url": "https://museum.example.org/object", "title": "Museum", "content": ""},
        {"url": "https://www.researchgate.net/publication/example", "title": "ResearchGate", "content": ""},
    ]
    ranked = search_tools._rerank_results(results)
    ranked_urls = [item["url"] for item in ranked]
    assert ranked_urls[:2] == [
        "https://www.cambridge.org/core/journals/example",
        "https://museum.example.org/object",
    ], ranked_urls
    assert ranked_urls[-2:] == [
        "https://www.facebook.com/example/post",
        "https://www.researchgate.net/publication/example",
    ], ranked_urls

    excluded = search_tools._filter_excluded_results(
        'ring of nestor -site:facebook.com -site:reddit.com',
        [
            {"url": "https://www.facebook.com/example/post"},
            {"url": "https://www.reddit.com/r/example"},
            {"url": "https://www.cambridge.org/core/journals/example"},
        ],
    )
    assert [item["url"] for item in excluded] == [
        "https://www.cambridge.org/core/journals/example",
    ], excluded

    print("ALL SEARCH TOOL RANKING CHECKS PASSED")


if __name__ == "__main__":
    main()
