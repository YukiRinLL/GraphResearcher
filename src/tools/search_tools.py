"""Web search tools for the Searcher agent.

Exposes two web-search tools: `serper_search` (Serper.dev, the default) and
`tavily_search` (Tavily, alternative). Clients are created lazily so importing
this module does not require any API key until a search actually runs.
"""

import os
import re
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
_SITE_EXCLUSION_RE = re.compile(r"-site:([A-Za-z0-9.-]+\.[A-Za-z]{2,})", re.IGNORECASE)
_DEPRIORITIZED_DOMAINS = {
    "academia.edu",
    "facebook.com",
    "instagram.com",
    "pinterest.com",
    "reddit.com",
    "researchgate.net",
    "scribd.com",
    "youtube.com",
}
_PREFERRED_DOMAIN_TOKENS = (
    "ashmolean.org",
    "cambridge.org",
    "heidelberg.de",
    "jstor.org",
    "museum",
    "ox.ac.uk",
    "uchicago.edu",
)


def _excluded_domains_from_query(query: str) -> list[str]:
    """Parse domain exclusions already embedded in the literal query text."""
    domains: list[str] = []
    for match in _SITE_EXCLUSION_RE.finditer(str(query or "")):
        domain = match.group(1).lower().strip().lstrip(".")
        if domain and domain not in domains:
            domains.append(domain)
    return domains


def _host(url: str) -> str:
    """Return the lowercase hostname for a URL-like string."""
    try:
        return (urlparse(url).netloc or "").lower().lstrip(".")
    except Exception:  # noqa: BLE001 - a malformed URL should simply skip filtering
        return ""


def _is_excluded_result(url: str, excluded_domains: list[str]) -> bool:
    """Return whether the URL falls under any excluded domain."""
    host = _host(url)
    if not host:
        return False
    return any(host == domain or host.endswith(f".{domain}") for domain in excluded_domains)


def _filter_excluded_results(query: str, results: list[dict]) -> list[dict]:
    """Drop results whose domains contradict explicit ``-site:...`` query terms."""
    excluded_domains = _excluded_domains_from_query(query)
    if not excluded_domains:
        return results
    return [
        item for item in results
        if not _is_excluded_result(str(item.get("url") or ""), excluded_domains)
    ]


def _result_quality_score(item: dict) -> int:
    """Prefer institutional/academic pages over social reposts and gateways."""
    url = str(item.get("url") or "")
    host = _host(url).lstrip(".")
    host_no_www = host[4:] if host.startswith("www.") else host
    score = 0
    if host_no_www.endswith(".edu") or host_no_www.endswith(".ac.uk"):
        score += 3
    if any(token in host_no_www for token in _PREFERRED_DOMAIN_TOKENS):
        score += 2
    if url.lower().endswith(".pdf"):
        score += 1
    if any(host_no_www == domain or host_no_www.endswith(f".{domain}") for domain in _DEPRIORITIZED_DOMAINS):
        score -= 4
    return score


def _rerank_results(results: list[dict]) -> list[dict]:
    """Return results with better-source domains first, preserving stable ties."""
    indexed = list(enumerate(results))
    indexed.sort(key=lambda pair: (-_result_quality_score(pair[1]), pair[0]))
    return [item for _, item in indexed]


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
            json={"q": query, "num": min(20, max(max_results * 2, max_results))},
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
            for item in (items or [])
        ]
        results = _filter_excluded_results(query, results)
        results = _rerank_results(results)[:max_results]
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
        if isinstance(response, dict):
            response["results"] = _rerank_results(
                _filter_excluded_results(query, response.get("results", []) or [])
            )
        return response
    except Exception as e:  # noqa: BLE001 — surface any search failure as data, not a crash
        return {
            "error": f"{type(e).__name__}: {e}",
            "query": query,
            "results": [],
            "note": "Search request failed (see error for the exact cause). Try the alternate engine, adjust the query, or proceed with evidence already collected.",
        }
