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
    return {
        "url": url,
        "title": item.get("title"),
        "content": item.get("content"),
        "raw_content": raw_content[:_MAX_SOURCE_RAW_CHARS],
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


def web_search_node(state: SearcherState) -> dict:
    """固定执行一次 Tavily general 搜索，并只保留唯一且带正文的来源."""
    result = _TAVILY_SEARCH(
        query=state["query_text"],
        max_results=_DEFAULT_MAX_RESULTS,
        topic="general",
    )
    if not isinstance(result, dict):
        result = {
            "error": "tavily_search returned a non-dict response",
            "query": state["query_text"],
            "results": [],
        }

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
        "query": result.get("query") or state["query_text"],
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


_EXTRACT_SOURCE_PACKET_USER_TEMPLATE = """\
## 任务
只基于下面这个单一来源的网页正文做结构化知识抽取，返回该来源自己的 source packet。

## 必须按顺序执行的硬门槛

### 第一门槛：来源类型准入
在抽取任何内容前，先根据 URL、站点、标题、页面信息和 `raw_content` 判断来源类型。

以下来源一律拒绝：社交媒体平台上的帖子、动态、评论、视频或图片说明及其他用户发布内容；论坛、问答、讨论串和评论区内容；只有搜索摘要、AI 摘要、自动摘要、聚合片段、图片、alt text、导航、标签或元数据而无可核验正文的页面。

即使这些来源完整讨论 Query 的目标主体，也必须拒绝。不得通过降低 confidence 或添加 limitations 保留。如果普通网页同时包含原始正文和 AI 摘要或评论，忽略后者；只有剩余原始正文能够独立通过硬门槛时才允许继续。

### 第二门槛：主体匹配
通过来源类型准入后，从 Query 提取目标主体的名称、明确别名、对象类型和关键消歧特征，再检查 `raw_content` 是否真正讨论该主体。

只有在来源正文对目标主体进行对象级讨论，并且正文包含该主体自身的事实、描述、解释、争议或目录信息时，才允许继续抽取。以下情况一律拒绝整篇来源：只讨论相关人物、地点、时代、一般类别、相似或同名对象；仅在标题、标签、相关推荐、元数据或搜索摘要中出现 Query 关键词；只是无对象级正文的泛化汇总；无法确认正文内容属于目标主体。

如果任一硬门槛不通过，必须只返回以下完全空 packet，不得生成任何负面说明或占位内容：
{{"source": {{}}, "document": {{}}, "statements": [], "evidence": [], "conflicts": []}}

硬门槛不通过时禁止把拒绝原因、“该来源无关”“没有找到目标”或主体混淆判断写入 `document_summary`、statement、evidence 或 conflict。`confidence=low` 不能替代硬拒绝。

## Query
{query_text}

## 来源正文
{source_payload}

## 输出要求
只输出一个 JSON 对象（不要 markdown 代码块，不要额外说明），结构如下：
{{
  "source": {{"source_type": "official|paper|report|news|blog|other", "published_at": null}},
  "document": {{"document_summary": "忠实摘要..."}},
  "statements": [
    {{"local_ref": "st1", "text": "该文档声称的事实性陈述...", "qualifiers": [], "limitations": [], "confidence": "high|medium|low", "locator": null}}
  ],
  "evidence": [
    {{"local_ref": "e1", "text": "可复核的具体证据片段...", "evidence_type": "data|definition|quote|policy|experiment|code_fact|other", "locator": null, "qualifiers": [], "limitations": [], "confidence": "high|medium|low"}}
  ],
  "conflicts": [
    {{"local_ref": "x1", "description": "该来源内部存在的矛盾描述...", "evidence_refs": ["e1", "e2"]}}
  ]
}}
- 这是单一来源抽取，不要跨来源合并。
- 只能依据 raw_content；标题仅用于识别来源，不得把搜索摘要或外部知识写入结果。
- 两个硬门槛都通过时，`document_summary` 必须非空，并且至少抽取一条 statement 或 evidence；任一硬门槛不通过时必须返回上面的完全空 packet。
- 主体匹配成功后，如果某条内容无法确认属于目标主体，则排除该条内容；如果整个来源的主体归属变得不确定，则返回完全空 packet，不返回部分 packet。
- 不要生成 Claim。
"""


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


def _extract_source_packet(query_text: str, source: dict[str, Any]) -> dict:
    """对单个带正文来源执行一次 analyzer 抽取."""
    source_payload = {
        "url": source.get("url"),
        "title": source.get("title"),
        "published_at": source.get("published_at"),
        "raw_content": (source.get("raw_content") or "")[:_MAX_SOURCE_RAW_CHARS],
    }
    prompt = _EXTRACT_SOURCE_PACKET_USER_TEMPLATE.format(
        query_text=query_text,
        source_payload=json.dumps(source_payload, ensure_ascii=False),
    )
    response = config.searcher_model.invoke([
        SystemMessage(content=config.analyzer_system_prompt),
        HumanMessage(content=prompt),
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


def _merge_source_packets(search_results: dict, packets: list[dict]) -> dict:
    """把有效的单来源 packet 合并为现有 evidence_package shape."""
    package = _empty_package()
    statement_counter = 0
    evidence_counter = 0
    conflict_counter = 0

    for source, packet in zip(search_results.get("results", []) or [], packets):
        if not isinstance(source, dict) or not isinstance(packet, dict):
            continue
        document = packet.get("document") if isinstance(packet.get("document"), dict) else {}
        summary = str(document.get("document_summary") or "").strip()
        statements = _nonempty_items(packet.get("statements"))
        evidence_items = _nonempty_items(packet.get("evidence"))
        if not summary or not (statements or evidence_items):
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

        for statement in statements:
            statement_counter += 1
            package["statements"].append({
                "local_ref": f"st{statement_counter}",
                "text": str(statement.get("text") or "").strip(),
                "document_ref": document_ref,
                "source_ref": source_ref,
                "qualifiers": statement.get("qualifiers") if isinstance(statement.get("qualifiers"), list) else [],
                "limitations": statement.get("limitations") if isinstance(statement.get("limitations"), list) else [],
                "confidence": statement.get("confidence"),
                "locator": statement.get("locator"),
            })

        local_evidence_map: dict[str, str] = {}
        for evidence in evidence_items:
            evidence_counter += 1
            global_ref = f"e{evidence_counter}"
            local_ref = str(evidence.get("local_ref") or global_ref)
            local_evidence_map[local_ref] = global_ref
            package["evidence"].append({
                "local_ref": global_ref,
                "text": str(evidence.get("text") or "").strip(),
                "document_ref": document_ref,
                "source_ref": source_ref,
                "evidence_type": evidence.get("evidence_type"),
                "locator": evidence.get("locator"),
                "qualifiers": evidence.get("qualifiers") if isinstance(evidence.get("qualifiers"), list) else [],
                "limitations": evidence.get("limitations") if isinstance(evidence.get("limitations"), list) else [],
                "confidence": evidence.get("confidence"),
            })

        conflicts = packet.get("conflicts") if isinstance(packet.get("conflicts"), list) else []
        for conflict in conflicts:
            if not isinstance(conflict, dict):
                continue
            refs = [
                local_evidence_map[ref]
                for ref in conflict.get("evidence_refs") or []
                if ref in local_evidence_map
            ]
            description = str(conflict.get("description") or "").strip()
            if not description or not refs:
                continue
            conflict_counter += 1
            package["conflicts"].append({
                "local_ref": f"x{conflict_counter}",
                "description": description,
                "evidence_refs": refs,
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
    packets = [
        _extract_source_packet(state["query_text"], source)
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
