"""Searcher agent — a LangGraph StateGraph for deterministic evidence collection.

Replaces the prompt-based ``create_deep_agent`` with an explicit StateGraph
so that the pipeline order and data hand-off are guaranteed by the graph,
not by the model's interpretation of a prompt:

    init → web_search (Tavily fetch) → extract_evidence_package (LLM extraction) → submit (function)

The Orchestrator dispatches it via the structured ``dispatch_searcher`` tool,
which injects ``query_id``/``query_text`` directly into the state (so the query
node ID never round-trips through free text) and invokes this compiled graph.
The state schema keeps a ``messages`` key reduced with ``add_messages`` so the
caller can read the final report message.
"""

import json
import re
from typing import Annotated, Any, Optional, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

import config
from tools.graph_manager_tools import submit_search_result  # langchain @tool
from tools.search_tools import tavily_search

# ── State ────────────────────────────────────────────────────────────────


class SearcherState(TypedDict):
    """State carried through the Searcher pipeline.

    ``messages`` is required by ``CompiledSubAgent`` — the runtime reads the
    last AIMessage text as the sub-agent's return value.
    """

    messages: Annotated[list, add_messages]
    query_id: str
    search_run_id: str
    query_text: str
    search_results: Optional[dict]
    search_output: str
    evidence_package: Optional[dict]
    submit_result: Optional[dict]


# ── Helpers ──────────────────────────────────────────────────────────────

_QID_RE = re.compile(r"(?:query_id|Query ID|queryId|qid|id)[=:]\s*([a-f0-9_]+)", re.IGNORECASE)

_MAX_DEBUG_SEARCH_OUTPUT_CHARS = 30_000
_MAX_SOURCE_RAW_CHARS = 20_000
_DEFAULT_MAX_RESULTS = 5

_EMPTY_PACKAGE: dict = {
    "sources": [],
    "documents": [],
    "statements": [],
    "evidence": [],
    "conflicts": [],
}

_EMPTY_SOURCE_PACKET: dict = {
    "source": {},
    "document": {},
    "statements": [],
    "evidence": [],
    "conflicts": [],
}

# ── Nodes ────────────────────────────────────────────────────────────────


def init_node(state: SearcherState) -> dict:
    """Resolve ``query_id`` and ``query_text`` for the run.

    The Orchestrator dispatches via ``dispatch_searcher(query_id, instructions)``,
    which injects both fields into the state directly — use them as-is so the
    query node ID never round-trips through free text. Only when they are absent
    (e.g. a raw-text dispatch) fall back to parsing them from the last message.
    """
    qid = state.get("query_id")
    qtext = state.get("query_text")
    if qid and qid != "unknown" and qtext:
        return {"query_id": qid, "query_text": qtext}

    last = state["messages"][-1]
    content: str = last.content if hasattr(last, "content") else str(last)

    m = _QID_RE.search(content)
    qid = m.group(1) if m else "unknown"

    # Remove the query_id=… token.  Collapse the whitespace it leaves behind.
    qtext = re.sub(r"\s+", " ", _QID_RE.sub("", content)).strip()
    # Drop common Chinese lead-in phrases the Orchestrator sometimes wraps with.
    for lead_in in ("围绕", "检索", "搜索", "的问题检索", "的检索", "任务"):
        for sep in ("：", ":", " "):
            prefix = lead_in + sep
            while qtext.startswith(prefix):
                qtext = qtext[len(prefix):].strip()
    # Strip any orphaned colon the regex left behind.
    qtext = qtext.lstrip("：:").strip()

    return {"query_id": qid, "query_text": qtext}


_TAVILY_SEARCH = getattr(tavily_search, "func", tavily_search)


def _compact_search_output(search_results: dict) -> str:
    """Render a compact debug string from structured Tavily results."""
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
        "dropped_without_raw_content": search_results.get("dropped_without_raw_content", 0),
    }
    text = json.dumps(compact, ensure_ascii=False)
    if len(text) > _MAX_DEBUG_SEARCH_OUTPUT_CHARS:
        return text[:_MAX_DEBUG_SEARCH_OUTPUT_CHARS] + "…（调试输出过长已截断）"
    return text


def _normalize_search_result(item: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Keep one Tavily result only when it contains extractable raw content."""
    raw_content = item.get("raw_content")
    if not isinstance(raw_content, str) or not raw_content.strip():
        return None
    return {
        "url": item.get("url"),
        "title": item.get("title"),
        "content": item.get("content"),
        "raw_content": raw_content,
        "score": item.get("score"),
        "published_at": item.get("published_at") or item.get("date"),
    }


_EXTRACT_SOURCE_PACKET_USER_TEMPLATE = """\
## 任务
只基于下面这个单一来源对象做结构化知识抽取，返回该来源自己的 source packet。

## Query
{query_text}

## 来源对象
{source_payload}

## 输出要求
只输出一个 JSON 对象（不要 markdown 代码块，不要额外说明），结构如下：
{{
  "source": {{
    "source_type": "official|paper|report|news|blog|other",
    "published_at": null
  }},
  "document": {{
    "document_summary": "忠实摘要…"
  }},
  "statements": [
    {{"local_ref": "st1", "text": "该文档声称的事实性陈述…", "qualifiers": [], "limitations": [], "confidence": "high|medium|low", "locator": null}}
  ],
  "evidence": [
    {{"local_ref": "e1", "text": "可复核的具体证据片段…", "evidence_type": "data|definition|quote|policy|experiment|code_fact|other", "locator": null, "qualifiers": [], "limitations": [], "confidence": "high|medium|low"}}
  ],
  "conflicts": [
    {{"local_ref": "x1", "description": "该来源内部存在的矛盾描述…", "evidence_refs": ["e1", "e2"]}}
  ]
}}
- 这是单一来源抽取，不要跨来源合并。
- `document_summary` 只写该来源正文内容的忠实摘要。
- 每条 statement/evidence 都必须来自该来源的 `raw_content`，不要把标题或短摘要当强证据。
- 如果该来源没有足够信息可抽取，返回空数组，但 `document.document_summary` 仍尽量给出忠实摘要。
- 不要生成 Claim。
"""


def web_search_node(state: SearcherState) -> dict:
    """Search the web for ``query_text`` and return structured source objects."""
    result = _TAVILY_SEARCH(
        query=state["query_text"],
        max_results=_DEFAULT_MAX_RESULTS,
        topic="general",
        include_raw_content=True,
    )
    if not isinstance(result, dict):
        result = {
            "error": "tavily_search returned a non-dict response",
            "query": state["query_text"],
            "results": [],
        }

    kept: list[dict[str, Any]] = []
    dropped_without_raw = 0
    for item in result.get("results", []) or []:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_search_result(item)
        if normalized is None:
            dropped_without_raw += 1
            continue
        kept.append(normalized)

    structured = {
        "query": result.get("query") or state["query_text"],
        "error": result.get("error"),
        "results": kept,
        "dropped_without_raw_content": dropped_without_raw,
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
    """Extract one source packet from model output."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        data = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        match = re.search(r"\{.*\}", stripped, re.DOTALL)
        if not match:
            return dict(_EMPTY_SOURCE_PACKET)
        try:
            data = json.loads(match.group(0))
        except (json.JSONDecodeError, ValueError):
            return dict(_EMPTY_SOURCE_PACKET)
    if not isinstance(data, dict):
        return dict(_EMPTY_SOURCE_PACKET)
    for key, default in _EMPTY_SOURCE_PACKET.items():
        data.setdefault(key, {} if isinstance(default, dict) else [])
    return data


def _extract_source_packet(query_text: str, source: dict[str, Any]) -> dict:
    """Run one source-level extraction pass."""
    source_payload = {
        "url": source.get("url"),
        "title": source.get("title"),
        "content": source.get("content"),
        "published_at": source.get("published_at"),
        # Bound prompt size even when the stored raw_content is much larger.
        "raw_content": (source.get("raw_content") or "")[:_MAX_SOURCE_RAW_CHARS],
    }
    prompt = _EXTRACT_SOURCE_PACKET_USER_TEMPLATE.format(
        query_text=query_text,
        source_payload=json.dumps(source_payload, ensure_ascii=False),
    )
    msgs = [
        SystemMessage(content=config.analyzer_system_prompt),
        HumanMessage(content=prompt),
    ]
    response = config.searcher_model.invoke(msgs)
    text: str = response.content if hasattr(response, "content") else str(response)
    return _parse_source_packet(text)


def _merge_source_packets(search_results: dict, packets: list[dict]) -> dict:
    """Merge per-source packets into the evidence_package schema."""
    package = dict(_EMPTY_PACKAGE)
    statement_counter = 0
    evidence_counter = 0
    conflict_counter = 0

    for index, (source, packet) in enumerate(zip(search_results.get("results", []) or [], packets), start=1):
        if not isinstance(source, dict) or not isinstance(packet, dict):
            continue
        source_ref = f"s{index}"
        document_ref = f"d{index}"
        source_meta = packet.get("source") if isinstance(packet.get("source"), dict) else {}
        document_meta = packet.get("document") if isinstance(packet.get("document"), dict) else {}
        package["sources"].append({
            "local_ref": source_ref,
            "url": source.get("url"),
            "title": source.get("title"),
            "source_type": source_meta.get("source_type") or "other",
            "published_at": source_meta.get("published_at") or source.get("published_at"),
        })
        package["documents"].append({
            "local_ref": document_ref,
            "document_summary": str(document_meta.get("document_summary") or "").strip(),
            "source_ref": source_ref,
            "raw_content": source.get("raw_content"),
        })

        local_evidence_map: dict[str, str] = {}
        for statement in packet.get("statements") or []:
            if not isinstance(statement, dict):
                continue
            text = str(statement.get("text") or "").strip()
            if not text:
                continue
            statement_counter += 1
            package["statements"].append({
                "local_ref": f"st{statement_counter}",
                "text": text,
                "document_ref": document_ref,
                "source_ref": source_ref,
                "qualifiers": statement.get("qualifiers") if isinstance(statement.get("qualifiers"), list) else [],
                "limitations": statement.get("limitations") if isinstance(statement.get("limitations"), list) else [],
                "confidence": statement.get("confidence"),
                "locator": statement.get("locator"),
            })
        for evidence in packet.get("evidence") or []:
            if not isinstance(evidence, dict):
                continue
            text = str(evidence.get("text") or "").strip()
            if not text:
                continue
            evidence_counter += 1
            global_ref = f"e{evidence_counter}"
            local_ref = str(evidence.get("local_ref") or global_ref)
            local_evidence_map[local_ref] = global_ref
            package["evidence"].append({
                "local_ref": global_ref,
                "text": text,
                "document_ref": document_ref,
                "source_ref": source_ref,
                "evidence_type": evidence.get("evidence_type"),
                "locator": evidence.get("locator"),
                "qualifiers": evidence.get("qualifiers") if isinstance(evidence.get("qualifiers"), list) else [],
                "limitations": evidence.get("limitations") if isinstance(evidence.get("limitations"), list) else [],
                "confidence": evidence.get("confidence"),
            })
        for conflict in packet.get("conflicts") or []:
            if not isinstance(conflict, dict):
                continue
            refs = [
                local_evidence_map[ref]
                for ref in conflict.get("evidence_refs") or []
                if ref in local_evidence_map
            ]
            if not refs:
                continue
            conflict_counter += 1
            package["conflicts"].append({
                "local_ref": f"x{conflict_counter}",
                "description": str(conflict.get("description") or "").strip(),
                "evidence_refs": refs,
            })
    return package


def extract_evidence_package_node(state: SearcherState) -> dict:
    """Extract a structured ``evidence_package`` from source-level Tavily results."""
    search_results = state.get("search_results") or {}
    sources = search_results.get("results") or []
    if not isinstance(sources, list) or not sources:
        return {
            "evidence_package": dict(_EMPTY_PACKAGE),
            "messages": [AIMessage(content="未保留任何带 raw_content 的来源。")],
        }
    packets = [
        _extract_source_packet(state["query_text"], source)
        for source in sources
        if isinstance(source, dict)
    ]
    ep = _merge_source_packets(search_results, packets)
    return {
        "evidence_package": ep,
        "messages": [AIMessage(content=json.dumps({"kept_sources": len(sources)}, ensure_ascii=False))],
    }

def submit_node(state: SearcherState) -> dict:
    """Write the evidence package into the Research Graph.

    This is a deterministic function — no LLM involved, so the
    ``Field required`` error on ``evidence_package`` cannot happen.
    """
    ep = state.get("evidence_package") or dict(_EMPTY_PACKAGE)
    if not isinstance(ep, dict):
        ep = dict(_EMPTY_PACKAGE)

    result = submit_search_result.invoke({
        "search_run_id": state["search_run_id"],
        "query_id": state["query_id"],
        "evidence_package": ep,
    })
    summary = json.dumps(result, ensure_ascii=False)
    return {"submit_result": result, "messages": [AIMessage(content=summary)]}


# ── Graph ────────────────────────────────────────────────────────────────


def _build_graph() -> StateGraph:
    g = StateGraph(SearcherState)
    g.add_node("init", init_node)
    g.add_node("web_search", web_search_node)
    g.add_node("extract_evidence_package", extract_evidence_package_node)
    g.add_node("submit", submit_node)

    g.add_edge("init", "web_search")
    g.add_edge("web_search", "extract_evidence_package")
    g.add_edge("extract_evidence_package", "submit")
    g.add_edge("submit", END)

    g.set_entry_point("init")
    return g


searcher = _build_graph().compile()
"""Compiled LangGraph Searcher — a drop-in ``Runnable`` replacement for the
old ``create_deep_agent``, compatible with ``CompiledSubAgent``."""
