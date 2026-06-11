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

import hashlib
import json
import logging
import threading
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
_INTERNAL_NODE_FIELDS = ("kind", "status", "sufficiency_score", "_claim_lock", "_budget_lock")

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


def _query_spec(item: Any) -> tuple:
    """Return ``(text, importance, acceptance_criteria)`` from a query item.

    Accepts the structured ``{"text", "importance"}`` form or a bare string
    (lenient parsing). A missing importance is left as ``None`` so the priority
    model applies its own default.

    Args:
        item: One element of a planner's query list.

    Returns:
        A ``(text, importance)`` tuple.
    """
    if isinstance(item, dict):
        criteria = item.get("acceptance_criteria")
        return item.get("text"), item.get("importance"), criteria if isinstance(criteria, list) else []
    return item, None, []


def _gap_key(description: str) -> str:
    """Return a stable normalized fingerprint for one atomic knowledge gap."""
    normalized = " ".join((description or "").lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]


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
        self._state_lock = threading.RLock()

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

        from tools import middleware, research_state

        goal_id = graph_tools.create_user_request(
            request=user_request,
            research_goal=parsed.get("research_goal"),
            language=parsed.get("language"),
            time_window=parsed.get("time_window"),
            region_scope=parsed.get("region_scope"),
            source_preferences=parsed.get("source_preferences") or [],
            research_state="INITIALIZING",
            max_search_rounds=middleware.get_max_search_rounds(),
            dispatched_search_rounds=0,
            successful_search_rounds=0,
            last_convergence_recommendation="continue",
        )

        queries = []
        initial_queries = parsed.get("initial_queries")
        if not isinstance(initial_queries, list) or not initial_queries:
            initial_queries = [
            {
                "text": user_request,
                "importance": "core",
                "acceptance_criteria": ["Directly answer the user's research request with reliable evidence"],
            }
            ]
        for item in initial_queries:
            text, importance, criteria = _query_spec(item)
            if not isinstance(text, str) or not text.strip():
                continue
            importance = importance or "supporting"
            query_id = graph_tools.create_query_child(
                parent_id=goal_id,
                text=text,
                importance=importance,
                acceptance_criteria=criteria,
            )
            query = graph_tools.get_node(query_id)
            queries.append({
                "handle": query.get("handle"),
                "id": query_id,
                "text": text,
                "priority_tier": query.get("priority_tier"),
                "acceptance_criteria": criteria,
            })
        if not queries:
            query_id = graph_tools.create_query_child(
                parent_id=goal_id,
                text=user_request,
                importance="core",
                acceptance_criteria=["Directly answer the user's research request with reliable evidence"],
            )
            query = graph_tools.get_node(query_id)
            queries.append({
                "handle": query.get("handle"),
                "id": query_id,
                "text": user_request,
                "priority_tier": query.get("priority_tier"),
                "acceptance_criteria": query.get("acceptance_criteria") or [],
            })

        research_state.update_goal({"research_state": research_state.RESEARCHING}, goal_id)

        return {
            "goal_id": goal_id,
            "research_goal": parsed.get("research_goal", ""),
            "language": parsed.get("language"),
            "queries": queries,
        }

    def get_next_actions(self, limit: int = 4) -> list[dict]:
        """Return the highest-priority deterministic workflow actions.

        Advances existing work before dispatching new searches.

        Args:
            limit: Maximum number of queries to return.

        Returns:
            A list of ``{id, text, status, priority_tier, priority}`` dicts,
            highest priority first.
        """
        from tools import research_state

        status = research_state.get_status()
        if status.get("research_state") != research_state.RESEARCHING:
            return []

        queries = graph_tools.search_nodes("query", {})
        actions: list[dict] = []
        terminal = research_state.TERMINAL_QUERY_STATUSES
        for node in queries:
            query_status = node.get("status")
            action = None
            reason = ""
            gap_ids: list[str] = []
            if query_status == "assessing":
                action, reason = "assess_query", "successful search completed"
            elif query_status == "needs_expansion":
                gap_ids = self._query_gap_ids(node["id"], statuses={"open"})
                action, reason = "expand_gaps", "atomic gaps await child queries"
            elif query_status == "waiting_children":
                required_children = [
                    graph_tools.get_node(cid) for cid in graph_tools.get_query_children(node["id"])
                    if graph_tools.get_node(cid).get("required_for_parent", True)
                ]
                if required_children and all(c.get("status") in terminal for c in required_children):
                    action, reason = "assess_query", "all required child queries completed"
            elif query_status == "pending":
                action, reason = "dispatch_searcher", "query awaits its first successful search"
            if action:
                actions.append({
                    "action": action,
                    "query_id": node.get("handle") or node["id"],
                    "exact_query_id": node["id"],
                    "priority": node.get("priority", 0.0),
                    "required_for_parent": node.get("required_for_parent", True),
                    "required_path": research_state.is_required_path(node["id"]),
                    "semantic_importance": node.get("sem", 0.0),
                    "gap_ids": gap_ids,
                    "reason": reason,
                })

        action_rank = {"assess_query": 0, "expand_gaps": 1, "dispatch_searcher": 2}
        actions.sort(key=lambda a: (
            action_rank[a["action"]],
            -int(bool(a["required_path"])),
            -float(a["semantic_importance"] or 0.0),
            -float(a["priority"] or 0.0),
            a["exact_query_id"],
        ))
        remaining = research_state.remaining_budget()
        if remaining == 0 and any(a["action"] == "dispatch_searcher" for a in actions):
            research_state.mark_budget_exhausted()
            return []
        return actions[:limit]

    def _query_gap_ids(self, query_id: str, statuses: Optional[set[str]] = None) -> list[str]:
        """Return gap nodes owned by a Query, optionally filtered by status."""
        result = []
        for edge in graph_tools.get_node_edges(query_id, direction="out"):
            if str(edge.get("type", "")).lower() != "has_gap":
                continue
            gap = graph_tools.get_node(edge["target"])
            if gap.get("analysis_type") != "gap":
                continue
            if statuses is None or gap.get("status") in statuses:
                result.append(gap["id"])
        return result

    def _addressed_gap_ids(self, query_id: str) -> list[str]:
        """Return gap nodes assigned to a child Query."""
        return [
            edge["target"]
            for edge in graph_tools.get_node_edges(query_id, direction="out")
            if str(edge.get("type", "")).lower() == "addresses_gap"
        ]

    def assess_query(self, query_id: str) -> dict:
        """Assess one Query's owned evidence and automatically advance its state."""
        from tools import research_state

        if research_state.get_status().get("research_state") != research_state.RESEARCHING:
            return {"error": "Query assessment is only allowed while research_state is RESEARCHING"}
        resolved = self._resolve_query_id(query_id)
        if resolved is None:
            return {"error": f"Unknown query reference: {query_id!r}"}
        query = graph_tools.get_node(resolved)
        if query.get("status") not in {"assessing", "waiting_children"}:
            return {"error": f"Query {query.get('handle') or resolved} is not ready for assessment"}
        if query.get("status") == "waiting_children":
            required_children = [
                graph_tools.get_node(cid)
                for cid in graph_tools.get_query_children(resolved)
                if graph_tools.get_node(cid).get("required_for_parent", True)
            ]
            if any(c.get("status") not in {"sufficient", "blocked", "failed"} for c in required_children):
                return {"error": f"Query {query.get('handle') or resolved} still has unfinished required children"}

        evaluation = graph_tools.get_query_evaluation_subgraph(resolved)
        prompt = mm_prompts.assess_query.replace(
            "{query}", json.dumps({
                "text": query.get("text"),
                "acceptance_criteria": query.get("acceptance_criteria") or [],
            }, ensure_ascii=False)
        ).replace("{evaluation_subgraph}", json.dumps(evaluation, ensure_ascii=False))
        verdict = self._invoke_json(prompt)
        try:
            score = max(0.0, min(1.0, float(verdict.get("sufficiency_score", 0.0))))
        except (TypeError, ValueError):
            score = 0.0

        if int(query.get("low_novelty_streak") or 0) >= 2 and not (
            verdict.get("recommendation") == "sufficient" and score >= 0.7
        ):
            for gap_id in self._query_gap_ids(resolved, {"open", "assigned"}):
                graph_tools.upsert_node(NodeType.ANALYSIS, {
                    "status": "blocked",
                    "resolution_reason": "two consecutive low-novelty searches on this gap path",
                }, gap_id)
            graph_tools.transition_query(
                resolved,
                "blocked",
                sufficiency_score=score,
                covered=verdict.get("covered") or [],
                assessment_reason="branch stopped after two consecutive low-novelty searches",
            )
            self._propagate_child_completion(resolved, "blocked")
            return {
                "query_id": query.get("handle") or resolved,
                "exact_query_id": resolved,
                "sufficiency_score": score,
                "status": "blocked",
                "created_gaps": [],
                "next_action": "get_next_actions",
            }

        created_gaps: list[str] = []
        existing = {
            graph_tools.get_node(gid).get("gap_key"): gid
            for gid in self._query_gap_ids(resolved)
        }
        raw_gaps = verdict.get("gaps") or []
        if not isinstance(raw_gaps, list):
            raw_gaps = []
        for raw in raw_gaps:
            if isinstance(raw, str):
                spec = {"description": raw, "importance": "supporting"}
            elif isinstance(raw, dict):
                spec = raw
            else:
                continue
            description = str(spec.get("description") or "").strip()
            if not description:
                continue
            key = _gap_key(description)
            if key in existing or self._gap_key_in_ancestors(resolved, key):
                continue
            importance = spec.get("importance")
            if importance not in {"core", "supporting", "peripheral"}:
                importance = "supporting"
            gap_id = graph_tools.create_analysis(
                text=description,
                query_id=resolved,
                analysis_type="gap",
                description=description,
                gap_key=key,
                importance=importance,
                required_for_parent=importance != "peripheral",
                status="open",
                acceptance_criteria=(
                    spec.get("acceptance_criteria")
                    if isinstance(spec.get("acceptance_criteria"), list)
                    else []
                ),
            )
            existing[key] = gap_id
            created_gaps.append(gap_id)

        recommendation = verdict.get("recommendation")
        if recommendation == "blocked":
            new_status = "blocked"
        elif recommendation == "sufficient" and score >= 0.7 and not created_gaps:
            new_status = "sufficient"
        elif created_gaps or self._query_gap_ids(resolved, {"open"}):
            new_status = "needs_expansion"
        else:
            # An insufficient assessment must always leave an actionable,
            # atomic gap rather than sending the same Query back to search.
            description = str(verdict.get("reason") or "Evidence remains insufficient for the query").strip()
            key = _gap_key(description)
            if key in existing or self._gap_key_in_ancestors(resolved, key):
                new_status = "blocked"
            else:
                gap_id = graph_tools.create_analysis(
                    text=description,
                    query_id=resolved,
                    analysis_type="gap",
                    description=description,
                    gap_key=key,
                    importance="supporting",
                    required_for_parent=True,
                    status="open",
                    acceptance_criteria=[],
                )
                created_gaps.append(gap_id)
                new_status = "needs_expansion"

        graph_tools.transition_query(
            resolved,
            new_status,
            sufficiency_score=score,
            covered=verdict.get("covered") or [],
            assessment_reason=verdict.get("reason") or "",
        )
        if new_status in {"sufficient", "blocked"}:
            self._propagate_child_completion(resolved, new_status)
        return {
            "query_id": query.get("handle") or resolved,
            "exact_query_id": resolved,
            "sufficiency_score": score,
            "status": new_status,
            "created_gaps": created_gaps,
            "next_action": "expand_gaps" if new_status == "needs_expansion" else "get_next_actions",
        }

    def _gap_key_in_ancestors(self, query_id: str, gap_key: str) -> bool:
        """Return whether a gap fingerprint already exists on the ancestor path."""
        current = graph_tools.get_query_parent(query_id)
        while current:
            node = graph_tools.get_node(current)
            if node.get("type") != NodeType.QUERY.value:
                break
            for gap_id in self._query_gap_ids(current):
                if graph_tools.get_node(gap_id).get("gap_key") == gap_key:
                    return True
            current = graph_tools.get_query_parent(current)
        return False

    def _propagate_child_completion(self, query_id: str, child_status: str) -> None:
        """Resolve assigned gaps and make a completed child's parent assessable."""
        gap_status = "resolved" if child_status == "sufficient" else "blocked"
        for gap_id in self._addressed_gap_ids(query_id):
            gap = graph_tools.get_node(gap_id)
            graph_tools.upsert_node(NodeType.ANALYSIS, {
                "status": gap_status,
                "resolution_reason": f"child query finished as {child_status}",
            }, gap_id)
            conflict_id = gap.get("conflict_id")
            if conflict_id:
                graph_tools.upsert_node(NodeType.CONFLICT, {
                    "resolution_status": "resolved" if child_status == "sufficient" else "disclosed",
                }, conflict_id)
        parent_id = graph_tools.get_query_parent(query_id)
        parent = graph_tools.get_node(parent_id) if parent_id else {}
        if parent.get("type") != NodeType.QUERY.value or parent.get("status") != "waiting_children":
            return
        required_children = [
            graph_tools.get_node(cid) for cid in graph_tools.get_query_children(parent_id)
            if graph_tools.get_node(cid).get("required_for_parent", True)
        ]
        if required_children and all(c.get("status") in {"sufficient", "blocked", "failed"} for c in required_children):
            graph_tools.transition_query(parent_id, "assessing")

    def expand_gaps(self, parent_id: str, gap_ids: Optional[list[str]] = None) -> dict:
        """Create one self-contained child Query per open atomic gap."""
        from tools import research_state

        if research_state.get_status().get("research_state") != research_state.RESEARCHING:
            return {"error": "Gap expansion is only allowed while research_state is RESEARCHING"}
        resolved = self._resolve_query_id(parent_id)
        if resolved is None:
            return {"error": f"Unknown query reference: {parent_id!r}"}
        parent = graph_tools.get_node(resolved)
        if parent.get("status") != "needs_expansion":
            return {"error": f"Query {parent.get('handle') or resolved} is not awaiting expansion"}
        if int(parent.get("low_novelty_streak") or 0) >= 2:
            for gap_id in self._query_gap_ids(resolved, {"open"}):
                graph_tools.upsert_node(NodeType.ANALYSIS, {
                    "status": "blocked",
                    "resolution_reason": "two consecutive low-novelty searches on this branch",
                }, gap_id)
            graph_tools.transition_query(resolved, "blocked")
            self._propagate_child_completion(resolved, "blocked")
            return {
                "parent_id": parent.get("handle") or resolved,
                "created": [],
                "blocked_for_low_novelty": True,
                "next_action": "get_next_actions",
            }
        owned_open_gap_ids = set(self._query_gap_ids(resolved, {"open"}))
        candidates = gap_ids or list(owned_open_gap_ids)
        gaps = [
            graph_tools.get_node(gid) for gid in candidates
            if gid in owned_open_gap_ids
            and graph_tools.get_node(gid).get("analysis_type") == "gap"
            and graph_tools.get_node(gid).get("status") == "open"
        ]
        remaining = research_state.remaining_budget()
        deferred = []
        if remaining is not None:
            deferred = gaps[remaining:]
            gaps = gaps[:remaining]
            for gap in deferred:
                graph_tools.upsert_node(NodeType.ANALYSIS, {
                    "status": "deferred_budget",
                    "resolution_reason": "insufficient remaining search budget",
                }, gap["id"])

        created = []
        goal = research_state.get_goal()
        sibling_texts = [
            graph_tools.get_node(cid).get("text")
            for cid in graph_tools.get_query_children(resolved)
        ]
        for gap in gaps:
            gap_key = gap.get("gap_key")
            if gap_key and self._gap_key_in_ancestors(resolved, gap_key):
                graph_tools.upsert_node(NodeType.ANALYSIS, {
                    "status": "blocked",
                    "resolution_reason": "duplicate gap_key already exists on the ancestor path",
                }, gap["id"])
                continue
            followups = self._plan_followup_queries(
                research_goal=goal.get("research_goal") or goal.get("request") or "",
                parent_text=parent.get("text") or "",
                sibling_texts=sibling_texts,
                gaps=[{
                    "id": gap["id"],
                    "description": gap.get("description") or gap.get("text"),
                    "acceptance_criteria": gap.get("acceptance_criteria") or [],
                }],
                reason=gap.get("description") or gap.get("text") or "",
                max_new=1,
            )
            if not followups:
                graph_tools.upsert_node(NodeType.ANALYSIS, {
                    "status": "blocked",
                    "resolution_reason": "query planner could not author a self-contained child query",
                }, gap["id"])
                continue
            spec = followups[0]
            importance = spec.get("importance") or gap.get("importance") or "supporting"
            child_id = graph_tools.create_query_child(
                parent_id=resolved,
                text=spec["text"],
                importance=importance,
                acceptance_criteria=spec.get("acceptance_criteria") or gap.get("acceptance_criteria") or [],
                gap_ids=[gap["id"]],
            )
            child = graph_tools.get_node(child_id)
            created.append({"id": child_id, "handle": child.get("handle"), "text": child.get("text"), "gap_id": gap["id"]})
            sibling_texts.append(child.get("text"))

        next_status = "waiting_children" if created else "blocked"
        graph_tools.transition_query(resolved, next_status)
        if next_status == "blocked":
            self._propagate_child_completion(resolved, "blocked")
        return {
            "parent_id": parent.get("handle") or resolved,
            "created": created,
            "deferred_gap_ids": [g["id"] for g in deferred],
            "next_action": "get_next_actions",
        }

    def assess_convergence(self, goal_id: Optional[str] = None) -> dict:
        """Authorize reporting only when required tree branches have terminated."""
        from tools import research_state

        current_state = research_state.get_status(goal_id).get("research_state")
        if current_state != research_state.RESEARCHING:
            return {
                "converged": current_state in {research_state.REPORT_READY, research_state.BUDGET_EXHAUSTED},
                "recommendation": "stop" if current_state in research_state.REPORT_ALLOWED else "failed",
                "research_state": current_state,
                "next_actions": [],
            }
        tree = graph_tools.validate_query_tree()
        all_queries = graph_tools.search_nodes("query", {})
        if not tree.get("valid") or not all_queries:
            reason = "invalid Query tree" if not tree.get("valid") else "research has no Query nodes"
            research_state.update_goal({
                "research_state": research_state.FAILED,
                "last_convergence_recommendation": "continue",
                "last_error": reason,
            }, goal_id)
            return {
                "converged": False,
                "fatal_unresolved_conflicts": [],
                "open_required_gaps": [],
                "open_required_queries": [],
                "recommendation": "failed",
                "reason": reason,
                "research_state": research_state.FAILED,
                "tree_validation": tree,
                "next_actions": [],
            }
        open_required = [
            q for q in all_queries
            if research_state.is_required_path(q["id"])
            and q.get("status") not in research_state.TERMINAL_QUERY_STATUSES
        ]
        open_gaps = [
            gap for gap in graph_tools.search_nodes("analysis", {"analysis_type": "gap"})
            if research_state.gap_is_required_path(gap["id"])
            and gap.get("status") in research_state.OPEN_GAP_STATUSES
        ]
        conflicts = [
            {
                "id": c.get("id"),
                "description": c.get("description"),
                "conflict_type": c.get("conflict_type"),
            }
            for c in graph_tools.search_nodes("conflict", {})
            if c.get("resolution_status") not in {"resolved", "disclosed"}
        ]
        prompt = (
            mm_prompts.assess_convergence
            .replace("{core_queries}", json.dumps(all_queries, ensure_ascii=False))
            .replace("{open_queries}", json.dumps(open_required, ensure_ascii=False))
            .replace("{conflicts}", json.dumps(conflicts, ensure_ascii=False))
        )
        verdict = self._invoke_json(prompt)
        fatal = verdict.get("fatal_unresolved_conflicts") or []
        goal = research_state.get_goal(goal_id)
        for fatal_description in fatal:
            conflict = next(
                (c for c in graph_tools.search_nodes("conflict", {})
                 if c.get("description") == fatal_description),
                None,
            )
            if not conflict:
                continue
            owner_id = self._conflict_owner_query(conflict["id"])
            if not owner_id:
                continue
            key = _gap_key(f"Resolve conflict: {fatal_description}")
            owner = graph_tools.get_node(owner_id)
            gap_parent_id = (
                goal["id"]
                if owner.get("status") in research_state.TERMINAL_QUERY_STATUSES
                else owner_id
            )
            if key not in {
                graph_tools.get_node(gid).get("gap_key") for gid in self._query_gap_ids(gap_parent_id)
            }:
                gap_id = graph_tools.create_analysis(
                    text=f"Resolve conflict: {fatal_description}",
                    query_id=gap_parent_id,
                    analysis_type="gap",
                    description=f"Resolve conflict: {fatal_description}",
                    gap_key=key,
                    importance="core",
                    required_for_parent=True,
                    status="open",
                    conflict_id=conflict["id"],
                    acceptance_criteria=["Find independent evidence that resolves or clearly scopes the conflict"],
                )
                open_gaps.append(graph_tools.get_node(gap_id))
                if gap_parent_id == goal["id"]:
                    child_id = graph_tools.create_query_child(
                        parent_id=goal["id"],
                        text=fatal_description,
                        importance="core",
                        acceptance_criteria=[
                            "Find independent evidence that resolves or clearly scopes the conflict"
                        ],
                        gap_ids=[gap_id],
                    )
                    open_required.append(graph_tools.get_node(child_id))
                elif owner.get("status") == "assessing":
                    graph_tools.transition_query(owner_id, "needs_expansion")
        remaining = research_state.remaining_budget(goal_id)
        if remaining == 0 and (open_required or open_gaps):
            research_state.mark_budget_exhausted(goal_id)
            recommendation = "stop"
            state = research_state.BUDGET_EXHAUSTED
        elif tree["valid"] and not open_required and not open_gaps and not fatal:
            research_state.update_goal({
                "research_state": research_state.REPORT_READY,
                "last_convergence_recommendation": "stop",
                "report_authorized_reason": "all required query branches converged",
            }, goal_id)
            recommendation = "stop"
            state = research_state.REPORT_READY
        else:
            research_state.update_goal({
                "research_state": research_state.RESEARCHING,
                "last_convergence_recommendation": "continue",
                "report_authorized_reason": None,
            }, goal_id)
            recommendation = "continue"
            state = research_state.RESEARCHING

        return {
            "converged": recommendation == "stop",
            "fatal_unresolved_conflicts": fatal,
            "open_required_gaps": [
                {"id": g["id"], "description": g.get("description") or g.get("text")}
                for g in open_gaps
            ],
            "open_required_queries": [
                {"id": q["id"], "handle": q.get("handle"), "status": q.get("status")}
                for q in open_required
            ],
            "recommendation": recommendation,
            "reason": verdict.get("reason", ""),
            "research_state": state,
            "tree_validation": tree,
            "next_actions": self.get_next_actions() if recommendation == "continue" else [],
        }

    def _conflict_owner_query(self, conflict_id: str) -> Optional[str]:
        """Return the Query whose SearchRun produced a conflict."""
        for edge in graph_tools.get_node_edges(conflict_id, direction="in"):
            if str(edge.get("type", "")).lower() != "produced":
                continue
            run_id = edge.get("source")
            for parent_edge in graph_tools.get_node_edges(run_id, direction="in"):
                if str(parent_edge.get("type", "")).lower() == "searched_by":
                    return parent_edge.get("source")
        return None

    # -----------------------------
    # Searcher-facing
    # -----------------------------
    def prepare_search(self, query_id: str, source_preferences: Optional[list[str]] = None) -> dict:
        """Atomically claim a pending Query, reserve budget and create a SearchRun."""
        from tools import research_state

        with self._state_lock:
            goal = research_state.get_goal()
            if goal.get("research_state") != research_state.RESEARCHING:
                return {
                    "error": "Search dispatch is only allowed while research_state is RESEARCHING",
                    "research_state": goal.get("research_state"),
                }
            resolved = self._resolve_query_id(query_id)
            if resolved is None:
                return {"error": f"Unknown query reference: {query_id!r}"}
            query = graph_tools.get_node(resolved)
            if query.get("status") != "pending":
                return {"error": f"Query {query.get('handle') or resolved} is not pending", "status": query.get("status")}
            if int(query.get("successful_search_runs") or 0) > 0:
                return {"error": "A Query with a successful SearchRun cannot be searched again; expand its gaps instead"}
            remaining = research_state.remaining_budget()
            if remaining == 0:
                goal = research_state.mark_budget_exhausted()
                return {"error": "Search budget exhausted", "research_state": goal.get("research_state")}

            claim = graph_tools.claim_query_search(resolved, goal["id"])
            if not claim:
                refreshed = graph_tools.get_node(resolved)
                if research_state.remaining_budget(goal["id"]) == 0:
                    goal = research_state.mark_budget_exhausted(goal["id"])
                    return {"error": "Search budget exhausted", "research_state": goal.get("research_state")}
                return {
                    "error": "Query could not be atomically claimed for search",
                    "status": refreshed.get("status"),
                }
            run_id = claim["search_run_id"]

            gaps = [graph_tools.get_node(gid) for gid in self._addressed_gap_ids(resolved)]
            parent = graph_tools.get_node(graph_tools.get_query_parent(resolved) or "")
            task = {
                "query": query.get("text"),
                "acceptance_criteria": query.get("acceptance_criteria") or [],
                "assigned_gaps": [
                    {
                        "description": g.get("description") or g.get("text"),
                        "acceptance_criteria": g.get("acceptance_criteria") or [],
                    }
                    for g in gaps
                ],
                "research_goal": goal.get("research_goal") or goal.get("request"),
                "time_window": goal.get("time_window"),
                "region_scope": goal.get("region_scope"),
                "source_preferences": source_preferences or goal.get("source_preferences") or [],
                "parent_covered": parent.get("covered") or [],
                "requirement": "Collect evidence for this Query only. Do not broaden into sibling topics.",
            }
            return {
                "search_run_id": run_id,
                "query_id": resolved,
                "query_handle": query.get("handle"),
                "query_text": json.dumps(task, ensure_ascii=False),
            }

    def fail_search(self, search_run_id: str, query_id: str, error: str) -> dict:
        """Record a Searcher execution failure and make the Query retryable."""
        with self._state_lock:
            resolved = self._resolve_query_id(query_id)
            query = graph_tools.get_node(resolved) if resolved else {}
            run = graph_tools.get_node(search_run_id)
            if (
                not resolved
                or query.get("status") != "searching"
                or run.get("type") != NodeType.SEARCH_RUN.value
                or run.get("status") != "running"
                or run.get("query_id") != resolved
            ):
                return {
                    "search_run_id": search_run_id,
                    "query_id": resolved,
                    "error": "SearchRun is not running or does not belong to the Query",
                }
            attempts = int(query.get("search_attempts") or 0)
            next_status = "failed" if attempts >= 3 else "pending"
            graph_tools.upsert_node(NodeType.SEARCH_RUN, {"status": "failed", "error": error}, search_run_id)
            graph_tools.transition_query(resolved, next_status, last_error=error)
            if next_status == "failed":
                self._propagate_child_completion(resolved, "failed")
            return {"search_run_id": search_run_id, "query_id": resolved, "status": next_status, "error": error}

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
        if node and str(node.get("type", "")).lower() == "query":
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
            "existing_subgraph": graph_tools.get_query_evaluation_subgraph(resolved),
        }

    def create_insight(self, text: str, query_id: Optional[str] = None) -> dict:
        """Create a typed insight and safely bind an optional Query handle."""
        resolved = self._resolve_query_id(query_id) if query_id else None
        if query_id and resolved is None:
            return {"error": f"Unknown query reference: {query_id!r}"}
        insight_id = graph_tools.create_analysis(text=text, query_id=resolved, analysis_type="insight")
        return {"analysis_id": insight_id, "query_id": resolved}

    def submit_search_result(self, search_run_id: str, query_id: str, evidence_package: dict) -> dict:
        """Write one Searcher's result exactly once and advance its Query."""
        with self._state_lock:
            return self._submit_search_result_unlocked(search_run_id, query_id, evidence_package)

    def _validate_evidence_package_refs(self, evidence_package: dict) -> Optional[str]:
        """Return a reference-validation error before any evidence nodes are written."""
        local_types: dict[str, str] = {}
        sections = {
            "sources": ("Source", lambda item: bool(_first(item, "url"))),
            "documents": ("Document", lambda item: bool(_first(item, "document_summary", "summary_zh", "summary", "text", "content"))),
            "claims": ("Claim", lambda item: bool(_first(item, "statement", "text_zh", "text"))),
            "evidence": ("Evidence", lambda item: bool(_first(item, "statement", "evidence_text", "text_zh", "text"))),
        }
        for section, (node_type, valid) in sections.items():
            for item in evidence_package.get(section, []) or []:
                ref = item.get("local_ref")
                if ref and valid(item):
                    local_types[ref] = node_type

        def valid_ref(ref: Optional[str], expected: str) -> bool:
            if not ref:
                return False
            if ref in local_types:
                return local_types[ref] == expected
            return graph_tools.get_node(ref).get("type") == expected

        for document in evidence_package.get("documents", []) or []:
            if not valid_ref(_first(document, "source_ref", "source"), NodeType.SOURCE.value):
                return "Document source_ref must reference a valid Source"
        for claim in evidence_package.get("claims", []) or []:
            if not valid_ref(_first(claim, "document_ref", "document"), NodeType.DOCUMENT.value):
                return "Claim document_ref must reference a valid Document"
            if not valid_ref(_first(claim, "source_ref", "source"), NodeType.SOURCE.value):
                return "Claim source_ref must reference a valid Source"
        for evidence in evidence_package.get("evidence", []) or []:
            if not valid_ref(_first(evidence, "document_ref", "document"), NodeType.DOCUMENT.value):
                return "Evidence document_ref must reference a valid Document"
            if not valid_ref(_first(evidence, "source_ref", "source"), NodeType.SOURCE.value):
                return "Evidence source_ref must reference a valid Source"
            supports = _first(evidence, "supports_or_contradicts", "supports_claim")
            if supports and not valid_ref(supports, NodeType.CLAIM.value):
                return "Evidence supports_or_contradicts must reference a valid Claim"
        for conflict in evidence_package.get("conflicts", []) or []:
            refs = conflict.get("evidence_refs") or conflict.get("related_claims") or []
            if any(not valid_ref(ref, NodeType.EVIDENCE.value) for ref in refs):
                return "Conflict evidence_refs must all reference valid Evidence"
        return None

    def _submit_search_result_unlocked(self, search_run_id: str, query_id: str, evidence_package: dict) -> dict:
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
        source_ids: list[str] = []
        document_ids: list[str] = []
        claim_ids: list[str] = []
        evidence_ids: list[str] = []
        conflict_ids: list[str] = []

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

        run = graph_tools.get_node(search_run_id)
        query = graph_tools.get_node(resolved_query_id)
        if (
            run.get("type") != NodeType.SEARCH_RUN.value
            or run.get("query_id") != resolved_query_id
            or run.get("status") != "running"
            or query.get("status") != "searching"
        ):
            return {
                "search_run_id": search_run_id,
                "query_id": resolved_query_id,
                "written": {"sources": 0, "documents": 0, "claims": 0, "evidence": 0, "conflicts": 0},
                "error": "SearchRun is not running or does not belong to the Query",
            }
        validation_error = self._validate_evidence_package_refs(evidence_package)
        if validation_error:
            return self.fail_search(search_run_id, resolved_query_id, validation_error)
        run_id = search_run_id
        produced_ids: list[str] = []

        for source in evidence_package.get("sources", []) or []:
            # Reuse an existing source node when the same URL was already
            # written; deduplication is the Graph Manager's job at write time.
            url = _first(source, "url")
            if not url:
                continue
            source_id = self.deduplicate_source(source) or graph_tools.create_source(
                url=url,
                title=_first(source, "title"),
                source_type=_first(source, "source_type", "type"),
            )
            source_ids.append(source_id)
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
            document_ids.append(doc_id)
            produced_ids.append(doc_id)

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
            claim_ids.append(claim_id)
            produced_ids.append(claim_id)

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
            evidence_ids.append(evidence_id)
            produced_ids.append(evidence_id)

        for conflict in evidence_package.get("conflicts", []) or []:
            refs = conflict.get("evidence_refs") or conflict.get("related_claims") or []
            conflict_evidence_ids = [resolve(r) for r in refs if resolve(r)]
            
            # Extract conflict type if provided
            conflict_type = conflict.get("conflict_type", conflict.get("type", "factual"))
            # Validate and normalize conflict type
            valid_types = ["factual", "temporal", "methodological", "opinion"]
            if conflict_type not in valid_types:
                conflict_type = "factual"
            
            conflict_id = graph_tools.create_conflict(
                description=_first(conflict, "description", "description_zh") or "",
                evidence_ids=conflict_evidence_ids,
                conflict_type=conflict_type,
                resolution_status="unresolved"
            )
            conflict_ids.append(conflict_id)
            produced_ids.append(conflict_id)

        for node_id in produced_ids:
            graph_tools.add_edge(run_id, node_id, EdgeType.PRODUCED)

        source_count = len(source_ids)
        evidence_count = len(evidence_ids)
        succeeded = source_count > 0 and evidence_count > 0
        evidence_keys = {
            _gap_key(_first(item, "statement", "evidence_text", "text_zh", "text") or "")
            for item in evidence_package.get("evidence", []) or []
            if _first(item, "statement", "evidence_text", "text_zh", "text")
        }
        ancestor_keys = self._ancestor_evidence_keys(resolved_query_id)
        novelty = len(evidence_keys - ancestor_keys) / len(evidence_ids) if evidence_ids else None
        parent = graph_tools.get_node(graph_tools.get_query_parent(resolved_query_id) or "")
        parent_streak = int(parent.get("low_novelty_streak") or 0)
        low_streak = parent_streak + 1 if novelty is not None and novelty < 0.2 else 0

        run_status = "succeeded" if succeeded else "empty"
        graph_tools.upsert_node(NodeType.SEARCH_RUN, {
            "status": run_status,
            "novelty_score": novelty,
            "evidence_fingerprints": sorted(evidence_keys),
        }, run_id)
        if succeeded:
            from tools import research_state

            goal = research_state.get_goal()
            graph_tools.transition_query(
                resolved_query_id,
                "assessing",
                successful_search_runs=1,
                low_novelty_streak=low_streak,
            )
            graph_tools.increment_successful_search_rounds(goal["id"])
        else:
            attempts = int(query.get("search_attempts") or 0)
            next_status = "blocked" if attempts >= 3 else "pending"
            transition_attributes = (
                {"block_reason": "three SearchRuns completed without valid Source and Evidence"}
                if next_status == "blocked"
                else {}
            )
            graph_tools.transition_query(resolved_query_id, next_status, **transition_attributes)
            if next_status == "blocked":
                self._propagate_child_completion(resolved_query_id, "blocked")

        graph_tools.save_graph()
        result = {
            "search_run_id": run_id,
            "query_id": resolved_query_id,
            "ref_map": ref_map,
            "written": {
                "sources": len(source_ids),
                "documents": len(document_ids),
                "claims": len(claim_ids),
                "evidence": len(evidence_ids),
                "conflicts": len(conflict_ids),
            },
            "status": run_status,
            "query_status": "assessing" if succeeded else ("blocked" if int(query.get("search_attempts") or 0) >= 3 else "pending"),
            "novelty_score": novelty,
        }
        return result

    def _ancestor_evidence_keys(self, query_id: str) -> set[str]:
        """Collect evidence fingerprints produced on the Query's ancestor path."""
        keys: set[str] = set()
        current = graph_tools.get_query_parent(query_id)
        while current:
            node = graph_tools.get_node(current)
            if node.get("type") != NodeType.QUERY.value:
                break
            evaluation = graph_tools.get_query_evaluation_subgraph(current)
            for item in evaluation.get("nodes", []):
                if item.get("type") == NodeType.EVIDENCE.value:
                    keys.add(_gap_key(item.get("claim") or ""))
            current = graph_tools.get_query_parent(current)
        return keys

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
        raw_subgraph = {
            "nodes": graph_tools.get_all_nodes(),
            "edges": graph_tools.get_all_edges(),
        } if goal_id else {"nodes": [], "edges": []}
        raw_limitations = [
            node for node in raw_subgraph["nodes"]
            if str(node.get("type") or "").lower() == "analysis"
            and node.get("analysis_type") == "gap"
            and node.get("status") in {"blocked", "deferred_budget", "open", "assigned"}
        ]
        raw_limitations.extend(
            node for node in raw_subgraph["nodes"]
            if str(node.get("type") or "").lower() == "query"
            and node.get("status") != "sufficient"
        )
        raw_limitations.extend(
            node for node in raw_subgraph["nodes"]
            if str(node.get("type") or "").lower() == "conflict"
            and node.get("resolution_status") in {"unresolved", "investigating", "disclosed"}
        )

        # Strip internal scheduling fields from every node before they reach the
        # Reporter, so the writing context carries content only (not graph state).
        goal = _strip_internal_fields(goal) if goal else goal
        subgraph = {
            "nodes": [_strip_internal_fields(n) for n in raw_subgraph.get("nodes", [])],
            "edges": raw_subgraph.get("edges", []),
        }

        grouped: dict[str, list[dict]] = {
            "query": [], "evidence": [], "conflict": [], "analysis": [],
            "source": [], "reportsection": [],
        }
        for node in subgraph["nodes"]:
            node_type = str(node.get("type") or "").lower()
            if node_type in grouped:
                grouped[node_type].append(node)

        # Local import avoids any import cycle (report_tools never imports this
        # module). The registry pre-numbers sources so the Reporter cites stable
        # [n] that finalize_report can rebuild deterministically.
        from tools import report_tools, research_state

        return {
            "goal": goal,
            "subgraph": subgraph,
            "queries": grouped["query"],
            "evidence": grouped["evidence"],
            "conflicts": grouped["conflict"],
            "analysis": grouped["analysis"],
            "sources": grouped["source"],
            "report_sections": grouped["reportsection"],
            "research_status": research_state.get_status(goal_id),
            "limitations": raw_limitations,
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
        valid_evidence_ids = []
        for eid in evidence_ids or []:
            if graph_tools.get_node(eid).get("type") == NodeType.EVIDENCE.value:
                valid_evidence_ids.append(eid)
            else:
                raise ValueError(f"ReportSection evidence binding requires Evidence: {eid!r}")
        
        # Validate claim IDs exist in the graph
        valid_claim_ids = []
        for cid in claim_ids or []:
            if graph_tools.get_node(cid).get("type") == NodeType.CLAIM.value:
                valid_claim_ids.append(cid)
            else:
                raise ValueError(f"ReportSection claim binding requires Claim: {cid!r}")
        
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
                .replace("{research_goal}", research_goal or "")
                .replace("{parent_text}", parent_text or "")
                .replace("{sibling_texts}", json.dumps(sibling_texts or [], ensure_ascii=False))
                .replace("{gaps}", gaps_text)
                .replace("{reason}", reason or "")
                .replace("{max_new}", str(max_new))
            )
            parsed = self._invoke_json(prompt + extra)
            items = []
            raw_queries = parsed.get("queries") or []
            if not isinstance(raw_queries, list):
                raw_queries = []
            for raw in raw_queries:
                text, importance, criteria = _query_spec(raw)
                if isinstance(text, str) and text.strip():
                    items.append({"text": text, "importance": importance, "acceptance_criteria": criteria})
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
