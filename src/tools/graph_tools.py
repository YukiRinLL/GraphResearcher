import asyncio
import os
from typing import Any, Optional

try:
    import nest_asyncio
    nest_asyncio.apply()
    HAS_NEST_ASYNCIO = True
except ImportError:
    HAS_NEST_ASYNCIO = False

from memory.graph import NodeType, EdgeType, GraphNode, GraphEdge


def _run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    if HAS_NEST_ASYNCIO:
        return asyncio.run(coro)

    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(asyncio.run, coro)
        return future.result()


_manager_cache = {}


def _get_manager():
    from memory.graph import GraphManager
    cache_key = "default"
    if cache_key not in _manager_cache:
        _manager_cache[cache_key] = GraphManager()
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


def create_evidence(
    claim: str,
    document_id: Optional[str] = None,
    source_id: Optional[str] = None
) -> dict[str, Any]:
    manager = _get_manager()
    evidence_id = _run_async(manager.add_node(NodeType.EVIDENCE, {"claim": claim, "status": "pending"}))
    if document_id:
        _run_async(manager.add_edge(document_id, evidence_id, EdgeType.EXTRACTED_STATEMENT))
    if source_id:
        _run_async(manager.add_edge(source_id, evidence_id, EdgeType.SUPPORTED_BY))
    return evidence_id


def create_conflict(
    description: str,
    evidence_ids: list[str]
) -> dict[str, Any]:
    manager = _get_manager()
    conflict_id = _run_async(manager.add_node(NodeType.CONFLICT, {"description": description}))
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
