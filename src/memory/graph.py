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
    USER_REQUEST = "UserRequest"
    QUERY = "Query"
    SEARCH_RUN = "SearchRun"
    SOURCE = "Source"
    DOCUMENT = "Document"
    STATEMENT = "Statement"
    EVIDENCE = "Evidence"
    ENTITY = "Entity"
    CONFLICT = "Conflict"
    ANALYSIS = "Analysis"
    REPORT_SECTION = "ReportSection"


class EdgeType(StrEnum):
    HAS_QUERY = "HAS_QUERY"
    PARENT_OF = "PARENT_OF"
    SEARCHED_BY = "SEARCHED_BY"
    FOUND_SOURCE = "FOUND_SOURCE"
    HAS_DOCUMENT = "HAS_DOCUMENT"
    EXTRACTED_STATEMENT = "EXTRACTED_STATEMENT"
    SUPPORTED_BY = "SUPPORTED_BY"
    CONTRADICTED_BY = "CONTRADICTED_BY"
    MENTIONS = "MENTIONS"
    RELATED_TO = "RELATED_TO"
    HAS_CONFLICT = "HAS_CONFLICT"
    RESOLVES_GAP = "RESOLVES_GAP"
    USES = "USES"


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
NEO4J_TIMEOUT = int(os.environ.get("NEO4J_TIMEOUT", "30"))


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
            try:
                label = NodeType(node_type).value
            except ValueError:
                try:
                    label = NodeType[node_type.upper()].value
                except KeyError:
                    label = node_type
            query = f"""
            MERGE (n:{label} {{id: $id}})
            SET n.context = $context,
                n += $properties
            RETURN n.id
            """
            result = await session.run(
                query,
                id=node_id,
                context=self.context,
                properties=attributes
            )
            record = await result.single()
            return str(record["n.id"])

    async def upsert_node(self, node_type: str, attributes: dict, dedupe_key: Optional[str] = None) -> str:
        if dedupe_key:
            session = await self._get_session()
            async with session:
                try:
                    label = NodeType(node_type).value
                except ValueError:
                    try:
                        label = NodeType[node_type.upper()].value
                    except KeyError:
                        label = node_type
                query = f"""
                MATCH (n:{label} {{id: $id}})
                SET n.context = $context,
                    n += $properties
                RETURN n.id
                """
                result = await session.run(
                    query,
                    id=dedupe_key,
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
            try:
                rel_type = EdgeType(edge_type).value
            except ValueError:
                try:
                    rel_type = EdgeType[edge_type.upper()].value
                except KeyError:
                    rel_type = edge_type
            query = f"""
            MATCH (source)
            WHERE source.id = $source_id
            MATCH (target)
            WHERE target.id = $target_id
            MERGE (source)-[r:{rel_type}]->(target)
            SET r += $properties
            RETURN source.id, target.id, type(r)
            """
            result = await session.run(
                query,
                source_id=source_id,
                target_id=target_id,
                properties=attributes or {}
            )
            record = await result.single()
            if record is None:
                logger.warning(
                    "add_edge skipped: missing node(s) source=%s target=%s type=%s",
                    source_id, target_id, edge_type,
                )
                return ""
            return f"{record['source.id']}_{record['type(r)']}_{record['target.id']}"

    async def get_node(self, node_id: str) -> dict:
        session = await self._get_session()
        async with session:
            query = """
            MATCH (n)
            WHERE n.id = $id
            RETURN n, labels(n) as labels
            """
            result = await session.run(query, id=node_id)
            record = await result.single()
            if not record:
                return {}
            node = record["n"]
            labels = record["labels"]
            properties = dict(node)
            
            node_type = next((label for label in labels if label != 'Node'), labels[0] if labels else 'Node')
            return {
                "id": node.get("id"),
                "type": node_type,
                **{k: v for k, v in properties.items() if k not in ("id", "context")}
            }

    async def search_node(self, node_type: str, filter: dict) -> list[dict]:
        session = await self._get_session()
        async with session:
            try:
                label = NodeType(node_type).value
            except ValueError:
                try:
                    label = NodeType[node_type.upper()].value
                except KeyError:
                    label = node_type
            where_clauses = []
            params = {"context": self.context}

            for i, (key, value) in enumerate(filter.items()):
                where_clauses.append(f"n.{key} = $param{i}")
                params[f"param{i}"] = value

            query = f"""
            MATCH (n:{label})
            WHERE {" AND ".join(where_clauses) if where_clauses else "true"}
            AND (n.context = $context OR ($context IS NULL AND n.context IS NULL))
            RETURN n, labels(n) as labels
            """
            result = await session.run(query, **params)
            records = [record async for record in result]
            nodes = []
            for record in records:
                node = record["n"]
                labels = record["labels"]
                properties = dict(node)
                node_type = next((label for label in labels if label != 'Node'), labels[0] if labels else 'Node')
                nodes.append({
                    "id": node.get("id"),
                    "type": node_type,
                    **{k: v for k, v in properties.items() if k not in ("id", "context")}
                })
            return nodes

    async def get_subgraph(self, node_id: str, depth: int = 2) -> dict:
        session = await self._get_session()
        async with session:
            query = """
            MATCH (start)
            WHERE start.id = $id
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
                safe_depth = max(1, int(depth))
                query = f"""
                MATCH path = (start)-[*0..{safe_depth}]-(other)
                WHERE start.id = $id
                UNWIND nodes(path) AS node
                WITH collect(DISTINCT node) AS allNodes
                UNWIND allNodes AS n
                OPTIONAL MATCH (n)-[r]->(m)
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
                    labels = getattr(node, 'labels', [])
                    node_type = next((label for label in labels if label != 'Node'), 'Node') if labels else 'Node'
                    nodes.append({
                        "id": node.get("id"),
                        "type": node_type,
                        **{k: v for k, v in properties.items() if k not in ("id", "context")}
                    })

            edges = []
            for rel in record["relationships"]:
                if hasattr(rel, "start_node") and hasattr(rel, "end_node"):
                    properties = dict(rel)
                    edges.append({
                        "source": rel.start_node.get("id"),
                        "target": rel.end_node.get("id"),
                        "type": rel.type,
                        **{k: v for k, v in properties.items()}
                    })

            return {"nodes": nodes, "edges": edges}

    async def save(self) -> None:
        pass

    async def get_all_nodes(self) -> list[dict]:
        session = await self._get_session()
        async with session:
            query = """
            MATCH (n)
            WHERE (n.context = $context OR ($context IS NULL AND n.context IS NULL))
            RETURN n, labels(n) as labels
            """
            result = await session.run(query, context=self.context)
            records = [record async for record in result]
            nodes = []
            for record in records:
                node = record["n"]
                labels = record["labels"]
                properties = dict(node)
                node_type = next((label for label in labels if label != 'Node'), labels[0] if labels else 'Node')
                nodes.append({
                    "id": node.get("id"),
                    "type": node_type,
                    **{k: v for k, v in properties.items() if k not in ("id", "context")}
                })
            return nodes

    async def get_all_edges(self) -> list[dict]:
        session = await self._get_session()
        async with session:
            query = """
            MATCH (source)-[r]->(target)
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
                    "type": rel.type,
                    **{k: v for k, v in properties.items()}
                })
            return edges

    async def delete_node(self, node_id: str) -> None:
        session = await self._get_session()
        async with session:
            query = """
            MATCH (n)
            WHERE n.id = $id
            DETACH DELETE n
            """
            await session.run(query, id=node_id)

    async def get_node_edges(self, node_id: str, direction: str = "both") -> list[dict]:
        session = await self._get_session()
        async with session:
            if direction == "out":
                query = """
                MATCH (source)-[r]->(target)
                WHERE source.id = $id
                RETURN source, r, target
                """
            elif direction == "in":
                query = """
                MATCH (source)-[r]->(target)
                WHERE target.id = $id
                RETURN source, r, target
                """
            else:
                query = """
                MATCH (source)-[r]-(target)
                WHERE target.id = $id
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
                    "type": rel.type,
                    **{k: v for k, v in properties.items()}
                })
            return edges