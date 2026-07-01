"""Web search tools for the Searcher agent.

Exposes `tavily_search` as the sole web-search tool. The Tavily client is
created lazily so importing this module does not require an API key until a
search actually runs.
"""

import os
from typing import Literal, Optional

from langchain_core.tools import tool
from tavily import TavilyClient

_tavily_client: Optional[TavilyClient] = None

# Cap per-result raw page text returned to the agent (chars).
_MAX_RAW_CONTENT_CHARS = 4000


def _client() -> TavilyClient:
    """Return the Tavily client, creating it on first use.

    Deferring construction keeps importing this module cheap and avoids
    requiring ``TAVILY_API_KEY`` until a search actually runs.

    Returns:
        A configured ``TavilyClient``.
    """
    global _tavily_client
    if _tavily_client is None:
        _tavily_client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    return _tavily_client


@tool
def tavily_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
    include_raw_content: bool = False,
) -> dict:
    """Run a web search via Tavily.

    Args:
        query: The search query.
        max_results: Maximum number of results to return.
        topic: Search topic — ``general``, ``news`` or ``finance``.
        include_raw_content: Whether to include the full page text of results.

    Returns:
        The Tavily search response, or, on failure, a dict with an ``error``
        key describing the problem so the agent can degrade gracefully instead
        of crashing the whole run.
    """
    try:
        response = _client().search(
            query,
            max_results=max_results,
            include_raw_content=include_raw_content,
            topic=topic,
        )
        # Cap per-result raw page text so a few long pages don't flood the
        # conversation (context bloat + larger content-filter surface).
        if include_raw_content and isinstance(response, dict):
            for item in response.get("results", []) or []:
                raw = item.get("raw_content")
                if isinstance(raw, str) and len(raw) > _MAX_RAW_CONTENT_CHARS:
                    item["raw_content"] = raw[:_MAX_RAW_CONTENT_CHARS] + "…(truncated)"
        return response
    except Exception as e:  # noqa: BLE001 — surface any search failure as data, not a crash
        return {
            "error": f"{type(e).__name__}: {e}",
            "query": query,
            "results": [],
            "note": "Search request failed (see error for the exact cause). Adjust the query or proceed with evidence already collected.",
        }
