"""MemoryManager: LLM-powered service layer between agents and GraphManager."""

import json
import logging
from typing import Any

from langchain.chat_models import init_chat_model

from memory.graph import EdgeType, GraphManager, NodeType

logger = logging.getLogger(__name__)


def _parse_json(content: str) -> dict:
    """Parse JSON from an LLM response, stripping markdown code fences if present."""
    content = content.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        lines = [ln for ln in lines if not ln.startswith("```")]
        content = "\n".join(lines).strip()
    return json.loads(content)


class MemoryManager:
    """Async service that bridges agents with the Research Graph.

    All public methods are async and must be awaited.
    Each agent (Orchestrator, Searcher, Reporter) holds a shared MemoryManager instance.
    """

    def __init__(self, config: dict):  # noqa: D107
        self.config = config
        self.graph = GraphManager(
            cache_dir=config.get("cache_dir"),
            context=config.get("graph_context"),
        )
        self.model = init_chat_model(
            config.get("model_name", "gpt-4o-mini"),
            temperature=config.get("temperature", 0.3),
            max_tokens=config.get("max_tokens", 4096),
            max_retries=config.get("max_retries", 3),
        )

    # ── Orchestrator API ──────────────────────────────────────────────────────

    async def init_research(self, user_request: str) -> dict:
        """Parse user request and initialize graph with UserRequest + Query nodes.

        Returns:
            {user_request_id, research_goal, language, initial_queries: [{id, text}]}
        """
        from prompts.memory_manager_prompts import init_research as init_prompt

        response = await self.model.ainvoke(init_prompt.format(user_request=user_request))
        try:
            parsed = _parse_json(response.content)
        except (json.JSONDecodeError, AttributeError, KeyError) as exc:
            logger.warning("init_research JSON parse failed (%s); using fallback", exc)
            parsed = {
                "research_goal": user_request,
                "language": None,
                "initial_queries": [user_request],
            }

        research_goal = parsed.get("research_goal") or user_request
        language = parsed.get("language") or "auto"
        raw_queries: list[str] = parsed.get("initial_queries") or [user_request]
        if not raw_queries:
            raw_queries = [user_request]

        user_request_id = await self.graph.add_node(
            NodeType.USER_REQUEST,
            {
                "request": user_request,
                "research_goal": research_goal,
                "language": language,
            },
        )

        initial_queries: list[dict] = []
        for query_text in raw_queries:
            if not isinstance(query_text, str) or not query_text.strip():
                continue
            query_id = await self.graph.add_node(
                NodeType.QUERY,
                {"text": query_text.strip(), "status": "pending"},
            )
            await self.graph.add_edge(user_request_id, query_id, EdgeType.HAS_QUERY)
            initial_queries.append({"id": query_id, "text": query_text.strip()})

        logger.info("Research initialized: %d initial queries created", len(initial_queries))
        return {
            "user_request_id": user_request_id,
            "research_goal": research_goal,
            "language": language,
            "initial_queries": initial_queries,
        }

    async def get_next_queries(self, limit: int = 4) -> list[dict]:
        """Return up to `limit` actionable queries (pending + needs_vertical/horizontal)."""
        seen_ids: set[str] = set()
        results: list[dict] = []
        for status in ("pending", "needs_vertical", "needs_horizontal"):
            nodes = await self.graph.search_node(NodeType.QUERY, {"status": status})
            for node in nodes:
                node_id = node.get("id")
                if node_id and node_id not in seen_ids:
                    seen_ids.add(node_id)
                    results.append(node)
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break
        return results

    async def get_query_context(self, query_id: str) -> dict:
        """Return query node, its parent node, and sibling query summaries."""
        query_node = await self.graph.get_node(query_id)
        if not query_node:
            return {}

        in_edges = await self.graph.get_node_edges(query_id, "in")
        parent_node: dict = {}
        siblings: list[dict] = []

        for edge in in_edges:
            if edge.get("type") in (EdgeType.HAS_QUERY, EdgeType.PARENT_OF):
                parent_node = await self.graph.get_node(edge["source"]) or {}
                parent_out = await self.graph.get_node_edges(edge["source"], "out")
                for pe in parent_out:
                    if (
                        pe.get("type") in (EdgeType.HAS_QUERY, EdgeType.PARENT_OF)
                        and pe["target"] != query_id
                    ):
                        sib = await self.graph.get_node(pe["target"])
                        if sib:
                            siblings.append(
                                {
                                    "id": sib.get("id"),
                                    "text": sib.get("text", ""),
                                    "status": sib.get("status", ""),
                                }
                            )
                break

        return {"query": query_node, "parent": parent_node, "siblings": siblings}

    async def analyze_subgraph(self, query_id: str) -> dict:
        """Score evidence coverage for a query using LLM analysis of its subgraph.

        Returns:
            {coverage_score, sufficient, gaps, suggest_horizontal, suggest_vertical, reason}
        """
        from prompts.memory_manager_prompts import analyze_sufficiency

        query_node = await self.graph.get_node(query_id)
        if not query_node:
            return {
                "coverage_score": 0.0,
                "sufficient": False,
                "gaps": ["Query node not found"],
                "suggest_horizontal": False,
                "suggest_vertical": False,
                "reason": "Query not found in graph",
            }

        subgraph = await self.graph.get_subgraph(query_id, depth=2)

        response = await self.model.ainvoke(
            analyze_sufficiency.format(
                query_text=query_node.get("text", ""),
                subgraph_json=json.dumps(subgraph, ensure_ascii=False, indent=2),
            )
        )

        try:
            result = _parse_json(response.content)
        except (json.JSONDecodeError, AttributeError) as exc:
            logger.warning("analyze_subgraph JSON parse failed (%s); using heuristic fallback", exc)
            evidence_count = sum(
                1 for n in subgraph.get("nodes", []) if n.get("type") == "evidence"
            )
            score = min(0.65, evidence_count * 0.15)
            result = {
                "coverage_score": score,
                "sufficient": score >= 0.7,
                "gaps": ["Analysis unavailable due to parse error"],
                "suggest_horizontal": False,
                "suggest_vertical": score < 0.4,
                "reason": "Heuristic fallback: LLM response could not be parsed",
            }

        return result

    async def mark_query(self, query_id: str, status: str, **metrics: Any) -> None:
        """Update query node status and optional metrics (e.g., coverage_score)."""
        attrs: dict[str, Any] = {"status": status, **metrics}
        await self.graph.upsert_node(NodeType.QUERY, attrs, dedupe_key=query_id)

    async def add_followup_query(
        self,
        parent_id: str,
        text: str,
        expansion_type: str = "vertical",
        reason: str = "",
    ) -> str:
        """Create a child query node linked from parent with a HAS_QUERY edge.

        Returns:
            The new query node ID.
        """
        query_id = await self.graph.add_node(
            NodeType.QUERY,
            {
                "text": text,
                "status": "pending",
                "expansion_type": expansion_type,
                "reason": reason,
            },
        )
        await self.graph.add_edge(parent_id, query_id, EdgeType.HAS_QUERY)
        return query_id

    async def export_report_context(self, user_request_id: str) -> dict:
        """Export a structured graph context for the Reporter.

        Returns:
            {research_goal, language, queries (with evidence), sources, evidence, conflicts, analyses}
        """
        user_node = await self.graph.get_node(user_request_id)
        if not user_node:
            return {}

        full_subgraph = await self.graph.get_subgraph(user_request_id, depth=5)
        nodes_by_type: dict[str, list[dict]] = {}
        for node in full_subgraph.get("nodes", []):
            ntype = node.get("type", "unknown")
            nodes_by_type.setdefault(ntype, []).append(node)

        # Enrich each query with its direct evidence
        enriched_queries: list[dict] = []
        for q in nodes_by_type.get("query", []):
            q_subgraph = await self.graph.get_subgraph(q["id"], depth=2)
            evidence_nodes = [
                n for n in q_subgraph.get("nodes", []) if n.get("type") == "evidence"
            ]
            enriched_queries.append({**q, "evidence": evidence_nodes})

        return {
            "research_goal": user_node.get("research_goal", ""),
            "language": user_node.get("language", "auto"),
            "queries": enriched_queries,
            "sources": nodes_by_type.get("source", []),
            "evidence": nodes_by_type.get("evidence", []),
            "conflicts": nodes_by_type.get("conflict", []),
            "analyses": nodes_by_type.get("analysis", []),
        }

    async def bind_report_section(
        self,
        section_id: str,
        evidence_ids: list[str],
        claim_ids: list[str] | None = None,
    ) -> None:
        """Link a ReportSection node to evidence and claim nodes via USES edges."""
        for ev_id in evidence_ids:
            await self.graph.add_edge(section_id, ev_id, EdgeType.USES)
        for claim_id in claim_ids or []:
            await self.graph.add_edge(section_id, claim_id, EdgeType.USES)

    # ── Searcher API ──────────────────────────────────────────────────────────

    async def submit_search_result(self, query_id: str, evidence_package: dict) -> dict:
        """Process a Searcher evidence_package and write structured nodes to the graph.

        Args:
            query_id: The query node ID this evidence belongs to.
            evidence_package: Dict with keys: sources, documents, evidence, conflicts.

        Returns:
            {nodes_written, edges_written}
        """
        nodes_written = 0
        edges_written = 0
        id_map: dict[str, str] = {}  # local_ref → graph node ID

        # 1. Source nodes
        for src in evidence_package.get("sources", []):
            local_ref = src.get("local_ref")
            source_id = await self.graph.add_node(
                NodeType.SOURCE,
                {
                    "url": src.get("url", ""),
                    "title": src.get("title", ""),
                    "source_type": src.get("source_type", ""),
                    "publisher": src.get("publisher") or "",
                    "publication_date": src.get("publication_date"),
                    "accessed_at": src.get("accessed_at", ""),
                    "source_quality_tier": src.get("source_quality_tier", "unknown"),
                },
            )
            nodes_written += 1
            await self.graph.add_edge(query_id, source_id, EdgeType.FOUND_SOURCE)
            edges_written += 1
            if local_ref:
                id_map[local_ref] = source_id

        # 2. Document nodes
        for doc in evidence_package.get("documents", []):
            local_ref = doc.get("local_ref")
            source_ref = doc.get("source_ref", "")
            source_id = id_map.get(source_ref, source_ref)

            doc_id = await self.graph.add_node(
                NodeType.DOCUMENT,
                {
                    "title": doc.get("title", ""),
                    "summary": doc.get("document_summary", ""),
                    "language": doc.get("language") or "",
                    "source_id": source_id,
                },
            )
            nodes_written += 1
            if source_id:
                await self.graph.add_edge(source_id, doc_id, EdgeType.HAS_DOCUMENT)
                edges_written += 1
            if local_ref:
                id_map[local_ref] = doc_id

        # 3. Evidence nodes
        for ev in evidence_package.get("evidence", []):
            local_ref = ev.get("local_ref")
            source_ref = ev.get("source_ref", "")
            doc_ref = ev.get("document_ref") or ""
            source_id = id_map.get(source_ref, source_ref)
            doc_id = id_map.get(doc_ref, doc_ref)

            ev_id = await self.graph.add_node(
                NodeType.EVIDENCE,
                {
                    "claim": ev.get("evidence_text", ""),
                    "evidence_type": ev.get("evidence_type", ""),
                    "supports_or_contradicts": ev.get("supports_or_contradicts", "supports"),
                    "confidence_score": ev.get("confidence_score", 0.5),
                    "freshness_score": ev.get("freshness_score", 0.5),
                    "scope": ev.get("scope", ""),
                    "status": "pending",
                },
            )
            nodes_written += 1

            if source_id:
                await self.graph.add_edge(source_id, ev_id, EdgeType.SUPPORTED_BY)
                edges_written += 1
            if doc_id:
                await self.graph.add_edge(doc_id, ev_id, EdgeType.EXTRACTED_STATEMENT)
                edges_written += 1
            await self.graph.add_edge(query_id, ev_id, EdgeType.SUPPORTED_BY)
            edges_written += 1

            if local_ref:
                id_map[local_ref] = ev_id

        # 4. Conflict nodes
        for conflict in evidence_package.get("conflicts", []):
            local_ref = conflict.get("local_ref")
            ev_ids = [
                id_map.get(ref, ref)
                for ref in conflict.get("evidence_refs", [])
                if ref
            ]

            conflict_id = await self.graph.add_node(
                NodeType.CONFLICT,
                {
                    "description": conflict.get("description", ""),
                    "conflict_type": conflict.get("conflict_type", "factual"),
                    "possible_explanation": conflict.get("possible_explanation") or "",
                },
            )
            nodes_written += 1
            for ev_id in ev_ids:
                await self.graph.add_edge(conflict_id, ev_id, EdgeType.HAS_CONFLICT)
                edges_written += 1
            if local_ref:
                id_map[local_ref] = conflict_id

        logger.info("submit_search_result: %d nodes, %d edges written", nodes_written, edges_written)
        return {"nodes_written": nodes_written, "edges_written": edges_written}

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def extract_content(self, content: str) -> dict:
        """LLM-powered extraction of keywords, statements, and summary from text."""
        from prompts.memory_manager_prompts import extract_content as ec_prompt

        response = await self.model.ainvoke(ec_prompt + content)
        try:
            return _parse_json(response.content)
        except (json.JSONDecodeError, AttributeError) as exc:
            logger.error("extract_content JSON parse failed: %s", exc)
            return {"keywords": [], "statement": [], "summary": ""}

    async def summarize_subgraph(self, node_id: str) -> str:
        """Generate a readable research status summary for the subgraph around node_id."""
        from prompts.memory_manager_prompts import summarize_subgraph as sg_prompt

        subgraph = await self.graph.get_subgraph(node_id, depth=2)
        if not subgraph.get("nodes"):
            return "No research data found for this node."

        response = await self.model.ainvoke(
            sg_prompt.format(
                subgraph_json=json.dumps(subgraph, ensure_ascii=False, indent=2)
            )
        )
        return getattr(response, "content", str(response))
