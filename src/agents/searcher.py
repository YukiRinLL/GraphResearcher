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
from urllib.parse import urlparse
from typing import Annotated, Optional, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

import config
from tools.graph_manager_tools import submit_search_result  # langchain @tool
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
    search_task: Optional[dict]
    search_output: str
    evidence_package: Optional[dict]
    submit_result: Optional[dict]


# ── Helpers ──────────────────────────────────────────────────────────────

_QID_RE = re.compile(r"(?:query_id|Query ID|queryId|qid|id)[=:]\s*([a-f0-9_]+)", re.IGNORECASE)

# Characters beyond this limit are dropped from the search output before it is
# passed to the extraction node, to avoid context-window exhaustion.
_MAX_SEARCH_OUTPUT_CHARS = 50_000
_PUBLIC_DISCOURSE_QUERY_RE = re.compile(
    r"\b(?:public|popular|social media|social-media|media|reception|legacy|influence|culture|discourse)\b|"
    r"公众|传播|舆论|社交媒体|接受史|影响",
    re.IGNORECASE,
)
_WEAK_PUBLIC_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "pinterest.com",
    "reddit.com",
    "researchgate.net",
    "scribd.com",
    "substack.com",
    "youtube.com",
}
_WEAK_HOSTED_DOMAINS = {
    "academia.edu",
    "researchgate.net",
    "scribd.com",
}
_LOW_UTILITY_PAGE_RE = re.compile(
    r"sign up for access|log in|login|search results?|image library search|"
    r"this site is protected by anubis|access denied|forbidden|captcha|"
    r"fact-checked by grok|error message|page not found|not available|"
    r"create account|register to continue|sparkles ai|key takeaways|"
    r"related papers|uploaded by|share this document|visibility\s*$|"
    r"get our free apps|outline\s*$",
    re.IGNORECASE,
)
_WEAK_HOSTED_LIMITATION_RE = re.compile(
    r"ai-generated|key takeaways|ai summary|hosting platform|full text.*not visible|"
    r"visible excerpt|snippet|platform-generated|abstract.*summary",
    re.IGNORECASE,
)

_EMPTY_PACKAGE: dict = {
    "sources": [],
    "documents": [],
    "statements": [],
    "evidence": [],
    "conflicts": [],
}
_MAX_ENGINE_QUERY_CHARS = 380


def _parse_search_task(raw: object) -> dict:
    """Parse the Searcher task payload when the caller passes structured JSON."""
    if isinstance(raw, dict):
        return raw
    text = str(raw or "").strip()
    if not text.startswith("{"):
        return {}
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _task_language(task: dict) -> str:
    """Return the preferred output language for search summaries/extraction."""
    language = str(task.get("language") or "").strip()
    if language:
        return language
    query = str(task.get("query") or "").strip()
    return "Chinese" if re.search(r"[\u4e00-\u9fff]", query) else "English"


def _host(url: str) -> str:
    """Return a normalized hostname without a leading www."""
    host = (urlparse(str(url or "")).netloc or "").lower()
    return host[4:] if host.startswith("www.") else host


def _query_allows_public_discourse(query: str) -> bool:
    """Return whether the current query explicitly asks about reception/media."""
    return bool(_PUBLIC_DISCOURSE_QUERY_RE.search(str(query or "")))


def _compact_search_query(query: str, limit: int = _MAX_ENGINE_QUERY_CHARS) -> str:
    """Shorten overly long queries without dropping the core subject/constraint cues."""
    text = " ".join(str(query or "").split()).strip()
    if len(text) <= limit:
        return text

    site_tokens = re.findall(r"-site:[^\s]+", text)
    base = re.sub(r"\s*-site:[^\s]+", "", text).strip()
    sentences = re.split(r"(?<=[.!?])\s+", base)
    kept: list[str] = []
    total = 0
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        extra = len(sentence) + (1 if kept else 0)
        if total + extra > max(120, limit - sum(len(token) + 1 for token in site_tokens)):
            break
        kept.append(sentence)
        total += extra

    compact = " ".join(kept).strip() or base[: max(0, limit - 32)].rstrip(" ,;:")
    if len(compact) > limit:
        compact = compact[:limit].rstrip(" ,;:")

    suffix = " ".join(token for token in dict.fromkeys(site_tokens))
    if suffix:
        remaining = limit - len(suffix) - 1
        compact = compact[: max(0, remaining)].rstrip(" ,;:")
        compact = f"{compact} {suffix}".strip()
    return compact[:limit].rstrip()


def _should_drop_result(item: dict, allow_public_discourse: bool) -> bool:
    """Drop results that are weak/public or clearly unusable as factual support."""
    url = str(item.get("url") or "")
    host = _host(url)
    title = str(item.get("title") or "")
    content = str(item.get("content") or "")
    raw_content = str(item.get("raw_content") or "")
    combined = "\n".join(part for part in (title, content, raw_content) if part).strip()
    if not combined:
        return True
    if _LOW_UTILITY_PAGE_RE.search(combined):
        return True
    if not allow_public_discourse and any(
        host == domain or host.endswith(f".{domain}")
        for domain in _WEAK_PUBLIC_DOMAINS
    ):
        return True
    return False


def _filter_search_payload(payload: dict, query: str) -> dict:
    """Remove low-utility search results before the extraction model sees them."""
    if not isinstance(payload, dict):
        return payload
    results = payload.get("results")
    if not isinstance(results, list):
        return payload
    allow_public_discourse = _query_allows_public_discourse(query)
    kept = [item for item in results if not _should_drop_result(item, allow_public_discourse)]
    payload = dict(payload)
    payload["results"] = kept
    payload["dropped_results"] = len(results) - len(kept)
    return payload


def _should_drop_extracted_item(item: dict, source: dict, query: str) -> bool:
    """Drop extracted items that still depend on weak hosted/public pages."""
    host = _host(source.get("url") or "")
    if not _query_allows_public_discourse(query) and any(
        host == domain or host.endswith(f".{domain}")
        for domain in _WEAK_PUBLIC_DOMAINS
    ):
        return True

    limitations = " ".join(str(part or "") for part in item.get("limitations") or [])
    if any(host == domain or host.endswith(f".{domain}") for domain in _WEAK_HOSTED_DOMAINS):
        if _WEAK_HOSTED_LIMITATION_RE.search(limitations):
            return True

    return False


def _sanitize_evidence_package(data: dict, query: str) -> dict:
    """Prune weak extracted items and orphaned docs/sources before graph write."""
    if not isinstance(data, dict):
        return dict(_EMPTY_PACKAGE)

    sources = [item for item in data.get("sources", []) if isinstance(item, dict)]
    source_by_ref = {
        str(item.get("local_ref") or "").strip(): item
        for item in sources
        if str(item.get("local_ref") or "").strip()
    }

    kept_statements = []
    for item in data.get("statements", []) or []:
        if not isinstance(item, dict):
            continue
        source = source_by_ref.get(str(item.get("source_ref") or "").strip(), {})
        if _should_drop_extracted_item(item, source, query):
            continue
        kept_statements.append(item)

    kept_evidence = []
    for item in data.get("evidence", []) or []:
        if not isinstance(item, dict):
            continue
        source = source_by_ref.get(str(item.get("source_ref") or "").strip(), {})
        if _should_drop_extracted_item(item, source, query):
            continue
        kept_evidence.append(item)

    kept_evidence_refs = {
        str(item.get("local_ref") or "").strip()
        for item in kept_evidence
        if str(item.get("local_ref") or "").strip()
    }
    kept_conflicts = []
    for item in data.get("conflicts", []) or []:
        if not isinstance(item, dict):
            continue
        evidence_refs = [
            ref for ref in item.get("evidence_refs", []) or []
            if str(ref or "").strip() in kept_evidence_refs
        ]
        if len(evidence_refs) < 2:
            continue
        kept_item = dict(item)
        kept_item["evidence_refs"] = evidence_refs
        kept_conflicts.append(kept_item)

    kept_document_refs = {
        str(item.get("document_ref") or "").strip()
        for item in [*kept_statements, *kept_evidence]
        if str(item.get("document_ref") or "").strip()
    }
    kept_source_refs = {
        str(item.get("source_ref") or "").strip()
        for item in [*kept_statements, *kept_evidence]
        if str(item.get("source_ref") or "").strip()
    }

    kept_documents = [
        item for item in data.get("documents", []) or []
        if isinstance(item, dict) and str(item.get("local_ref") or "").strip() in kept_document_refs
    ]
    kept_sources = [
        item for item in data.get("sources", []) or []
        if isinstance(item, dict) and str(item.get("local_ref") or "").strip() in kept_source_refs
    ]

    sanitized = dict(_EMPTY_PACKAGE)
    sanitized["sources"] = kept_sources
    sanitized["documents"] = kept_documents
    sanitized["statements"] = kept_statements
    sanitized["evidence"] = kept_evidence
    sanitized["conflicts"] = kept_conflicts
    return sanitized


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
    task = _parse_search_task(qtext)
    if qid and qid != "unknown" and qtext:
        return {
            "query_id": qid,
            "query_text": str(task.get("query") or qtext),
            "search_task": task or None,
        }

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

    task = _parse_search_task(qtext)
    return {
        "query_id": qid,
        "query_text": str(task.get("query") or qtext),
        "search_task": task or None,
    }


def web_search_node(state: SearcherState) -> dict:
    """Search the web for ``query_text`` and return raw source materials.

    This stage is deterministic on purpose: it preserves the literal query,
    including any ``-site:...`` exclusions, and passes raw tool payloads
    directly to the extraction node instead of letting an LLM rewrite them.
    """
    task = state.get("search_task") or {"query": state["query_text"]}
    raw_query = str(task.get("query") or state["query_text"]).strip()
    query = _compact_search_query(raw_query)
    topic = "general"
    tool_payloads = [
        {
            "tool": "serper_search",
            "payload": _filter_search_payload(serper_search.invoke({
                "query": query,
                "max_results": 10,
                "topic": topic,
                "include_raw_content": False,
            }), query),
        },
        {
            "tool": "tavily_search",
            "payload": _filter_search_payload(tavily_search.invoke({
                "query": query,
                "max_results": 5,
                "topic": topic,
                "include_raw_content": True,
            }), query),
        },
    ]
    search_output = json.dumps(tool_payloads, ensure_ascii=False, indent=2)

    if len(search_output) > _MAX_SEARCH_OUTPUT_CHARS:
        search_output = search_output[:_MAX_SEARCH_OUTPUT_CHARS] + "… (truncated)"

    return {"search_output": search_output, "messages": [AIMessage(content=search_output)]}


# The user-message template for the extraction node.  The search output is
# inlined here — no sub-agent context-isolation gap.
_EXTRACT_EVIDENCE_PACKAGE_USER_TEMPLATE = """\
## Task
Extract a structured evidence_package from the following web materials.

## Query
{query_text}

## Output language
Write every `document_summary`, `statement.text`, `evidence.text`, `qualifiers`, `limitations`, and conflict description in: {output_language}

## Output format
Return exactly one JSON object with no Markdown fences and no extra explanation:
{{
  "sources": [
    {{"local_ref": "s1", "url": "https://...", "title": "...", "source_type": "paper|blog|report|news|other"}}
  ],
  "documents": [
    {{"local_ref": "d1", "document_summary": "faithful summary...", "source_ref": "s1"}}
  ],
  "statements": [
    {{"local_ref": "st1", "text": "factual statement made by the document...", "document_ref": "d1", "source_ref": "s1", "qualifiers": [], "limitations": [], "confidence": "high|medium|low"}}
  ],
  "evidence": [
    {{"local_ref": "e1", "text": "specific verifiable evidence snippet...", "document_ref": "d1", "source_ref": "s1", "evidence_type": "data|definition|quote|policy|experiment|code_fact|other", "locator": null, "qualifiers": [], "limitations": [], "confidence": "high|medium|low"}}
  ],
  "conflicts": [
    {{"local_ref": "x1", "description": "conflicting descriptions across sources...", "evidence_refs": ["e1", "e2"]}}
  ]
}}
- Use `local_ref` only for within-package references.
- Every statement and evidence item must keep traceable `source_ref` and `document_ref`.
- Do not generate Claim objects; Graph Manager will normalize claims later.
- If the materials contain nothing usable, return the same JSON shape with every field set to an empty array.
- Never invent URLs, titles, dates, data, or metadata; use null when the source does not provide a value.
- Treat the visible materials, not the presumed underlying page, as your evidence boundary. Do not extract factual statements from:
  - search-engine snippets alone;
  - login walls, access-denied pages, bot-protection pages, or error pages;
  - search-result listings, image-search listings, or navigation pages;
  - platform-generated "key takeaways" / AI summaries unless the underlying source text is also visible here.
- For social posts, forums, image boards, blogs, reposts, or public-summary pages:
  - do not use them as core factual support for identity, provenance, date, custody, authenticity, or other object-level claims when the query is about the subject itself;
  - only extract them when they are directly relevant to modern reception/public discourse, and mark limitations clearly.
- When a result is too weak or inaccessible for factual support, omit its statements/evidence instead of turning a title/snippet into a stronger claim.

## Materials
{search_output}"""


def extract_evidence_package_node(state: SearcherState) -> dict:
    """Extract a structured ``evidence_package`` from the raw search output.

    The web-search result is **inlined** in the prompt so the LLM always sees
    the actual materials — there is no sub-agent boundary between search and
    extraction.
    """
    prompt = _EXTRACT_EVIDENCE_PACKAGE_USER_TEMPLATE.format(
        query_text=state["query_text"],
        output_language=_task_language(state.get("search_task") or {}),
        search_output=state.get("search_output") or "(no search results)",
    )
    msgs = [
        SystemMessage(content=config.analyzer_system_prompt),
        HumanMessage(content=prompt),
    ]
    response = config.searcher_model.invoke(msgs)
    text: str = response.content if hasattr(response, "content") else str(response)

    ep = _parse_evidence_package(text)
    ep = _sanitize_evidence_package(ep, state["query_text"])
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
