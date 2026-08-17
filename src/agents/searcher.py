"""使用确定性 LangGraph 管线完成 Tavily 正文搜索、逐来源抽取和证据入图.

管线顺序固定为：

    init -> web_search -> extract_evidence_package -> submit

Orchestrator 通过 ``dispatch_searcher`` 注入 ``query_id``、``search_run_id``
和 ``query_text``。搜索节点直接调用 Tavily，只有带 ``raw_content`` 的来源才会进入 analyzer。
"""

import json
import re
from typing import Annotated, Any, Optional, TypedDict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

import config
from tools.graph_manager_tools import submit_search_result
from tools.search_tools import tavily_search


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
    search_results: Optional[dict]
    search_output: str
    evidence_package: Optional[dict]
    submit_result: Optional[dict]


_QID_RE = re.compile(r"(?:query_id|Query ID|queryId|qid|id)[=:]\s*([a-f0-9_]+)", re.IGNORECASE)
_TRACKING_QUERY_KEYS = {"gclid", "fbclid"}
_MAX_DEBUG_SEARCH_OUTPUT_CHARS = 30_000
_MAX_SOURCE_RAW_CHARS = 20_000
_DEFAULT_MAX_RESULTS = 5


def _empty_package() -> dict:
    """返回一份相互独立的空 evidence_package."""
    return {
        "sources": [],
        "documents": [],
        "statements": [],
        "evidence": [],
        "conflicts": [],
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


def _canonicalize_url(value: object) -> Optional[str]:
    """规范化 HTTP(S) URL，并移除 fragment 和常见跟踪参数."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parts = urlsplit(value.strip())
        hostname = parts.hostname
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"} or not hostname:
        return None

    netloc = parts.netloc.lower()
    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    query_items = sorted(
        (key, item_value)
        for key, item_value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_QUERY_KEYS
    )
    return urlunsplit((scheme, netloc, path, urlencode(query_items, doseq=True), ""))


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
    """固定执行一次 Tavily general 搜索，并只保留唯一且带正文的来源."""
    raw_query = state["query_text"]
    cleaned_query = _sanitize_query_text(raw_query)
    result = _TAVILY_SEARCH(
        query=cleaned_query,
        max_results=_DEFAULT_MAX_RESULTS,
        topic="general",
    )
    if not isinstance(result, dict):
        result = {
            "error": "tavily_search returned a non-dict response",
            "query": cleaned_query,
            "results": [],
        }

    # Empty-result sanitization retry: if the first call returned no usable
    # results AND removing all internal quotes yields a different query,
    # retry once with the aggressively-cleaned variant.
    kept_check = result.get("results") or []
    if not kept_check and cleaned_query:
        aggressive = re.sub(r'["\']', '', cleaned_query).strip()
        aggressive = re.sub(r'\s+', ' ', aggressive).strip()
        if aggressive and aggressive != cleaned_query:
            retry = _TAVILY_SEARCH(
                query=aggressive,
                max_results=_DEFAULT_MAX_RESULTS,
                topic="general",
            )
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
    "rights and permissions", "bibliographic information",
    "marc record", "library catalog record", "catalog record",
    "borrow", "viewability", "full text unavailable", "limited preview",
    "subscribe", "subscription required", "buy now", "unlock",
)

CATALOG_BOOLEAN_HINTS = (
    "catalog.hathitrust.org", "worldcat.org", "librarything.com", "goodreads.com",
)


def _looks_like_login_wall_or_catalog(source: dict, raw_content: str) -> bool:
    """Heuristic: reject sources with content dominated by login walls / catalog cards."""
    url = str(source.get("url") or "").lower()
    if any(domain in url for domain in CATALOG_BOOLEAN_HINTS):
        return True
    text = (raw_content or "").lower()
    if len(text) < 400:
        return True
    hits = sum(1 for hint in LOGIN_WALL_HINTS if hint in text)
    if hits >= 3:
        return False
    if hits == 2 and len(text) < 1200:
        return True
    if hits == 1 and len(text) < 700:
        return True
    return False


def _merge_source_packets(search_results: dict, packets: list[dict]) -> dict:
    """把有效的单来源 packet 合并为现有 evidence_package shape."""
    package = _empty_package()
    statement_counter = 0
    evidence_counter = 0

    for source, packet in zip(search_results.get("results", []) or [], packets):
        if not isinstance(source, dict) or not isinstance(packet, dict):
            continue
        raw_content = str(source.get("content") or source.get("raw_content") or "")
        if _looks_like_login_wall_or_catalog(source, raw_content):
            continue
        document = packet.get("document") if isinstance(packet.get("document"), dict) else {}
        summary = str(document.get("document_summary") or "").strip()
        statements = _nonempty_items(packet.get("statements"))
        evidence_items = _nonempty_items(packet.get("evidence"))
        if not summary or not statements or not evidence_items or packet.get("conflicts"):
            continue

        statement_local_refs = [str(item.get("local_ref") or "").strip() for item in statements]
        evidence_local_refs = [str(item.get("local_ref") or "").strip() for item in evidence_items]
        if (
            any(not ref for ref in statement_local_refs + evidence_local_refs)
            or len(set(statement_local_refs)) != len(statement_local_refs)
            or len(set(evidence_local_refs)) != len(evidence_local_refs)
        ):
            continue
        statement_ref_set = set(statement_local_refs)
        raw_evidence_statement_refs = [item.get("statement_refs") for item in evidence_items]
        if any(not isinstance(refs, list) for refs in raw_evidence_statement_refs):
            continue
        evidence_statement_refs = [
            [str(ref).strip() for ref in refs if str(ref).strip()]
            for refs in raw_evidence_statement_refs
        ]
        if (
            any(not refs or any(ref not in statement_ref_set for ref in refs) for refs in evidence_statement_refs)
            or set(ref for refs in evidence_statement_refs for ref in refs) != statement_ref_set
        ):
            continue

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
    summary = {
        "searched_sources": len(sources),
        "accepted_sources": len(package["sources"]),
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
