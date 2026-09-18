"""为 Searcher 提供仅基于 Tavily 的网页正文搜索工具."""

import logging
import os
import time
from typing import Literal, Optional

from langchain_core.tools import tool
from tavily import TavilyClient

from memory import source_snapshots

logger = logging.getLogger(__name__)

_tavily_client: Optional[TavilyClient] = None

# 单条正文的上限既约束工具返回，也保护后续逐来源抽取的上下文。
_MAX_RAW_CONTENT_CHARS = 20_000
SEARCH_TIMEOUT = float(os.environ.get("SEARCH_TIMEOUT", "30"))
_TRANSIENT_SEARCH_RETRIES = 2
_TRANSIENT_SEARCH_BACKOFF_SECONDS = (1.0, 3.0)

# Search profile domain whitelists. Live in code only — never exposed via
# prompts or tool docstrings, so the LLM never sees concrete platform names
# leaking into its decision context.
_LINKEDIN_INCLUDE_DOMAINS = ["linkedin.com"]
_GITHUB_INCLUDE_DOMAINS = ["github.com"]
# Tight academic core used for the first search_mode=academic attempt. These
# domains are reliable PDF / abstract hosts and should dominate results when
# the query matches a real paper / textbook / catalog entry. Keep the list
# focused — fall back to the wide list below if the narrow try yields <=1
# documents.
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
    "medrxiv.org",
    "crossref.org",
    "doabooks.org",
    "openlibrary.org",
    "projecteuclid.org",
    "cambridge.org",
    "ox.ac.uk",
    "cam.ac.uk",
    "harvard.edu",
    "princeton.edu",
    "stanford.edu",
    "berkeley.edu",
    "britishmuseum.org",
    "metmuseum.org",
    "smithsonianmag.com",
    "si.edu",
    "getty.edu",
    "louvre.fr",
    "ashmolean.org",
    "cms-archive.org",
    "taphros.info",
    "jstor.org",
    "catalog.hathitrust.org",
    "archive.org",
    "core.ac.uk",
    "worldcat.org",
    "mdpi.com",
    "plos.org",
    "frontiersin.org",
    "pmc.ncbi.nlm.nih.gov",
    "eric.ed.gov",
    "unesdoc.unesco.org",
]
# Wide fallback domains: authoritative but not strictly journal-hosts. Used
# only when the narrow + advanced run returns <=1 effective result (i.e. the
# user actually searched a topic that legitimately lives on museum / catalog /
# university sites, not papers). We never drop to truly open search for an
# explicitly requested academic mode, so the domain list still stays inside
# reputable sources.
_ACADEMIC_WIDE_INCLUDE_DOMAINS = list({
    *_ACADEMIC_INCLUDE_DOMAINS,
    "perseus.tufts.edu",
    "penelope.uchicago.edu",
    "classics.mit.edu",
    "theoi.com",
    "encyclopedia.com",
    "britannica.com",
    "dictionary.com",
    "wikipedia.org",
})
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
    # Detect search_mode=academic invocations without changing the public
    # tool signature: an academic call is the unique case where the caller
    # passes include_domains equal to the academic whitelist AND leaves
    # topic=general / search_depth=advanced. For those we implement a
    # 3-stage cascade: (1) narrow whitelist + advanced, (2) narrow whitelist
    # + basic, (3) wide academic whitelist + basic. The caller never sees
    # anything but the final response.
    is_academic_call = (
        bool(include_domains)
        and set(include_domains) == set(_ACADEMIC_INCLUDE_DOMAINS)
        and topic == "general"
    )

    def _call(depth_override: Optional[str], domains: Optional[list[str]], stage: str = "single") -> dict:
        search_kwargs = {
            "max_results": max_results,
            "include_raw_content": True,
            "topic": topic,
            "timeout": SEARCH_TIMEOUT,
        }
        effective_depth = depth_override if depth_override is not None else search_depth
        if effective_depth:
            search_kwargs["search_depth"] = effective_depth
        if domains:
            search_kwargs["include_domains"] = list(domains)
        elif include_domains:
            search_kwargs["include_domains"] = list(include_domains)
        if exclude_domains:
            search_kwargs["exclude_domains"] = list(exclude_domains)

        for attempt in range(_TRANSIENT_SEARCH_RETRIES + 1):
            try:
                response = _client().search(query, **search_kwargs)
                break
            except Exception as exc:  # noqa: BLE001 - preserve existing empty-result behavior
                error_text = f"{type(exc).__name__}: {exc}"
                transient = any(
                    marker in error_text.lower()
                    for marker in ("429", "rate limit", "timeout", "timed out", "temporarily", "503", "502", "504")
                )
                if not transient or attempt >= _TRANSIENT_SEARCH_RETRIES:
                    return {
                        "error": error_text,
                        "query": query,
                        "results": [],
                        "note": "Tavily search failed. Adjust the query or continue with evidence already collected.",
                    }
                delay = _TRANSIENT_SEARCH_BACKOFF_SECONDS[attempt]
                logger.warning(
                    "tavily_search transient failure stage=%s attempt=%s/%s retry_in=%.1fs error=%s",
                    stage,
                    attempt + 1,
                    _TRANSIENT_SEARCH_RETRIES + 1,
                    delay,
                    error_text[:300],
                )
                time.sleep(delay)
        try:
            if isinstance(response, dict):
                items = [
                    (index, item)
                    for index, item in enumerate(response.get("results", []) or [])
                    if isinstance(item, dict)
                ]
                # 空响应也保留实际阶段记录，不改变原有级联选择和空结果语义。
                for result_index, item in items or [(None, {})]:
                    capture = source_snapshots.capture_source(
                        item,
                        query=query,
                        stage=stage,
                        search_parameters=search_kwargs,
                        response=response,
                        result_index=result_index,
                        raw_content_limit=_MAX_RAW_CONTENT_CHARS,
                    )
                    if result_index is None:
                        response["source_snapshot"] = capture
                    else:
                        item["source_snapshot"] = capture
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

    def _count_usable(resp: dict) -> int:
        if not isinstance(resp, dict):
            return 0
        count = 0
        for item in resp.get("results", []) or []:
            if not isinstance(item, dict):
                continue
            if item.get("url") and item.get("raw_content"):
                count += 1
        return count

    if not is_academic_call:
        return _call(search_depth, include_domains)

    stages = [
        ("narrow-advanced", search_depth if search_depth else "advanced", _ACADEMIC_INCLUDE_DOMAINS),
        ("narrow-basic", "basic", _ACADEMIC_INCLUDE_DOMAINS),
        ("wide-basic", "basic", _ACADEMIC_WIDE_INCLUDE_DOMAINS),
    ]
    last_response: dict = {"query": query, "results": []}
    for stage_name, depth, domains in stages:
        response = _call(depth, domains, stage_name)
        usable = _count_usable(response)
        if usable >= 2:
            if isinstance(response, dict):
                response["academic_fallback"] = {
                    "stage": stage_name,
                    "usable_results": usable,
                }
            return response
        last_response = response or last_response
        logger.warning(
            "tavily_search academic fallback: stage=%s usable=%s query=%r",
            stage_name, usable, query,
        )
    if isinstance(last_response, dict):
        last_response["academic_fallback"] = {
            "stage": "wide-basic (final)",
            "usable_results": _count_usable(last_response),
            "note": "all 3 academic stages produced <2 usable documents; returning wide-basic response",
        }
    return last_response
