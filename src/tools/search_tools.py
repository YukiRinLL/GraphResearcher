"""Web search tools for the Searcher agent.

Exposes two web-search tools: `serper_search` (Serper.dev, the default) and
`tavily_search` (Tavily, alternative). Clients are created lazily so importing
this module does not require any API key until a search actually runs.
"""

import os
from typing import Literal, Optional

import requests
from langchain_core.tools import tool
from tavily import TavilyClient

_tavily_client: Optional[TavilyClient] = None

# Cap per-result raw page text returned to the agent (chars).
_MAX_RAW_CONTENT_CHARS = 4000

SERPER_ENDPOINTS = {
    "general": "https://google.serper.dev/search",
    "news": "https://google.serper.dev/news",
    "finance": "https://google.serper.dev/search",
}

# Timeout configuration (seconds)
SEARCH_TIMEOUT = int(os.environ.get("SEARCH_TIMEOUT", "30"))


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
def serper_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
    include_raw_content: bool = False,
) -> dict:
    """Run a web search via Serper.dev (Google Search API). This is the default search tool.

    Args:
        query: The search query.
        max_results: Maximum number of results to return.
        topic: Search topic — ``general`` or ``news`` (``finance`` falls back to
            general; Serper has no dedicated finance endpoint).
        include_raw_content: Accepted for interface parity with ``tavily_search``;
            Serper returns snippets, not full page text, so this is ignored.

    Returns:
        A normalized dict ``{"query", "results": [{title, url, content, date}], "raw"}``,
        or, on failure, a dict with an ``error`` key so the agent can degrade
        gracefully instead of crashing the whole run.
    """
    try:
        endpoint = SERPER_ENDPOINTS.get(topic, SERPER_ENDPOINTS["general"])
        response = requests.post(
            endpoint,
            headers={"X-API-KEY": os.environ["SERPER_API_KEY"], "Content-Type": "application/json"},
            json={"q": query, "num": max_results},
            timeout=SEARCH_TIMEOUT,
        )
        if response.status_code >= 400:
            # Surface Serper's own message (e.g. "Not enough credits") rather than a bare HTTP code.
            return {
                "error": f"HTTP {response.status_code}: {response.text[:200]}",
                "query": query,
                "results": [],
                "note": "Serper search failed (see error). The alternate engine will be tried.",
            }
        data = response.json()
        items = data.get("news") if topic == "news" else data.get("organic")
        results = [
            {
                "title": item.get("title"),
                "url": item.get("link"),
                "content": item.get("snippet"),
                "date": item.get("date"),
            }
            for item in (items or [])[:max_results]
        ]
        # Return only the normalized results; echoing the full raw Serper
        # response back into the conversation bloats context and enlarges the
        # surface that the proxy's content filter can trip on.
        return {"query": query, "results": results}
    except Exception as e:  # noqa: BLE001 — surface any search failure as data, not a crash
        return {
            "error": f"{type(e).__name__}: {e}",
            "query": query,
            "results": [],
            "note": "Search request failed (see error for the exact cause). Try the alternate engine, adjust the query, or proceed with evidence already collected.",
        }


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
            "note": "Search request failed (see error for the exact cause). Try the alternate engine, adjust the query, or proceed with evidence already collected.",
        }
