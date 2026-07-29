"""Synchronous typed helpers over the Research Graph."""

import asyncio
import hashlib
import os
import re
import threading
from typing import Any, Optional

from memory.graph import EdgeType, NodeType

# Source credibility scoring based on source type
# Higher score = more credible
_SOURCE_CREDIBILITY_MAP = {
    # Academic sources (highest credibility)
    "peer_reviewed_paper": 0.95,
    "academic_paper": 0.90,
    "academic_journal": 0.90,
    "conference_paper": 0.88,
    "thesis": 0.85,
    # Authoritative institutions
    "museum_official": 0.85,
    "museum_website": 0.82,
    "government_publication": 0.85,
    "research_institution": 0.85,
    # Educational
    "edu": 0.80,
    "academic_book": 0.88,
    "university_press": 0.87,
    # Media
    "major_newspaper": 0.65,
    "major_news": 0.65,
    "news": 0.55,
    # Preprints and working papers
    "preprint": 0.55,
    "working_paper": 0.55,
    # Low credibility sources
    "blog": 0.35,
    "personal_website": 0.30,
    "social_media": 0.15,
    "forum": 0.25,
    "wiki": 0.40,
}

# URL pattern-based credibility estimation for auto-detection
_URL_CREDIBILITY_PATTERNS = [
    # Academic domains
    (r"\.edu$", 0.80),
    (r"\.ac\.", 0.82),
    (r"arxiv\.org", 0.55),
    (r"biorxiv\.org", 0.55),
    (r"scholar\.google", 0.75),
    # Museum and cultural institution domains
    (r"museum", 0.82),
    (r"britannica", 0.45),
    # Major news outlets
    (r"nytimes\.com", 0.68),
    (r"bbc\.com", 0.65),
    (r"reuters\.com", 0.68),
    (r"theguardian\.com", 0.65),
    (r"wsj\.com", 0.65),
    (r"economist\.com", 0.68),
    # University presses
    (r"cambridge\.org", 0.87),
    (r"oxford\.org", 0.87),
    (r"springer\.com", 0.88),
    (r"nature\.com", 0.85),
    (r"science\.org", 0.88),
    # Low credibility domains
    (r"instagram\.com", 0.15),
    (r"facebook\.com", 0.15),
    (r"twitter\.com", 0.15),
    (r"x\.com", 0.15),
    (r"reddit\.com", 0.25),
    (r"youtube\.com", 0.20),
    (r"blogspot\.com", 0.30),
    (r"medium\.com", 0.35),
    (r"wordpress\.com", 0.30),
    (r"weebly\.com", 0.20),
    (r"wix\.com", 0.20),
]


def _estimate_source_credibility(url: str, source_type: Optional[str] = None) -> float:
    """Estimate source credibility based on type and URL patterns.

    Returns a score from 0.0 (lowest) to 1.0 (highest).
    """
    # First try explicit source_type mapping
    if source_type:
        normalized_type = source_type.lower().replace("-", "_").replace(" ", "_")
        if normalized_type in _SOURCE_CREDIBILITY_MAP:
            return _SOURCE_CREDIBILITY_MAP[normalized_type]

    # Fall back to URL pattern matching
    url_lower = url.lower() if url else ""
    for pattern, score in _URL_CREDIBILITY_PATTERNS:
        if re.search(pattern, url_lower):
            return score

    # Default: moderate credibility
    return 0.50


_QUERY_TRANSITIONS = {
    "pending": {"searching", "deferred"},
    "searching": {"assessing", "pending", "blocked", "failed"},
    "assessing": {"sufficient", "needs_expansion", "blocked"},
    "needs_expansion": {"waiting_children", "sufficient", "blocked"},
    "waiting_children": {"assessing"},
    "sufficient": set(),
    "blocked": set(),
    "failed": set(),
    "deferred": set(),
}

# A single persistent background event loop runs every coroutine. The neo4j
# AsyncDriver caches a connection pool bound to the loop it was created on, so
# all graph access must share one loop — using a fresh ``asyncio.run`` per call
# (as before) rebinds the driver to a dead loop and raises "Future attached to
# a different loop" once LangGraph's ToolNode dispatches tools across threads.
_loop: Optional[asyncio.AbstractEventLoop] = None
_loop_lock = threading.Lock()


def _get_loop() -> asyncio.AbstractEventLoop:
    global _loop
    with _loop_lock:
        if _loop is None or _loop.is_closed():
            _loop = asyncio.new_event_loop()
            threading.Thread(target=_loop.run_forever, daemon=True).start()
        return _loop


def _run_async(coro):
    loop = _get_loop()
    return asyncio.run_coroutine_threadsafe(coro, loop).result()


_manager_cache = {}
_context: Optional[str] = None


class AmbiguousQueryReference(ValueError):
    """Raised when one Query reference matches multiple nodes."""

    def __init__(self, reference: str, matches: list[str]):
        """Store the ambiguous reference and all matching Query IDs."""
        super().__init__(
            f"Ambiguous query reference {reference!r}; use one exact query ID from {matches}"
        )
        self.reference = reference
        self.matches = matches


def set_context(context: Optional[str]) -> None:
    """Scope all graph access to a per-run ``context``.

    neo4j is a single shared database, so without a context every run writes
    into one global pool and text-based query resolution cross-matches nodes
    from earlier runs. Tagging each run's nodes with the output directory
    restores the per-run isolation the file-based store had.

    Args:
        context: The run's output-directory identifier, or ``None`` for the
            default global scope.
    """
    global _context
    if context != _context:
        _context = context
        _manager_cache.clear()


def _get_manager():
    from memory.graph import GraphManager
    cache_key = _context or "default"
    if cache_key not in _manager_cache:
        _manager_cache[cache_key] = GraphManager(context=_context)
    return _manager_cache[cache_key]


def clear_manager_cache():
    _manager_cache.clear()


def clear_current_context() -> None:
    """Delete every graph node in the current non-empty run context."""
    if not _context:
        raise ValueError("Cannot clear an empty graph context")
    _run_async(_get_manager().clear_context())


def add_node(
    node_type: str,
    attributes: dict[str, Any],
    node_id: Optional[str] = None
) -> dict[str, Any]:
    if str(node_type).replace("_", "").lower() == "query":
        raise ValueError("Query nodes must be created through create_query_child")
    manager = _get_manager()
    return _run_async(manager.add_node(node_type, attributes, node_id))


def upsert_node(
    node_type: str,
    attributes: dict[str, Any],
    dedupe_key: Optional[str] = None
) -> dict[str, Any]:
    manager = _get_manager()
    return _run_async(manager.upsert_node(node_type, attributes, dedupe_key))


def add_edge(
    source_id: str,
    target_id: str,
    edge_type: str,
    attributes: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    manager = _get_manager()
    return _run_async(manager.add_edge(source_id, target_id, edge_type, attributes))


def get_node(node_id: str) -> dict[str, Any]:
    manager = _get_manager()
    return _run_async(manager.get_node(node_id))


def search_nodes(node_type: str, filter: dict[str, Any]) -> list[dict[str, Any]]:
    manager = _get_manager()
    return _run_async(manager.search_node(node_type, filter))


def resolve_query_reference(reference: str) -> Optional[str]:
    """Resolve a Query handle or node-ID variant without guessing ambiguity."""
    if not reference:
        return None
    node = get_node(reference) or {}
    if str(node.get("type") or "").lower() == "query":
        return reference
    queries = search_nodes("query", {})

    def unique(matches: list[dict[str, Any]]) -> Optional[str]:
        ids = [item.get("id") for item in matches if item.get("id")]
        if len(ids) > 1:
            raise AmbiguousQueryReference(reference, ids)
        return ids[0] if ids else None

    resolved = unique([item for item in queries if item.get("handle") == reference])
    if resolved:
        return resolved
    resolved = unique([
        item for item in queries
        if str(item.get("id") or "").startswith(reference)
        or reference.startswith(str(item.get("id") or ""))
    ])
    if resolved:
        return resolved
    suffix = reference.rsplit("_", 1)[-1]
    if suffix and suffix != reference:
        resolved = unique([
            item for item in queries
            if str(item.get("id") or "").rsplit("_", 1)[-1] == suffix
        ])
        if resolved:
            return resolved
    return unique([
        item for item in queries
        if item.get("text")
        and (
            item["text"] == reference
            or reference in item["text"]
            or item["text"] in reference
        )
    ])


def get_subgraph(node_id: str, depth: int = 2) -> dict[str, Any]:
    manager = _get_manager()
    return _run_async(manager.get_subgraph(node_id, depth))


def get_all_nodes() -> list[dict[str, Any]]:
    """Return every node in the current run context."""
    return _run_async(_get_manager().get_all_nodes())


def get_all_edges() -> list[dict[str, Any]]:
    """Return every edge in the current run context."""
    return _run_async(_get_manager().get_all_edges())


def get_node_edges(node_id: str, direction: str = "both") -> list[dict[str, Any]]:
    """Return edges touching a node in the requested direction."""
    return _run_async(_get_manager().get_node_edges(node_id, direction))


def claim_query_search(query_id: str, goal_id: str) -> dict[str, Any]:
    """Atomically claim a Query and reserve one root search round."""
    return _run_async(_get_manager().claim_query_search(query_id, goal_id))


def increment_successful_search_rounds(goal_id: str) -> int:
    """Atomically increment the root's successful SearchRun count."""
    return _run_async(_get_manager().increment_successful_search_rounds(goal_id))


def save_graph() -> None:
    manager = _get_manager()
    return _run_async(manager.save())


def export_graph_jsonl(file_path: str) -> int:
    """Dump the current context's graph to a JSONL file for the viewer.

    Writes the marker line followed by one ``"kind": "node"`` / ``"kind":
    "edge"`` object per line — the format ``graph_viewer.html`` loads. neo4j is
    the source of truth now, so this is an export step (the old file-based store
    saved on every mutation; the migration dropped that, leaving the promised
    ``research_graph.jsonl`` unwritten).

    Args:
        file_path: Destination ``.jsonl`` path.

    Returns:
        The number of node + edge lines written.
    """
    import json

    manager = _get_manager()
    nodes = _run_async(manager.get_all_nodes())
    edges = _run_async(manager.get_all_edges())
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "_graphresearcher", "source": "graph-researcher"}, ensure_ascii=False) + "\n")
        for node in nodes:
            f.write(json.dumps({"kind": "node", **node}, ensure_ascii=False) + "\n")
        for edge in edges:
            f.write(json.dumps({"kind": "edge", **edge}, ensure_ascii=False) + "\n")
    return len(nodes) + len(edges)


def create_user_request(
    request: str,
    research_goal: Optional[str] = None,
    language: Optional[str] = None,
    **attributes: Any,
) -> dict[str, Any]:
    manager = _get_manager()
    attributes = {"request": request, **attributes}
    if research_goal:
        attributes["research_goal"] = research_goal
    if language:
        attributes["language"] = language
    return _run_async(manager.add_node(NodeType.USER_REQUEST, attributes))


def _create_query(
    text: str,
    status: str = "pending",
    parent_id: Optional[str] = None,
    priority: Optional[float] = None,
    priority_tier: Optional[str] = None,
    sem: Optional[float] = None,
    handle: Optional[str] = None,
    **extra: Any,
) -> dict[str, Any]:
    manager = _get_manager()
    attributes: dict[str, Any] = {"text": text, "status": status, **extra}
    if priority is not None:
        attributes["priority"] = priority
    if priority_tier is not None:
        attributes["priority_tier"] = priority_tier
    if sem is not None:
        attributes["sem"] = sem
    if handle is not None:
        attributes["handle"] = handle
    query_id = _run_async(manager.add_node(NodeType.QUERY, attributes))
    if parent_id:
        parent = get_node(parent_id)
        edge_type = EdgeType.HAS_QUERY if parent.get("type") == NodeType.USER_REQUEST.value else EdgeType.PARENT_OF
        _run_async(manager.add_edge(parent_id, query_id, edge_type))
    return query_id


def create_query_child(
    parent_id: str,
    text: str,
    importance: str,
    acceptance_criteria: Optional[list[str]] = None,
    gap_ids: Optional[list[str]] = None,
    **attributes: Any,
) -> str:
    """Create one structurally valid Query child and bind its assigned gaps."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Query text must be a non-empty string")
    if importance not in {"core", "supporting", "peripheral"}:
        importance = "supporting"
    if acceptance_criteria is not None and not isinstance(acceptance_criteria, list):
        raise ValueError("acceptance_criteria must be a list")
    if gap_ids is not None and not isinstance(gap_ids, list):
        raise ValueError("gap_ids must be a list")
    parent = get_node(parent_id)
    if parent.get("type") not in {NodeType.USER_REQUEST.value, NodeType.QUERY.value}:
        raise ValueError(f"Query parent must be UserRequest or Query: {parent_id!r}")
    if parent.get("type") == NodeType.QUERY.value and not gap_ids:
        raise ValueError("Non-root Query children must address at least one gap")
    validated_gaps = []
    for gap_id in gap_ids or []:
        gap = get_node(gap_id)
        if gap.get("type") != NodeType.ANALYSIS.value or gap.get("analysis_type") != "gap":
            raise ValueError(f"Assigned gap is not an Analysis(gap): {gap_id!r}")
        validated_gaps.append(gap)

    from tools import convergence

    children = get_query_children(parent_id)
    parent_handle = parent.get("handle")
    handle = f"{parent_handle}.{len(children) + 1}" if parent_handle else f"q{len(children) + 1}"
    depth = int(parent.get("depth") or 0) + 1
    priority, tier, sem = convergence.compute_priority(importance, parent_id)
    required = bool(attributes.pop("required_for_parent", False))
    query_id = _create_query(
        text=text,
        status="pending",
        parent_id=parent_id,
        priority=priority,
        priority_tier=tier,
        sem=sem,
        handle=handle,
        depth=depth,
        importance=importance,
        required_for_parent=required,
        acceptance_criteria=acceptance_criteria or [],
        search_attempts=0,
        successful_search_runs=0,
        **attributes,
    )
    for gap in validated_gaps:
        gap_id = gap["id"]
        add_edge(query_id, gap_id, EdgeType.ADDRESSES_GAP)
        upsert_node(NodeType.ANALYSIS, {"status": "assigned"}, gap_id)
    return query_id


def transition_query(query_id: str, status: str, **attributes: Any) -> str:
    """Validate and apply one legal Query state transition."""
    query = get_node(query_id)
    if query.get("type") != NodeType.QUERY.value:
        raise ValueError(f"Query transition target must be a Query: {query_id!r}")
    current = query.get("status")
    if status not in _QUERY_TRANSITIONS.get(current, set()):
        raise ValueError(f"Invalid Query state transition: {current} -> {status}")
    return upsert_node(NodeType.QUERY, {"status": status, **attributes}, query_id)


def create_source(
    url: str,
    title: Optional[str] = None,
    source_type: Optional[str] = None,
    **attributes: Any,
) -> dict[str, Any]:
    manager = _get_manager()
    attributes = {"url": url, **attributes}
    if title:
        attributes["title"] = title
    if source_type:
        attributes["source_type"] = source_type
    # Auto-estimate and store source credibility score
    credibility = _estimate_source_credibility(url, source_type)
    attributes["credibility_score"] = credibility
    return _run_async(manager.add_node(NodeType.SOURCE, attributes))


def create_document(
    text: str,
    source_id: Optional[str] = None
) -> dict[str, Any]:
    if source_id and get_node(source_id).get("type") != NodeType.SOURCE.value:
        raise ValueError(f"Document source must be Source: {source_id!r}")
    manager = _get_manager()
    attributes = {"text": text}
    if source_id:
        attributes["source_id"] = source_id
    doc_id = _run_async(manager.add_node(NodeType.DOCUMENT, attributes))
    if source_id:
        _run_async(manager.add_edge(source_id, doc_id, EdgeType.HAS_DOCUMENT))
    return doc_id


def _stable_text_key(prefix: str, *parts: Any) -> str:
    normalized = "\n".join(" ".join(str(part or "").split()).lower() for part in parts)
    return f"{prefix}:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:24]}"


def create_statement(
    text: str,
    document_id: str,
    source_id: Optional[str] = None,
    qualifiers: Optional[list[str]] = None,
    limitations: Optional[list[str]] = None,
    confidence: Optional[str] = None,
    locator: Optional[str] = None,
    statement_key: Optional[str] = None,
    **attributes: Any,
) -> dict[str, Any]:
    if document_id and get_node(document_id).get("type") != NodeType.DOCUMENT.value:
        raise ValueError(f"Statement document must be Document: {document_id!r}")
    if source_id and get_node(source_id).get("type") != NodeType.SOURCE.value:
        raise ValueError(f"Statement source must be Source: {source_id!r}")
    statement_key = statement_key or _stable_text_key("statement", document_id, locator, text)
    matches = search_nodes("statement", {"statement_key": statement_key})
    if matches:
        statement_id = matches[0]["id"]
        upsert_node(NodeType.STATEMENT, {
            "text": text,
            "document_id": document_id,
            "source_id": source_id,
            "qualifiers": qualifiers or [],
            "limitations": limitations or [],
            "confidence": confidence,
            "locator": locator,
            "statement_key": statement_key,
            **attributes,
        }, statement_id)
    else:
        manager = _get_manager()
        statement_id = _run_async(manager.add_node(NodeType.STATEMENT, {
            "text": text,
            "document_id": document_id,
            "source_id": source_id,
            "qualifiers": qualifiers or [],
            "limitations": limitations or [],
            "confidence": confidence,
            "locator": locator,
            "statement_key": statement_key,
            **attributes,
        }))
    _run_async(_get_manager().add_edge(document_id, statement_id, EdgeType.EXTRACTED_STATEMENT))
    if source_id:
        _run_async(_get_manager().add_edge(source_id, statement_id, EdgeType.SUPPORTED_BY))
    return statement_id


def create_claim(
    statement: str,
    document_id: Optional[str] = None,
    source_id: Optional[str] = None,
    claim_key: Optional[str] = None,
    canonical_text: Optional[str] = None,
    **attributes: Any,
) -> dict[str, Any]:
    if document_id and get_node(document_id).get("type") != NodeType.DOCUMENT.value:
        raise ValueError(f"Claim document must be Document: {document_id!r}")
    if source_id and get_node(source_id).get("type") != NodeType.SOURCE.value:
        raise ValueError(f"Claim source must be Source: {source_id!r}")
    canonical_text = canonical_text or statement
    claim_key = claim_key or _stable_text_key("claim", canonical_text)
    properties = {
        "statement": statement,
        "canonical_text": canonical_text,
        "claim_key": claim_key,
        "status": attributes.pop("status", "normalized"),
        **attributes,
    }
    manager = _get_manager()
    matches = search_nodes("claim", {"claim_key": claim_key})
    if matches:
        claim_id = matches[0]["id"]
        upsert_node(NodeType.CLAIM, properties, claim_id)
    else:
        claim_id = _run_async(manager.add_node(NodeType.CLAIM, properties))
    if document_id:
        _run_async(manager.add_edge(document_id, claim_id, EdgeType.CLAIMED_BY))
    if source_id:
        _run_async(manager.add_edge(source_id, claim_id, EdgeType.SUPPORTED_BY))
    return claim_id


def create_evidence(
    claim: Optional[str] = None,
    document_id: Optional[str] = None,
    source_id: Optional[str] = None,
    supports_claim_id: Optional[str] = None,
    text: Optional[str] = None,
    evidence_type: Optional[str] = None,
    confidence: Optional[str] = None,
    qualifiers: Optional[list[str]] = None,
    limitations: Optional[list[str]] = None,
    locator: Optional[str] = None,
    evidence_key: Optional[str] = None,
    **attributes: Any,
) -> dict[str, Any]:
    if document_id and get_node(document_id).get("type") != NodeType.DOCUMENT.value:
        raise ValueError(f"Evidence document must be Document: {document_id!r}")
    if source_id and get_node(source_id).get("type") != NodeType.SOURCE.value:
        raise ValueError(f"Evidence source must be Source: {source_id!r}")
    if supports_claim_id and get_node(supports_claim_id).get("type") != NodeType.CLAIM.value:
        raise ValueError(f"Evidence claim target must be Claim: {supports_claim_id!r}")
    evidence_text = text or claim or ""
    evidence_key = evidence_key or _stable_text_key("evidence", document_id, locator, evidence_text)
    manager = _get_manager()
    properties = {
        "text": evidence_text,
        "claim": evidence_text,  # legacy report/readiness code still reads this field.
        "status": "pending",
        "document_id": document_id,
        "source_id": source_id,
        "evidence_type": evidence_type,
        "confidence": confidence,
        "qualifiers": qualifiers or [],
        "limitations": limitations or [],
        "locator": locator,
        "evidence_key": evidence_key,
        **attributes,
    }
    matches = search_nodes("evidence", {"evidence_key": evidence_key})
    if matches:
        evidence_id = matches[0]["id"]
        upsert_node(NodeType.EVIDENCE, properties, evidence_id)
    else:
        evidence_id = _run_async(manager.add_node(NodeType.EVIDENCE, properties))
    if document_id:
        _run_async(manager.add_edge(document_id, evidence_id, EdgeType.HAS_EVIDENCE))
    if source_id:
        _run_async(manager.add_edge(source_id, evidence_id, EdgeType.SUPPORTED_BY))
    if supports_claim_id:
        _run_async(manager.add_edge(evidence_id, supports_claim_id, EdgeType.SUPPORTED_BY))
    return evidence_id


def create_conflict(
    description: str,
    evidence_ids: list[str],
    conflict_type: str = "factual",
    resolution_status: str = "unresolved"
) -> dict[str, Any]:
    if resolution_status not in {"unresolved", "investigating", "resolved", "disclosed"}:
        raise ValueError(f"Invalid conflict status: {resolution_status!r}")
    if any(get_node(eid).get("type") != NodeType.EVIDENCE.value for eid in evidence_ids):
        raise ValueError("Conflict evidence_refs must all reference Evidence nodes")
    manager = _get_manager()
    conflict_id = _run_async(manager.add_node(NodeType.CONFLICT, {
        "description": description,
        "conflict_type": conflict_type,
        "resolution_status": resolution_status
    }))
    for evidence_id in evidence_ids:
        _run_async(manager.add_edge(conflict_id, evidence_id, EdgeType.HAS_CONFLICT))
    return conflict_id


def create_analysis(
    text: str,
    query_id: Optional[str] = None,
    analysis_type: str = "insight",
    **attributes: Any,
) -> dict[str, Any]:
    if analysis_type not in {"gap", "insight", "objective"}:
        raise ValueError(f"Invalid analysis_type: {analysis_type!r}")
    if query_id:
        parent_type = get_node(query_id).get("type")
        allowed = {NodeType.QUERY.value}
        if analysis_type in {"gap", "objective"}:
            allowed.add(NodeType.USER_REQUEST.value)
        if parent_type not in allowed:
            raise ValueError(f"Invalid Analysis parent type for {query_id!r}")
    manager = _get_manager()
    analysis_id = _run_async(manager.add_node(
        NodeType.ANALYSIS,
        {"text": text, "analysis_type": analysis_type, **attributes},
    ))
    if query_id:
        edge_type = {
            "gap": EdgeType.HAS_GAP,
            "objective": EdgeType.HAS_OBJECTIVE,
        }.get(analysis_type, EdgeType.HAS_ANALYSIS)
        _run_async(manager.add_edge(query_id, analysis_id, edge_type))
    return analysis_id


def create_report_section(
    title: str,
    content: str,
    section_type: Optional[str] = None
) -> dict[str, Any]:
    manager = _get_manager()
    attributes = {"title": title, "content": content}
    if section_type:
        attributes["section_type"] = section_type
    return _run_async(manager.add_node(NodeType.REPORT_SECTION, attributes))


def bind_evidence_to_section(
    section_id: str,
    evidence_ids: list[str],
    claim_ids: Optional[list[str]] = None
) -> None:
    if get_node(section_id).get("type") != NodeType.REPORT_SECTION.value:
        raise ValueError(f"USES source must be a ReportSection: {section_id!r}")
    if any(get_node(eid).get("type") != NodeType.EVIDENCE.value for eid in evidence_ids):
        raise ValueError("USES evidence targets must all be Evidence nodes")
    if any(get_node(cid).get("type") != NodeType.CLAIM.value for cid in claim_ids or []):
        raise ValueError("USES claim targets must all be Claim nodes")
    manager = _get_manager()
    for evidence_id in evidence_ids:
        _run_async(manager.add_edge(section_id, evidence_id, EdgeType.USES))
    if claim_ids:
        for claim_id in claim_ids:
            _run_async(manager.add_edge(section_id, claim_id, EdgeType.USES))


def get_pending_queries() -> list[dict[str, Any]]:
    manager = _get_manager()
    return _run_async(manager.search_node(NodeType.QUERY, {"status": "pending"}))


def get_query_subgraph(query_id: str, depth: int = 2) -> dict[str, Any]:
    manager = _get_manager()
    return _run_async(manager.get_subgraph(query_id, depth))


# The query hierarchy uses two edge types: HAS_QUERY (user_request -> initial
# query) and PARENT_OF (query -> follow-up query). Traversal must accept both;
# compared lower-cased so a stored "parent_of"/"PARENT_OF" both match.
_PARENT_EDGE_TYPES = {"has_query", "parent_of"}


def get_query_parent(query_id: str) -> Optional[str]:
    """Return the structural parent node ID of a query, or ``None``.

    Reached via an inbound ``HAS_QUERY`` edge (from the ``user_request`` goal,
    for initial queries) or an inbound ``PARENT_OF`` edge (from another query,
    for follow-ups). Uses an explicit ``"in"`` direction because
    ``get_node_edges`` ``"both"`` mode only matches incoming edges.

    Args:
        query_id: The query node ID.

    Returns:
        The parent node ID, or ``None`` if the query has no structural parent.
    """
    manager = _get_manager()
    edges = _run_async(manager.get_node_edges(query_id, direction="in"))
    for edge in edges:
        if str(edge.get("type", "")).lower() in _PARENT_EDGE_TYPES:
            return edge.get("source")
    return None


def get_query_children(query_id: str) -> list[str]:
    """Return the child query node IDs of a goal or query.

    Follows outbound ``HAS_QUERY`` / ``PARENT_OF`` edges, so it works for both
    a ``user_request`` goal (its initial queries) and a ``query`` (its
    follow-ups).

    Args:
        query_id: The parent node ID (a ``user_request`` or ``query``).

    Returns:
        A list of child query node IDs (empty if none).
    """
    manager = _get_manager()
    edges = _run_async(manager.get_node_edges(query_id, direction="out"))
    return [
        edge.get("target")
        for edge in edges
        if str(edge.get("type", "")).lower() in _PARENT_EDGE_TYPES
    ]


def validate_query_tree() -> dict[str, Any]:
    """Validate the current run's Query hierarchy as a strict rooted tree."""
    nodes = {n["id"]: n for n in get_all_nodes()}
    queries = {nid: n for nid, n in nodes.items() if n.get("type") == NodeType.QUERY.value}
    parent_edges: dict[str, list[str]] = {qid: [] for qid in queries}
    invalid_parent_edges: list[dict[str, str]] = []
    for edge in get_all_edges():
        edge_type = str(edge.get("type", "")).lower()
        if edge_type not in _PARENT_EDGE_TYPES:
            continue
        target = edge.get("target")
        source = edge.get("source")
        if target in queries:
            source_type = nodes.get(source, {}).get("type")
            expected_type = NodeType.USER_REQUEST.value if edge_type == "has_query" else NodeType.QUERY.value
            if source_type != expected_type:
                invalid_parent_edges.append({
                    "source": source,
                    "target": target,
                    "type": str(edge.get("type")),
                })
                continue
            parent_edges[target].append(source)

    orphans = [qid for qid, parents in parent_edges.items() if not parents]
    multi_parent = [qid for qid, parents in parent_edges.items() if len(parents) > 1]
    cycles: list[str] = []
    for qid in queries:
        seen: set[str] = set()
        current = qid
        while parent_edges.get(current):
            current = parent_edges[current][0]
            if current in seen:
                cycles.append(qid)
                break
            seen.add(current)
    invalid_handles = [
        qid for qid, node in queries.items()
        if not re.fullmatch(r"q\d+(?:\.\d+)*", str(node.get("handle") or ""))
    ]
    handles: dict[str, list[str]] = {}
    for qid, node in queries.items():
        handles.setdefault(str(node.get("handle") or ""), []).append(qid)
    duplicate_handles = [
        {"handle": handle, "query_ids": ids}
        for handle, ids in handles.items()
        if handle and len(ids) > 1
    ]
    goals = [node["id"] for node in nodes.values() if node.get("type") == NodeType.USER_REQUEST.value]
    multiple_goals = goals if len(goals) > 1 else []
    return {
        "valid": not (
            orphans or multi_parent or cycles or invalid_handles or invalid_parent_edges
            or duplicate_handles or multiple_goals
        ),
        "orphans": orphans,
        "multi_parent_queries": multi_parent,
        "cycles": sorted(set(cycles)),
        "invalid_handles": invalid_handles,
        "duplicate_handles": duplicate_handles,
        "multiple_goals": multiple_goals,
        "invalid_parent_edges": invalid_parent_edges,
    }


def get_query_evaluation_subgraph(query_id: str) -> dict[str, Any]:
    """Return only evidence owned by a Query plus direct-child summaries."""
    query = get_node(query_id)
    if query.get("type") != NodeType.QUERY.value:
        return {"query": query, "nodes": [], "edges": [], "children": []}

    nodes = {n["id"]: n for n in get_all_nodes()}
    edges = get_all_edges()
    selected_ids = {query_id}
    selected_edges: list[dict[str, Any]] = []

    run_ids = {
        e["target"] for e in edges
        if e.get("source") == query_id and str(e.get("type", "")).lower() == "searched_by"
        and nodes.get(e["target"], {}).get("status") == "succeeded"
    }
    selected_ids.update(run_ids)
    for edge in edges:
        etype = str(edge.get("type", "")).lower()
        run_owned = edge.get("source") in run_ids and etype in {"found_source", "produced"}
        query_owned = edge.get("source") == query_id and etype in {
            "searched_by",
            "has_gap",
            "has_analysis",
        }
        if run_owned or query_owned:
            selected_ids.add(edge["target"])
            selected_edges.append(edge)

    produced_ids = set(selected_ids)
    for edge in edges:
        etype = str(edge.get("type", "")).lower()
        if etype == "has_conflict" and edge.get("target") in produced_ids:
            selected_ids.add(edge["source"])
            selected_edges.append(edge)
        elif (
            edge.get("source") in selected_ids
            and etype in {"normalized_to", "supported_by", "contradicted_by", "qualified_by"}
            and nodes.get(edge.get("target"), {}).get("type") == NodeType.CLAIM.value
        ):
            selected_ids.add(edge["target"])
            selected_edges.append(edge)
        elif edge.get("source") in selected_ids and edge.get("target") in selected_ids:
            selected_edges.append(edge)

    for edge in edges:
        if edge.get("source") in selected_ids and edge.get("target") in selected_ids:
            selected_edges.append(edge)

    deduped_edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[Any, Any, Any]] = set()
    for edge in selected_edges:
        key = (edge.get("source"), edge.get("target"), edge.get("type"))
        if key in seen_edges:
            continue
        seen_edges.add(key)
        deduped_edges.append(edge)

    children = []
    for child_id in get_query_children(query_id):
        child = nodes.get(child_id, {})
        gap_ids = [
            e["target"] for e in edges
            if e.get("source") == child_id and str(e.get("type", "")).lower() == "addresses_gap"
        ]
        children.append({
            "id": child_id,
            "handle": child.get("handle"),
            "text": child.get("text"),
            "status": child.get("status"),
            "sufficiency_score": child.get("sufficiency_score"),
            "required_for_parent": child.get("required_for_parent"),
            "gap_ids": gap_ids,
        })
    return {
        "query": query,
        "nodes": [nodes[nid] for nid in selected_ids if nid in nodes],
        "edges": deduped_edges,
        "children": children,
    }


def list_graph_databases() -> dict[str, Any]:
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    database = os.environ.get("NEO4J_DATABASE", "neo4j")
    return {
        "databases": [database],
        "location": uri,
        "type": "neo4j"
    }
