"""LLM-powered Graph Manager for GraphResearcher.

`MemoryManager` is the intelligent layer over the Research Graph. It wraps the
synchronous graph toolkit (`tools/graph_tools.py`) with LLM-assisted operations
(request parsing, sub-graph sufficiency analysis, evidence-package writing,
report-context export). Its methods are exposed to the agents as tools via
`tools/graph_manager_tools.py`.

Notes:
- All graph access goes through the sync wrappers in `tools/graph_tools.py`;
  this module never awaits `GraphManager` directly.
- The prompt templates embed literal JSON braces, so placeholders are injected
  with ``str.replace`` rather than ``str.format``.
"""

import json
from typing import Any, Optional

import config
import prompts.memory_manager_prompts as mm_prompts
from tools import graph_tools


def _parse_json(text: str) -> dict:
    """Parse a JSON object from an LLM response, tolerating Markdown fences.

    Args:
        text: Raw model output.

    Returns:
        The parsed object, or an empty dict if parsing fails.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Strip a leading ```json / ``` fence and the trailing fence.
        cleaned = cleaned.split("```", 2)[1] if "```" in cleaned else cleaned
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip().rstrip("`").strip()
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except (json.JSONDecodeError, ValueError):
                return {}
        return {}


class MemoryManager:
    """LLM-powered manager of the Research Graph."""

    def __init__(self, model: Optional[Any] = None, cache_dir: Optional[str] = None):
        """Initialize the manager.

        Args:
            model: A chat model; defaults to ``config.build_model()``.
            cache_dir: Graph storage directory passed through to the toolkit.
        """
        self.cache_dir = cache_dir
        self.model = model if model is not None else config.build_model()

    def _invoke_json(self, prompt: str) -> dict:
        """Invoke the model and parse a JSON object from its response."""
        response = self.model.invoke(prompt)
        content = getattr(response, "content", response)
        if isinstance(content, list):  # some providers return content parts
            content = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
        return _parse_json(str(content))

    # -----------------------------
    # Orchestrator-facing
    # -----------------------------
    def init_research(self, user_request: str) -> dict:
        """Parse the user request and seed the Research Graph.

        Creates a ``user_request`` node and a set of parallel initial ``query``
        nodes under it.

        Args:
            user_request: The original research request from the user.

        Returns:
            dict with ``goal_id``, ``research_goal``, ``language`` and the list
            of created ``queries`` (each ``{id, text}``).
        """
        prompt = mm_prompts.init_research.replace("{user_request}", user_request)
        parsed = self._invoke_json(prompt)

        goal_id = graph_tools.create_user_request(
            request=user_request,
            research_goal=parsed.get("research_goal"),
            language=parsed.get("language"),
            cache_dir=self.cache_dir,
        )

        queries = []
        for text in parsed.get("initial_queries", []) or []:
            if not text:
                continue
            query_id = graph_tools.create_query(
                text=text, status="pending", parent_id=goal_id, cache_dir=self.cache_dir
            )
            queries.append({"id": query_id, "text": text})

        return {
            "goal_id": goal_id,
            "research_goal": parsed.get("research_goal", ""),
            "language": parsed.get("language"),
            "queries": queries,
        }

    def get_next_queries(self, limit: int = 4) -> list[dict]:
        """Return high-priority queries awaiting work.

        Collects queries whose status is ``pending``, ``needs_horizontal`` or
        ``needs_vertical``.

        Args:
            limit: Maximum number of queries to return.

        Returns:
            A list of ``{id, text, status}`` dicts.
        """
        results: list[dict] = []
        for status in ("pending", "needs_horizontal", "needs_vertical"):
            for node in graph_tools.search_nodes("query", {"status": status}, cache_dir=self.cache_dir):
                results.append({"id": node.get("id"), "text": node.get("text"), "status": status})
        return results[:limit]

    def analyze_subgraph(self, query_id: str) -> dict:
        """Score the sufficiency of a query's evidence sub-graph via the LLM.

        Args:
            query_id: The query node ID to evaluate.

        Returns:
            dict with ``sufficiency_score``, ``covered``, ``gaps``,
            ``conflicts``, ``recommendation`` and ``reason``.
        """
        node = graph_tools.get_node(query_id, cache_dir=self.cache_dir)
        subgraph = graph_tools.get_query_subgraph(query_id, depth=4, cache_dir=self.cache_dir)
        prompt = mm_prompts.summarize_subgraph.replace(
            "{query}", node.get("text", query_id)
        ).replace("{subgraph}", json.dumps(subgraph, ensure_ascii=False))
        return self._invoke_json(prompt)

    def add_followup_query(
        self, parent_query_id: str, query_text: str, expansion_type: str, reason: str
    ) -> str:
        """Create a follow-up query as a child of an existing query.

        Args:
            parent_query_id: The parent query node ID.
            query_text: The new query text.
            expansion_type: ``horizontal`` or ``vertical``.
            reason: Why this follow-up is needed (stored on the node).

        Returns:
            The new query node ID.
        """
        query_id = graph_tools.add_node(
            "query",
            {
                "text": query_text,
                "status": "pending",
                "expansion_type": expansion_type,
                "reason": reason,
            },
            cache_dir=self.cache_dir,
        )
        graph_tools.add_edge(parent_query_id, query_id, "parent_of", cache_dir=self.cache_dir)
        return query_id

    def mark_query(self, query_id: str, status: str, **metrics: Any) -> dict:
        """Update a query's status and optional metrics.

        Args:
            query_id: The query node ID.
            status: New status (e.g. ``sufficient``, ``blocked``).
            **metrics: Additional attributes to store (e.g. scores).

        Returns:
            The updated query node.
        """
        return graph_tools.upsert_node(
            "query", {"status": status, **metrics}, dedupe_key=query_id, cache_dir=self.cache_dir
        )

    # -----------------------------
    # Searcher-facing
    # -----------------------------
    def get_query_context(self, query_id: str) -> dict:
        """Return existing context for a query to avoid duplicate searching.

        Args:
            query_id: The query node ID.

        Returns:
            dict with the ``query`` node and its ``existing_subgraph``.
        """
        return {
            "query": graph_tools.get_node(query_id, cache_dir=self.cache_dir),
            "existing_subgraph": graph_tools.get_query_subgraph(
                query_id, depth=4, cache_dir=self.cache_dir
            ),
        }

    def submit_search_result(self, query_id: str, evidence_package: dict) -> dict:
        """Write a structured evidence package into the Research Graph.

        Accepts the evidence package produced by the Searcher (sources,
        documents, claims, evidence, conflicts), creates the corresponding
        nodes/edges, and connects them to ``query_id`` through a ``search_run``
        node. Local references (``local_ref``) in the package are resolved to
        the created graph IDs.

        Args:
            query_id: The query this evidence answers.
            evidence_package: Structured package; missing sections are tolerated.

        Returns:
            dict mapping ``local_ref`` values to created graph IDs, plus a
            ``search_run`` ID and counts.
        """
        ref_map: dict[str, str] = {}

        def resolve(ref: Optional[str]) -> Optional[str]:
            if ref is None:
                return None
            return ref_map.get(ref, ref)

        run_id = graph_tools.add_node("search_run", {"query_id": query_id}, cache_dir=self.cache_dir)
        graph_tools.add_edge(query_id, run_id, "searched_by", cache_dir=self.cache_dir)

        for source in evidence_package.get("sources", []) or []:
            source_id = graph_tools.create_source(
                url=source.get("url", ""),
                title=source.get("title"),
                source_type=source.get("source_type"),
                cache_dir=self.cache_dir,
            )
            if source.get("local_ref"):
                ref_map[source["local_ref"]] = source_id
            graph_tools.add_edge(run_id, source_id, "found_source", cache_dir=self.cache_dir)

        for document in evidence_package.get("documents", []) or []:
            doc_id = graph_tools.create_document(
                text=document.get("document_summary", ""),
                source_id=resolve(document.get("source_ref")),
                cache_dir=self.cache_dir,
            )
            if document.get("local_ref"):
                ref_map[document["local_ref"]] = doc_id

        # Claims and evidence both become evidence nodes carrying the assertion.
        for item in (evidence_package.get("claims", []) or []) + (evidence_package.get("evidence", []) or []):
            claim_text = item.get("statement") or item.get("evidence_text") or ""
            if not claim_text:
                continue
            evidence_id = graph_tools.create_evidence(
                claim=claim_text,
                document_id=resolve(item.get("document_ref")),
                source_id=resolve(item.get("source_ref")),
                cache_dir=self.cache_dir,
            )
            if item.get("local_ref"):
                ref_map[item["local_ref"]] = evidence_id

        for conflict in evidence_package.get("conflicts", []) or []:
            evidence_ids = [resolve(r) for r in conflict.get("evidence_refs", []) or [] if resolve(r)]
            graph_tools.create_conflict(
                description=conflict.get("description", ""),
                evidence_ids=evidence_ids,
                cache_dir=self.cache_dir,
            )

        graph_tools.save_graph(cache_dir=self.cache_dir)
        return {
            "search_run_id": run_id,
            "ref_map": ref_map,
            "written": {
                "sources": len(evidence_package.get("sources", []) or []),
                "documents": len(evidence_package.get("documents", []) or []),
                "claims": len(evidence_package.get("claims", []) or []),
                "evidence": len(evidence_package.get("evidence", []) or []),
                "conflicts": len(evidence_package.get("conflicts", []) or []),
            },
        }

    # -----------------------------
    # Reporter-facing
    # -----------------------------
    def export_report_context(self, goal_id: str) -> dict:
        """Export the full graph context needed to write the report.

        Args:
            goal_id: The ``user_request`` node ID.

        Returns:
            dict with the goal node, the full sub-graph, and nodes grouped by
            type (``queries``, ``evidence``, ``conflicts``, ``analysis``,
            ``sources``, ``report_sections``).
        """
        goal = graph_tools.get_node(goal_id, cache_dir=self.cache_dir)
        subgraph = graph_tools.get_subgraph(goal_id, depth=8, cache_dir=self.cache_dir)

        grouped: dict[str, list[dict]] = {
            "query": [],
            "evidence": [],
            "conflict": [],
            "analysis": [],
            "source": [],
            "report_section": [],
        }
        for node in subgraph.get("nodes", []):
            node_type = node.get("type")
            if node_type in grouped:
                grouped[node_type].append(node)

        return {
            "goal": goal,
            "subgraph": subgraph,
            "queries": grouped["query"],
            "evidence": grouped["evidence"],
            "conflicts": grouped["conflict"],
            "analysis": grouped["analysis"],
            "sources": grouped["source"],
            "report_sections": grouped["report_section"],
        }

    def bind_report_section(
        self, section: dict, claim_ids: Optional[list[str]] = None, evidence_ids: Optional[list[str]] = None
    ) -> str:
        """Create a report-section node and bind it to the evidence/claims it uses.

        Args:
            section: dict with ``title``, ``content`` and optional ``section_type``.
            claim_ids: Claim/evidence node IDs the section cites.
            evidence_ids: Evidence node IDs the section cites.

        Returns:
            The created report-section node ID.
        """
        section_id = graph_tools.create_report_section(
            title=section.get("title", ""),
            content=section.get("content", ""),
            section_type=section.get("section_type"),
            cache_dir=self.cache_dir,
        )
        graph_tools.bind_evidence_to_section(
            section_id,
            evidence_ids=evidence_ids or [],
            claim_ids=claim_ids or [],
            cache_dir=self.cache_dir,
        )
        return section_id

    # -----------------------------
    # Internal LLM helpers
    # -----------------------------
    def extract_content(self, content: str) -> dict:
        """Extract keywords, statements and a summary from document text.

        Args:
            content: The text content to analyze.

        Returns:
            dict with ``keywords``, ``statement`` and ``summary``.
        """
        return self._invoke_json(mm_prompts.extract_content + content)

    def summarize_subgraph(self, node_id: str) -> dict:
        """Summarize the sub-graph around a node (alias of sufficiency analysis).

        Args:
            node_id: The node ID to summarize.

        Returns:
            The sufficiency-analysis dict (see :meth:`analyze_subgraph`).
        """
        return self.analyze_subgraph(node_id)

    def deduplicate_source(self, source: dict) -> Optional[str]:
        """Return the ID of an existing matching source, if any.

        Args:
            source: A source dict with at least a ``url``.

        Returns:
            The matching source node ID, or ``None``.
        """
        url = source.get("url")
        if not url:
            return None
        matches = graph_tools.search_nodes("source", {"url": url}, cache_dir=self.cache_dir)
        return matches[0]["id"] if matches else None
