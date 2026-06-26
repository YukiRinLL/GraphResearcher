"""Searcher agent — a LangGraph StateGraph for deterministic evidence collection.

Replaces the prompt-based ``create_deep_agent`` with an explicit StateGraph
so that the pipeline order and data hand-off are guaranteed by the graph,
not by the model's interpretation of a prompt:

    init → web_search (LLM agent) → extract_evidence_package (LLM extraction) → submit (function)

The Orchestrator dispatches it via the structured ``dispatch_searcher`` tool,
which injects ``query_id``/``query_text`` directly into the state (so the query
node ID never round-trips through free text) and invokes this compiled graph.
The state schema keeps a ``messages`` key reduced with ``add_messages`` so the
caller can read the final report message.
"""

import json
import re
from typing import Annotated, Optional, TypedDict

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

import config
from tools.graph_manager_tools import submit_search_result  # langchain @tool
from tools.middleware import SearchFallbackMiddleware
from tools.search_tools import serper_search, tavily_search

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
    search_output: str
    evidence_package: Optional[dict]
    submit_result: Optional[dict]


# ── Helpers ──────────────────────────────────────────────────────────────

_QID_RE = re.compile(r"(?:query_id|Query ID|queryId|qid|id)[=:]\s*([a-f0-9_]+)", re.IGNORECASE)

# Characters beyond this limit are dropped from the search output before it is
# passed to the extraction node, to avoid context-window exhaustion.
_MAX_SEARCH_OUTPUT_CHARS = 50_000

_EMPTY_PACKAGE: dict = {
    "sources": [],
    "documents": [],
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


# The web-search agent is built once and re-invoked per Searcher run.
_web_search_agent = create_agent(
    model=config.searcher_model,
    system_prompt=config.web_searcher_system_prompt,
    tools=[serper_search, tavily_search],
    middleware=[SearchFallbackMiddleware()],
)


def web_search_node(state: SearcherState) -> dict:
    """Search the web for ``query_text`` and return raw source materials.

    Uses a lightweight ``create_agent`` (not ``create_deep_agent``) — it only
    needs search + page-read tools, not the ``task()`` sub-agent dispatcher.
    """
    task_msg = HumanMessage(content=state["query_text"])
    result = _web_search_agent.invoke({"messages": [task_msg]})
    last_msg = result["messages"][-1]
    search_output: str = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    if len(search_output) > _MAX_SEARCH_OUTPUT_CHARS:
        search_output = search_output[:_MAX_SEARCH_OUTPUT_CHARS] + "…（内容过长已截断）"

    return {"search_output": search_output, "messages": result["messages"]}


# The user-message template for the extraction node.  The search output is
# inlined here — no sub-agent context-isolation gap.
_EXTRACT_EVIDENCE_PACKAGE_USER_TEMPLATE = """\
## 任务
对以下网页原始素材做结构化知识抽取，生成 evidence_package。

## Query
{query_text}

## 输出要求
只输出一个 JSON 对象（不要 markdown 代码块，不要额外说明），结构如下：
{{
  "sources": [
    {{"local_ref": "s1", "url": "https://...", "title": "...", "source_type": "paper|blog|report|news|other"}}
  ],
  "documents": [
    {{"local_ref": "d1", "document_summary": "忠实摘要…", "source_ref": "s1"}}
  ],
  "statements": [
    {{"local_ref": "st1", "text": "该文档声称的事实性陈述…", "document_ref": "d1", "source_ref": "s1", "qualifiers": [], "limitations": [], "confidence": "high|medium|low"}}
  ],
  "evidence": [
    {{"local_ref": "e1", "text": "可复核的具体证据片段…", "document_ref": "d1", "source_ref": "s1", "evidence_type": "data|definition|quote|policy|experiment|code_fact|other", "locator": null, "qualifiers": [], "limitations": [], "confidence": "high|medium|low"}}
  ],
  "conflicts": [
    {{"local_ref": "x1", "description": "不同来源的矛盾描述…", "evidence_refs": ["e1", "e2"]}}
  ]
}}
- local_ref 用于包内交叉引用（如 document.source_ref 指向 sources[].local_ref）。
- 每条 statement 和 evidence 必须有可追溯的 source_ref 和 document_ref。
- 不要生成 Claim；Claim 由 Graph Manager 后续从多个 Statement/Evidence 中归一化。
- 如果素材中完全没有可抽取的内容，返回所有字段为空数组的 JSON（不可省略任何字段）。
- 不要编造任何 URL、标题、数据或日期；缺失的元数据用 null。

## 素材
{search_output}"""


def extract_evidence_package_node(state: SearcherState) -> dict:
    """Extract a structured ``evidence_package`` from the raw search output.

    The web-search result is **inlined** in the prompt so the LLM always sees
    the actual materials — there is no sub-agent boundary between search and
    extraction.
    """
    prompt = _EXTRACT_EVIDENCE_PACKAGE_USER_TEMPLATE.format(
        query_text=state["query_text"],
        search_output=state.get("search_output") or "（无搜索结果）",
    )
    msgs = [
        SystemMessage(content=config.analyzer_system_prompt),
        HumanMessage(content=prompt),
    ]
    response = config.searcher_model.invoke(msgs)
    text: str = response.content if hasattr(response, "content") else str(response)

    ep = _parse_evidence_package(text)
    return {"evidence_package": ep, "messages": [response]}


def _parse_evidence_package(text: str) -> dict:
    """Extract a JSON evidence_package from the model's response.

    Handles bare JSON, markdown-fenced JSON, and JSON embedded in prose.
    Returns an empty package on any parse failure so the pipeline never
    halts on a formatting error.
    """
    # Strip markdown code fences.
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)

    try:
        data = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        # Try to find a JSON object anywhere in the text.
        m = re.search(r"\{.*\}", stripped, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
            except (json.JSONDecodeError, ValueError):
                return dict(_EMPTY_PACKAGE)
        else:
            return dict(_EMPTY_PACKAGE)

    if not isinstance(data, dict):
        return dict(_EMPTY_PACKAGE)

    # Fill in any missing top-level keys.
    for key in _EMPTY_PACKAGE:
        data.setdefault(key, [])
    # Backward compatibility for packages produced by older prompts.
    data.setdefault("claims", [])
    return data


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
