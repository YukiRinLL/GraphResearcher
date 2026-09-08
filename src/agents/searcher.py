"""使用确定性 LangGraph 管线完成 Tavily 正文搜索、逐来源抽取和证据入图.

管线顺序固定为：

    init -> web_search -> extract_evidence_package -> submit

Orchestrator 通过 ``dispatch_searcher`` 注入 ``query_id``、``search_run_id``
和 ``query_text``。搜索节点直接调用 Tavily，只有带 ``raw_content`` 的来源才会进入 analyzer。
"""

import json
import logging
import re
from typing import Annotated, Any, Optional, TypedDict
from urllib.parse import urlsplit

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

import config
from memory import source_snapshots
from memory.source_snapshots import canonicalize_source_url as _canonicalize_url
from tools.graph_manager_tools import submit_search_result
from tools.search_tools import tavily_search

logger = logging.getLogger(__name__)


class SearcherState(TypedDict):
    """保存单次 Searcher 运行的状态."""

    messages: Annotated[list, add_messages]
    query_id: str
    search_run_id: str
    query_text: str
    query_role: str
    acceptance_criteria: list[str]
    research_context: dict[str, Any]
    source_preferences: list[str]
    search_mode: str
    search_results: Optional[dict]
    search_output: str
    evidence_package: Optional[dict]
    submit_result: Optional[dict]


_QID_RE = re.compile(r"(?:query_id|Query ID|queryId|qid|id)[=:]\s*([a-f0-9_]+)", re.IGNORECASE)
_MAX_DEBUG_SEARCH_OUTPUT_CHARS = 30_000
_MAX_SOURCE_RAW_CHARS = 20_000
_DEFAULT_MAX_RESULTS = 5
_VALID_SEARCH_MODES = {
    "general", "news", "finance", "linkedin", "github", "academic"
}


def _mode_search_params(mode: str) -> tuple[str, Optional[list[str]], Optional[str]]:
    """Map a search_mode to (topic, include_domains, search_depth).

    - general / news / finance: pass through as the Tavily ``topic`` parameter,
      no domain restriction, no explicit depth.
    - linkedin / github / academic: force ``topic='general'`` (Tavily's news /
      finance topics are incompatible with domain-restricted profile search and
      would over-constrain results), and apply the profile's include_domains.
    - academic additionally enables ``search_depth='advanced'`` per the project
      decision that scholarly retrieval benefits from the deeper index.

    Returns ``("general", None, None)`` for any unknown mode so callers stay
    safe against LLM-emitted invalid values.
    """
    from tools.search_tools import _PROFILE_INCLUDE_DOMAINS

    if mode in ("general", "news", "finance"):
        return mode, None, None
    if mode == "academic":
        return "general", list(_PROFILE_INCLUDE_DOMAINS["academic"]), "advanced"
    if mode in ("linkedin", "github"):
        return "general", list(_PROFILE_INCLUDE_DOMAINS[mode]), None
    return "general", None, None


def _normalize_domain_pref(value: str) -> Optional[str]:
    """Normalize a ``source_preferences`` entry to a bare include-domain.

    Handles ``+site:domain`` and bare-domain forms (e.g. ``"linkedin.com"``,
    ``"+site:github.com"``). ``-site:`` entries are dropped here because they
    are routed through ``excluded_domains`` by ``prepare_search`` rather than
    through ``include_domains``.

    Non-domain category descriptions (e.g. ``"official sources"``,
    ``"academic journals"``) are rejected by requiring at least one dot and no
    whitespace — this prevents free-text preference labels from being
    misinterpreted as Tavily host constraints.
    """
    text = str(value or "").strip().lower()
    if not text or text.startswith("-site:"):
        return None
    if text.startswith("+site:"):
        text = text[6:]
    if "://" in text:
        text = urlsplit(text).hostname or ""
    text = text.strip("./")
    if not text or " " in text or "." not in text:
        return None
    return text


def _empty_package() -> dict:
    """返回一份相互独立的空 evidence_package."""
    return {
        "sources": [],
        "documents": [],
        "statements": [],
        "evidence": [],
        "conflicts": [],
        "extraction_log": [],
    }


def _empty_source_packet() -> dict:
    """返回一份相互独立的空单来源抽取结果."""
    return {
        "source": {},
        "document": {},
        "statements": [],
        "evidence": [],
        "conflicts": [],
    }


def init_node(state: SearcherState) -> dict:
    """优先使用结构化注入的 Query 标识和文本，并兼容旧的消息解析路径."""
    query_id = state.get("query_id")
    query_text = state.get("query_text")
    if query_id and query_id != "unknown" and query_text:
        return {"query_id": query_id, "query_text": query_text}

    last = state["messages"][-1]
    content = last.content if hasattr(last, "content") else str(last)
    match = _QID_RE.search(content)
    query_id = match.group(1) if match else "unknown"
    query_text = re.sub(r"\s+", " ", _QID_RE.sub("", content)).strip()
    for lead_in in ("围绕", "检索", "搜索", "的问题检索", "的检索", "任务"):
        for separator in ("：", ":", " "):
            prefix = lead_in + separator
            while query_text.startswith(prefix):
                query_text = query_text[len(prefix):].strip()
    return {"query_id": query_id, "query_text": query_text.lstrip("：:").strip()}


def _normalize_search_result(item: dict[str, Any]) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """规范化一条 Tavily 结果，并返回丢弃原因."""
    url = _canonicalize_url(item.get("url"))
    if url is None:
        return None, "without_url"
    raw_content = item.get("raw_content")
    if not isinstance(raw_content, str) or not raw_content.strip():
        return None, "without_raw_content"
    raw_content_truncated = bool(item.get("raw_content_truncated")) or len(raw_content) > _MAX_SOURCE_RAW_CHARS
    return {
        "url": url,
        "title": item.get("title"),
        "content": item.get("content"),
        "raw_content": raw_content[:_MAX_SOURCE_RAW_CHARS],
        "raw_content_truncated": raw_content_truncated,
        "score": item.get("score"),
        "published_at": item.get("published_at") or item.get("published_date") or item.get("date"),
        **({"source_snapshot": item["source_snapshot"]} if isinstance(item.get("source_snapshot"), dict) else {}),
    }, None


def _compact_search_output(search_results: dict) -> str:
    """构造不包含网页正文的搜索调试摘要."""
    compact = {
        "query": search_results.get("query"),
        "error": search_results.get("error"),
        "kept_results": [
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "content": item.get("content"),
                "raw_content_chars": len(item.get("raw_content") or ""),
                "raw_content_truncated": bool(item.get("raw_content_truncated")),
                "published_at": item.get("published_at"),
                "score": item.get("score"),
            }
            for item in search_results.get("results", []) or []
        ],
        "dropped_without_url": search_results.get("dropped_without_url", 0),
        "dropped_without_raw_content": search_results.get("dropped_without_raw_content", 0),
        "dropped_duplicates": search_results.get("dropped_duplicates", 0),
        "dropped_invalid_results": search_results.get("dropped_invalid_results", 0),
    }
    text = json.dumps(compact, ensure_ascii=False)
    if len(text) > _MAX_DEBUG_SEARCH_OUTPUT_CHARS:
        return text[:_MAX_DEBUG_SEARCH_OUTPUT_CHARS] + "...(truncated)"
    return text


_TAVILY_SEARCH = getattr(tavily_search, "func", tavily_search)

_QUERY_WRAP_QUOTE_RE = re.compile(r'^["\'\u201c\u201d\u2018\u2019]+|["\'\u201c\u201d\u2018\u2019]+$')
_QUERY_SCAFFOLD_RE = re.compile(r'\b(?:query|search|find|look up)\s*[:\uff1a]\s*', re.IGNORECASE)
_QUERY_QID_PREFIX_RE = re.compile(r'\bq\d+\s*[:\uff1a]\s*', re.IGNORECASE)


def _sanitize_query_text(text: str) -> str:
    """Normalize a query string before passing it to Tavily.

    Strips wrapping quotes, collapses whitespace, and removes scaffolding
    tokens (e.g. ``query:`` prefixes) that LLM-authored queries sometimes
    carry. Returns the cleaned text; never returns empty if input had content.
    """
    if not isinstance(text, str):
        return ""
    cleaned = text.strip()
    cleaned = _QUERY_WRAP_QUOTE_RE.sub('', cleaned)
    cleaned = _QUERY_SCAFFOLD_RE.sub('', cleaned)
    cleaned = _QUERY_QID_PREFIX_RE.sub('', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def web_search_node(state: SearcherState) -> dict:
    """执行一次 Tavily 搜索，按 search_mode 路由参数并去重.

    按 ``state['search_mode']`` 映射到 Tavily 的 ``topic`` /
    ``include_domains`` / ``search_depth``，调用 Tavily 搜索，并只保留唯一
    且带正文（``raw_content`` + ``url``）的来源结果。

    Args:
        state: 单次搜索状态，至少包含 ``query_text``。
    """
    raw_query = state["query_text"]
    cleaned_query = _sanitize_query_text(raw_query)
    mode = state.get("search_mode") or "general"
    if mode not in _VALID_SEARCH_MODES:
        mode = "general"
    topic, include_domains, search_depth = _mode_search_params(mode)

    # 用户硬约束优先：source_preferences 里的 +site: 或裸域名覆盖 mode 的
    # include_domains，避免 per-query mode 与用户 goal 级硬约束冲突。
    user_prefs = state.get("source_preferences") or []
    user_domains = [
        d for d in (_normalize_domain_pref(p) for p in user_prefs) if d
    ]
    if user_domains:
        include_domains = user_domains
        search_depth = None  # 用户硬约束不强制 advanced

    # Explicit routing trace so we can tell at a glance whether the LLM
    # actually surfaced search_mode=academic (etc.) instead of silently
    # defaulting to general on every call. One INFO row per search attempt.
    logger.info(
        "web_search_node: handle=%s mode=%s topic=%s include_domains=%s search_depth=%s",
        state.get("handle"),
        mode,
        topic,
        include_domains,
        search_depth,
    )

    call_kwargs = {
        "query": cleaned_query,
        "max_results": _DEFAULT_MAX_RESULTS,
        "topic": topic,
    }
    if include_domains:
        call_kwargs["include_domains"] = include_domains
    if search_depth:
        call_kwargs["search_depth"] = search_depth
    with source_snapshots.search_capture_scope(state.get("query_id"), state.get("search_run_id")):
        result = _TAVILY_SEARCH(**call_kwargs)
    if not isinstance(result, dict):
        result = {
            "error": "tavily_search returned a non-dict response",
            "query": cleaned_query,
            "results": [],
        }

    # Empty-result sanitization retry: if the first call returned no usable
    # results AND removing all internal quotes yields a different query,
    # retry once with the aggressively-cleaned variant. The retry keeps the
    # same topic / include_domains / search_depth because it is a query-text
    # wash (strip quotes), not a strategy retreat — dropping the profile
    # constraints would silently drift the search behavior and make run.log
    # attribution harder.
    kept_check = result.get("results") or []
    if not kept_check and cleaned_query:
        aggressive = re.sub(r'["\']', '', cleaned_query).strip()
        aggressive = re.sub(r'\s+', ' ', aggressive).strip()
        if aggressive and aggressive != cleaned_query:
            retry_kwargs = dict(call_kwargs, query=aggressive)
            with source_snapshots.search_capture_scope(state.get("query_id"), state.get("search_run_id")):
                retry = _TAVILY_SEARCH(**retry_kwargs)
            if isinstance(retry, dict) and (retry.get("results") or []):
                result = retry
                cleaned_query = aggressive

    kept: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    dropped_without_url = 0
    dropped_without_raw_content = 0
    dropped_duplicates = 0
    dropped_invalid_results = 0
    for item in result.get("results", []) or []:
        if not isinstance(item, dict):
            dropped_invalid_results += 1
            continue
        normalized, reason = _normalize_search_result(item)
        if reason == "without_url":
            dropped_without_url += 1
            continue
        if reason == "without_raw_content":
            dropped_without_raw_content += 1
            continue
        if normalized["url"] in seen_urls:
            dropped_duplicates += 1
            continue
        seen_urls.add(normalized["url"])
        kept.append(normalized)

    structured = {
        "query": result.get("query") or cleaned_query,
        "error": result.get("error"),
        "results": kept,
        "dropped_without_url": dropped_without_url,
        "dropped_without_raw_content": dropped_without_raw_content,
        "dropped_duplicates": dropped_duplicates,
        "dropped_invalid_results": dropped_invalid_results,
        "request_id": result.get("request_id"),
        "response_time": result.get("response_time"),
    }
    search_output = _compact_search_output(structured)
    return {
        "search_results": structured,
        "search_output": search_output,
        "messages": [AIMessage(content=search_output)],
    }


def _parse_source_packet(text: str) -> dict:
    """从模型文本中解析一个 source packet，失败时返回空 packet."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        data = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        match = re.search(r"\{.*\}", stripped, re.DOTALL)
        if not match:
            return _empty_source_packet()
        try:
            data = json.loads(match.group(0))
        except (json.JSONDecodeError, ValueError):
            return _empty_source_packet()
    if not isinstance(data, dict):
        return _empty_source_packet()
    packet = _empty_source_packet()
    packet["source"] = data.get("source") if isinstance(data.get("source"), dict) else {}
    packet["document"] = data.get("document") if isinstance(data.get("document"), dict) else {}
    for key in ("statements", "evidence", "conflicts"):
        packet[key] = data.get(key) if isinstance(data.get(key), list) else []
    return packet


def _extract_source_packet(
    query: dict[str, Any],
    research_context: dict[str, Any],
    source: dict[str, Any],
) -> dict:
    """对单个带正文来源执行一次 analyzer 抽取."""
    analyzer_input = {
        "query": query,
        "research_context": research_context,
        "source": {
            "title": source.get("title"),
            "url": source.get("url"),
            "raw_content": (source.get("raw_content") or "")[:_MAX_SOURCE_RAW_CHARS],
            "raw_content_truncated": bool(source.get("raw_content_truncated")),
            "published_at": source.get("published_at"),
        },
    }
    response = config.searcher_model.invoke([
        SystemMessage(content=config.analyzer_system_prompt),
        HumanMessage(content=json.dumps(analyzer_input, ensure_ascii=False)),
    ])
    text = response.content if hasattr(response, "content") else str(response)
    return _parse_source_packet(text)


def _nonempty_items(items: object, field: str = "text") -> list[dict]:
    """保留指定文本字段非空的字典项."""
    if not isinstance(items, list):
        return []
    return [
        item
        for item in items
        if isinstance(item, dict) and str(item.get(field) or "").strip()
    ]


LOGIN_WALL_HINTS = (
    "sign in", "sign up", "log in", "login", "register", "create an account",
    "access through your institution", "continue with google", "continue with orcid",
    "enjoying our latest content", "access the most recent journalism",
    "marc record", "library catalog record", "catalog record",
    "borrow", "viewability", "full text unavailable", "limited preview",
    "subscribe", "subscription required", "buy now", "unlock",
)

# NOTE: "rights and permissions" and "bibliographic information" were removed from
# LOGIN_WALL_HINTS. Both are normal phrases on scholarly publisher pages (Cambridge
# Core, journal sites) and caused legitimate article pages to be flagged as login
# walls when the Tavily snippet was short. Catalog-card signal phrases ("marc record",
# "library catalog record", "catalog record", "viewability", "borrow") are kept so
# HathiTrust catalog cards accumulate hits>=3 and are forwarded to the analyzer.

CATALOG_BOOLEAN_HINTS = (
    "catalog.hathitrust.org", "worldcat.org", "librarything.com", "goodreads.com",
)


def _looks_like_login_wall_or_catalog(source: dict, raw_content: str) -> bool:
    """Heuristic: flag sources whose body is dominated by login-wall / catalog boilerplate.

    Catalog domains and short pages are NO LONGER hard-rejected here. They are forwarded
    to the analyzer; sources that fail extraction are still registered as source nodes
    (without evidence) by _merge_source_packets. Only pages with login-wall boilerplate
    and too little extractable body text are flagged, so the caller can skip the strict
    statement/evidence binding path and fall back to source-only registration.
    """
    text = (raw_content or "").lower()
    if not text:
        return True
    hits = sum(1 for hint in LOGIN_WALL_HINTS if hint in text)
    if hits >= 3:
        return False
    if hits == 2 and len(text) < 1200:
        return True
    if hits == 1 and len(text) < 700:
        return True
    if hits == 0 and len(text) < 400:
        return True
    return False


_SCHOLAR_WIKI_RE = re.compile(
    r'https?://(?:en\.)?wikipedia\.org/wiki/([^)\s"\']+_(?:[A-Z][a-z]+(?:_[A-Z][a-z]+)+))',
    re.IGNORECASE,
)
_WIKI_GENERAL_RE = re.compile(
    r'https?://(?:en\.)?wikipedia\.org/wiki/([^)\s"\']+)',
    re.IGNORECASE,
)


def _extract_scholar_wiki_links(raw_content: str) -> list[dict[str, str]]:
    """Extract Wikipedia links for scholar-like names from raw content.

    Matches patterns like /wiki/Arthur_Evans, /wiki/Martin_P._Nilsson, etc.
    Returns list of {url, title} dicts for scholar Wikipedia pages.
    """
    if not raw_content:
        return []
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in _SCHOLAR_WIKI_RE.finditer(raw_content):
        slug = match.group(1)
        url = f"https://en.wikipedia.org/wiki/{slug}"
        if url in seen:
            continue
        seen.add(url)
        title = slug.replace("_", " ")
        found.append({"url": url, "title": title, "source_type": "scholar_wiki"})
    return found


def _merge_source_packets(search_results: dict, packets: list[dict]) -> dict:
    """把有效的单来源 packet 合并为现有 evidence_package shape."""
    package = _empty_package()
    statement_counter = 0
    evidence_counter = 0
    scholar_sources: list[dict[str, str]] = []

    for source, packet in zip(search_results.get("results", []) or [], packets):
        if not isinstance(source, dict) or not isinstance(packet, dict):
            continue
        src_url = source.get("url") or ""
        src_title = (source.get("title") or "")[:80]
        raw_content = str(source.get("content") or source.get("raw_content") or "")
        if _looks_like_login_wall_or_catalog(source, raw_content):
            package["extraction_log"].append({
                "url": src_url, "title": src_title,
                "stage": "B_login_wall", "reason": "login-wall/catalog boilerplate or too short",
            })
            continue

        scholar_links = _extract_scholar_wiki_links(raw_content)
        for sl in scholar_links:
            if sl["url"] not in {s["url"] for s in scholar_sources}:
                scholar_sources.append(sl)

        document = packet.get("document") if isinstance(packet.get("document"), dict) else {}
        summary = str(document.get("document_summary") or "").strip()
        # 关卡C：只有 analyzer 完全无法生成来源概述时才丢弃。
        # 有 summary 但缺 statements/evidence 的来源仍注册为可引用来源
        # （带 document_summary），只是不写结构化命题绑定。
        if not summary:
            package["extraction_log"].append({
                "url": src_url, "title": src_title,
                "stage": "C_no_summary", "reason": "analyzer returned empty packet (no document_summary)",
            })
            continue
        if packet.get("conflicts"):
            package["extraction_log"].append({
                "url": src_url, "title": src_title,
                "stage": "C_conflicts", "reason": "analyzer flagged conflicts in packet",
            })
            continue

        # 先注册 source + document（基于 analyzer 的来源概述）
        source_ref = f"s{len(package['sources']) + 1}"
        document_ref = f"d{len(package['documents']) + 1}"
        source_meta = packet.get("source") if isinstance(packet.get("source"), dict) else {}
        package["sources"].append({
            "local_ref": source_ref,
            "url": source.get("url"),
            "title": source.get("title"),
            "source_type": source_meta.get("source_type") or "other",
            "published_at": source_meta.get("published_at") or source.get("published_at"),
        })
        package["documents"].append({
            "local_ref": document_ref,
            "document_summary": summary,
            "source_ref": source_ref,
        })

        statements = _nonempty_items(packet.get("statements"))
        evidence_items = _nonempty_items(packet.get("evidence"))
        # 无完整 statement-evidence 绑定时，source+document 已注册，跳过绑定阶段
        if not statements or not evidence_items:
            package["extraction_log"].append({
                "url": src_url, "title": src_title,
                "stage": "registered_source_only", "reason": "has summary but missing statements/evidence",
            })
            continue

        # 关卡D：local_ref / statement_refs 格式校验；失败则跳过绑定，保留 source+document
        statement_local_refs = [str(item.get("local_ref") or "").strip() for item in statements]
        evidence_local_refs = [str(item.get("local_ref") or "").strip() for item in evidence_items]
        if (
            any(not ref for ref in statement_local_refs + evidence_local_refs)
            or len(set(statement_local_refs)) != len(statement_local_refs)
            or len(set(evidence_local_refs)) != len(evidence_local_refs)
        ):
            package["extraction_log"].append({
                "url": src_url, "title": src_title,
                "stage": "D_format_invalid", "reason": "local_ref missing/duplicate",
            })
            continue
        statement_ref_set = set(statement_local_refs)
        raw_evidence_statement_refs = [item.get("statement_refs") for item in evidence_items]
        if any(not isinstance(refs, list) for refs in raw_evidence_statement_refs):
            package["extraction_log"].append({
                "url": src_url, "title": src_title,
                "stage": "D_format_invalid", "reason": "statement_refs not a list",
            })
            continue
        evidence_statement_refs = [
            [str(ref).strip() for ref in refs if str(ref).strip()]
            for refs in raw_evidence_statement_refs
        ]
        if (
            any(not refs or any(ref not in statement_ref_set for ref in refs) for refs in evidence_statement_refs)
            or set(ref for refs in evidence_statement_refs for ref in refs) != statement_ref_set
        ):
            package["extraction_log"].append({
                "url": src_url, "title": src_title,
                "stage": "D_format_invalid", "reason": "statement_refs mismatch",
            })
            continue

        local_statement_map: dict[str, str] = {}
        for statement, local_ref in zip(statements, statement_local_refs):
            statement_counter += 1
            global_ref = f"st{statement_counter}"
            local_statement_map[local_ref] = global_ref
            package["statements"].append({
                "local_ref": global_ref,
                "text": str(statement.get("text") or "").strip(),
                "document_ref": document_ref,
                "source_ref": source_ref,
            })

        for evidence, statement_refs in zip(evidence_items, evidence_statement_refs):
            evidence_counter += 1
            global_ref = f"e{evidence_counter}"
            package["evidence"].append({
                "local_ref": global_ref,
                "text": str(evidence.get("text") or "").strip(),
                "document_ref": document_ref,
                "source_ref": source_ref,
                "statement_refs": [local_statement_map[ref] for ref in statement_refs],
            })
        package["extraction_log"].append({
            "url": src_url, "title": src_title,
            "stage": "binding_ok", "reason": f"statements={len(statements)} evidence={len(evidence_items)}",
        })

    for scholar in scholar_sources:
        scholar_ref = f"s{len(package['sources']) + 1}"
        document_ref = f"d{len(package['documents']) + 1}"
        package["sources"].append({
            "local_ref": scholar_ref,
            "url": scholar["url"],
            "title": scholar["title"],
            "source_type": "scholar_wiki",
            "published_at": None,
        })
        package["documents"].append({
            "local_ref": document_ref,
            "document_summary": f"Scholar Wikipedia page: {scholar['title']}",
            "source_ref": scholar_ref,
        })

    return package


def extract_evidence_package_node(state: SearcherState) -> dict:
    """逐个抽取保留来源，并合并为 evidence_package."""
    search_results = state.get("search_results") or {}
    sources = search_results.get("results") or []
    if not isinstance(sources, list) or not sources:
        return {
            "evidence_package": _empty_package(),
            "messages": [AIMessage(content="未保留任何带 raw_content 的来源。")],
        }
    query = {
        "text": state["query_text"],
        "role": state.get("query_role") or "evidence_gap",
        "acceptance_criteria": state.get("acceptance_criteria") or [],
    }
    research_context = state.get("research_context") or {
        "research_goal": "",
        "time_window": None,
        "region_scope": None,
    }
    packets = [
        _extract_source_packet(query, research_context, source)
        for source in sources
        if isinstance(source, dict)
    ]
    package = _merge_source_packets(search_results, packets)
    # Summarize extraction log per stage for quick diagnosis
    log_entries = package.get("extraction_log") or []
    stage_counts: dict[str, int] = {}
    for entry in log_entries:
        stage = entry.get("stage") or "unknown"
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
    summary = {
        "searched_sources": len(sources),
        "accepted_sources": len(package["sources"]),
        "extraction_stages": stage_counts,
    }
    return {
        "evidence_package": package,
        "messages": [AIMessage(content=json.dumps(summary, ensure_ascii=False))],
    }


def submit_node(state: SearcherState) -> dict:
    """把 evidence_package 写入既有 SearchRun，并沿用现有状态迁移."""
    package = state.get("evidence_package") or _empty_package()
    if not isinstance(package, dict):
        package = _empty_package()
    result = submit_search_result.invoke({
        "search_run_id": state["search_run_id"],
        "query_id": state["query_id"],
        "evidence_package": package,
    })
    return {
        "submit_result": result,
        "messages": [AIMessage(content=json.dumps(result, ensure_ascii=False))],
    }


def _build_graph() -> StateGraph:
    """构建确定性的 Searcher 状态图."""
    graph = StateGraph(SearcherState)
    graph.add_node("init", init_node)
    graph.add_node("web_search", web_search_node)
    graph.add_node("extract_evidence_package", extract_evidence_package_node)
    graph.add_node("submit", submit_node)
    graph.add_edge("init", "web_search")
    graph.add_edge("web_search", "extract_evidence_package")
    graph.add_edge("extract_evidence_package", "submit")
    graph.add_edge("submit", END)
    graph.set_entry_point("init")
    return graph


searcher = _build_graph().compile()
