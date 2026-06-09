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
import logging
from typing import Any, Optional

import config
import prompts.memory_manager_prompts as mm_prompts
from memory.graph import EdgeType, NodeType
from tools import graph_tools

logger = logging.getLogger(__name__)


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


# Internal scheduling/bookkeeping fields that the Orchestrator uses to drive the
# research loop but that must never leak into the Reporter's writing context —
# otherwise the model narrates graph state (e.g. "this query is blocked").
_INTERNAL_NODE_FIELDS = ("kind", "status", "sufficiency_score")

# Cross-reference tokens that break a query's self-containment: a follow-up
# query containing any of these depends on another query's output and is not
# independently searchable. Authored follow-ups containing them are dropped.
_CROSS_REF_TOKENS = ("上述", "前述", "该区域", "这些公司", "上文", "前文")


def _strip_internal_fields(node: dict) -> dict:
    """Return a copy of a node dict without internal scheduling fields.

    Keeps ``id``, ``type`` and all content fields (``text`` / ``claim`` /
    ``url`` / ``title`` / ``content`` / ...) so citations and section binding
    still work; drops the bookkeeping fields in ``_INTERNAL_NODE_FIELDS``.

    Args:
        node: A node dict as returned by the graph toolkit.

    Returns:
        A cleaned shallow copy (the graph is not modified).
    """
    return {k: v for k, v in node.items() if k not in _INTERNAL_NODE_FIELDS}


def _first(d: dict, *keys: str) -> Optional[Any]:
    """Return the first non-empty value among ``keys`` in ``d``.

    Lets the evidence-package reader accept several field-name variants the
    Searcher/analyzer may emit (e.g. ``summary_zh`` vs ``document_summary``)
    without the writer dropping content on a field-name mismatch.

    Args:
        d: The mapping to read from.
        *keys: Candidate keys, in priority order.

    Returns:
        The first value that is present and truthy, or ``None``.
    """
    for key in keys:
        value = d.get(key)
        if value:
            return value
    return None


def _query_text_importance(item: Any) -> tuple:
    """Return ``(text, importance)`` from a planner-authored query item.

    Accepts the structured ``{"text", "importance"}`` form or a bare string
    (lenient parsing). A missing importance is left as ``None`` so the priority
    model applies its own default.

    Args:
        item: One element of a planner's query list.

    Returns:
        A ``(text, importance)`` tuple.
    """
    if isinstance(item, dict):
        return item.get("text"), item.get("importance")
    return item, None


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
        parsed = self._plan_initial_queries(user_request)

        goal_id = graph_tools.create_user_request(
            request=user_request,
            research_goal=parsed.get("research_goal"),
            language=parsed.get("language"),
        )

        from tools import convergence

        queries = []
        for item in parsed.get("initial_queries", []) or []:
            text, importance = _query_text_importance(item)
            if not text:
                continue
            score, tier, sem = convergence.compute_priority(importance, goal_id)
            handle = self._assign_handle(goal_id)
            query_id = graph_tools.create_query(
                text=text,
                status="pending",
                parent_id=goal_id,
                priority=score,
                priority_tier=tier,
                sem=sem,
                handle=handle,
            )
            queries.append({"handle": handle, "id": query_id, "text": text, "priority_tier": tier})

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
            A list of ``{id, text, status, priority_tier, priority}`` dicts,
            highest priority first.
        """
        results: list[dict] = []
        for status in ("pending", "needs_horizontal", "needs_vertical"):
            for node in graph_tools.search_nodes("query", {"status": status}):
                results.append({
                    "handle": node.get("handle"),
                    "id": node.get("id"),
                    "text": node.get("text"),
                    "status": status,
                    "priority_tier": node.get("priority_tier"),
                    "priority": node.get("priority"),
                })
        results.sort(key=lambda q: q.get("priority") or 0.0, reverse=True)
        return results[:limit]

    def analyze_subgraph(self, query_id: str) -> dict:
        """Score the sufficiency of a query's evidence sub-graph via the LLM.

        Args:
            query_id: The query node ID to evaluate.

        Returns:
            dict with ``sufficiency_score``, ``covered``, ``gaps``,
            ``conflicts``, ``recommendation`` and ``reason``.
        """
        resolved = self._resolve_query_id(query_id) or query_id
        node = graph_tools.get_node(resolved) or {}
        subgraph = graph_tools.get_query_subgraph(resolved, depth=4)
        prompt = mm_prompts.summarize_subgraph.replace(
            "{query}", node.get("text") or resolved
        ).replace("{subgraph}", json.dumps(subgraph, ensure_ascii=False))
        return self._invoke_json(prompt)

    def analyze_coverage(self, parent_id: str) -> dict:
        """Judge whether the parallel sub-dimensions under a parent are complete.

        Reads the parent's text and the text+status of its IMMEDIATE child
        queries only (not their evidence or grandchildren), then asks the LLM
        whether any parallel dimension under the parent is still missing — the
        signal that drives horizontal expansion. Deliberately uses
        ``get_query_children`` (one level) rather than the undirected, deep
        ``get_query_subgraph`` so the prompt stays scoped to breadth.

        Args:
            parent_id: The parent node ID (the research-goal ``user_request`` or
                an intermediate ``query``).

        Returns:
            dict with ``covered_dimensions``, ``missing_dimensions``,
            ``recommendation`` (``complete``/``needs_horizontal``) and ``reason``.
        """
        parent = graph_tools.get_node(parent_id)
        parent_text = (
            parent.get("text")
            or parent.get("research_goal")
            or parent.get("request")
            or parent_id
        )
        children = []
        for child_id in graph_tools.get_query_children(parent_id):
            child = graph_tools.get_node(child_id)
            if child:
                children.append({"text": child.get("text"), "status": child.get("status")})
        prompt = mm_prompts.analyze_coverage.replace("{parent}", parent_text).replace(
            "{children}", json.dumps(children, ensure_ascii=False)
        )
        return self._invoke_json(prompt)

    def expand_query(
        self,
        anchor_query_id: str,
        direction: str,
        reason: str = "",
        gaps: Any = None,
        max_new: int = 1,
    ) -> dict:
        """Author and attach self-contained follow-up query node(s).

        The Query Planner authors the text; the Orchestrator only chooses the
        anchor, direction, reason and gaps — it never writes query text.

        ``direction``:
          - ``vertical``: attach the new query UNDER ``anchor_query_id`` (deepen it).
          - ``horizontal``: attach under the anchor's PARENT (a parallel sibling).
            Works at goal level too — a sibling added under the ``user_request``
            goal gets a ``HAS_QUERY`` edge, like an initial query.

        Args:
            anchor_query_id: Query to expand from (truncated/label IDs tolerated).
            direction: ``vertical`` or ``horizontal``.
            reason: Why this expansion is needed (stored on each new node).
            gaps: Gaps (vertical) or missing dimensions (horizontal) to cover.
            max_new: Maximum number of queries to author.

        Returns:
            dict with ``attach_point``, ``edge_type``, ``direction``, ``created``
            (each ``{id, text}``) and an optional ``warning``.
        """
        warning = None
        anchor_id = self._resolve_query_id(anchor_query_id) or anchor_query_id

        if direction == "horizontal":
            attach_point = graph_tools.get_query_parent(anchor_id)
            if not attach_point:
                attach_point = anchor_id
                warning = f"anchor {anchor_id!r} 无父节点，横向兄弟改挂在 anchor 自身下。"
        else:
            attach_point = anchor_id

        # Edge type follows the attach point: a goal (user_request) uses
        # HAS_QUERY, a query uses PARENT_OF — matching the existing hierarchy.
        attach_node = graph_tools.get_node(attach_point)
        edge_type = (
            EdgeType.HAS_QUERY
            if attach_node.get("type") == NodeType.USER_REQUEST.value
            else EdgeType.PARENT_OF
        )
        parent_text = (
            attach_node.get("text")
            or attach_node.get("research_goal")
            or attach_node.get("request")
            or ""
        )

        research_goal = ""
        requests = graph_tools.search_nodes("user_request", {})
        if requests:
            research_goal = requests[0].get("research_goal") or requests[0].get("request") or ""

        sibling_texts = []
        for sibling_id in graph_tools.get_query_children(attach_point):
            sibling = graph_tools.get_node(sibling_id)
            if sibling and sibling.get("text"):
                sibling_texts.append(sibling["text"])

        followups = self._plan_followup_queries(
            direction=direction,
            research_goal=research_goal,
            parent_text=parent_text,
            sibling_texts=sibling_texts,
            gaps=gaps if gaps is not None else [],
            reason=reason,
            max_new=max_new,
        )

        from tools import convergence

        created = []
        for followup in followups:
            text = followup["text"]
            score, tier, sem = convergence.compute_priority(followup.get("importance"), attach_point)
            handle = self._assign_handle(attach_point)
            new_id = graph_tools.add_node(
                "query",
                {
                    "text": text,
                    "status": "pending",
                    "expansion_type": direction,
                    "reason": reason,
                    "priority": score,
                    "priority_tier": tier,
                    "sem": sem,
                    "handle": handle,
                },
            )
            graph_tools.add_edge(attach_point, new_id, edge_type)
            created.append({"handle": handle, "id": new_id, "text": text})

        graph_tools.save_graph()
        result = {
            "attach_point": attach_point,
            "edge_type": edge_type.value,
            "direction": direction,
            "created": created,
        }
        if warning:
            result["warning"] = warning
        return result

    def mark_query(self, query_id: str, status: str, **metrics: Any) -> dict:
        """Update a query's status and optional metrics.

        Args:
            query_id: The query node ID.
            status: New status (e.g. ``sufficient``, ``blocked``).
            **metrics: Additional attributes to store (e.g. scores).

        Returns:
            The updated query node.
        """
        resolved = self._resolve_query_id(query_id)
        if resolved is None:
            return {
                "error": (
                    f"query_id {query_id!r} 未匹配到任何 query 节点；请用 init_research/"
                    "get_next_queries/expand_query 返回的句柄（如 q3.1）或精确 ID 重试。"
                )
            }
        return graph_tools.upsert_node(
            "query", {"status": status, **metrics}, dedupe_key=resolved
        )

    def assess_convergence(self, goal_id: Optional[str] = None) -> dict:
        """Decide whether the research can stop, blending code and a thin LLM call.

        The deterministic parts — high-priority coverage at the score threshold
        and novelty diminishing returns — come from ``tools.convergence``. The
        LLM supplies only the two judgments it is suited for: which unresolved
        conflicts are fatal, and which open gaps would undermine the core
        conclusions. The ``recommendation`` is then composed in code.

        Args:
            goal_id: The research-goal node ID; accepted for signature parity
                with the rest of the Orchestrator toolkit and not required.

        Returns:
            dict with ``converged``, ``fatal_unresolved_conflicts``,
            ``core_threatening_gaps``, ``recommendation``, ``reason`` and a
            ``metrics_summary``.
        """
        from tools import convergence

        all_queries = graph_tools.search_nodes("query", {})
        core_queries = [
            {
                "text": q.get("text"),
                "status": q.get("status"),
                "sufficiency_score": q.get("sufficiency_score"),
            }
            for q in all_queries
            if q.get("priority_tier") == "high"
        ]
        open_queries = [
            {
                "text": q.get("text"),
                "status": q.get("status"),
                "priority_tier": q.get("priority_tier"),
            }
            for q in all_queries
            if q.get("status") not in ("sufficient", "blocked")
        ]
        conflicts = [
            {
                "description": c.get("description"),
                "conflict_type": c.get("conflict_type"),
            }
            for c in graph_tools.search_nodes("conflict", {})
            if c.get("resolution_status") != "resolved"
        ]
        prompt = (
            mm_prompts.assess_convergence
            .replace("{core_queries}", json.dumps(core_queries, ensure_ascii=False))
            .replace("{open_queries}", json.dumps(open_queries, ensure_ascii=False))
            .replace("{conflicts}", json.dumps(conflicts, ensure_ascii=False))
        )
        verdict = self._invoke_json(prompt)
        fatal = verdict.get("fatal_unresolved_conflicts") or []
        core_gaps = verdict.get("core_threatening_gaps") or []

        metrics = convergence.compute_metrics(advance_novelty=False)
        priority = metrics.get("priority", {})
        diminishing = bool(metrics.get("novelty", {}).get("diminishing"))
        structurally = bool(priority.get("structurally_converged"))
        pending_high = bool(priority.get("pending_high_priority"))

        # Diminishing returns only justify stopping once no high-priority query
        # is still pending (unsearched); otherwise there is obvious work left.
        if structurally and not fatal and not core_gaps:
            recommendation = "stop"
        elif diminishing and not pending_high:
            recommendation = "stop"
        else:
            recommendation = "continue"

        return {
            "converged": recommendation == "stop",
            "fatal_unresolved_conflicts": fatal,
            "core_threatening_gaps": core_gaps,
            "recommendation": recommendation,
            "reason": verdict.get("reason", ""),
            "metrics_summary": {
                "structurally_converged": structurally,
                "diminishing_novelty": diminishing,
                "high_priority_queries": metrics.get("priority", {}).get("tier_counts", {}).get("high", 0),
            },
        }

    # -----------------------------
    # Searcher-facing
    # -----------------------------
    def _assign_handle(self, attach_point: str) -> str:
        """Generate a short, stable handle (e.g. ``q1``, ``q3.1``) for a new query.

        The handle is what the Orchestrator references in later tool calls — a
        copy-safe alternative to the 20-digit node ID it transcribes unreliably.
        It is derived from the attach point: a child of the research goal gets a
        top-level ``q<n>``; a child of query ``q3`` gets ``q3.<k>``.

        Args:
            attach_point: The node the new query is being attached under (the
                research goal or an existing query).

        Returns:
            A handle string for the next child under ``attach_point``.
        """
        node = graph_tools.get_node(attach_point) or {}
        existing = len(graph_tools.get_query_children(attach_point))
        parent_handle = node.get("handle")
        if parent_handle:
            return f"{parent_handle}.{existing + 1}"
        # attach_point is the research goal (no handle) -> top-level handle.
        return f"q{existing + 1}"

    def _resolve_query_id(self, query_id: str) -> Optional[str]:
        """Map a query reference (handle, exact, truncated or corrupted ID) to a real node ID.

        The Orchestrator references queries by their short ``handle`` (``q3.1``)
        or, as a fallback, the node ID — which it sometimes truncates (drops the
        ``_<uuid8>`` suffix) or corrupts in the timestamp prefix. This recovers
        the real ID by, in order: exact node hit, handle match, prefix match
        (truncation), ``_<uuid8>`` suffix match (corrupted prefix), and text.

        Args:
            query_id: The query reference from the caller.

        Returns:
            The matching ``query`` node ID, or ``None`` if nothing matches.
        """
        if not query_id:
            return None
        node = graph_tools.get_node(query_id)
        if node and node.get("type") == "query":
            return query_id

        queries = graph_tools.search_nodes("query", {})
        # Short stable handle (e.g. ``q3.1``) — the preferred, copy-safe ref.
        for q in queries:
            if q.get("handle") and q.get("handle") == query_id:
                return q.get("id")
        # Truncated ID (the ``_<uuid8>`` suffix dropped).
        for q in queries:
            qid = q.get("id", "")
            if qid.startswith(query_id) or query_id.startswith(qid):
                return qid
        # Corrupted timestamp prefix but intact ``_<uuid8>`` suffix — the uuid8
        # is the unique discriminator, so match on it.
        ref_suffix = query_id.rsplit("_", 1)[-1]
        if ref_suffix and ref_suffix != query_id:
            for q in queries:
                if q.get("id", "").rsplit("_", 1)[-1] == ref_suffix:
                    return q.get("id")
        for q in queries:
            text = q.get("text") or ""
            if text and (text == query_id or query_id in text or text in query_id):
                return q.get("id")
        return None

    def get_query_context(self, query_id: str) -> dict:
        """Return existing context for a query to avoid duplicate searching.

        Args:
            query_id: The query node ID.

        Returns:
            dict with the ``query`` node and its ``existing_subgraph``.
        """
        resolved = self._resolve_query_id(query_id) or query_id
        return {
            "query": graph_tools.get_node(resolved),
            "existing_subgraph": graph_tools.get_query_subgraph(
                resolved, depth=4
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

        # Recover the real query node ID (handle / truncated / corrupted-prefix).
        resolved_query_id = self._resolve_query_id(query_id)
        if resolved_query_id is None:
            # Do not write an orphan search_run under an unresolved ID — that
            # silently detaches the evidence from the query tree. Report a zero
            # write so the Orchestrator's "未入图→重派" gate re-dispatches.
            return {
                "search_run_id": None,
                "query_id": query_id,
                "ref_map": {},
                "written": {"sources": 0, "documents": 0, "claims": 0, "evidence": 0, "conflicts": 0},
                "error": (
                    f"query_id {query_id!r} 未匹配到任何 query 节点，未写入图谱；"
                    "请用句柄（如 q3.1）或精确 query 节点 ID 重新派发。"
                ),
            }

        run_id = graph_tools.add_node(
            "search_run", {"query_id": resolved_query_id}
        )
        graph_tools.add_edge(resolved_query_id, run_id, "searched_by")

        for source in evidence_package.get("sources", []) or []:
            # Reuse an existing source node when the same URL was already
            # written; deduplication is the Graph Manager's job at write time.
            source_id = self.deduplicate_source(source) or graph_tools.create_source(
                url=_first(source, "url") or "",
                title=_first(source, "title"),
                source_type=_first(source, "source_type", "type"),
            )
            if source.get("local_ref"):
                ref_map[source["local_ref"]] = source_id
            graph_tools.add_edge(run_id, source_id, "found_source")

        for document in evidence_package.get("documents", []) or []:
            doc_id = graph_tools.create_document(
                text=_first(document, "document_summary", "summary_zh", "summary", "text", "content") or "",
                source_id=resolve(_first(document, "source_ref", "source")),
            )
            if document.get("local_ref"):
                ref_map[document["local_ref"]] = doc_id

        # Process claims first - these are the higher-level assertions
        for claim_item in evidence_package.get("claims", []) or []:
            claim_text = _first(claim_item, "statement", "text_zh", "text")
            if not claim_text:
                continue
            doc_ref = _first(claim_item, "document_ref", "document")
            claim_id = graph_tools.create_claim(
                statement=claim_text,
                document_id=resolve(doc_ref),
                source_id=resolve(_first(claim_item, "source_ref", "source")),
            )
            if claim_item.get("local_ref"):
                ref_map[claim_item["local_ref"]] = claim_id

        # Process evidence - these support or contradict claims
        for evidence_item in evidence_package.get("evidence", []) or []:
            evidence_text = _first(evidence_item, "statement", "evidence_text", "text_zh", "text")
            if not evidence_text:
                continue
            doc_ref = _first(evidence_item, "document_ref", "document")
            sources_ref = evidence_item.get("sources") or evidence_item.get("document_refs")
            if not doc_ref and isinstance(sources_ref, list) and sources_ref:
                doc_ref = sources_ref[0]
            
            # Check if this evidence supports a specific claim
            supports_ref = _first(evidence_item, "supports_or_contradicts", "supports_claim")
            supports_claim_id = resolve(supports_ref) if supports_ref else None
            
            evidence_id = graph_tools.create_evidence(
                claim=evidence_text,
                document_id=resolve(doc_ref),
                source_id=resolve(_first(evidence_item, "source_ref", "source")),
                supports_claim_id=supports_claim_id,
            )
            if evidence_item.get("local_ref"):
                ref_map[evidence_item["local_ref"]] = evidence_id

        for conflict in evidence_package.get("conflicts", []) or []:
            refs = conflict.get("evidence_refs") or conflict.get("related_claims") or []
            evidence_ids = [resolve(r) for r in refs if resolve(r)]
            
            # Extract conflict type if provided
            conflict_type = conflict.get("conflict_type", conflict.get("type", "factual"))
            # Validate and normalize conflict type
            valid_types = ["factual", "temporal", "methodological", "opinion"]
            if conflict_type not in valid_types:
                conflict_type = "factual"
            
            graph_tools.create_conflict(
                description=_first(conflict, "description", "description_zh") or "",
                evidence_ids=evidence_ids,
                conflict_type=conflict_type,
                resolution_status="unresolved"
            )

        graph_tools.save_graph()
        result = {
            "search_run_id": run_id,
            "query_id": resolved_query_id,
            "ref_map": ref_map,
            "written": {
                "sources": len(evidence_package.get("sources", []) or []),
                "documents": len(evidence_package.get("documents", []) or []),
                "claims": len(evidence_package.get("claims", []) or []),
                "evidence": len(evidence_package.get("evidence", []) or []),
                "conflicts": len(evidence_package.get("conflicts", []) or []),
            },
        }
        return result

    # -----------------------------
    # Reporter-facing
    # -----------------------------
    def export_report_context(self, goal_id: Optional[str] = None) -> dict:
        """Export the full graph context needed to write the report.

        Resolves the research goal from the graph's sole ``user_request`` node
        when ``goal_id`` is missing or does not match a node, so the report
        stage works without the caller tracking the exact ID.

        Args:
            goal_id: The ``user_request`` node ID; resolved automatically if
                omitted or unknown.

        Returns:
            dict with the goal node, the full sub-graph, and nodes grouped by
            type (``queries``, ``evidence``, ``conflicts``, ``analysis``,
            ``sources``, ``report_sections``).
        """
        goal = graph_tools.get_node(goal_id) if goal_id else {}
        if not goal:
            requests = graph_tools.search_nodes("user_request", {})
            if requests:
                goal = requests[0]
                goal_id = goal["id"]
        raw_subgraph = graph_tools.get_subgraph(goal_id, depth=8) if goal_id else {"nodes": [], "edges": []}

        # Strip internal scheduling fields from every node before they reach the
        # Reporter, so the writing context carries content only (not graph state).
        goal = _strip_internal_fields(goal) if goal else goal
        subgraph = {
            "nodes": [_strip_internal_fields(n) for n in raw_subgraph.get("nodes", [])],
            "edges": raw_subgraph.get("edges", []),
        }

        grouped: dict[str, list[dict]] = {
            "query": [],
            "evidence": [],
            "conflict": [],
            "analysis": [],
            "source": [],
            "report_section": [],
        }
        for node in subgraph["nodes"]:
            node_type = node.get("type")
            if node_type in grouped:
                grouped[node_type].append(node)

        # Local import avoids any import cycle (report_tools never imports this
        # module). The registry pre-numbers sources so the Reporter cites stable
        # [n] that finalize_report can rebuild deterministically.
        from tools import report_tools

        return {
            "goal": goal,
            "subgraph": subgraph,
            "queries": grouped["query"],
            "evidence": grouped["evidence"],
            "conflicts": grouped["conflict"],
            "analysis": grouped["analysis"],
            "sources": grouped["source"],
            "report_sections": grouped["report_section"],
            "reference_registry": report_tools.build_reference_registry(),
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
        # Validate evidence IDs exist in the graph
        valid_evidence_ids = []
        for eid in evidence_ids or []:
            if graph_tools.get_node(eid):
                valid_evidence_ids.append(eid)
            else:
                logger.warning(f"Evidence ID {eid} not found in graph, skipping")
        
        # Validate claim IDs exist in the graph
        valid_claim_ids = []
        for cid in claim_ids or []:
            if graph_tools.get_node(cid):
                valid_claim_ids.append(cid)
            else:
                logger.warning(f"Claim ID {cid} not found in graph, skipping")
        
        section_id = graph_tools.create_report_section(
            title=section.get("title", ""),
            content=section.get("content", ""),
            section_type=section.get("section_type"),
        )
        graph_tools.bind_evidence_to_section(
            section_id,
            evidence_ids=valid_evidence_ids,
            claim_ids=valid_claim_ids,
        )
        
        # Log binding statistics
        if evidence_ids or claim_ids:
            logger.info(
                f"Bound report section {section_id}: "
                f"{len(valid_evidence_ids)}/{len(evidence_ids or [])} evidence IDs, "
                f"{len(valid_claim_ids)}/{len(claim_ids or [])} claim IDs validated"
            )
        
        return section_id

    # -----------------------------
    # Internal LLM helpers
    # -----------------------------
    def _plan_initial_queries(self, user_request: str) -> dict:
        """Author the initial query set from the user request via the planner.

        Args:
            user_request: The original research request.

        Returns:
            dict with ``research_goal``, ``language`` and ``initial_queries``
            (each ``{text, importance}``).
        """
        prompt = mm_prompts.init_research.replace("{user_request}", user_request)
        return self._invoke_json(prompt)

    def _plan_followup_queries(
        self,
        direction: str,
        research_goal: str,
        parent_text: str,
        sibling_texts: list,
        gaps: Any,
        reason: str,
        max_new: int = 1,
    ) -> list:
        """Author self-contained follow-up query strings via the planner.

        Drops any authored query that references another query (a
        self-containment violation) and retries once before giving up.

        Args:
            direction: ``vertical`` (deepen the parent) or ``horizontal`` (add
                parallel sibling dimensions).
            research_goal: The overall research goal, for context.
            parent_text: The parent query/goal text whose subject is inlined.
            sibling_texts: Existing sibling query texts (for dedup).
            gaps: Gaps (vertical) or missing dimensions (horizontal) to cover.
            reason: Why this expansion is needed.
            max_new: Maximum number of queries to author.

        Returns:
            A list of ``{text, importance}`` dicts (cross-referencing ones dropped).
        """
        gaps_text = gaps if isinstance(gaps, str) else json.dumps(gaps or [], ensure_ascii=False)

        def author(extra: str = "") -> list:
            prompt = (
                mm_prompts.plan_followup_query
                .replace("{direction}", direction)
                .replace("{research_goal}", research_goal or "")
                .replace("{parent_text}", parent_text or "")
                .replace("{sibling_texts}", json.dumps(sibling_texts or [], ensure_ascii=False))
                .replace("{gaps}", gaps_text)
                .replace("{reason}", reason or "")
                .replace("{max_new}", str(max_new))
            )
            parsed = self._invoke_json(prompt + extra)
            items = []
            for raw in parsed.get("queries") or []:
                text, importance = _query_text_importance(raw)
                if text:
                    items.append({"text": text, "importance": importance})
            return items

        def self_contained(item: dict) -> bool:
            return not any(token in item["text"] for token in _CROSS_REF_TOKENS)

        queries = [q for q in author() if self_contained(q)]
        if not queries:
            retry = "\n\n注意：每条 query 必须自包含，把具体对象写进查询本身，禁止出现对其他 query 的指代。"
            queries = [q for q in author(retry) if self_contained(q)]
        return queries[:max_new]

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
        matches = graph_tools.search_nodes("source", {"url": url})
        return matches[0]["id"] if matches else None
