"""为 Searcher 提供仅基于 Tavily 的网页正文搜索工具."""

import os
from typing import Literal, Optional

from langchain_core.tools import tool
from tavily import TavilyClient

_tavily_client: Optional[TavilyClient] = None

# 单条正文的上限既约束工具返回，也保护后续逐来源抽取的上下文。
_MAX_RAW_CONTENT_CHARS = 20_000
SEARCH_TIMEOUT = float(os.environ.get("SEARCH_TIMEOUT", "30"))

# Search profile domain whitelists. Live in code only — never exposed via
# prompts or tool docstrings, so the LLM never sees concrete platform names
# leaking into its decision context.
_LINKEDIN_INCLUDE_DOMAINS = ["linkedin.com"]
_GITHUB_INCLUDE_DOMAINS = ["github.com"]
_ACADEMIC_INCLUDE_DOMAINS = [
    "arxiv.org",
    "scholar.google.com",
    "researchgate.net",
    "semanticscholar.org",
    "acm.org",
    "ieee.org",
    "sciencedirect.com",
    "nature.com",
    "science.org",
    "springer.com",
    "wiley.com",
    "jstor.org",
    "ncbi.nlm.nih.gov",
    "pubmed.gov",
    "academia.edu",
    "biorxiv.org",
    "crossref.org",
]
_PROFILE_INCLUDE_DOMAINS: dict[str, list[str]] = {
    "linkedin": _LINKEDIN_INCLUDE_DOMAINS,
    "github": _GITHUB_INCLUDE_DOMAINS,
    "academic": _ACADEMIC_INCLUDE_DOMAINS,
}


def _client() -> TavilyClient:
    """按需创建并复用 Tavily 客户端."""
    global _tavily_client
    if _tavily_client is None:
        _tavily_client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    return _tavily_client


@tool
def tavily_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
    search_depth: Optional[Literal["basic", "advanced"]] = None,
    include_domains: Optional[list[str]] = None,
    exclude_domains: Optional[list[str]] = None,
) -> dict:
    """使用 Tavily 搜索网页，并强制返回可用于证据抽取的正文.

    Args:
        query: 搜索查询。
        max_results: 最多返回的结果数。
        topic: 搜索主题，可取 ``general``、``news`` 或 ``finance``。
        search_depth: 可选的 Tavily 深度（``basic`` 或 ``advanced``）；
            为 None 时使用 Tavily 默认值。
        include_domains: 可选的主机名列表，将搜索范围限定在这些域名内；
            为 None 时不施加域名约束。
        exclude_domains: 可选的主机名列表，从搜索结果中排除这些域名；
            为 None 时不施加排除约束。
    Returns:
        Tavily 搜索响应。失败时返回包含 ``error`` 和空 ``results`` 的字典，
        让现有 SearchRun 生命周期把本轮作为空结果处理。
    """
    try:
        search_kwargs = {
            "max_results": max_results,
            "include_raw_content": True,
            "topic": topic,
            "timeout": SEARCH_TIMEOUT,
        }
        if search_depth:
            search_kwargs["search_depth"] = search_depth
        if include_domains:
            search_kwargs["include_domains"] = list(include_domains)
        if exclude_domains:
            search_kwargs["exclude_domains"] = list(exclude_domains)
        response = _client().search(query, **search_kwargs)
        if isinstance(response, dict):
            for item in response.get("results", []) or []:
                if not isinstance(item, dict):
                    continue
                raw_content = item.get("raw_content")
                if isinstance(raw_content, str) and len(raw_content) > _MAX_RAW_CONTENT_CHARS:
                    item["raw_content"] = raw_content[:_MAX_RAW_CONTENT_CHARS] + "...(truncated)"
        return response
    except Exception as exc:  # noqa: BLE001 - 搜索失败应进入现有空结果状态机，而不是中断整次运行。
        return {
            "error": f"{type(exc).__name__}: {exc}",
            "query": query,
            "results": [],
            "note": "Tavily search failed. Adjust the query or continue with evidence already collected.",
        }
