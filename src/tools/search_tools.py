"""Search and web content retrieval tools."""

import logging
import os
from typing import Literal

from tavily import TavilyClient

logger = logging.getLogger(__name__)

_tavily_client: "TavilyClient | None" = None


def _get_client() -> "TavilyClient":
    global _tavily_client
    if _tavily_client is None:
        api_key = os.environ.get("TAVILY_API_KEY", "")
        if not api_key:
            raise RuntimeError("TAVILY_API_KEY environment variable is not set")
        _tavily_client = TavilyClient(api_key=api_key)
    return _tavily_client


def tavily_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
    include_raw_content: bool = False,
) -> dict:
    """Run a web search via Tavily and return structured results."""
    return _get_client().search(
        query,
        max_results=max_results,
        include_raw_content=include_raw_content,
        topic=topic,
    )


def fetch_page_content(url: str) -> dict:
    """Fetch the full text content of a specific URL via Tavily extract.

    Returns:
        {url, title, text, error}
    """
    try:
        result = _get_client().extract(urls=[url])
        if result and result.get("results"):
            r = result["results"][0]
            return {
                "url": url,
                "title": r.get("title", ""),
                "text": r.get("raw_content", ""),
                "error": None,
            }
        return {"url": url, "title": "", "text": "", "error": "No content returned by Tavily extract"}
    except Exception as exc:
        logger.warning("fetch_page_content failed for %s: %s", url, exc)
        return {"url": url, "title": "", "text": "", "error": str(exc)}
