# src/memory/graph.py
import asyncio
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Optional

try:
    from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False


class NodeType(StrEnum):
    USER_REQUEST = "user_request"
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


import logging
logger = logging.getLogger(__name__)


NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.environ.get("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD")
NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")


class GraphManager:
    def __init__(self,
                 uri: Optional[str] = None,
                 username: Optional[str] = None,
                 password: Optional[str] = None,
                 database: Optional[str] = None,
                 context: Optional[str] = None):
        if not NEO4J_AVAILABLE:
            raise ImportError("neo4j is not installed. Install with: pip install neo4j")

        self.uri = uri or NEO4J_URI
        self.username = username or NEO4J_USERNAME
        self.password = password or NEO4J_PASSWORD
        self.database = database or NEO4J_DATABASE
        self.context = context
        self._driver: Optional[AsyncDriver] = None
        self._lock = asyncio.Lock()

    async def _get_driver(self) -> AsyncDriver:
        async with self._lock:
            if self._driver is None:
                self._driver = AsyncGraphDatabase.driver(
                    self.uri,
                    auth=(self.username, self.password) if self.password else None
                )
            return self._driver

    async def _get_session(self) -> AsyncSession:
        driver = await self._get_driver()
        return driver.session(database=self.database)

    async def close(self) -> None:
        async with self._lock:
            if self._driver:
                await self._driver.close()
                self._driver = None

    def _generate_id(self) -> str:
        return f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{uuid.uuid4().hex[:8]}"

    async def add_node(self, node_type: str, attributes: dict, node_id: Optional[str] = None) -> str:
        if node_id is None:
            node_id = self._generate_id()

        session = await self._get_session()
        async with session:
            query = """
            MERGE (n:Node {id: $id})
            SET n.type = $type,
                n.context = $context,
                n += $properties
            RETURN n.id
            """
            result = await session.run(
                query,
                id=node_id,
                type=node_type,
                context=self.context,
                properties=attributes
            )
            record = await result.single()
            return str(record["n.id"])

    async def upsert_node(self, node_type: str, attributes: dict, dedupe_key: Optional[str] = None) -> str:
        if dedupe_key:
            session = await self._get_session()
            async with session:
                query = """
                MATCH (n:Node {id: $id})
                SET n.type = $type,
                    n.context = $context,
                    n += $properties
                RETURN n.id
                """
                result = await session.run(
                    query,
                    id=dedupe_key,
                    type=node_type,
                    context=self.context,
                    properties=attributes
                )
                record = await result.single()
                if record:
                    return str(record["n.id"])

        return await self.add_node(node_type, attributes, dedupe_key)

    async def add_edge(self, source_id: str, target_id: str, edge_type: str, attributes: Optional[dict] = None) -> str:
        session = await self._get_session()
        async with session:
            query = """
            MATCH (source:Node {id: $source_id})
            MATCH (target:Node {id: $target_id})
            MERGE (source)-[r:RELATIONSHIP {type: $type}]->(target)
            SET r += $properties
            RETURN source.id, target.id, r.type
            """
            result = await session.run(
                query,
                source_id=source_id,
                target_id=target_id,
                type=edge_type,
                properties=attributes or {}
            )
            record = await result.single()
            if record is None:
                # One (or both) endpoints do not exist, so the MATCH yielded no
                # row and no edge was created. Skip rather than crash the run on
                # a dangling id (e.g. a citation the Reporter could not resolve).
                logger.warning(
                    "add_edge skipped: missing node(s) source=%s target=%s type=%s",
                    source_id, target_id, edge_type,
                )
                return ""
            return f"{record['source.id']}_{record['r.type']}_{record['target.id']}"

    async def get_node(self, node_id: str) -> dict:
        session = await self._get_session()
        async with session:
            query = """
            MATCH (n:Node {id: $id})
            RETURN n
            """
            result = await session.run(query, id=node_id)
            record = await result.single()
            if not record:
                return {}
            node = record["n"]
            properties = dict(node)
            return {
                "id": node.get("id"),
                "type": node.get("type"),
                **{k: v for k, v in properties.items() if k not in ("id", "type", "context")}
            }

    async def search_node(self, node_type: str, filter: dict) -> list[dict]:
        session = await self._get_session()
        async with session:
            where_clauses = ["n.type = $type"]
            params = {"type": node_type, "context": self.context}

            for i, (key, value) in enumerate(filter.items()):
                where_clauses.append(f"n.{key} = $param{i}")
                params[f"param{i}"] = value

            # Strict context isolation: a context-scoped run sees only its own
            # nodes (never legacy/other-run nodes), and the default unscoped
            # mode sees only the unscoped (NULL-context) nodes. The lenient
            # "OR context IS NULL" form let earlier runs' data leak in and broke
            # per-run query resolution.
            query = f"""
            MATCH (n:Node)
            WHERE {" AND ".join(where_clauses)}
            AND (n.context = $context OR ($context IS NULL AND n.context IS NULL))
            RETURN n
            """
            result = await session.run(query, **params)
            records = [record async for record in result]
            nodes = []
            for record in records:
                node = record["n"]
                properties = dict(node)
                nodes.append({
                    "id": node.get("id"),
                    "type": node.get("type"),
                    **{k: v for k, v in properties.items() if k not in ("id", "type", "context")}
                })
            return nodes

    async def get_subgraph(self, node_id: str, depth: int = 2) -> dict:
        session = await self._get_session()
        async with session:
            query = """
            MATCH (start:Node {id: $id})
            CALL apoc.path.subgraphAll(start, {
                maxLevel: $depth
            }) YIELD nodes, relationships
            RETURN nodes, relationships
            """
            try:
                result = await session.run(query, id=node_id, depth=depth)
                record = await result.single()
                if not record:
                    return {"nodes": [], "edges": []}
            except Exception:
                # Fallback when APOC is unavailable. Variable-length bounds
                # cannot be parameterized, so the (validated) depth is inlined.
                # Gather every node within `depth` hops, then the relationships
                # between those nodes — returning `nodes`/`relationships` to
                # match what the consumer below reads.
                safe_depth = max(1, int(depth))
                query = f"""
                MATCH path = (start:Node {{id: $id}})-[:RELATIONSHIP*0..{safe_depth}]-(other:Node)
                UNWIND nodes(path) AS node
                WITH collect(DISTINCT node) AS allNodes
                UNWIND allNodes AS n
                OPTIONAL MATCH (n)-[r:RELATIONSHIP]->(m:Node)
                WHERE m IN allNodes
                RETURN allNodes AS nodes, collect(DISTINCT r) AS relationships
                """
                result = await session.run(query, id=node_id)
                record = await result.single()
                if not record:
                    return {"nodes": [], "edges": []}

            nodes = []
            for node in record["nodes"]:
                if hasattr(node, "get"):
                    properties = dict(node)
                    nodes.append({
                        "id": node.get("id"),
                        "type": node.get("type"),
                        **{k: v for k, v in properties.items() if k not in ("id", "type", "context")}
                    })

            edges = []
            for rel in record["relationships"]:
                if hasattr(rel, "start_node") and hasattr(rel, "end_node"):
                    properties = dict(rel)
                    edges.append({
                        "source": rel.start_node.get("id"),
                        "target": rel.end_node.get("id"),
                        "type": rel.get("type"),
                        **{k: v for k, v in properties.items() if k not in ("type")}
                    })

            return {"nodes": nodes, "edges": edges}

    async def save(self) -> None:
        pass

    async def get_all_nodes(self) -> list[dict]:
        session = await self._get_session()
        async with session:
            query = """
            MATCH (n:Node)
            WHERE (n.context = $context OR ($context IS NULL AND n.context IS NULL))
            RETURN n
            """
            result = await session.run(query, context=self.context)
            records = [record async for record in result]
            nodes = []
            for record in records:
                node = record["n"]
                properties = dict(node)
                nodes.append({
                    "id": node.get("id"),
                    "type": node.get("type"),
                    **{k: v for k, v in properties.items() if k not in ("id", "type", "context")}
                })
            return nodes

    async def get_all_edges(self) -> list[dict]:
        session = await self._get_session()
        async with session:
            query = """
            MATCH (source:Node)-[r:RELATIONSHIP]->(target:Node)
            WHERE (source.context = $context OR ($context IS NULL AND source.context IS NULL))
            RETURN source, r, target
            """
            result = await session.run(query, context=self.context)
            records = [record async for record in result]
            edges = []
            for record in records:
                rel = record["r"]
                properties = dict(rel)
                edges.append({
                    "source": record["source"].get("id"),
                    "target": record["target"].get("id"),
                    "type": rel.get("type"),
                    **{k: v for k, v in properties.items() if k not in ("type")}
                })
            return edges

    async def delete_node(self, node_id: str) -> None:
        session = await self._get_session()
        async with session:
            query = """
            MATCH (n:Node {id: $id})
            DETACH DELETE n
            """
            await session.run(query, id=node_id)

    async def get_node_edges(self, node_id: str, direction: str = "both") -> list[dict]:
        session = await self._get_session()
        async with session:
            if direction == "out":
                query = """
                MATCH (source:Node {id: $id})-[r:RELATIONSHIP]->(target:Node)
                RETURN source, r, target
                """
            elif direction == "in":
                query = """
                MATCH (source:Node)-[r:RELATIONSHIP]->(target:Node {id: $id})
                RETURN source, r, target
                """
            else:
                query = """
                MATCH (source:Node)-[r:RELATIONSHIP]-(target:Node {id: $id})
                RETURN source, r, target
                """

            result = await session.run(query, id=node_id)
            records = [record async for record in result]
            edges = []
            for record in records:
                rel = record["r"]
                properties = dict(rel)
                edges.append({
                    "source": record["source"].get("id"),
                    "target": record["target"].get("id"),
                    "type": rel.get("type"),
                    **{k: v for k, v in properties.items() if k not in ("type")}
                })
            return edges
