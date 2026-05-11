# src/memory/graph.py
import asyncio
import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Optional


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

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type.value,
            **self.properties
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GraphNode":
        return cls(
            id=data["id"],
            type=NodeType(data["type"]),
            properties={k: v for k, v in data.items() if k not in ("id", "type")}
        )


@dataclass
class GraphEdge:
    source: str
    target: str
    type: EdgeType
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "type": self.type.value,
            **self.properties
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GraphEdge":
        return cls(
            source=data["source"],
            target=data["target"],
            type=EdgeType(data["type"]),
            properties={k: v for k, v in data.items() if k not in ("source", "target", "type")}
        )


FILE_MARKER = {"type": "_graphresearcher", "source": "graph-researcher"}


def get_default_graph_cache_dir() -> Path:
    if os.environ.get("REPO_BASE_DIR"):
        return Path(os.environ["REPO_BASE_DIR"]) / ".graphresearcher"
    return Path.home() / ".graphresearcher"


def get_graph_file_path(cache_dir: Path, context: Optional[str] = None) -> Path:
    filename = "research_graph.jsonl" if context is None else f"research_graph-{context}.jsonl"
    return cache_dir / filename


def get_index_file_path(cache_dir: Path, context: Optional[str] = None) -> Path:
    filename = "index.pkl" if context is None else f"index-{context}.pkl"
    return cache_dir / filename


class GraphManager:
    def __init__(self, cache_dir: Optional[str] = None, context: Optional[str] = None):
        if cache_dir:
            self._cache_dir = Path(cache_dir)
        else:
            self._cache_dir = get_default_graph_cache_dir()
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._context = context

        self._nodes: dict[str, GraphNode] = {}
        self._edges: list[GraphEdge] = []
        self._loaded = False
        self._file_mtime: Optional[float] = None

        self._out_edges: dict[str, list[GraphEdge]] = {}
        self._in_edges: dict[str, list[GraphEdge]] = {}

    async def _ensure_loaded(self) -> None:
        if self._loaded:
            file_path = get_graph_file_path(self._cache_dir, self._context)
            try:
                current_mtime = os.path.getmtime(file_path) if file_path.exists() else 0.0
                if current_mtime != self._file_mtime:
                    await self._load_from_file()
            except OSError:
                await self._load_from_file()
        else:
            await self._load_from_file()

    async def _load_from_file(self) -> None:
        file_path = get_graph_file_path(self._cache_dir, self._context)

        self._nodes.clear()
        self._edges.clear()
        self._out_edges.clear()
        self._in_edges.clear()

        if not file_path.exists():
            self._loaded = True
            self._file_mtime = 0.0
            return

        try:
            self._file_mtime = os.path.getmtime(file_path)

            with open(file_path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f if line.strip()]

            if not lines:
                self._loaded = True
                return

            first_line = json.loads(lines[0])
            if first_line.get("type") != "_graphresearcher" or first_line.get("source") != "graph-researcher":
                raise ValueError(f"Invalid file marker in {file_path}")

            for line in lines[1:]:
                try:
                    item = json.loads(line)
                    if item.get("kind") == "node":
                        node = GraphNode.from_dict(item)
                        self._nodes[node.id] = node
                    elif item.get("kind") == "edge":
                        edge = GraphEdge.from_dict(item)
                        self._edges.append(edge)
                        self._out_edges.setdefault(edge.source, []).append(edge)
                        self._in_edges.setdefault(edge.target, []).append(edge)
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue

            self._loaded = True

        except FileNotFoundError:
            self._loaded = True
            self._file_mtime = 0.0

    async def _save_to_file(self) -> None:
        file_path = get_graph_file_path(self._cache_dir, self._context)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        lines = [json.dumps(FILE_MARKER)]

        for node in self._nodes.values():
            lines.append(json.dumps({"kind": "node", **node.to_dict()}))

        for edge in self._edges:
            lines.append(json.dumps({"kind": "edge", **edge.to_dict()}))

        with open(file_path, 'w', encoding='utf-8') as f:
            for line in lines:
                f.write(line + '\n')

        try:
            self._file_mtime = os.path.getmtime(file_path)
        except OSError:
            pass

    def _generate_id(self) -> str:
        return f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{uuid.uuid4().hex[:8]}"

    async def add_node(self, node_type: str, attributes: dict, node_id: Optional[str] = None) -> str:
        await self._ensure_loaded()

        if node_id is None:
            node_id = self._generate_id()

        node = GraphNode(
            id=node_id,
            type=NodeType(node_type),
            properties=attributes
        )
        self._nodes[node_id] = node
        await self._save_to_file()
        return node_id

    async def upsert_node(self, node_type: str, attributes: dict, dedupe_key: Optional[str] = None) -> str:
        await self._ensure_loaded()

        if dedupe_key and dedupe_key in self._nodes:
            node = self._nodes[dedupe_key]
            node.properties.update(attributes)
            await self._save_to_file()
            return dedupe_key

        return await self.add_node(node_type, attributes)

    async def add_edge(self, source_id: str, target_id: str, edge_type: str, attributes: Optional[dict] = None) -> str:
        await self._ensure_loaded()

        edge = GraphEdge(
            source=source_id,
            target=target_id,
            type=EdgeType(edge_type),
            properties=attributes or {}
        )

        self._edges.append(edge)
        self._out_edges.setdefault(source_id, []).append(edge)
        self._in_edges.setdefault(target_id, []).append(edge)

        await self._save_to_file()
        return f"{source_id}_{edge_type}_{target_id}"

    async def get_node(self, node_id: str) -> dict:
        await self._ensure_loaded()

        if node_id in self._nodes:
            return self._nodes[node_id].to_dict()
        return {}

    async def search_node(self, node_type: str, filter: dict) -> list[dict]:
        await self._ensure_loaded()

        results = []
        for node in self._nodes.values():
            if node.type.value == node_type:
                match = True
                for key, value in filter.items():
                    if key not in node.properties or node.properties[key] != value:
                        match = False
                        break
                if match:
                    results.append(node.to_dict())
        return results

    async def get_subgraph(self, node_id: str, depth: int = 2) -> dict:
        await self._ensure_loaded()

        if node_id not in self._nodes:
            return {"nodes": [], "edges": []}

        visited_nodes = set()
        visited_edges = set()
        nodes_to_visit = [(node_id, 0)]

        while nodes_to_visit:
            current_id, current_depth = nodes_to_visit.pop(0)
            if current_id in visited_nodes or current_depth > depth:
                continue

            visited_nodes.add(current_id)

            for edge in self._in_edges.get(current_id, []):
                edge_key = (edge.source, edge.type.value, edge.target)
                if edge_key not in visited_edges:
                    visited_edges.add(edge_key)
                    nodes_to_visit.append((edge.source, current_depth + 1))

            for edge in self._out_edges.get(current_id, []):
                edge_key = (edge.source, edge.type.value, edge.target)
                if edge_key not in visited_edges:
                    visited_edges.add(edge_key)
                    nodes_to_visit.append((edge.target, current_depth + 1))

        result_nodes = []
        for nid in visited_nodes:
            if nid in self._nodes:
                result_nodes.append(self._nodes[nid].to_dict())

        result_edges = []
        for edge in self._edges:
            edge_key = (edge.source, edge.type.value, edge.target)
            if edge_key in visited_edges:
                result_edges.append(edge.to_dict())

        return {"nodes": result_nodes, "edges": result_edges}

    async def save(self) -> None:
        await self._ensure_loaded()
        await self._save_to_file()

    async def get_all_nodes(self) -> list[dict]:
        await self._ensure_loaded()
        return [node.to_dict() for node in self._nodes.values()]

    async def get_all_edges(self) -> list[dict]:
        await self._ensure_loaded()
        return [edge.to_dict() for edge in self._edges]

    async def delete_node(self, node_id: str) -> None:
        await self._ensure_loaded()

        if node_id not in self._nodes:
            return

        del self._nodes[node_id]

        self._edges = [
            e for e in self._edges
            if e.source != node_id and e.target != node_id
        ]

        if node_id in self._out_edges:
            del self._out_edges[node_id]
        if node_id in self._in_edges:
            del self._in_edges[node_id]

        await self._save_to_file()

    async def get_node_edges(self, node_id: str, direction: str = "both") -> list[dict]:
        await self._ensure_loaded()

        edges = []
        if direction in ("out", "both"):
            for edge in self._out_edges.get(node_id, []):
                edges.append(edge.to_dict())
        if direction in ("in", "both"):
            for edge in self._in_edges.get(node_id, []):
                edges.append(edge.to_dict())
        return edges