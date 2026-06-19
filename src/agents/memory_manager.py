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
import re
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

OBJECTIVE_COVERAGE_THRESHOLD = 0.75
OBJECTIVE_CONFIDENCE_THRESHOLD = 0.65
EXPANSION_UTILITY_THRESHOLD = 0.45
LOW_REALIZED_GAIN_THRESHOLD = 0.05
LOW_GAIN_WINDOW = 2
_GAP_CATEGORIES = {
    "missing_core_evidence",
    "fatal_conflict",
    "enrichment",
    "additional_example",
    "verification",
    "detail",
}


class AmbiguousQueryReference(ValueError):
    """Raised when a short Query reference matches more than one node."""

    def __init__(self, reference: str, matches: list[str]):
        """Describe the ambiguous reference and every matching exact ID."""
        super().__init__(
            f"Ambiguous query reference {reference!r}; use one exact query ID from {matches}"
        )
        self.reference = reference
        self.matches = matches


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
        objective_keys = item.get("objective_keys")
        return (
            item.get("text"),
            item.get("importance"),
            criteria if isinstance(criteria, list) else [],
            objective_keys if isinstance(objective_keys, list) else [],
        )
    return item, None, [], []


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
        from tools import middleware, research_state

        with self._state_lock:
            existing_goals = graph_tools.search_nodes("user_request", {})
            if existing_goals:
                return {
                    "error": "Research is already initialized in this run context",
                    "existing_goal_id": existing_goals[0]["id"],
                }

            parsed = self._plan_initial_queries(user_request)
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
                scope_mode=(
                    parsed.get("scope_mode")
                    if parsed.get("scope_mode") in {"bounded", "exhaustive"}
                    else "bounded"
                ),
                convergence_policy="aggressive",
                portfolio_revision=1,
                evaluated_portfolio_revision=1,
                last_max_marginal_utility=0.0,
                report_readiness_score=0.0,
                report_phase=None,
                report_revision_attempts=0,
                report_quality_status=None,
                report_validation_issues=[],
            )

        objectives = self._create_objectives(goal_id, parsed.get("objectives"), user_request)
        queries = []
        initial_queries = parsed.get("initial_queries")
        if not isinstance(initial_queries, list) or not initial_queries:
            initial_queries = [
                {
                    "text": user_request,
                    "importance": "core",
                    "objective_keys": [objectives[0]["objective_key"]],
                    "acceptance_criteria": ["Directly answer the user's research request with reliable evidence"],
                }
            ]
        initial_queries = self._select_initial_queries(initial_queries, objectives)
        covered_objective_keys = {
            key
            for item in initial_queries
            for key in _query_spec(item)[3]
        }
        for objective in objectives:
            if (
                objective.get("requirement") == "must"
                and objective.get("objective_key") not in covered_objective_keys
            ):
                initial_queries.append({
                    "text": objective.get("description") or user_request,
                    "importance": "core",
                    "objective_keys": [objective["objective_key"]],
                    "acceptance_criteria": objective.get("acceptance_criteria") or [],
                })
        objective_by_key = {o["objective_key"]: o for o in objectives}
        for item in initial_queries:
            text, importance, criteria, objective_keys = _query_spec(item)
            if not isinstance(text, str) or not text.strip():
                continue
            importance = importance or "supporting"
            query_id = graph_tools.create_query_child(
                parent_id=goal_id,
                text=text,
                importance=importance,
                acceptance_criteria=criteria,
                objective_keys=[key for key in objective_keys if key in objective_by_key],
                required_for_parent=False,
            )
            for key in objective_keys:
                objective = objective_by_key.get(key)
                if objective:
                    graph_tools.add_edge(query_id, objective["id"], EdgeType.COVERS_OBJECTIVE)
            query = graph_tools.get_node(query_id)
            queries.append({
                "handle": query.get("handle"),
                "id": query_id,
                "text": text,
                "priority_tier": query.get("priority_tier"),
                "acceptance_criteria": criteria,
                "objective_keys": objective_keys,
            })
        if not queries:
            query_id = graph_tools.create_query_child(
                parent_id=goal_id,
                text=user_request,
                importance="core",
                acceptance_criteria=["Directly answer the user's research request with reliable evidence"],
                objective_keys=[objectives[0]["objective_key"]],
                required_for_parent=False,
            )
            graph_tools.add_edge(query_id, objectives[0]["id"], EdgeType.COVERS_OBJECTIVE)
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
            "scope_mode": graph_tools.get_node(goal_id).get("scope_mode", "bounded"),
            "objectives": objectives,
            "queries": queries,
        }

    def _create_objectives(self, goal_id: str, raw_objectives: Any, user_request: str) -> list[dict]:
        """Persist a compact report-level research contract."""
        specs = raw_objectives if isinstance(raw_objectives, list) else []
        objectives: list[dict] = []
        seen: set[str] = set()
        for index, raw in enumerate(specs):
            if not isinstance(raw, dict):
                continue
            description = str(raw.get("description") or "").strip()
            if not description:
                continue
            key = str(raw.get("objective_key") or f"objective-{index + 1}").strip()
            key = "-".join(key.lower().split())
            if not key or key in seen:
                continue
            seen.add(key)
            requirement = raw.get("requirement") if raw.get("requirement") in {"must", "should"} else "must"
            try:
                weight = max(0.0, min(1.0, float(raw.get("weight", 1.0))))
            except (TypeError, ValueError):
                weight = 1.0
            objective_id = graph_tools.create_analysis(
                text=description,
                query_id=goal_id,
                analysis_type="objective",
                objective_key=key,
                description=description,
                requirement=requirement,
                weight=weight,
                acceptance_criteria=raw.get("acceptance_criteria") if isinstance(raw.get("acceptance_criteria"), list) else [],
                coverage=0.0,
                confidence=0.0,
                status="open",
                low_gain_streak=0,
                last_evaluated_successful_rounds=0,
            )
            objectives.append(graph_tools.get_node(objective_id))
        if objectives:
            return objectives
        objective_id = graph_tools.create_analysis(
            text=user_request,
            query_id=goal_id,
            analysis_type="objective",
            objective_key="answer-request",
            description=user_request,
            requirement="must",
            weight=1.0,
            acceptance_criteria=["Answer the user's request with reliable evidence"],
            coverage=0.0,
            confidence=0.0,
            status="open",
            low_gain_streak=0,
            last_evaluated_successful_rounds=0,
        )
        return [graph_tools.get_node(objective_id)]

    @staticmethod
    def _select_initial_queries(candidates: Any, objectives: list[dict]) -> list:
        """Greedily choose the smallest candidate set covering must objectives."""
        items = [item for item in candidates or [] if isinstance(item, (dict, str))]
        if not items:
            return []
        must = {
            objective["objective_key"]
            for objective in objectives
            if objective.get("requirement") == "must"
        } or {objective["objective_key"] for objective in objectives}
        uncovered = set(must)
        selected: list = []
        remaining = list(items)
        while uncovered and remaining:
            best = max(
                remaining,
                key=lambda item: len(set(_query_spec(item)[3]) & uncovered),
            )
            covered = set(_query_spec(best)[3]) & uncovered
            if not covered:
                break
            selected.append(best)
            uncovered -= covered
            remaining.remove(best)
        for objective in objectives:
            key = objective.get("objective_key")
            if key not in uncovered:
                continue
            selected.append({
                "text": objective.get("description") or objective.get("text"),
                "importance": "core" if objective.get("requirement") == "must" else "supporting",
                "objective_keys": [key],
                "acceptance_criteria": objective.get("acceptance_criteria") or [],
            })
        return selected or items[:1]

    def get_research_objectives(self, goal_id: Optional[str] = None) -> list[dict]:
        """Return report-level objectives ordered by requirement and weight."""
        objectives = graph_tools.search_nodes("analysis", {"analysis_type": "objective"})
        return sorted(
            objectives,
            key=lambda item: (
                item.get("requirement") != "must",
                -float(item.get("weight") or 0.0),
                item.get("objective_key") or "",
            ),
        )

    @staticmethod
    def _bump_portfolio_revision() -> int:
        """Mark the global portfolio evaluation stale after graph changes."""
        from tools import research_state

        goal = research_state.get_goal()
        revision = int(goal.get("portfolio_revision") or 0) + 1
        graph_tools.upsert_node(NodeType.USER_REQUEST, {"portfolio_revision": revision}, goal["id"])
        return revision

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

        tree = graph_tools.validate_query_tree()
        if not tree.get("valid"):
            research_state.update_goal({
                "research_state": research_state.FAILED,
                "last_error": "Query tree validation failed before scheduling actions",
            })
            return []

        queries = graph_tools.search_nodes("query", {})
        goal = research_state.get_goal()
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
                gap_ids = [
                    gap["id"]
                    for gap in graph_tools.search_nodes("analysis", {"analysis_type": "gap"})
                    if gap.get("status") == "selected"
                    and gap.get("expansion_parent_id") == node["id"]
                ]
                if gap_ids:
                    action, reason = "expand_gaps", "globally selected gaps await child queries"
            elif query_status == "waiting_children":
                children = [
                    graph_tools.get_node(cid) for cid in graph_tools.get_query_children(node["id"])
                ]
                if children and all(c.get("status") in terminal for c in children):
                    action, reason = "assess_query", "all selected child queries completed"
            elif query_status == "pending":
                action, reason = "dispatch_searcher", "query awaits its first successful search"
            if action:
                actions.append({
                    "action": action,
                    "query_id": node["id"],
                    "query_handle": node.get("handle"),
                    "priority": node.get("priority", 0.0),
                    "required_for_parent": node.get("required_for_parent", False),
                    "required_path": research_state.is_required_path(node["id"]),
                    "semantic_importance": node.get("sem", 0.0),
                    "gap_ids": gap_ids,
                    "reason": reason,
                })

        if not any(action["action"] == "assess_query" for action in actions):
            if int(goal.get("evaluated_portfolio_revision") or 0) < int(goal.get("portfolio_revision") or 0):
                actions.append({
                    "action": "evaluate_research_portfolio",
                    "query_id": None,
                    "goal_id": goal.get("id"),
                    "priority": 1.0,
                    "required_for_parent": False,
                    "required_path": False,
                    "semantic_importance": 1.0,
                    "gap_ids": [],
                    "reason": "research portfolio changed since the last global evaluation",
                })
            elif not actions:
                recovery = self._recover_unactionable_research(goal, queries)
                if recovery:
                    actions.append(recovery)
                elif research_state.get_status().get("research_state") != research_state.RESEARCHING:
                    return []
            if not actions:
                actions.append({
                    "action": "assess_convergence",
                    "query_id": None,
                    "goal_id": goal.get("id"),
                    "priority": 0.0,
                    "required_for_parent": False,
                    "required_path": False,
                    "semantic_importance": 0.0,
                    "gap_ids": [],
                    "reason": "no higher-priority workflow action remains",
                })

        action_rank = {
            "assess_query": 0,
            "evaluate_research_portfolio": 1,
            "expand_gaps": 2,
            "dispatch_searcher": 3,
            "assess_convergence": 4,
        }
        actions.sort(key=lambda a: (
            action_rank[a["action"]],
            -int(bool(a["required_path"])),
            -float(a["semantic_importance"] or 0.0),
            -float(a["priority"] or 0.0),
            a.get("query_id") or a.get("goal_id") or "",
        ))
        if any(action["action"] == "assess_query" for action in actions):
            actions = [action for action in actions if action["action"] == "assess_query"]
        elif any(action["action"] == "evaluate_research_portfolio" for action in actions):
            actions = [action for action in actions if action["action"] == "evaluate_research_portfolio"]
        remaining = research_state.remaining_budget()
        if remaining == 0 and any(a["action"] == "dispatch_searcher" for a in actions):
            research_state.mark_budget_exhausted()
            return []
        return actions[:limit]

    def _recover_unactionable_research(self, goal: dict, queries: list[dict]) -> Optional[dict]:
        """Create one bounded recovery Query or close an exhausted Objective."""
        from tools import research_state

        if int(goal.get("evaluated_portfolio_revision") or 0) < int(goal.get("portfolio_revision") or 0):
            return None
        open_must = [
            objective
            for objective in self.get_research_objectives(goal.get("id"))
            if objective.get("requirement") == "must"
            and objective.get("status") not in {"satisfied", "blocked_best_effort"}
        ]
        if not open_must:
            return None
        if research_state.remaining_budget(goal.get("id")) == 0:
            research_state.mark_budget_exhausted(goal.get("id"))
            return None

        for objective in open_must:
            key = objective.get("objective_key")
            prior = [query for query in queries if query.get("recovery_objective_key") == key]
            if prior:
                if goal.get("scope_mode") == "bounded":
                    graph_tools.upsert_node(NodeType.ANALYSIS, {
                        "status": "blocked_best_effort",
                        "resolution_reason": "targeted recovery query did not satisfy the objective",
                    }, objective["id"])
                    continue
                research_state.update_goal({
                    "research_state": research_state.FAILED,
                    "last_error": f"Exhaustive objective remained open after targeted recovery: {key}",
                }, goal.get("id"))
                return None

            query_id = graph_tools.create_query_child(
                parent_id=goal["id"],
                text=objective.get("description") or objective.get("text"),
                importance="core",
                acceptance_criteria=objective.get("acceptance_criteria") or [],
                objective_keys=[key],
                required_for_parent=False,
                recovery_objective_key=key,
            )
            graph_tools.add_edge(query_id, objective["id"], EdgeType.COVERS_OBJECTIVE)
            query = graph_tools.get_node(query_id)
            return {
                "action": "dispatch_searcher",
                "query_id": query_id,
                "query_handle": query.get("handle"),
                "priority": query.get("priority", 0.0),
                "required_for_parent": False,
                "required_path": False,
                "semantic_importance": query.get("sem", 0.0),
                "gap_ids": [],
                "reason": f"targeted recovery for uncovered objective {key}",
            }
        return None

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

    def _gap_owner_query_id(self, gap_id: str) -> Optional[str]:
        """Return the Query that originally identified a Gap."""
        for edge in graph_tools.get_node_edges(gap_id, direction="in"):
            if str(edge.get("type", "")).lower() != "has_gap":
                continue
            owner = graph_tools.get_node(edge.get("source"))
            if owner.get("type") == NodeType.QUERY.value:
                return owner["id"]
        return None

    def assess_query(self, query_id: str) -> dict:
        """Assess one Query's owned evidence and automatically advance its state."""
        from tools import research_state

        if research_state.get_status().get("research_state") != research_state.RESEARCHING:
            return {"error": "Query assessment is only allowed while research_state is RESEARCHING"}
        try:
            resolved = self._resolve_query_id(query_id)
        except AmbiguousQueryReference as exc:
            return {"error": str(exc)}
        if resolved is None:
            return {"error": f"Unknown query reference: {query_id!r}"}
        query = graph_tools.get_node(resolved)
        if query.get("status") not in {"assessing", "waiting_children"}:
            return {"error": f"Query {query.get('handle') or resolved} is not ready for assessment"}
        if query.get("status") == "waiting_children":
            children = [
                graph_tools.get_node(cid)
                for cid in graph_tools.get_query_children(resolved)
            ]
            if any(c.get("status") not in {"sufficient", "blocked", "failed", "deferred"} for c in children):
                return {"error": f"Query {query.get('handle') or resolved} still has unfinished selected children"}

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
            category = spec.get("gap_category")
            if category not in _GAP_CATEGORIES:
                category = "enrichment"
            objective_keys = spec.get("objective_keys")
            if not isinstance(objective_keys, list):
                objective_keys = query.get("objective_keys") or []
            try:
                decision_impact = max(0.0, min(1.0, float(spec.get("decision_impact", 0.0))))
                confidence_gain = max(0.0, min(1.0, float(spec.get("confidence_gain", 0.0))))
                estimated_rounds = max(1, int(spec.get("estimated_search_rounds", 1)))
            except (TypeError, ValueError):
                decision_impact, confidence_gain, estimated_rounds = 0.0, 0.0, 1
            gap_id = graph_tools.create_analysis(
                text=description,
                query_id=resolved,
                analysis_type="gap",
                description=description,
                gap_key=key,
                importance=importance,
                required_for_parent=False,
                status="candidate",
                gap_category=category,
                objective_keys=objective_keys,
                search_subject_key=str(spec.get("search_subject_key") or key),
                decision_impact=decision_impact,
                confidence_gain=confidence_gain,
                estimated_search_rounds=estimated_rounds,
                acceptance_criteria=(
                    spec.get("acceptance_criteria")
                    if isinstance(spec.get("acceptance_criteria"), list)
                    else []
                ),
            )
            existing[key] = gap_id
            created_gaps.append(gap_id)
            for objective in self.get_research_objectives():
                if objective.get("objective_key") in objective_keys:
                    graph_tools.add_edge(gap_id, objective["id"], EdgeType.IMPACTS_OBJECTIVE)

        recommendation = verdict.get("recommendation")
        if recommendation == "blocked":
            new_status = "blocked"
        elif recommendation == "sufficient" and score >= 0.7 and not created_gaps:
            new_status = "sufficient"
        elif created_gaps or self._query_gap_ids(resolved, {"candidate", "selected"}):
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
                    required_for_parent=False,
                    status="candidate",
                    gap_category="missing_core_evidence",
                    objective_keys=query.get("objective_keys") or [],
                    search_subject_key=key,
                    decision_impact=0.7,
                    confidence_gain=0.5,
                    estimated_search_rounds=1,
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
        revision = self._bump_portfolio_revision()
        graph_tools.upsert_node(
            NodeType.QUERY,
            {"portfolio_revision_at_assessment": revision},
            resolved,
        )
        return {
            "query_id": resolved,
            "query_handle": query.get("handle"),
            "sufficiency_score": score,
            "status": new_status,
            "created_gaps": created_gaps,
            "next_action": "evaluate_research_portfolio" if new_status == "needs_expansion" else "get_next_actions",
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
        gap_status = {
            "sufficient": "resolved",
            "deferred": "deferred_low_value",
        }.get(child_status, "blocked")
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
        children = [
            graph_tools.get_node(cid) for cid in graph_tools.get_query_children(parent_id)
        ]
        if children and all(
            c.get("status") in {"sufficient", "blocked", "failed", "deferred"}
            for c in children
        ):
            graph_tools.transition_query(parent_id, "assessing")

    def evaluate_research_portfolio(self, goal_id: Optional[str] = None) -> dict:
        """Select candidate gaps by report-level marginal utility."""
        from tools import research_state

        goal = research_state.get_goal(goal_id)
        if goal.get("research_state") != research_state.RESEARCHING:
            return {"error": "Portfolio evaluation is only allowed while researching"}
        objectives = self.get_research_objectives(goal_id)
        queries = graph_tools.search_nodes("query", {})
        prompt = (
            mm_prompts.evaluate_portfolio
            .replace("{objectives}", json.dumps(objectives, ensure_ascii=False))
            .replace("{queries}", json.dumps([
                {
                    "handle": q.get("handle"),
                    "text": q.get("text"),
                    "objective_keys": q.get("objective_keys") or [],
                    "status": q.get("status"),
                    "sufficiency_score": q.get("sufficiency_score"),
                    "covered": q.get("covered") or [],
                }
                for q in queries
            ], ensure_ascii=False))
        )
        verdict = self._invoke_json(prompt)
        scored = {
            item.get("objective_key"): item
            for item in verdict.get("objectives", [])
            if isinstance(item, dict) and item.get("objective_key")
        }
        objective_by_key: dict[str, dict] = {}
        objective_deltas: dict[str, tuple[float, float]] = {}
        for objective in objectives:
            key = objective.get("objective_key")
            linked_scores = [
                float(query.get("sufficiency_score") or 0.0)
                for query in queries
                if key in (query.get("objective_keys") or [])
                and query.get("sufficiency_score") is not None
                and self._query_evidence_within_time_window(query["id"], goal.get("time_window"))
            ]
            fallback = max(linked_scores, default=0.0)
            item = scored.get(key, {})
            try:
                coverage = max(0.0, min(1.0, float(item.get("coverage", fallback))))
                confidence = max(0.0, min(1.0, float(item.get("confidence", fallback * 0.9))))
            except (TypeError, ValueError):
                coverage, confidence = fallback, fallback * 0.9
            old_coverage = float(objective.get("coverage") or 0.0)
            old_confidence = float(objective.get("confidence") or 0.0)
            realized_gain = max(0.0, coverage - old_coverage) + max(0.0, confidence - old_confidence)
            meets = coverage >= OBJECTIVE_COVERAGE_THRESHOLD and confidence >= OBJECTIVE_CONFIDENCE_THRESHOLD
            successful_rounds = int(goal.get("successful_search_rounds") or 0)
            last_evaluated_rounds = int(objective.get("last_evaluated_successful_rounds") or 0)
            streak = int(objective.get("low_gain_streak") or 0)
            new_successful_rounds = max(0, successful_rounds - last_evaluated_rounds)
            if new_successful_rounds and not meets:
                streak = streak + new_successful_rounds if realized_gain < LOW_REALIZED_GAIN_THRESHOLD else 0
            status = "satisfied" if meets else (
                "blocked_best_effort"
                if objective.get("status") == "blocked_best_effort"
                else "open"
            )
            if (
                status != "satisfied"
                and streak >= LOW_GAIN_WINDOW
                and goal.get("scope_mode", "bounded") != "exhaustive"
            ):
                status = "blocked_best_effort"
            graph_tools.upsert_node(NodeType.ANALYSIS, {
                "coverage": coverage,
                "confidence": confidence,
                "status": status,
                "low_gain_streak": streak,
                "last_realized_gain": realized_gain,
                "last_evaluated_successful_rounds": successful_rounds,
                "assessment_reason": item.get("reason") or "",
            }, objective["id"])
            objective_deltas[key] = (coverage - old_coverage, confidence - old_confidence)
            objective_by_key[key] = graph_tools.get_node(objective["id"])

        old_evaluated_revision = int(goal.get("evaluated_portfolio_revision") or 0)
        changed_queries = [
            query for query in queries
            if int(query.get("portfolio_revision_at_assessment") or 0) > old_evaluated_revision
        ]
        if changed_queries:
            for query in changed_queries:
                linked_deltas = [
                    objective_deltas[key]
                    for key in query.get("objective_keys") or []
                    if key in objective_deltas
                ]
                coverage_delta = sum(delta[0] for delta in linked_deltas)
                confidence_delta = sum(delta[1] for delta in linked_deltas)
                gain_attributes = {
                    "realized_marginal_gain": max(0.0, coverage_delta + confidence_delta),
                    "objective_coverage_delta": coverage_delta,
                    "objective_confidence_delta": confidence_delta,
                }
                graph_tools.upsert_node(NodeType.QUERY, gain_attributes, query["id"])
                for edge in graph_tools.get_node_edges(query["id"], direction="out"):
                    if str(edge.get("type", "")).lower() == "searched_by":
                        graph_tools.upsert_node(NodeType.SEARCH_RUN, gain_attributes, edge["target"])

        candidates = [
            gap for gap in graph_tools.search_nodes("analysis", {"analysis_type": "gap"})
            if gap.get("status") in {"candidate", "selected"}
        ]
        selected: list[dict] = []
        deferred: list[dict] = []
        existing_subjects = {
            str(query.get("search_subject_key"))
            for query in queries
            if query.get("search_subject_key") and query.get("successful_search_runs")
        }
        grouped_candidates: dict[str, list[dict]] = {}
        for gap in candidates:
            subject = str(gap.get("search_subject_key") or gap.get("gap_key") or gap["id"])
            grouped_candidates.setdefault(subject, []).append(gap)
        for subject, group in grouped_candidates.items():
            keys = {
                key
                for gap in group
                for key in (gap.get("objective_keys") or [])
            }
            impacted = [objective_by_key[key] for key in keys if key in objective_by_key]
            must_impacted = [item for item in impacted if item.get("requirement") == "must"]
            deficits = [
                max(
                    0.0,
                    OBJECTIVE_COVERAGE_THRESHOLD - float(item.get("coverage") or 0.0),
                    OBJECTIVE_CONFIDENCE_THRESHOLD - float(item.get("confidence") or 0.0),
                )
                for item in must_impacted
                if item.get("status") not in {"satisfied", "blocked_best_effort"}
            ]
            deficit = max(deficits, default=0.0)
            redundancy = 0.75 if subject in existing_subjects else 0.0
            decision_impact = max(float(gap.get("decision_impact") or 0.0) for gap in group)
            confidence_gain = max(float(gap.get("confidence_gain") or 0.0) for gap in group)
            rounds = max(1, max(int(gap.get("estimated_search_rounds") or 1) for gap in group))
            benefit = 0.5 * deficit + 0.3 * decision_impact + 0.2 * confidence_gain
            utility = benefit * (1.0 - redundancy) / rounds
            fatal = any(gap.get("gap_category") == "fatal_conflict" for gap in group)
            choose = fatal or (
                bool(deficits)
                and utility >= EXPANSION_UTILITY_THRESHOLD
            )
            new_status = "selected" if choose else "deferred_low_value"
            owners = [
                graph_tools.get_node(owner_id)
                for owner_id in {self._gap_owner_query_id(gap["id"]) for gap in group}
                if owner_id
            ]
            expansion_parent_id = (
                max(owners, key=lambda item: float(item.get("priority") or 0.0))["id"]
                if choose and owners else None
            )
            for gap in group:
                graph_tools.upsert_node(NodeType.ANALYSIS, {
                    "status": new_status,
                    "marginal_utility": utility,
                    "objective_deficit": deficit,
                    "expansion_parent_id": expansion_parent_id,
                    "resolution_reason": None if choose else "global marginal utility below expansion threshold",
                }, gap["id"])
                (selected if choose else deferred).append(graph_tools.get_node(gap["id"]))

        for query in queries:
            if query.get("status") == "needs_expansion":
                selected_for_query = [
                    gap for gap in selected
                    if gap.get("expansion_parent_id") == query["id"]
                ]
                if not selected_for_query:
                    graph_tools.transition_query(
                        query["id"],
                        "sufficient",
                        assessment_reason="remaining gaps deferred by global portfolio evaluation",
                    )
                    self._propagate_child_completion(query["id"], "sufficient")
            elif query.get("status") == "pending" and query.get("objective_keys"):
                linked = [
                    objective_by_key[key]
                    for key in query.get("objective_keys") or []
                    if key in objective_by_key
                ]
                if linked and all(item.get("status") in {"satisfied", "blocked_best_effort"} for item in linked):
                    graph_tools.transition_query(query["id"], "deferred")
                    self._propagate_child_completion(query["id"], "deferred")

        objectives = self.get_research_objectives(goal_id)
        must = [item for item in objectives if item.get("requirement") == "must"]
        readiness = (
            sum(float(item.get("weight") or 1.0) for item in must if item.get("status") == "satisfied")
            / sum(float(item.get("weight") or 1.0) for item in must)
            if must else 1.0
        )
        revision = int(goal.get("portfolio_revision") or 0)
        max_utility = max(
            (float(item.get("marginal_utility") or 0.0) for item in selected + deferred),
            default=0.0,
        )
        graph_tools.upsert_node(NodeType.USER_REQUEST, {
            "evaluated_portfolio_revision": revision,
            "last_max_marginal_utility": max_utility,
            "report_readiness_score": readiness,
        }, goal["id"])
        return {
            "selected_gap_ids": [item["id"] for item in selected],
            "deferred_gap_ids": [item["id"] for item in deferred],
            "objectives": objectives,
            "report_readiness_score": readiness,
            "last_max_marginal_utility": max_utility,
            "next_action": "get_next_actions",
        }

    @staticmethod
    def _query_evidence_within_time_window(query_id: str, time_window: Optional[str]) -> bool:
        """Return whether dated query sources include evidence inside the requested window."""
        if not time_window:
            return True
        years = [int(year) for year in re.findall(r"\b(?:19|20)\d{2}\b", time_window)]
        if not years:
            return True
        lower, upper = min(years), max(years)
        evaluation = graph_tools.get_query_evaluation_subgraph(query_id)
        dated: list[int] = []
        for node in evaluation.get("nodes", []):
            if node.get("type") != NodeType.SOURCE.value:
                continue
            value = str(node.get("published_at") or node.get("publication_date") or "")
            match = re.search(r"\b(?:19|20)\d{2}\b", value)
            if match:
                dated.append(int(match.group()))
        # Query scores are not evidence-item granular. Conservatively reject a
        # mixed dated set so out-of-window evidence cannot inflate coverage.
        return not dated or all(lower <= year <= upper for year in dated)

    def expand_gaps(self, parent_id: str, gap_ids: Optional[list[str]] = None) -> dict:
        """Create one child Query per selected search subject."""
        from tools import research_state

        if research_state.get_status().get("research_state") != research_state.RESEARCHING:
            return {"error": "Gap expansion is only allowed while research_state is RESEARCHING"}
        try:
            resolved = self._resolve_query_id(parent_id)
        except AmbiguousQueryReference as exc:
            return {"error": str(exc)}
        if resolved is None:
            return {"error": f"Unknown query reference: {parent_id!r}"}
        parent = graph_tools.get_node(resolved)
        if parent.get("status") != "needs_expansion":
            return {"error": f"Query {parent.get('handle') or resolved} is not awaiting expansion"}
        assigned_selected_gap_ids = {
            gap["id"]
            for gap in graph_tools.search_nodes("analysis", {"analysis_type": "gap"})
            if gap.get("status") == "selected"
            and gap.get("expansion_parent_id") == resolved
        }
        candidates = gap_ids or list(assigned_selected_gap_ids)
        gaps = [
            graph_tools.get_node(gid) for gid in candidates
            if gid in assigned_selected_gap_ids
            and graph_tools.get_node(gid).get("analysis_type") == "gap"
            and graph_tools.get_node(gid).get("status") == "selected"
        ]
        grouped: dict[str, list[dict]] = {}
        for gap in gaps:
            subject = str(gap.get("search_subject_key") or gap.get("gap_key") or gap["id"])
            grouped.setdefault(subject, []).append(gap)
        remaining = research_state.remaining_budget()
        deferred = []
        if remaining is not None:
            group_items = list(grouped.items())
            deferred_groups = group_items[remaining:]
            grouped = dict(group_items[:remaining])
            deferred = [gap for _, group in deferred_groups for gap in group]
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
        objective_by_key = {item["objective_key"]: item for item in self.get_research_objectives()}
        for subject, group in grouped.items():
            if any(gap.get("gap_key") and self._gap_key_in_ancestors(resolved, gap.get("gap_key")) for gap in group):
                for gap in group:
                    graph_tools.upsert_node(NodeType.ANALYSIS, {
                        "status": "blocked",
                        "resolution_reason": "duplicate gap_key already exists on the ancestor path",
                    }, gap["id"])
                continue
            followups = self._plan_followup_queries(
                research_goal=goal.get("research_goal") or goal.get("request") or "",
                parent_text=parent.get("text") or "",
                sibling_texts=sibling_texts,
                gaps=[
                    {
                        "id": gap["id"],
                        "description": gap.get("description") or gap.get("text"),
                        "acceptance_criteria": gap.get("acceptance_criteria") or [],
                    }
                    for gap in group
                ],
                reason=f"Globally selected search subject: {subject}",
                max_new=1,
            )
            if not followups:
                for gap in group:
                    graph_tools.upsert_node(NodeType.ANALYSIS, {
                        "status": "blocked",
                        "resolution_reason": "query planner could not author a self-contained child query",
                    }, gap["id"])
                continue
            spec = followups[0]
            importance = "core" if any(gap.get("importance") == "core" for gap in group) else (
                "supporting" if any(gap.get("importance") == "supporting" for gap in group) else "peripheral"
            )
            objective_keys = sorted({
                key for gap in group for key in (gap.get("objective_keys") or [])
                if key in objective_by_key
            })
            child_id = graph_tools.create_query_child(
                parent_id=resolved,
                text=spec["text"],
                importance=importance,
                acceptance_criteria=spec.get("acceptance_criteria") or [
                    criterion for gap in group for criterion in (gap.get("acceptance_criteria") or [])
                ],
                gap_ids=[gap["id"] for gap in group],
                objective_keys=objective_keys,
                required_for_parent=False,
                search_subject_key=subject,
            )
            for key in objective_keys:
                graph_tools.add_edge(child_id, objective_by_key[key]["id"], EdgeType.COVERS_OBJECTIVE)
            child = graph_tools.get_node(child_id)
            created.append({
                "id": child_id,
                "handle": child.get("handle"),
                "text": child.get("text"),
                "gap_ids": [gap["id"] for gap in group],
            })
            sibling_texts.append(child.get("text"))

        next_status = "waiting_children" if created else "blocked"
        graph_tools.transition_query(resolved, next_status)
        if next_status == "blocked":
            self._propagate_child_completion(resolved, "blocked")
        self._bump_portfolio_revision()
        return {
            "parent_id": resolved,
            "parent_handle": parent.get("handle"),
            "created": created,
            "deferred_gap_ids": [g["id"] for g in deferred],
            "next_action": "get_next_actions",
        }

    def assess_convergence(self, goal_id: Optional[str] = None) -> dict:
        """Authorize reporting after Objective-level marginal-utility convergence."""
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
                "selected_gaps": [],
                "active_queries": [],
                "recommendation": "failed",
                "reason": reason,
                "research_state": research_state.FAILED,
                "tree_validation": tree,
                "next_actions": [],
            }
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
            .replace("{open_queries}", json.dumps([
                query for query in all_queries
                if query.get("status") not in research_state.TERMINAL_QUERY_STATUSES
            ], ensure_ascii=False))
            .replace("{conflicts}", json.dumps(conflicts, ensure_ascii=False))
        )
        verdict = self._invoke_json(prompt)
        fatal = verdict.get("fatal_unresolved_conflicts") or []
        goal = research_state.get_goal(goal_id)
        created_fatal_gaps: list[str] = []
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
            gap_parent_id = owner_id
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
                    required_for_parent=False,
                    status="candidate",
                    gap_category="fatal_conflict",
                    objective_keys=[
                        objective.get("objective_key")
                        for objective in self.get_research_objectives(goal_id)
                        if objective.get("requirement") == "must"
                    ],
                    search_subject_key=f"fatal-conflict-{conflict['id']}",
                    decision_impact=1.0,
                    confidence_gain=1.0,
                    estimated_search_rounds=1,
                    conflict_id=conflict["id"],
                    acceptance_criteria=["Find independent evidence that resolves or clearly scopes the conflict"],
                )
                created_fatal_gaps.append(gap_id)
                if owner.get("status") == "assessing":
                    graph_tools.transition_query(owner_id, "needs_expansion")
                elif owner.get("status") in research_state.TERMINAL_QUERY_STATUSES:
                    graph_tools.upsert_node(NodeType.ANALYSIS, {"status": "selected"}, gap_id)
                    child_id = graph_tools.create_query_child(
                        parent_id=owner_id,
                        text=f"Resolve conflict: {fatal_description}",
                        importance="core",
                        acceptance_criteria=["Find independent evidence that resolves or clearly scopes the conflict"],
                        gap_ids=[gap_id],
                        objective_keys=[
                            objective.get("objective_key")
                            for objective in self.get_research_objectives(goal_id)
                            if objective.get("requirement") == "must"
                        ],
                        required_for_parent=False,
                        search_subject_key=f"fatal-conflict-{conflict['id']}",
                    )
                    for objective in self.get_research_objectives(goal_id):
                        if objective.get("requirement") == "must":
                            graph_tools.add_edge(child_id, objective["id"], EdgeType.COVERS_OBJECTIVE)
        fatal_set = set(fatal)
        for conflict in graph_tools.search_nodes("conflict", {}):
            if (
                conflict.get("resolution_status") in {"unresolved", "investigating"}
                and conflict.get("description") not in fatal_set
            ):
                graph_tools.upsert_node(
                    NodeType.CONFLICT,
                    {"resolution_status": "disclosed"},
                    conflict["id"],
                )
        if created_fatal_gaps:
            self._bump_portfolio_revision()

        goal = research_state.get_goal(goal_id)
        objectives = self.get_research_objectives(goal_id)
        must = [item for item in objectives if item.get("requirement") == "must"]
        objectives_ready = bool(must) and all(
            item.get("status") in {"satisfied", "blocked_best_effort"}
            for item in must
        )
        active = [
            query for query in all_queries
            if query.get("status") in {"searching", "assessing"}
        ]
        selected_gaps = [
            gap for gap in graph_tools.search_nodes("analysis", {"analysis_type": "gap"})
            if gap.get("status") in {"selected", "assigned"}
        ]
        portfolio_current = int(goal.get("evaluated_portfolio_revision") or 0) >= int(goal.get("portfolio_revision") or 0)
        exhaustive_open = [
            query for query in all_queries
            if query.get("status") not in research_state.TERMINAL_QUERY_STATUSES
        ] if goal.get("scope_mode") == "exhaustive" else []
        remaining = research_state.remaining_budget(goal_id)
        if remaining == 0 and (active or selected_gaps or not objectives_ready or exhaustive_open):
            research_state.mark_budget_exhausted(goal_id)
            recommendation = "stop"
            state = research_state.BUDGET_EXHAUSTED
        elif (
            tree["valid"]
            and portfolio_current
            and objectives_ready
            and not active
            and not selected_gaps
            and not created_fatal_gaps
            and not exhaustive_open
        ):
            for query in all_queries:
                if query.get("status") == "pending":
                    graph_tools.transition_query(query["id"], "deferred")
                    self._propagate_child_completion(query["id"], "deferred")
            research_state.update_goal({
                "research_state": research_state.REPORT_READY,
                "last_convergence_recommendation": "stop",
                "report_authorized_reason": "report-level objectives reached marginal-utility convergence",
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
            "selected_gaps": [
                {"id": gap["id"], "description": gap.get("description") or gap.get("text")}
                for gap in selected_gaps
            ],
            "active_queries": [
                {"id": query["id"], "handle": query.get("handle"), "status": query.get("status")}
                for query in active + exhaustive_open
            ],
            "objectives": objectives,
            "portfolio_current": portfolio_current,
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
            try:
                resolved = self._resolve_query_id(query_id)
            except AmbiguousQueryReference as exc:
                return {"error": str(exc)}
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
            try:
                resolved = self._resolve_query_id(query_id)
            except AmbiguousQueryReference as exc:
                return {"search_run_id": search_run_id, "query_id": None, "error": str(exc)}
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

        Workflow actions pass exact node IDs. Human callers may still use short
        handles, truncated IDs, corrupted timestamp prefixes, or query text.
        Non-exact references are accepted only when they resolve uniquely.

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

        def unique(matches: list[dict]) -> Optional[str]:
            ids = [match.get("id") for match in matches if match.get("id")]
            if len(ids) > 1:
                raise AmbiguousQueryReference(query_id, ids)
            return ids[0] if ids else None

        # Short handles remain accepted for humans, but ambiguity is never guessed.
        resolved = unique([q for q in queries if q.get("handle") == query_id])
        if resolved:
            return resolved
        # Truncated ID (the ``_<uuid8>`` suffix dropped).
        resolved = unique([
            q for q in queries
            if q.get("id", "").startswith(query_id) or query_id.startswith(q.get("id", ""))
        ])
        if resolved:
            return resolved
        # Corrupted timestamp prefix but intact ``_<uuid8>`` suffix — the uuid8
        # is the unique discriminator, so match on it.
        ref_suffix = query_id.rsplit("_", 1)[-1]
        if ref_suffix and ref_suffix != query_id:
            resolved = unique([
                q for q in queries
                if q.get("id", "").rsplit("_", 1)[-1] == ref_suffix
            ])
            if resolved:
                return resolved
        return unique([
            q for q in queries
            if (q.get("text") or "")
            and ((q.get("text") or "") == query_id or query_id in (q.get("text") or "") or (q.get("text") or "") in query_id)
        ])

    def get_query_context(self, query_id: str) -> dict:
        """Return existing context for a query to avoid duplicate searching.

        Args:
            query_id: The query node ID.

        Returns:
            dict with the ``query`` node and its ``existing_subgraph``.
        """
        try:
            resolved = self._resolve_query_id(query_id)
        except AmbiguousQueryReference as exc:
            return {"error": str(exc)}
        resolved = resolved or query_id
        return {
            "query": graph_tools.get_node(resolved),
            "existing_subgraph": graph_tools.get_query_evaluation_subgraph(resolved),
        }

    def create_insight(self, text: str, query_id: Optional[str] = None) -> dict:
        """Create a typed insight and safely bind an optional Query handle."""
        try:
            resolved = self._resolve_query_id(query_id) if query_id else None
        except AmbiguousQueryReference as exc:
            return {"error": str(exc)}
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
        try:
            resolved_query_id = self._resolve_query_id(query_id)
        except AmbiguousQueryReference as exc:
            return {
                "search_run_id": None,
                "query_id": query_id,
                "ref_map": {},
                "written": {"sources": 0, "documents": 0, "claims": 0, "evidence": 0, "conflicts": 0},
                "error": str(exc),
            }
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
            source_attributes = {}
            published_at = _first(source, "published_at", "publication_date", "date")
            if published_at:
                source_attributes["published_at"] = published_at
            source_tier = _first(source, "source_tier", "quality_tier")
            if source_tier:
                source_attributes["source_tier"] = source_tier
            source_id = self.deduplicate_source(source) or graph_tools.create_source(
                url=url,
                title=_first(source, "title"),
                source_type=_first(source, "source_type", "type"),
                **source_attributes,
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
            claim_attributes = {
                key: claim_item.get(key)
                for key in ("confidence", "qualifiers", "limitations", "time_scope")
                if claim_item.get(key) not in (None, [], "")
            }
            claim_id = graph_tools.create_claim(
                statement=claim_text,
                document_id=resolve(doc_ref),
                source_id=resolve(_first(claim_item, "source_ref", "source")),
                **claim_attributes,
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
            
            evidence_attributes = {
                key: evidence_item.get(key)
                for key in ("confidence", "qualifiers", "limitations", "time_scope")
                if evidence_item.get(key) not in (None, [], "")
            }
            evidence_id = graph_tools.create_evidence(
                claim=evidence_text,
                document_id=resolve(doc_ref),
                source_id=resolve(_first(evidence_item, "source_ref", "source")),
                supports_claim_id=supports_claim_id,
                **evidence_attributes,
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
            self._bump_portfolio_revision()
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
        """Export compact report metadata; evidence is fetched page by page."""
        goal = graph_tools.get_node(goal_id) if goal_id else {}
        if not goal:
            requests = graph_tools.search_nodes("user_request", {})
            if requests:
                goal = requests[0]
                goal_id = goal["id"]
        objectives = self.get_research_objectives(goal_id)
        conflicts = graph_tools.search_nodes("conflict", {})
        from tools import report_tools

        limitations = [
            str(item.get("description") or item.get("text") or "").strip()
            for item in objectives
            if item.get("status") == "blocked_best_effort"
        ]
        limitations = [item for item in limitations if item]
        return {
            "goal": {
                key: goal.get(key)
                for key in (
                    "id", "request", "research_goal", "language", "time_window",
                    "region_scope", "source_preferences",
                )
            } if goal else {},
            "queries": [
                {
                    key: query.get(key)
                    for key in ("id", "handle", "text", "importance")
                }
                for query in graph_tools.search_nodes("query", {})
            ],
            "objectives": [
                {
                    key: objective.get(key)
                    for key in (
                        "id", "objective_key", "description", "text",
                        "requirement", "acceptance_criteria", "status",
                        "coverage", "confidence", "assessment_reason",
                    )
                }
                for objective in objectives
            ],
            "limitations": limitations,
            "disclosed_conflicts": [
                {
                    "description": item.get("description"),
                    "conflict_type": item.get("conflict_type"),
                }
                for item in conflicts if item.get("resolution_status") == "disclosed"
            ],
            "reference_registry": report_tools.build_reference_registry(),
        }

    def get_report_evidence(self, query_id: str, offset: int = 0, limit: int = 20) -> dict:
        """Return a compact page for a Query or an Objective reference."""
        from tools import report_tools

        node = graph_tools.get_node(query_id)
        if (
            node.get("type") == NodeType.ANALYSIS.value
            and node.get("analysis_type") == "objective"
        ):
            item_ids = report_tools.resolve_report_item_ids([query_id])
            items = report_tools.get_report_items(item_ids)
            offset = max(0, int(offset or 0))
            limit = min(100, max(1, int(limit or 20)))
            page = items[offset : offset + limit]
            next_offset = offset + len(page)
            return {
                "objective": {
                    key: node.get(key)
                    for key in (
                        "id", "objective_key", "description", "requirement",
                        "status", "coverage", "confidence",
                    )
                },
                "items": page,
                "offset": offset,
                "limit": limit,
                "total": len(items),
                "next_offset": next_offset if next_offset < len(items) else None,
            }
        try:
            resolved = self._resolve_query_id(query_id)
        except AmbiguousQueryReference as exc:
            return {"error": str(exc)}
        if resolved is None:
            return {"error": f"Unknown query reference: {query_id!r}"}
        return report_tools.get_report_evidence(resolved, offset=offset, limit=limit)

    def bind_report_section(
        self,
        section: dict,
        claim_ids: Optional[list[str]] = None,
        evidence_ids: Optional[list[str]] = None,
        source_ids: Optional[list[str]] = None,
    ) -> str:
        """Best-effort persist a report section and its evidence bindings.

        Args:
            section: dict with ``title``, ``content`` and optional ``section_type``.
            claim_ids: Claim/evidence node IDs the section cites.
            evidence_ids: Evidence node IDs the section cites.

        Returns:
            The created report-section node ID.
        """
        valid_evidence_ids = []
        for eid in evidence_ids or []:
            try:
                node_type = graph_tools.get_node(eid).get("type")
            except Exception:  # noqa: BLE001 - binding repair must not block reporting
                node_type = None
            if node_type == NodeType.EVIDENCE.value:
                valid_evidence_ids.append(eid)
            else:
                logger.warning("Skipping invalid ReportSection Evidence binding: %r", eid)

        valid_claim_ids = []
        for cid in claim_ids or []:
            try:
                node_type = graph_tools.get_node(cid).get("type")
            except Exception:  # noqa: BLE001 - binding repair must not block reporting
                node_type = None
            if node_type == NodeType.CLAIM.value:
                valid_claim_ids.append(cid)
            else:
                logger.warning("Skipping invalid ReportSection Claim binding: %r", cid)

        valid_source_ids = []
        for sid in source_ids or []:
            try:
                node_type = graph_tools.get_node(sid).get("type")
            except Exception:  # noqa: BLE001 - binding repair must not block reporting
                node_type = None
            if node_type == NodeType.SOURCE.value:
                valid_source_ids.append(sid)
            else:
                logger.warning("Skipping invalid ReportSection Source binding: %r", sid)

        content = str(section.get("content") or "").strip()
        if len(content) >= 80 and not (valid_evidence_ids or valid_claim_ids or valid_source_ids):
            logger.warning("Persisting unbound ReportSection: %s", section.get("title", ""))

        try:
            section_id = graph_tools.create_report_section(
                title=section.get("title", ""),
                content=section.get("content", ""),
                section_type=section.get("section_type"),
            )
        except Exception:  # noqa: BLE001 - section persistence must not block reporting
            logger.warning("Skipping ReportSection persistence", exc_info=True)
            return ""

        try:
            graph_tools.bind_evidence_to_section(
                section_id,
                evidence_ids=valid_evidence_ids,
                claim_ids=valid_claim_ids,
            )
        except Exception:  # noqa: BLE001 - binding repair must not block reporting
            logger.warning("ReportSection evidence/claim binding failed", exc_info=True)
        for source_id in valid_source_ids:
            try:
                graph_tools.add_edge(section_id, source_id, EdgeType.USES)
            except Exception:  # noqa: BLE001 - binding repair must not block reporting
                logger.warning("ReportSection source binding failed: %s", source_id, exc_info=True)

        if evidence_ids or claim_ids or source_ids:
            logger.info(
                "Bound report section %s: %s/%s evidence IDs, %s/%s claim IDs, "
                "%s/%s source IDs accepted",
                section_id,
                len(valid_evidence_ids),
                len(evidence_ids or []),
                len(valid_claim_ids),
                len(claim_ids or []),
                len(valid_source_ids),
                len(source_ids or []),
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
                text, importance, criteria, objective_keys = _query_spec(raw)
                if isinstance(text, str) and text.strip():
                    items.append({
                        "text": text,
                        "importance": importance,
                        "acceptance_criteria": criteria,
                        "objective_keys": objective_keys,
                    })
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
