import asyncio
import os
import threading
from typing import Any, Optional

from memory.graph import NodeType, EdgeType, GraphNode, GraphEdge


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


def set_context(context: Optional[str]) -> None:
    """Scope all graph access to a per-run ``context``.

    neo4j is a single shared database, so without a context every run writes
    into one global pool and text-based query resolution cross-matches nodes
    from earlier runs. Tagging each run's nodes with a context (the run's
    output directory) restores the per-run isolation the file-based store had.

    Args:
        context: A stable per-run identifier (the run's output directory), or
            ``None`` for the default global scope.
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


def add_node(
    node_type: str,
    attributes: dict[str, Any],
    node_id: Optional[str] = None
) -> dict[str, Any]:
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


def get_subgraph(node_id: str, depth: int = 2) -> dict[str, Any]:
    manager = _get_manager()
    return _run_async(manager.get_subgraph(node_id, depth))


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
    language: Optional[str] = None
) -> dict[str, Any]:
    manager = _get_manager()
    attributes = {"request": request}
    if research_goal:
        attributes["research_goal"] = research_goal
    if language:
        attributes["language"] = language
    return _run_async(manager.add_node(NodeType.USER_REQUEST, attributes))


def create_query(
    text: str,
    status: str = "pending",
    parent_id: Optional[str] = None
) -> dict[str, Any]:
    manager = _get_manager()
    query_id = _run_async(manager.add_node(NodeType.QUERY, {"text": text, "status": status}))
    if parent_id:
        _run_async(manager.add_edge(parent_id, query_id, EdgeType.HAS_QUERY))
    return query_id


def create_source(
    url: str,
    title: Optional[str] = None,
    source_type: Optional[str] = None
) -> dict[str, Any]:
    manager = _get_manager()
    attributes = {"url": url}
    if title:
        attributes["title"] = title
    if source_type:
        attributes["source_type"] = source_type
    return _run_async(manager.add_node(NodeType.SOURCE, attributes))


def create_document(
    text: str,
    source_id: Optional[str] = None
) -> dict[str, Any]:
    manager = _get_manager()
    attributes = {"text": text}
    if source_id:
        attributes["source_id"] = source_id
    doc_id = _run_async(manager.add_node(NodeType.DOCUMENT, attributes))
    if source_id:
        _run_async(manager.add_edge(source_id, doc_id, EdgeType.HAS_DOCUMENT))
    return doc_id


def create_claim(
    statement: str,
    document_id: Optional[str] = None,
    source_id: Optional[str] = None
) -> dict[str, Any]:
    manager = _get_manager()
    claim_id = _run_async(manager.add_node(NodeType.CLAIM, {"statement": statement, "status": "pending"}))
    if document_id:
        _run_async(manager.add_edge(document_id, claim_id, EdgeType.CLAIMED_BY))
    if source_id:
        _run_async(manager.add_edge(source_id, claim_id, EdgeType.SUPPORTED_BY))
    return claim_id


def create_evidence(
    claim: str,
    document_id: Optional[str] = None,
    source_id: Optional[str] = None,
    supports_claim_id: Optional[str] = None
) -> dict[str, Any]:
    manager = _get_manager()
    evidence_id = _run_async(manager.add_node(NodeType.EVIDENCE, {"claim": claim, "status": "pending"}))
    if document_id:
        _run_async(manager.add_edge(document_id, evidence_id, EdgeType.EXTRACTED_STATEMENT))
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
    query_id: Optional[str] = None
) -> dict[str, Any]:
    manager = _get_manager()
    analysis_id = _run_async(manager.add_node(NodeType.ANALYSIS, {"text": text}))
    if query_id:
        _run_async(manager.add_edge(query_id, analysis_id, EdgeType.RESOLVES_GAP))
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


def mark_query_status(query_id: str, status: str) -> dict[str, Any]:
    manager = _get_manager()
    return _run_async(manager.upsert_node(NodeType.QUERY, {"status": status}, dedupe_key=query_id))


def list_graph_databases() -> dict[str, Any]:
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    database = os.environ.get("NEO4J_DATABASE", "neo4j")
    return {
        "databases": [database],
        "location": uri,
        "type": "neo4j"
    }
