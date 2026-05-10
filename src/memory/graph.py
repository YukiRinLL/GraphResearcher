# src/memory/graph.py
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal
from datetime import datetime


class NodeType(StrEnum):
    USER_REQUEST = "user_request" # unique node representing the original user request and research goal
    QUERY = "query"
    SEARCH_RUN = "search_run"
    SOURCE = "source"
    DOCUMENT = "document"
    STATEMENT = "statement"
    EVIDENCE = "evidence"
    ENTITY = "entity"
    CONFLICT = "conflict"
    ANALYSIS = "analysis"
    REPORT_SECTION = "report_section"


class EdgeType(StrEnum):
    HAS_QUERY = "has_query"
    PARENT_OF = "parent_of"
    SEARCHED_BY = "searched_by"
    FOUND_SOURCE = "found_source"
    HAS_DOCUMENT = "has_document"
    EXTRACTED_STATEMENT = "extracted_statement"
    SUPPORTED_BY = "supported_by"
    CONTRADICTED_BY = "contradicted_by"
    MENTIONS = "mentions"
    RELATED_TO = "related_to"
    HAS_CONFLICT = "has_conflict"
    RESOLVES_GAP = "resolves_gap"
    USES = "uses"


@dataclass
class GraphNode:
    id: str
    type: NodeType
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    source: str
    target: str
    type: EdgeType
    properties: dict[str, Any] = field(default_factory=dict)


class GraphManager:
    def add_node(self, node_type: str, attributes: dict, node_id: str | None = None) -> str: ...
    def upsert_node(self, node_type: str, attributes: dict, dedupe_key: str | None = None) -> str: ...
    def add_edge(self, source_id: str, target_id: str, edge_type: str, attributes: dict | None = None) -> str: ...
    def get_node(self, node_id: str) -> dict: ...
    def search_node(self, node_type: str, filter: dict) -> list[dict]: ...
    def get_subgraph(self, node_id: str, depth: int = 2) -> dict: ...
    def save(self) -> None: ...
