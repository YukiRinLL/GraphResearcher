"""Web search tools for the Searcher agent.

Exposes two web-search tools: `serper_search` (Serper.dev, the default) and
`tavily_search` (Tavily, alternative). Clients are created lazily so importing
this module does not require any API key until a search actually runs.
"""

import os
from urllib.parse import urlparse
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
_DOMAIN_SOURCE_TYPE_MAP = {
    "abebooks.com": "retail",
    "alibris.com": "retail",
    "amazon.com": "retail",
    "amazon.com.au": "retail",
    "amazon.co.jp": "retail",
    "amazon.co.uk": "retail",
    "amazon.de": "retail",
    "amazon.fr": "retail",
    "amazon.in": "retail",
    "amazon.it": "retail",
    "barnesandnoble.com": "retail",
    "ebay.com": "retail",
    "facebook.com": "social_media",
    "instagram.com": "social_media",
    "linkedin.com": "social_media",
    "pinterest.com": "social_media",
    "reddit.com": "forum",
    "scribd.com": "ugc_aggregator",
    "tiktok.com": "social_media",
    "twitter.com": "social_media",
    "x.com": "social_media",
}


def _normalize_domain(domain: str) -> str:
    """Normalize a domain string for deny-list checks."""
    return (domain or "").strip().lower().lstrip(".")


def _url_domain(url: str) -> str:
    """Extract a normalized domain from a URL."""
    return _normalize_domain(urlparse(url or "").netloc)


def _is_blocked_url(
    url: str,
    blocked_domains: Optional[list[str]] = None,
    blocked_urls: Optional[list[str]] = None,
) -> bool:
    """Return whether one URL is blocked by exact-URL or domain rule."""
    if not url:
        return False
    if url in {item for item in (blocked_urls or []) if item}:
        return True
    domain = _url_domain(url)
    for blocked in (_normalize_domain(item) for item in (blocked_domains or [])):
        if blocked and (domain == blocked or domain.endswith(f".{blocked}")):
            return True
    return False


def _filter_blocked_results(
    results: list[dict],
    blocked_domains: Optional[list[str]] = None,
    blocked_urls: Optional[list[str]] = None,
    blocked_source_types: Optional[list[str]] = None,
) -> list[dict]:
    """Drop search results that violate explicit user constraints."""
    blocked_types = {
        str(item).strip().lower() for item in (blocked_source_types or []) if item
    }
    filtered: list[dict] = []
    for item in results:
        url = str(item.get("url") or "")
        if _is_blocked_url(
            url,
            blocked_domains=blocked_domains,
            blocked_urls=blocked_urls,
        ):
            continue
        domain = _url_domain(url)
        inferred_type = next(
            (
                source_type
                for blocked_domain, source_type in _DOMAIN_SOURCE_TYPE_MAP.items()
                if domain == blocked_domain or domain.endswith(f".{blocked_domain}")
            ),
            None,
        )
        if inferred_type and inferred_type in blocked_types:
            continue
        filtered.append(item)
    return filtered


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
    blocked_domains: Optional[list[str]] = None,
    blocked_urls: Optional[list[str]] = None,
    blocked_source_types: Optional[list[str]] = None,
) -> dict:
    """Run a web search via Serper.dev (Google Search API). This is the default search tool.

    Args:
        query: The search query.
        max_results: Maximum number of results to return.
        topic: Search topic — ``general`` or ``news`` (``finance`` falls back to
            general; Serper has no dedicated finance endpoint).
        include_raw_content: Accepted for interface parity with ``tavily_search``;
            Serper returns snippets, not full page text, so this is ignored.
        blocked_domains: Optional domain deny-list applied after search.
        blocked_urls: Optional exact URL deny-list applied after search.
        blocked_source_types: Optional source-type deny-list applied after search.

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
        results = _filter_blocked_results(
            results,
            blocked_domains=blocked_domains,
            blocked_urls=blocked_urls,
            blocked_source_types=blocked_source_types,
        )
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
    blocked_domains: Optional[list[str]] = None,
    blocked_urls: Optional[list[str]] = None,
    blocked_source_types: Optional[list[str]] = None,
) -> dict:
    """Run a web search via Tavily.

    Args:
        query: The search query.
        max_results: Maximum number of results to return.
        topic: Search topic — ``general``, ``news`` or ``finance``.
        include_raw_content: Whether to include the full page text of results.
        blocked_domains: Optional domain deny-list applied after search.
        blocked_urls: Optional exact URL deny-list applied after search.
        blocked_source_types: Optional source-type deny-list applied after search.

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
        if isinstance(response, dict):
            response["results"] = _filter_blocked_results(
                response.get("results") or [],
                blocked_domains=blocked_domains,
                blocked_urls=blocked_urls,
                blocked_source_types=blocked_source_types,
            )
        return response
    except Exception as e:  # noqa: BLE001 — surface any search failure as data, not a crash
        return {
            "error": f"{type(e).__name__}: {e}",
            "query": query,
            "results": [],
            "note": "Search request failed (see error for the exact cause). Try the alternate engine, adjust the query, or proceed with evidence already collected.",
        }
