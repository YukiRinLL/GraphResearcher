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
EXPANSION_UTILITY_THRESHOLD = 0.25
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
        """Create a TaskContract, CoverageSlots and the initial seed frontier."""
        from tools import middleware, research_state

        with self._state_lock:
            existing_goals = graph_tools.search_nodes("user_request", {})
            if existing_goals:
                return {
                    "error": "Research is already initialized in this run context",
                    "existing_goal_id": existing_goals[0]["id"],
                }

            parsed = self._plan_task_contract(user_request)
            task_contract = parsed.get("task_contract") if isinstance(parsed.get("task_contract"), dict) else {}
            deliverable_type = task_contract.get("deliverable_type") or "research_report"
            target_shape = task_contract.get("target_shape") or user_request
            max_rounds = middleware.get_max_search_rounds()
            if max_rounds and max_rounds > 0:
                breadth_budget = max(1, int(round(max_rounds * 0.4)))
                verification_budget = max(1, int(round(max_rounds * 0.25)))
                depth_budget = max(1, max_rounds - breadth_budget - verification_budget)
            else:
                breadth_budget = depth_budget = verification_budget = 0
            goal_id = graph_tools.create_user_request(
                request=user_request,
                research_goal=parsed.get("research_goal"),
                language=parsed.get("language"),
                time_window=parsed.get("time_window"),
                region_scope=parsed.get("region_scope"),
                source_preferences=parsed.get("source_preferences") or [],
                research_state="INITIALIZING",
                max_search_rounds=max_rounds,
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
                deliverable_type=deliverable_type,
                breadth_budget=breadth_budget,
                depth_budget=depth_budget,
                verification_budget=verification_budget,
                breadth_budget_used=0,
                depth_budget_used=0,
                verification_budget_used=0,
                horizontal_closure_score=0.0,
                slot_completion_score=0.0,
                delivery_readiness=False,
            )

        contract_id = graph_tools.create_task_contract(
            goal_id=goal_id,
            deliverable_type=deliverable_type,
            target_shape=target_shape,
            coverage_axes=task_contract.get("coverage_axes") or [],
            required_sections=task_contract.get("required_sections") or [],
            required_tables=task_contract.get("required_tables") or [],
            time_scope=task_contract.get("time_scope") or parsed.get("time_window"),
            source_constraints=task_contract.get("source_constraints") or [],
            completeness_mode=task_contract.get("completeness_mode") or parsed.get("scope_mode") or "bounded",
            freshness_requirement=task_contract.get("freshness_requirement") or "medium",
        )
        slot_specs = parsed.get("coverage_slots") if isinstance(parsed.get("coverage_slots"), list) else []
        slots = self._create_coverage_slots(goal_id, contract_id, task_contract, slot_specs)
        seed_plan = self._plan_seed_queries({
            "goal_id": goal_id,
            "research_goal": parsed.get("research_goal"),
            "language": parsed.get("language"),
            "task_contract": task_contract,
            "coverage_slots": slots,
        })
        queries = []
        seed_queries = seed_plan.get("seed_queries") if isinstance(seed_plan.get("seed_queries"), list) else []
        if not seed_queries:
            seed_queries = [
                {
                    "text": user_request,
                    "importance": "core",
                    "query_role": "seed",
                    "granularity_level": "topic",
                    "scope_signature": "answer-request",
                    "target_slot_keys": [slot["slot_key"] for slot in slots[:3]],
                    "acceptance_criteria": ["Directly answer the user's research request with reliable evidence"],
                }
            ]
        slot_by_key = {slot.get("slot_key"): slot for slot in slots}
        for item in seed_queries:
            text = item.get("text") if isinstance(item, dict) else item
            importance = item.get("importance") if isinstance(item, dict) else "supporting"
            criteria = item.get("acceptance_criteria") if isinstance(item, dict) else []
            if not isinstance(text, str) or not text.strip():
                continue
            importance = importance or "supporting"
            query_id = graph_tools.create_query_child(
                parent_id=goal_id,
                text=text,
                importance=importance,
                acceptance_criteria=criteria,
                required_for_parent=False,
                query_role=item.get("query_role") or "seed",
                granularity_level=item.get("granularity_level") or "topic",
                scope_signature=item.get("scope_signature") or _gap_key(text),
                target_slot_keys=item.get("target_slot_keys") or [],
                anchor_claim_ids=[],
                anchor_conflict_ids=[],
                anchor_evidence_ids=[],
            )
            for slot_key in item.get("target_slot_keys") or []:
                slot = slot_by_key.get(slot_key)
                if slot:
                    graph_tools.add_edge(query_id, slot["id"], EdgeType.TARGETS_SLOT)
            query = graph_tools.get_node(query_id)
            queries.append({
                "handle": query.get("handle"),
                "id": query_id,
                "text": text,
                "priority_tier": query.get("priority_tier"),
                "acceptance_criteria": criteria,
                "query_role": query.get("query_role"),
                "granularity_level": query.get("granularity_level"),
                "target_slot_keys": item.get("target_slot_keys") or [],
            })
        if not queries:
            query_id = graph_tools.create_query_child(
                parent_id=goal_id,
                text=user_request,
                importance="core",
                acceptance_criteria=["Directly answer the user's research request with reliable evidence"],
                required_for_parent=False,
                query_role="seed",
                granularity_level="topic",
                scope_signature="answer-request",
                target_slot_keys=[slot["slot_key"] for slot in slots[:3]],
                anchor_claim_ids=[],
                anchor_conflict_ids=[],
                anchor_evidence_ids=[],
            )
            for slot in slots[:3]:
                graph_tools.add_edge(query_id, slot["id"], EdgeType.TARGETS_SLOT)
            query = graph_tools.get_node(query_id)
            queries.append({
                "handle": query.get("handle"),
                "id": query_id,
                "text": user_request,
                "priority_tier": query.get("priority_tier"),
                "acceptance_criteria": query.get("acceptance_criteria") or [],
                "query_role": query.get("query_role"),
                "granularity_level": query.get("granularity_level"),
            })

        research_state.update_goal({"research_state": research_state.RESEARCHING}, goal_id)

        return {
            "goal_id": goal_id,
            "research_goal": parsed.get("research_goal", ""),
            "language": parsed.get("language"),
            "scope_mode": graph_tools.get_node(goal_id).get("scope_mode", "bounded"),
            "task_contract": graph_tools.get_node(contract_id),
            "coverage_slots": slots,
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
        """Return the next deterministic actions from the frontier backlog."""
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
        for node in queries:
            query_status = node.get("status")
            if query_status == "assessing":
                actions.append({
                    "action": "assess_query",
                    "query_id": node["id"],
                    "query_handle": node.get("handle"),
                    "priority": node.get("priority", 0.0),
                    "required_for_parent": node.get("required_for_parent", False),
                    "required_path": research_state.is_required_path(node["id"]),
                    "semantic_importance": node.get("sem", 0.0),
                    "frontier_ids": [],
                    "reason": "successful search completed",
                })
            elif query_status == "pending":
                actions.append({
                    "action": "dispatch_searcher",
                    "query_id": node["id"],
                    "query_handle": node.get("handle"),
                    "priority": node.get("priority", 0.0),
                    "required_for_parent": node.get("required_for_parent", False),
                    "required_path": research_state.is_required_path(node["id"]),
                    "semantic_importance": node.get("sem", 0.0),
                    "frontier_ids": [],
                    "reason": "query awaits its first successful search",
                })

        selected_frontiers = self._get_selected_frontier_actions()
        actions.extend(selected_frontiers)

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
                    "frontier_ids": [],
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
                    "frontier_ids": [],
                    "reason": "no higher-priority workflow action remains",
                })

        action_rank = {
            "assess_query": 0,
            "evaluate_research_portfolio": 1,
            "expand_vertically": 2,
            "expand_horizontally": 3,
            "dispatch_searcher": 4,
            "assess_convergence": 5,
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

    @staticmethod
    def _normalize_claim_key(text: str, explicit: Optional[str] = None) -> str:
        """Return a stable key for a canonical Claim."""
        explicit = str(explicit or "").strip()
        if explicit and explicit.lower() not in {"null", "none"}:
            return "-".join(explicit.lower().split())[:80]
        return _gap_key(text)

    @staticmethod
    def _stance_edge_type(stance: Optional[str]) -> EdgeType:
        """Map a normalizer stance to the graph edge type."""
        value = str(stance or "supports").lower()
        if value in {"contradicts", "contradict", "against"}:
            return EdgeType.CONTRADICTED_BY
        if value in {"qualifies", "qualify", "qualified"}:
            return EdgeType.QUALIFIED_BY
        return EdgeType.SUPPORTED_BY

    def _fallback_claim_specs(self, query: dict, statements: list[dict], evidence: list[dict]) -> list[dict]:
        """Build conservative Claim specs when the LLM normalizer returns none."""
        specs: list[dict] = []
        objective_keys = query.get("objective_keys") or []
        for statement in statements:
            text = str(statement.get("text") or statement.get("statement") or "").strip()
            if not text:
                continue
            specs.append({
                "canonical_text": text,
                "claim_key": self._normalize_claim_key(text),
                "statement_refs": [statement["id"]],
                "evidence_refs": [
                    {"id": item["id"], "stance": item.get("stance") or "supports"}
                    for item in evidence
                    if item.get("statement_ref") == statement["id"]
                ],
                "objective_keys": objective_keys,
                "confidence": 0.5,
                "qualifiers": statement.get("qualifiers") or [],
                "limitations": statement.get("limitations") or [],
            })
        if specs:
            return specs
        for item in evidence:
            text = str(item.get("text") or item.get("claim") or "").strip()
            if not text:
                continue
            specs.append({
                "canonical_text": text,
                "claim_key": self._normalize_claim_key(text),
                "statement_refs": [],
                "evidence_refs": [{"id": item["id"], "stance": item.get("stance") or "supports"}],
                "objective_keys": objective_keys,
                "confidence": 0.45,
                "qualifiers": item.get("qualifiers") or [],
                "limitations": item.get("limitations") or [],
            })
        return specs

    def normalize_claims(self, query_id: str) -> dict:
        """Create or update canonical Claims for one Query's owned materials."""
        query = graph_tools.get_node(query_id)
        evaluation = graph_tools.get_query_evaluation_subgraph(query_id)
        nodes = evaluation.get("nodes", [])
        statements = [
            node for node in nodes
            if node.get("type") == NodeType.STATEMENT.value
        ]
        evidence = [
            node for node in nodes
            if node.get("type") == NodeType.EVIDENCE.value
        ]
        if not statements and not evidence:
            return {"created_or_updated_claim_ids": [], "claim_count": 0}
        if not statements:
            specs = self._fallback_claim_specs(query, statements, evidence)
            return self._write_claim_specs(query, specs, statements, evidence)

        compact = {
            "statements": [
                {
                    "id": item.get("id"),
                    "text": item.get("text") or item.get("statement"),
                    "document_id": item.get("document_id"),
                    "source_id": item.get("source_id"),
                    "qualifiers": item.get("qualifiers") or [],
                    "limitations": item.get("limitations") or [],
                    "confidence": item.get("confidence"),
                }
                for item in statements
            ],
            "evidence": [
                {
                    "id": item.get("id"),
                    "text": item.get("text") or item.get("claim"),
                    "document_id": item.get("document_id"),
                    "source_id": item.get("source_id"),
                    "statement_ref": item.get("statement_ref"),
                    "claim_ref": item.get("claim_ref"),
                    "stance": item.get("stance"),
                    "qualifiers": item.get("qualifiers") or [],
                    "limitations": item.get("limitations") or [],
                    "confidence": item.get("confidence"),
                }
                for item in evidence
            ],
        }
        prompt = (
            mm_prompts.normalize_claims
            .replace("{query}", json.dumps({
                "id": query.get("id"),
                "text": query.get("text"),
                "objective_keys": query.get("objective_keys") or [],
                "acceptance_criteria": query.get("acceptance_criteria") or [],
            }, ensure_ascii=False))
            .replace("{evidence_subgraph}", json.dumps(compact, ensure_ascii=False))
        )
        verdict = self._invoke_json(prompt)
        raw_specs = verdict.get("claims") if isinstance(verdict, dict) else None
        specs = [item for item in raw_specs or [] if isinstance(item, dict)]
        if not specs:
            specs = self._fallback_claim_specs(query, statements, evidence)
        return self._write_claim_specs(query, specs, statements, evidence)

    def _write_claim_specs(
        self,
        query: dict,
        specs: list[dict],
        statements: list[dict],
        evidence: list[dict],
    ) -> dict:
        """Persist normalized Claim specs and their provenance edges."""
        node_by_id = {node.get("id"): node for node in statements + evidence if node.get("id")}
        objective_by_key = {item["objective_key"]: item for item in self.get_research_objectives()}
        claim_ids: list[str] = []
        for spec in specs:
            canonical = str(spec.get("canonical_text") or spec.get("statement") or "").strip()
            if not canonical:
                continue
            claim_key = self._normalize_claim_key(canonical, spec.get("claim_key"))
            try:
                confidence = max(0.0, min(1.0, float(spec.get("confidence", 0.5))))
            except (TypeError, ValueError):
                confidence = 0.5
            objective_keys = [
                key for key in (spec.get("objective_keys") or query.get("objective_keys") or [])
                if key in objective_by_key
            ]
            claim_id = graph_tools.create_claim(
                statement=canonical,
                canonical_text=canonical,
                claim_key=claim_key,
                confidence=confidence,
                qualifiers=spec.get("qualifiers") if isinstance(spec.get("qualifiers"), list) else [],
                limitations=spec.get("limitations") if isinstance(spec.get("limitations"), list) else [],
                objective_keys=objective_keys,
            )
            claim_ids.append(claim_id)
            for statement_id in spec.get("statement_refs") or []:
                if node_by_id.get(statement_id, {}).get("type") == NodeType.STATEMENT.value:
                    graph_tools.add_edge(statement_id, claim_id, EdgeType.NORMALIZED_TO)
            for item in spec.get("evidence_refs") or []:
                if isinstance(item, str):
                    evidence_id, stance = item, "supports"
                elif isinstance(item, dict):
                    evidence_id = item.get("id")
                    stance = item.get("stance")
                else:
                    continue
                if node_by_id.get(evidence_id, {}).get("type") == NodeType.EVIDENCE.value:
                    graph_tools.add_edge(evidence_id, claim_id, self._stance_edge_type(stance))
            for key in objective_keys:
                graph_tools.add_edge(claim_id, objective_by_key[key]["id"], EdgeType.COVERS_OBJECTIVE)
        return {
            "created_or_updated_claim_ids": list(dict.fromkeys(claim_ids)),
            "claim_count": len(set(claim_ids)),
        }

    def assess_query(self, query_id: str) -> dict:
        """Assess one Query, update slots, and emit frontier candidates."""
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
        if query.get("status") != "assessing":
            return {"error": f"Query {query.get('handle') or resolved} is not ready for assessment"}

        normalization = self.normalize_claims(resolved)
        evaluation = graph_tools.get_query_evaluation_subgraph(resolved)
        task_contract = self._task_contract_snapshot()
        prompt = mm_prompts.assess_query_frontiers.replace(
            "{query}", json.dumps({
                "id": query.get("id"),
                "handle": query.get("handle"),
                "text": query.get("text"),
                "query_role": query.get("query_role"),
                "granularity_level": query.get("granularity_level"),
                "scope_signature": query.get("scope_signature"),
                "acceptance_criteria": query.get("acceptance_criteria") or [],
                "target_slot_keys": query.get("target_slot_keys") or [],
                "normalized_claims": normalization,
            }, ensure_ascii=False)
        ).replace(
            "{task_contract}",
            json.dumps(task_contract, ensure_ascii=False),
        ).replace(
            "{evaluation_subgraph}",
            json.dumps(evaluation, ensure_ascii=False),
        )
        verdict = self._invoke_json(prompt)
        try:
            score = max(0.0, min(1.0, float(verdict.get("sufficiency_score", 0.0))))
        except (TypeError, ValueError):
            score = 0.0
        filled_slot_keys = verdict.get("filled_slot_keys") if isinstance(verdict.get("filled_slot_keys"), list) else []
        remaining_slot_keys = verdict.get("remaining_slot_keys") if isinstance(verdict.get("remaining_slot_keys"), list) else []
        slot_update = self._apply_slot_fill_status(resolved, filled_slot_keys, remaining_slot_keys, evaluation)
        created_horizontal = self._upsert_frontiers_from_specs(
            owner_query_id=resolved,
            frontier_specs=verdict.get("horizontal_frontiers") if isinstance(verdict.get("horizontal_frontiers"), list) else [],
            frontier_type="horizontal",
            default_parent_query_id=graph_tools.get_query_parent(resolved),
        )
        created_vertical = self._upsert_frontiers_from_specs(
            owner_query_id=resolved,
            frontier_specs=verdict.get("vertical_frontiers") if isinstance(verdict.get("vertical_frontiers"), list) else [],
            frontier_type="vertical",
            default_parent_query_id=resolved,
        )
        created_hypotheses = self._upsert_dimension_hypotheses(
            resolved,
            verdict.get("dimension_hypotheses") if isinstance(verdict.get("dimension_hypotheses"), list) else [],
        )

        recommendation = verdict.get("recommendation") or "continue"
        new_status = "blocked" if recommendation == "blocked" else "sufficient"

        graph_tools.transition_query(
            resolved,
            new_status,
            sufficiency_score=score,
            covered=verdict.get("covered") or [],
            assessment_reason=verdict.get("reason") or "",
            local_recommendation=recommendation,
            filled_slot_keys=filled_slot_keys,
            remaining_slot_keys=remaining_slot_keys,
        )
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
            "filled_slot_ids": slot_update.get("filled_slot_ids"),
            "remaining_slot_ids": slot_update.get("remaining_slot_ids"),
            "created_horizontal_frontier_ids": created_horizontal,
            "created_vertical_frontier_ids": created_vertical,
            "created_dimension_hypothesis_ids": created_hypotheses,
            "next_action": "evaluate_research_portfolio",
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
        """Resolve selected vertical frontiers once a child query finishes."""
        frontier_status = {
            "sufficient": "resolved",
            "deferred": "deferred_low_value",
        }.get(child_status, "blocked")
        parent_id = graph_tools.get_query_parent(query_id)
        if not parent_id:
            return
        child = graph_tools.get_node(query_id)
        for frontier in graph_tools.get_frontiers(parent_id, {"selected", "expanded"}):
            if frontier.get("frontier_type") != "vertical":
                continue
            if frontier.get("scope_signature") != child.get("scope_signature"):
                continue
            graph_tools.upsert_node(NodeType.RESEARCH_FRONTIER, {
                "status": frontier_status,
                "resolution_reason": f"child query finished as {child_status}",
                "resolved_by_query_id": query_id,
            }, frontier["id"])

    def evaluate_research_portfolio(self, goal_id: Optional[str] = None) -> dict:
        """Score frontier candidates and select the active expansion backlog."""
        from tools import research_state

        goal = research_state.get_goal(goal_id)
        if goal.get("research_state") != research_state.RESEARCHING:
            return {"error": "Portfolio evaluation is only allowed while researching"}
        frontiers = [item for item in graph_tools.get_frontiers() if item.get("status") == "candidate"]
        metrics = self._compute_research_metrics(goal["id"])
        if not frontiers:
            graph_tools.upsert_node(NodeType.USER_REQUEST, {
                "evaluated_portfolio_revision": int(goal.get("portfolio_revision") or 0),
                "last_max_marginal_utility": 0.0,
                "horizontal_closure_score": metrics["horizontal_closure_score"],
                "slot_completion_score": metrics["slot_completion_score"],
                "report_readiness_score": metrics["delivery_readiness_score"],
                "delivery_readiness": metrics["delivery_ready"],
            }, goal["id"])
            return {
                "selected_frontier_ids": [],
                "deferred_frontier_ids": [],
                "last_max_marginal_utility": 0.0,
                **metrics,
                "next_action": "get_next_actions",
            }

        strong_dimensions = {
            hypothesis.get("dimension_label")
            for hypothesis in graph_tools.search_nodes("dimension_hypothesis", {})
            if float(hypothesis.get("support_strength") or 0.0) >= 0.6
            and not (hypothesis.get("covered_by_query_ids") or [])
        }
        budgets = self._remaining_frontier_budgets(goal)
        horizontal_open = metrics["horizontal_closure_score"] < 0.85
        ranked: list[tuple[float, dict[str, Any]]] = []
        for frontier in frontiers:
            slot_blocking = float(frontier.get("slot_blocking_score") or 0.0)
            decision_impact = float(frontier.get("decision_impact") or 0.0)
            confidence_gain = float(frontier.get("confidence_gain") or 0.0)
            novelty_score = float(frontier.get("novelty_score") or 0.0)
            primary_source_need = float(frontier.get("primary_source_need") or 0.0)
            estimated_rounds = max(1, int(frontier.get("estimated_search_rounds") or 1))
            redundancy = self._frontier_redundancy(frontier)
            score = (
                decision_impact * 0.30
                + confidence_gain * 0.25
                + novelty_score * 0.15
                + slot_blocking * 0.20
                + primary_source_need * 0.10
                - redundancy * 0.25
            ) / estimated_rounds
            if frontier.get("frontier_type") == "vertical" and self._is_verification_frontier(frontier):
                score += 0.6
            if frontier.get("frontier_type") == "horizontal" and frontier.get("dimension") in strong_dimensions:
                score += 0.3
            ranked.append((score, frontier))
        ranked.sort(key=lambda item: item[0], reverse=True)

        selected_frontier_ids: list[str] = []
        deferred_frontier_ids: list[str] = []
        max_utility = ranked[0][0] if ranked else 0.0
        for score, frontier in ranked:
            frontier_type = frontier.get("frontier_type")
            choose = False
            if frontier_type == "vertical" and self._is_verification_frontier(frontier) and budgets["verification"] > 0:
                budgets["verification"] -= 1
                choose = True
            elif horizontal_open and frontier_type == "horizontal" and budgets["breadth"] > 0:
                budgets["breadth"] -= 1
                choose = True
            elif frontier_type == "vertical" and budgets["depth"] > 0:
                budgets["depth"] -= 1
                choose = True
            elif frontier_type == "horizontal" and budgets["breadth"] > 0 and score >= 0.2:
                budgets["breadth"] -= 1
                choose = True
            new_status = "selected" if choose else ("deferred_low_value" if score < 0.2 else "deferred_budget")
            graph_tools.upsert_node(NodeType.RESEARCH_FRONTIER, {
                "status": new_status,
                "marginal_utility": score,
            }, frontier["id"])
            if choose:
                selected_frontier_ids.append(frontier["id"])
            else:
                deferred_frontier_ids.append(frontier["id"])

        graph_tools.upsert_node(NodeType.USER_REQUEST, {
            "evaluated_portfolio_revision": int(goal.get("portfolio_revision") or 0),
            "last_max_marginal_utility": max_utility,
            "horizontal_closure_score": metrics["horizontal_closure_score"],
            "slot_completion_score": metrics["slot_completion_score"],
            "report_readiness_score": metrics["delivery_readiness_score"],
            "delivery_readiness": metrics["delivery_ready"],
        }, goal["id"])
        return {
            "selected_frontier_ids": selected_frontier_ids,
            "deferred_frontier_ids": deferred_frontier_ids,
            "last_max_marginal_utility": max_utility,
            **metrics,
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

    def expand_horizontally(self, parent_id: str, frontier_ids: Optional[list[str]] = None) -> dict:
        """Create sibling queries from selected horizontal frontiers."""
        from tools import research_state

        if research_state.get_status().get("research_state") != research_state.RESEARCHING:
            return {"error": "Horizontal expansion is only allowed while research_state is RESEARCHING"}
        try:
            resolved = self._resolve_query_id(parent_id)
        except AmbiguousQueryReference as exc:
            return {"error": str(exc)}
        if resolved is None:
            return {"error": f"Unknown query reference: {parent_id!r}"}
        attach_parent = graph_tools.get_node(resolved)
        if attach_parent.get("type") not in {NodeType.USER_REQUEST.value, NodeType.QUERY.value}:
            return {"error": f"Invalid horizontal attach parent: {resolved!r}"}
        candidate_frontiers = [
            frontier for frontier in graph_tools.get_frontiers()
            if frontier.get("status") == "selected"
            and frontier.get("frontier_type") == "horizontal"
            and frontier.get("parent_query_id") == resolved
        ]
        if frontier_ids:
            candidate_frontiers = [frontier for frontier in candidate_frontiers if frontier["id"] in frontier_ids]
        if not candidate_frontiers:
            return {"parent_id": resolved, "created": [], "next_action": "get_next_actions"}

        goal = research_state.get_goal()
        siblings = [graph_tools.get_node(cid) for cid in graph_tools.get_query_children(resolved)]
        frontier_specs = [
            {
                "id": frontier["id"],
                "description": frontier.get("description"),
                "importance": frontier.get("importance"),
                "granularity_level": frontier.get("granularity_level"),
                "scope_signature": frontier.get("scope_signature"),
                "target_slot_keys": frontier.get("target_slot_keys") or [],
                "acceptance_criteria": frontier.get("acceptance_criteria") or [],
            }
            for frontier in candidate_frontiers
        ]
        planner_output = self._plan_horizontal_queries(
            research_goal=goal.get("research_goal") or goal.get("request") or "",
            attach_parent=attach_parent,
            current_query=None,
            siblings=siblings,
            frontiers=frontier_specs,
            max_new=min(3, len(frontier_specs)),
        )
        created = self._materialize_horizontal_queries(resolved, candidate_frontiers, planner_output.get("queries") or [])
        self._bump_portfolio_revision()
        return {
            "parent_id": resolved,
            "parent_handle": attach_parent.get("handle"),
            "created": created,
            "next_action": "get_next_actions",
        }

    def expand_vertically(self, query_id: str, frontier_ids: Optional[list[str]] = None) -> dict:
        """Create child queries from selected vertical frontiers."""
        from tools import research_state

        if research_state.get_status().get("research_state") != research_state.RESEARCHING:
            return {"error": "Vertical expansion is only allowed while research_state is RESEARCHING"}
        try:
            resolved = self._resolve_query_id(query_id)
        except AmbiguousQueryReference as exc:
            return {"error": str(exc)}
        if resolved is None:
            return {"error": f"Unknown query reference: {query_id!r}"}
        parent = graph_tools.get_node(resolved)
        frontiers = graph_tools.get_frontiers(resolved, {"selected"})
        frontiers = [item for item in frontiers if item.get("frontier_type") == "vertical"]
        if frontier_ids:
            frontiers = [item for item in frontiers if item["id"] in frontier_ids]
        if not frontiers:
            return {"query_id": resolved, "created": [], "next_action": "get_next_actions"}

        goal = research_state.get_goal()
        planner_output = self._plan_vertical_queries(
            research_goal=goal.get("research_goal") or goal.get("request") or "",
            current_query=parent,
            frontiers=frontiers,
            max_new=min(3, len(frontiers)),
        )
        created = self._materialize_vertical_queries(resolved, frontiers, planner_output.get("queries") or [])
        self._bump_portfolio_revision()
        return {
            "query_id": resolved,
            "query_handle": parent.get("handle"),
            "created": created,
            "next_action": "get_next_actions",
        }

    def assess_convergence(self, goal_id: Optional[str] = None) -> dict:
        """Authorize reporting only when frontier closure and delivery slots are ready."""
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
                "selected_frontier_backlog": 0,
                "active_queries": [],
                "recommendation": "failed",
                "reason": reason,
                "research_state": research_state.FAILED,
                "tree_validation": tree,
                "next_actions": [],
            }
        goal = research_state.get_goal(goal_id)
        metrics = self._compute_research_metrics(goal.get("id"))
        task_contract = self._task_contract_snapshot(goal.get("id"))
        selected_frontiers = graph_tools.get_frontiers(statuses={"selected"})
        active_queries = [
            query for query in all_queries
            if query.get("status") in {"pending", "searching", "assessing"}
        ]
        open_conflicts = [
            conflict for conflict in graph_tools.search_nodes("conflict", {})
            if conflict.get("resolution_status") in {"unresolved", "investigating"}
        ]
        readiness = self._invoke_json(
            mm_prompts.assess_delivery_readiness
            .replace("{task_contract}", json.dumps(task_contract, ensure_ascii=False))
            .replace("{portfolio}", json.dumps({
                "metrics": metrics,
                "selected_frontiers": selected_frontiers,
                "active_queries": active_queries,
                "open_conflicts": open_conflicts,
            }, ensure_ascii=False))
        )
        remaining = research_state.remaining_budget(goal_id)
        delivery_ready = bool(readiness.get("delivery_ready")) and metrics["selected_frontier_backlog"] == 0
        low_value_open = self._all_remaining_frontiers_low_value()
        if (
            tree["valid"]
            and delivery_ready
            and metrics["horizontal_closure_score"] >= 0.85
            and metrics["slot_completion_score"] >= metrics["slot_completion_threshold"]
            and metrics["selected_frontier_backlog"] == 0
            and metrics["core_claim_support_score"] >= 0.7
        ):
            research_state.update_goal({
                "research_state": research_state.REPORT_READY,
                "last_convergence_recommendation": "stop",
                "report_authorized_reason": "frontier closure and delivery slots are ready",
            }, goal_id)
            recommendation = "stop"
            state = research_state.REPORT_READY
        elif (
            remaining == 0
            and metrics["slot_completion_score"] >= metrics["slot_completion_threshold"]
            and metrics["selected_frontier_backlog"] == 0
            and low_value_open
        ):
            research_state.mark_budget_exhausted(goal_id)
            research_state.update_goal({
                "report_authorized_reason": "budget exhausted after delivery slots reached threshold and only low-value frontier remained",
            }, goal_id)
            recommendation = "stop"
            state = research_state.BUDGET_EXHAUSTED
        else:
            research_state.update_goal({
                "research_state": research_state.RESEARCHING,
                "last_convergence_recommendation": "continue",
                "report_authorized_reason": None,
            }, goal_id)
            recommendation = "continue"
            state = research_state.RESEARCHING

        graph_tools.upsert_node(NodeType.USER_REQUEST, {
            "horizontal_closure_score": metrics["horizontal_closure_score"],
            "slot_completion_score": metrics["slot_completion_score"],
            "report_readiness_score": max(
                float(readiness.get("slot_completion_score") or 0.0),
                metrics["delivery_readiness_score"],
            ),
            "delivery_readiness": delivery_ready,
        }, goal["id"])
        return {
            "converged": recommendation == "stop",
            "selected_frontier_backlog": metrics["selected_frontier_backlog"],
            "horizontal_closure_score": metrics["horizontal_closure_score"],
            "slot_completion_score": metrics["slot_completion_score"],
            "core_claim_support_score": metrics["core_claim_support_score"],
            "delivery_ready": delivery_ready,
            "missing_sections": readiness.get("missing_sections") or [],
            "missing_tables": readiness.get("missing_tables") or [],
            "recommendation": recommendation,
            "reason": readiness.get("reason", ""),
            "research_state": state,
            "tree_validation": tree,
            "next_actions": self.get_next_actions() if recommendation == "continue" else [],
        }

    def _goal_node(self, goal_id: Optional[str] = None) -> dict:
        from tools import research_state

        return research_state.get_goal(goal_id)

    def _task_contract_snapshot(self, goal_id: Optional[str] = None) -> dict:
        goal = self._goal_node(goal_id)
        contract = graph_tools.get_task_contract(goal.get("id")) if goal else None
        slots = graph_tools.get_coverage_slots(goal.get("id")) if goal else []
        return {
            "goal": {
                "id": goal.get("id"),
                "request": goal.get("request"),
                "research_goal": goal.get("research_goal"),
                "language": goal.get("language"),
                "deliverable_type": goal.get("deliverable_type"),
            } if goal else {},
            "task_contract": contract or {},
            "slot_registry": [
                {
                    "id": slot.get("id"),
                    "slot_key": slot.get("slot_key"),
                    "section": slot.get("section"),
                    "unit_type": slot.get("unit_type"),
                    "dimension": slot.get("dimension"),
                    "priority": slot.get("priority"),
                    "status": slot.get("status"),
                    "completion_score": slot.get("completion_score"),
                    "description": slot.get("description"),
                    "min_sources": slot.get("min_sources"),
                    "needs_primary_source": slot.get("needs_primary_source"),
                }
                for slot in slots
            ],
        }

    def _create_coverage_slots(
        self,
        goal_id: str,
        contract_id: str,
        task_contract: dict[str, Any],
        slot_specs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        required_sections = task_contract.get("required_sections") if isinstance(task_contract.get("required_sections"), list) else []
        specs = [item for item in slot_specs if isinstance(item, dict)]
        if not specs:
            for section in required_sections:
                section_key = str(section.get("section_key") or _gap_key(section.get("title") or "section"))[:48]
                specs.append({
                    "slot_key": f"{section_key}-core",
                    "section": section_key,
                    "unit_type": "paragraph",
                    "dimension": None,
                    "priority": "core",
                    "min_sources": 2,
                    "needs_primary_source": False,
                    "description": section.get("purpose") or section.get("title") or section_key,
                })
        created: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        for spec in specs:
            slot_key = str(spec.get("slot_key") or "").strip()
            if not slot_key or slot_key in seen_keys:
                continue
            seen_keys.add(slot_key)
            section = str(spec.get("section") or "").strip() or "body"
            slot_id = graph_tools.create_coverage_slot(
                goal_id=goal_id,
                task_contract_id=contract_id,
                slot_key=slot_key,
                section=section,
                unit_type=spec.get("unit_type") or "paragraph",
                status="open",
                dimension=spec.get("dimension"),
                priority=spec.get("priority") or "supporting",
                completion_score=0.0,
                min_sources=max(1, int(spec.get("min_sources") or 1)),
                needs_primary_source=bool(spec.get("needs_primary_source")),
                description=spec.get("description") or slot_key,
            )
            created.append(graph_tools.get_node(slot_id))
        return created

    def _query_target_slots(self, query_id: str) -> list[dict[str, Any]]:
        slots: list[dict[str, Any]] = []
        for edge in graph_tools.get_node_edges(query_id, direction="out"):
            if str(edge.get("type", "")).lower() != "targets_slot":
                continue
            slot = graph_tools.get_node(edge["target"])
            if slot.get("type") == NodeType.COVERAGE_SLOT.value:
                slots.append(slot)
        if slots:
            return slots
        query = graph_tools.get_node(query_id)
        slot_by_key = {slot.get("slot_key"): slot for slot in graph_tools.get_coverage_slots(self._goal_node().get("id"))}
        return [
            slot_by_key[key]
            for key in query.get("target_slot_keys") or []
            if key in slot_by_key
        ]

    def _apply_slot_fill_status(
        self,
        query_id: str,
        filled_slot_keys: list[str],
        remaining_slot_keys: list[str],
        evaluation: dict[str, Any],
    ) -> dict[str, list[str]]:
        goal = self._goal_node()
        slots = graph_tools.get_coverage_slots(goal.get("id"))
        slot_by_key = {slot.get("slot_key"): slot for slot in slots}
        evidence_ids = [node["id"] for node in evaluation.get("nodes", []) if node.get("type") == NodeType.EVIDENCE.value]
        claim_ids = [node["id"] for node in evaluation.get("nodes", []) if node.get("type") == NodeType.CLAIM.value]
        filled_slot_ids: list[str] = []
        remaining_slot_ids: list[str] = []
        for slot_key in filled_slot_keys:
            slot = slot_by_key.get(slot_key)
            if not slot:
                continue
            filled_slot_ids.append(slot["id"])
            graph_tools.upsert_node(NodeType.COVERAGE_SLOT, {
                "status": "filled" if evidence_ids else "partial",
                "completion_score": 1.0 if evidence_ids else 0.6,
                "last_filled_by_query_id": query_id,
            }, slot["id"])
            graph_tools.bind_slot_filler(slot["id"], evidence_ids=evidence_ids, claim_ids=claim_ids)
        for slot_key in remaining_slot_keys:
            slot = slot_by_key.get(slot_key)
            if not slot:
                continue
            remaining_slot_ids.append(slot["id"])
            if slot.get("status") != "filled":
                graph_tools.upsert_node(NodeType.COVERAGE_SLOT, {
                    "status": "partial" if slot.get("completion_score") else "open",
                }, slot["id"])
        return {"filled_slot_ids": filled_slot_ids, "remaining_slot_ids": remaining_slot_ids}

    def _upsert_frontiers_from_specs(
        self,
        owner_query_id: str,
        frontier_specs: list[dict[str, Any]],
        frontier_type: str,
        default_parent_query_id: Optional[str],
    ) -> list[str]:
        goal = self._goal_node()
        slot_by_key = {slot.get("slot_key"): slot for slot in graph_tools.get_coverage_slots(goal.get("id"))}
        existing = {
            (item.get("frontier_type"), item.get("scope_signature") or item.get("description")): item["id"]
            for item in graph_tools.get_frontiers(owner_query_id)
        }
        created: list[str] = []
        for raw in frontier_specs:
            if not isinstance(raw, dict):
                continue
            description = str(raw.get("description") or "").strip()
            if not description:
                continue
            scope_signature = str(raw.get("scope_signature") or _gap_key(description))
            dedupe_key = (frontier_type, scope_signature)
            if dedupe_key in existing:
                graph_tools.upsert_node(NodeType.RESEARCH_FRONTIER, {
                    "description": description,
                    "decision_impact": float(raw.get("decision_impact") or 0.0),
                    "confidence_gain": float(raw.get("confidence_gain") or 0.0),
                    "novelty_score": float(raw.get("novelty_score") or 0.0),
                    "slot_blocking_score": float(raw.get("slot_blocking_score") or 0.0),
                    "primary_source_need": float(raw.get("primary_source_need") or 0.0),
                    "estimated_search_rounds": max(1, int(raw.get("estimated_search_rounds") or 1)),
                }, existing[dedupe_key])
                created.append(existing[dedupe_key])
                continue
            target_slot_keys = [key for key in (raw.get("target_slot_keys") or []) if key in slot_by_key]
            frontier_id = graph_tools.create_frontier(
                owner_id=owner_query_id,
                frontier_type=frontier_type,
                description=description,
                status="candidate",
                slot_ids=[slot_by_key[key]["id"] for key in target_slot_keys],
                anchor_claim_ids=raw.get("anchor_claim_ids") if isinstance(raw.get("anchor_claim_ids"), list) else [],
                anchor_conflict_ids=raw.get("anchor_conflict_ids") if isinstance(raw.get("anchor_conflict_ids"), list) else [],
                anchor_evidence_ids=raw.get("anchor_evidence_ids") if isinstance(raw.get("anchor_evidence_ids"), list) else [],
                parent_query_id=default_parent_query_id,
                importance=raw.get("importance") or "supporting",
                granularity_level=raw.get("granularity_level"),
                scope_signature=scope_signature,
                target_slot_keys=target_slot_keys,
                decision_impact=float(raw.get("decision_impact") or 0.0),
                confidence_gain=float(raw.get("confidence_gain") or 0.0),
                novelty_score=float(raw.get("novelty_score") or 0.0),
                slot_blocking_score=float(raw.get("slot_blocking_score") or 0.0),
                primary_source_need=float(raw.get("primary_source_need") or 0.0),
                estimated_search_rounds=max(1, int(raw.get("estimated_search_rounds") or 1)),
                acceptance_criteria=raw.get("acceptance_criteria") if isinstance(raw.get("acceptance_criteria"), list) else [],
                dimension=raw.get("dimension"),
            )
            created.append(frontier_id)
        return created

    def _upsert_dimension_hypotheses(self, owner_query_id: str, hypotheses: list[dict[str, Any]]) -> list[str]:
        goal = self._goal_node()
        queries = graph_tools.search_nodes("query", {})
        created: list[str] = []
        for raw in hypotheses:
            if not isinstance(raw, dict):
                continue
            label = str(raw.get("dimension_label") or "").strip()
            if not label:
                continue
            existing = [
                node for node in graph_tools.search_nodes("dimension_hypothesis", {})
                if node.get("dimension_label") == label and node.get("parent_query_id") == owner_query_id
            ]
            covered_signatures = set(raw.get("covered_by_scope_signatures") or [])
            covered_query_ids = [
                query["id"]
                for query in queries
                if query.get("scope_signature") in covered_signatures
            ]
            if existing:
                graph_tools.upsert_node(NodeType.DIMENSION_HYPOTHESIS, {
                    "support_strength": float(raw.get("support_strength") or 0.0),
                    "covered_by_query_ids": covered_query_ids,
                }, existing[0]["id"])
                created.append(existing[0]["id"])
            else:
                created.append(graph_tools.create_dimension_hypothesis(
                    goal_id=goal["id"],
                    dimension_label=label,
                    parent_query_id=owner_query_id,
                    support_strength=float(raw.get("support_strength") or 0.0),
                    covered_by_query_ids=covered_query_ids,
                ))
        return created

    def _frontier_owner_id(self, frontier_id: str) -> Optional[str]:
        for edge in graph_tools.get_node_edges(frontier_id, direction="in"):
            if str(edge.get("type", "")).lower() != "has_frontier":
                continue
            return edge.get("source")
        return None

    def _is_verification_frontier(self, frontier: dict[str, Any]) -> bool:
        return bool(
            frontier.get("anchor_conflict_ids")
            or frontier.get("anchor_claim_ids")
            or float(frontier.get("primary_source_need") or 0.0) >= 0.7
        )

    def _frontier_redundancy(self, frontier: dict[str, Any]) -> float:
        scope_signature = frontier.get("scope_signature")
        if not scope_signature:
            return 0.0
        for query in graph_tools.search_nodes("query", {}):
            if query.get("scope_signature") == scope_signature:
                return 1.0
        return 0.0

    def _remaining_frontier_budgets(self, goal: dict[str, Any]) -> dict[str, int]:
        def remaining(max_key: str, used_key: str) -> int:
            limit = int(goal.get(max_key) or 0)
            used = int(goal.get(used_key) or 0)
            return 999 if limit <= 0 else max(0, limit - used)

        return {
            "breadth": remaining("breadth_budget", "breadth_budget_used"),
            "depth": remaining("depth_budget", "depth_budget_used"),
            "verification": remaining("verification_budget", "verification_budget_used"),
        }

    def _get_selected_frontier_actions(self) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        vertical: dict[str, list[dict[str, Any]]] = {}
        horizontal: dict[str, list[dict[str, Any]]] = {}
        for frontier in graph_tools.get_frontiers(statuses={"selected"}):
            owner_id = self._frontier_owner_id(frontier["id"])
            if frontier.get("frontier_type") == "vertical" and owner_id:
                vertical.setdefault(owner_id, []).append(frontier)
            elif frontier.get("frontier_type") == "horizontal":
                attach_parent = frontier.get("parent_query_id")
                if attach_parent:
                    horizontal.setdefault(attach_parent, []).append(frontier)
        for owner_id, items in vertical.items():
            owner = graph_tools.get_node(owner_id)
            actions.append({
                "action": "expand_vertically",
                "query_id": owner_id,
                "query_handle": owner.get("handle"),
                "priority": max(float(item.get("marginal_utility") or 0.0) for item in items),
                "required_for_parent": False,
                "required_path": False,
                "semantic_importance": 1.0 if any(self._is_verification_frontier(item) for item in items) else 0.7,
                "frontier_ids": [item["id"] for item in items],
                "reason": "selected vertical frontier awaits child query creation",
            })
        for parent_id, items in horizontal.items():
            parent = graph_tools.get_node(parent_id)
            actions.append({
                "action": "expand_horizontally",
                "query_id": parent_id,
                "query_handle": parent.get("handle"),
                "priority": max(float(item.get("marginal_utility") or 0.0) for item in items),
                "required_for_parent": False,
                "required_path": False,
                "semantic_importance": 0.9,
                "frontier_ids": [item["id"] for item in items],
                "reason": "selected horizontal frontier awaits sibling query creation",
            })
        return actions

    def _compute_research_metrics(self, goal_id: str) -> dict[str, Any]:
        goal = self._goal_node(goal_id)
        contract = graph_tools.get_task_contract(goal_id) or {}
        slots = graph_tools.get_coverage_slots(goal_id)
        weighted_total = 0.0
        weighted_done = 0.0
        for slot in slots:
            weight = {"core": 1.0, "supporting": 0.7, "peripheral": 0.4}.get(slot.get("priority"), 0.6)
            weighted_total += weight
            weighted_done += weight * float(slot.get("completion_score") or 0.0)
        slot_completion_score = weighted_done / weighted_total if weighted_total else 0.0
        open_horizontal = [
            frontier for frontier in graph_tools.get_frontiers()
            if frontier.get("frontier_type") == "horizontal"
            and frontier.get("status") in {"candidate", "selected"}
        ]
        axes = contract.get("coverage_axes") if isinstance(contract.get("coverage_axes"), list) else []
        horizontal_closure_score = max(0.0, 1.0 - len(open_horizontal) / max(1, len(axes) or 3))
        sufficient_queries = [
            query for query in graph_tools.search_nodes("query", {})
            if query.get("status") == "sufficient"
        ]
        core_scores = [
            float(query.get("sufficiency_score") or 0.0)
            for query in sufficient_queries
            if query.get("importance") == "core" or query.get("query_role") == "seed"
        ]
        core_claim_support_score = sum(core_scores) / len(core_scores) if core_scores else 0.0
        selected_frontier_backlog = len(graph_tools.get_frontiers(statuses={"selected"}))
        delivery_readiness_score = (
            horizontal_closure_score * 0.3
            + slot_completion_score * 0.45
            + core_claim_support_score * 0.25
        )
        deliverable_type = goal.get("deliverable_type") or contract.get("deliverable_type") or "research_report"
        threshold = 0.8 if deliverable_type == "wikipedia_article" else 0.75
        return {
            "horizontal_closure_score": horizontal_closure_score,
            "slot_completion_score": slot_completion_score,
            "core_claim_support_score": core_claim_support_score,
            "selected_frontier_backlog": selected_frontier_backlog,
            "delivery_readiness_score": delivery_readiness_score,
            "delivery_ready": (
                horizontal_closure_score >= 0.85
                and slot_completion_score >= threshold
                and selected_frontier_backlog == 0
                and core_claim_support_score >= 0.7
            ),
            "slot_completion_threshold": threshold,
        }

    def _all_remaining_frontiers_low_value(self) -> bool:
        for frontier in graph_tools.get_frontiers():
            if frontier.get("status") in {"candidate", "selected"}:
                return False
        return True

    def _plan_task_contract(self, user_request: str) -> dict:
        prompt = mm_prompts.plan_task_contract.replace("{user_request}", user_request)
        return self._invoke_json(prompt)

    def _plan_seed_queries(self, task_contract: dict[str, Any]) -> dict:
        prompt = mm_prompts.plan_seed_queries.replace(
            "{task_contract}",
            json.dumps(task_contract, ensure_ascii=False),
        )
        return self._invoke_json(prompt)

    def _plan_horizontal_queries(
        self,
        research_goal: str,
        attach_parent: dict[str, Any],
        current_query: Optional[dict[str, Any]],
        siblings: list[dict[str, Any]],
        frontiers: list[dict[str, Any]],
        max_new: int,
    ) -> dict:
        prompt = (
            mm_prompts.plan_horizontal_queries
            .replace("{research_goal}", research_goal)
            .replace("{attach_parent}", json.dumps(attach_parent, ensure_ascii=False))
            .replace("{current_query}", json.dumps(current_query or {}, ensure_ascii=False))
            .replace("{siblings}", json.dumps(siblings, ensure_ascii=False))
            .replace("{frontiers}", json.dumps(frontiers, ensure_ascii=False))
            .replace("{max_new}", str(max_new))
        )
        return self._invoke_json(prompt)

    def _plan_vertical_queries(
        self,
        research_goal: str,
        current_query: dict[str, Any],
        frontiers: list[dict[str, Any]],
        max_new: int,
    ) -> dict:
        prompt = (
            mm_prompts.plan_vertical_queries
            .replace("{research_goal}", research_goal)
            .replace("{current_query}", json.dumps(current_query, ensure_ascii=False))
            .replace("{frontiers}", json.dumps(frontiers, ensure_ascii=False))
            .replace("{max_new}", str(max_new))
        )
        return self._invoke_json(prompt)

    def _materialize_horizontal_queries(
        self,
        parent_id: str,
        selected_frontiers: list[dict[str, Any]],
        planned_queries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        goal = self._goal_node()
        slot_by_key = {slot.get("slot_key"): slot for slot in graph_tools.get_coverage_slots(goal.get("id"))}
        frontier_by_signature = {item.get("scope_signature"): item for item in selected_frontiers}
        frontier_by_desc = {item.get("description"): item for item in selected_frontiers}
        sibling_queries = [graph_tools.get_node(cid) for cid in graph_tools.get_query_children(parent_id)]
        existing_signatures = {item.get("scope_signature") for item in sibling_queries}
        existing_texts = {item.get("text") for item in sibling_queries}
        created: list[dict[str, Any]] = []
        used = 0
        for raw in planned_queries[:3]:
            if not isinstance(raw, dict):
                continue
            text = str(raw.get("text") or "").strip()
            scope_signature = str(raw.get("scope_signature") or _gap_key(text))
            if not text or scope_signature in existing_signatures or text in existing_texts:
                continue
            frontier = frontier_by_signature.get(scope_signature) or frontier_by_desc.get(raw.get("frontier_description"))
            if not frontier:
                continue
            query_id = graph_tools.create_query_child(
                parent_id=parent_id,
                text=text,
                importance=raw.get("importance") or frontier.get("importance") or "supporting",
                acceptance_criteria=raw.get("acceptance_criteria") or frontier.get("acceptance_criteria") or [],
                required_for_parent=False,
                query_role="horizontal",
                granularity_level=raw.get("granularity_level") or frontier.get("granularity_level"),
                scope_signature=scope_signature,
                target_slot_keys=raw.get("target_slot_keys") or frontier.get("target_slot_keys") or [],
                anchor_claim_ids=[],
                anchor_conflict_ids=[],
                anchor_evidence_ids=[],
            )
            for slot_key in raw.get("target_slot_keys") or frontier.get("target_slot_keys") or []:
                slot = slot_by_key.get(slot_key)
                if slot:
                    graph_tools.add_edge(query_id, slot["id"], EdgeType.TARGETS_SLOT)
            graph_tools.upsert_node(NodeType.RESEARCH_FRONTIER, {
                "status": "expanded",
                "spawned_query_id": query_id,
            }, frontier["id"])
            query = graph_tools.get_node(query_id)
            created.append({"id": query_id, "handle": query.get("handle"), "text": query.get("text"), "frontier_id": frontier["id"]})
            existing_signatures.add(scope_signature)
            existing_texts.add(text)
            used += 1
        if used:
            graph_tools.upsert_node(NodeType.USER_REQUEST, {
                "breadth_budget_used": int(goal.get("breadth_budget_used") or 0) + used,
            }, goal["id"])
        return created

    def _materialize_vertical_queries(
        self,
        parent_id: str,
        selected_frontiers: list[dict[str, Any]],
        planned_queries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        goal = self._goal_node()
        slot_by_key = {slot.get("slot_key"): slot for slot in graph_tools.get_coverage_slots(goal.get("id"))}
        frontier_by_signature = {item.get("scope_signature"): item for item in selected_frontiers}
        frontier_by_desc = {item.get("description"): item for item in selected_frontiers}
        children = [graph_tools.get_node(cid) for cid in graph_tools.get_query_children(parent_id)]
        existing_signatures = {item.get("scope_signature") for item in children}
        existing_texts = {item.get("text") for item in children}
        created: list[dict[str, Any]] = []
        depth_used = 0
        verification_used = 0
        for raw in planned_queries[:3]:
            if not isinstance(raw, dict):
                continue
            text = str(raw.get("text") or "").strip()
            scope_signature = str(raw.get("scope_signature") or _gap_key(text))
            if not text or scope_signature in existing_signatures or text in existing_texts:
                continue
            frontier = frontier_by_signature.get(scope_signature) or frontier_by_desc.get(raw.get("frontier_description"))
            if not frontier:
                continue
            query_id = graph_tools.create_query_child(
                parent_id=parent_id,
                text=text,
                importance=raw.get("importance") or frontier.get("importance") or "supporting",
                acceptance_criteria=raw.get("acceptance_criteria") or frontier.get("acceptance_criteria") or [],
                required_for_parent=False,
                query_role="vertical",
                granularity_level=raw.get("granularity_level") or frontier.get("granularity_level"),
                scope_signature=scope_signature,
                target_slot_keys=raw.get("target_slot_keys") or frontier.get("target_slot_keys") or [],
                anchor_claim_ids=raw.get("anchor_claim_ids") or frontier.get("anchor_claim_ids") or [],
                anchor_conflict_ids=raw.get("anchor_conflict_ids") or frontier.get("anchor_conflict_ids") or [],
                anchor_evidence_ids=raw.get("anchor_evidence_ids") or frontier.get("anchor_evidence_ids") or [],
            )
            for slot_key in raw.get("target_slot_keys") or frontier.get("target_slot_keys") or []:
                slot = slot_by_key.get(slot_key)
                if slot:
                    graph_tools.add_edge(query_id, slot["id"], EdgeType.TARGETS_SLOT)
            graph_tools.upsert_node(NodeType.RESEARCH_FRONTIER, {
                "status": "expanded",
                "spawned_query_id": query_id,
            }, frontier["id"])
            query = graph_tools.get_node(query_id)
            created.append({"id": query_id, "handle": query.get("handle"), "text": query.get("text"), "frontier_id": frontier["id"]})
            existing_signatures.add(scope_signature)
            existing_texts.add(text)
            if self._is_verification_frontier(frontier):
                verification_used += 1
            else:
                depth_used += 1
        if depth_used or verification_used:
            graph_tools.upsert_node(NodeType.USER_REQUEST, {
                "depth_budget_used": int(goal.get("depth_budget_used") or 0) + depth_used,
                "verification_budget_used": int(goal.get("verification_budget_used") or 0) + verification_used,
            }, goal["id"])
        return created

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
                return {"error": "A Query with a successful SearchRun cannot be searched again; create new frontiers instead"}
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

            parent = graph_tools.get_node(graph_tools.get_query_parent(resolved) or "")
            target_slots = self._query_target_slots(resolved)
            task = {
                "query": query.get("text"),
                "query_role": query.get("query_role") or "seed",
                "granularity_level": query.get("granularity_level"),
                "scope_signature": query.get("scope_signature"),
                "acceptance_criteria": query.get("acceptance_criteria") or [],
                "target_slots": [
                    {
                        "slot_key": slot.get("slot_key"),
                        "section": slot.get("section"),
                        "dimension": slot.get("dimension"),
                        "description": slot.get("description"),
                    }
                    for slot in target_slots
                ],
                "anchor_claim_ids": query.get("anchor_claim_ids") or [],
                "anchor_conflict_ids": query.get("anchor_conflict_ids") or [],
                "anchor_evidence_ids": query.get("anchor_evidence_ids") or [],
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
            "statements": ("Statement", lambda item: bool(_first(item, "statement", "text_zh", "text"))),
            # Legacy packages used ``claims`` for document-bound extracted
            # statements. Treat them as Statement refs at ingest time; Claim
            # nodes are created later by normalize_claims().
            "claims": ("Statement", lambda item: bool(_first(item, "statement", "text_zh", "text"))),
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
        statement_items = list(evidence_package.get("statements", []) or [])
        statement_items.extend(evidence_package.get("claims", []) or [])
        for statement in statement_items:
            if not valid_ref(_first(statement, "document_ref", "document"), NodeType.DOCUMENT.value):
                return "Statement document_ref must reference a valid Document"
            if not valid_ref(_first(statement, "source_ref", "source"), NodeType.SOURCE.value):
                return "Statement source_ref must reference a valid Source"
        for evidence in evidence_package.get("evidence", []) or []:
            if not valid_ref(_first(evidence, "document_ref", "document"), NodeType.DOCUMENT.value):
                return "Evidence document_ref must reference a valid Document"
            if not valid_ref(_first(evidence, "source_ref", "source"), NodeType.SOURCE.value):
                return "Evidence source_ref must reference a valid Source"
            claim_ref = _first(evidence, "claim_ref", "normalized_claim_ref")
            if claim_ref and not valid_ref(claim_ref, NodeType.CLAIM.value):
                return "Evidence claim_ref must reference a valid Claim"
            legacy_ref = _first(evidence, "supports_or_contradicts", "supports_claim")
            if (
                legacy_ref
                and legacy_ref not in {"supports", "contradicts", "qualifies", "support", "contradict", "qualify"}
                and not (
                    valid_ref(legacy_ref, NodeType.STATEMENT.value)
                    or valid_ref(legacy_ref, NodeType.CLAIM.value)
                )
            ):
                return "Evidence legacy support reference must reference a valid Statement or Claim"
        for conflict in evidence_package.get("conflicts", []) or []:
            refs = conflict.get("evidence_refs") or conflict.get("related_claims") or []
            if any(not valid_ref(ref, NodeType.EVIDENCE.value) for ref in refs):
                return "Conflict evidence_refs must all reference valid Evidence"
        return None

    def _submit_search_result_unlocked(self, search_run_id: str, query_id: str, evidence_package: dict) -> dict:
        """Write a structured evidence package into the Research Graph.

        Accepts the evidence package produced by the Searcher (sources,
        documents, statements, evidence, conflicts), creates the corresponding
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
        statement_ids: list[str] = []
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
                "written": {"sources": 0, "documents": 0, "statements": 0, "claims": 0, "evidence": 0, "conflicts": 0},
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
                "written": {"sources": 0, "documents": 0, "statements": 0, "claims": 0, "evidence": 0, "conflicts": 0},
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
                "written": {"sources": 0, "documents": 0, "statements": 0, "claims": 0, "evidence": 0, "conflicts": 0},
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

        statement_items = list(evidence_package.get("statements", []) or [])
        # Backward compatibility: old analyzers emitted document-bound
        # ``claims``. They are statements here; canonical Claim nodes are
        # created later by normalize_claims().
        statement_items.extend(evidence_package.get("claims", []) or [])
        for statement_item in statement_items:
            statement_text = _first(statement_item, "statement", "text_zh", "text")
            if not statement_text:
                continue
            doc_ref = _first(statement_item, "document_ref", "document")
            statement_id = graph_tools.create_statement(
                text=statement_text,
                document_id=resolve(doc_ref),
                source_id=resolve(_first(statement_item, "source_ref", "source")),
                qualifiers=statement_item.get("qualifiers") if isinstance(statement_item.get("qualifiers"), list) else [],
                limitations=statement_item.get("limitations") if isinstance(statement_item.get("limitations"), list) else [],
                confidence=_first(statement_item, "confidence"),
                locator=_first(statement_item, "locator", "span", "quote_locator"),
            )
            if statement_item.get("local_ref"):
                ref_map[statement_item["local_ref"]] = statement_id
            statement_ids.append(statement_id)
            produced_ids.append(statement_id)

        # Process evidence. Claim stance is resolved after normalization.
        for evidence_item in evidence_package.get("evidence", []) or []:
            evidence_text = _first(evidence_item, "statement", "evidence_text", "text_zh", "text")
            if not evidence_text:
                continue
            doc_ref = _first(evidence_item, "document_ref", "document")
            sources_ref = evidence_item.get("sources") or evidence_item.get("document_refs")
            if not doc_ref and isinstance(sources_ref, list) and sources_ref:
                doc_ref = sources_ref[0]
            
            legacy_ref = _first(evidence_item, "supports_or_contradicts", "supports_claim")
            statement_ref = None
            claim_ref = resolve(_first(evidence_item, "claim_ref", "normalized_claim_ref"))
            if legacy_ref and legacy_ref not in {"supports", "contradicts", "qualifies", "support", "contradict", "qualify"}:
                resolved_legacy = resolve(legacy_ref)
                legacy_node = graph_tools.get_node(resolved_legacy) if resolved_legacy else {}
                if legacy_node.get("type") == NodeType.STATEMENT.value:
                    statement_ref = resolved_legacy
                elif legacy_node.get("type") == NodeType.CLAIM.value:
                    claim_ref = resolved_legacy
            
            evidence_id = graph_tools.create_evidence(
                claim=evidence_text,
                document_id=resolve(doc_ref),
                source_id=resolve(_first(evidence_item, "source_ref", "source")),
                evidence_type=_first(evidence_item, "evidence_type", "type"),
                confidence=_first(evidence_item, "confidence"),
                qualifiers=evidence_item.get("qualifiers") if isinstance(evidence_item.get("qualifiers"), list) else [],
                limitations=evidence_item.get("limitations") if isinstance(evidence_item.get("limitations"), list) else [],
                locator=_first(evidence_item, "locator", "span", "quote_locator"),
                statement_ref=statement_ref,
                claim_ref=claim_ref,
                stance=_first(evidence_item, "stance") or (
                    legacy_ref if legacy_ref in {"supports", "contradicts", "qualifies"} else None
                ),
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
        statement_count = len(statement_ids)
        succeeded = source_count > 0 and (evidence_count > 0 or statement_count > 0)
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
                "statements": len(statement_ids),
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
        """Export slot-driven report metadata; evidence is fetched section by section."""
        goal = graph_tools.get_node(goal_id) if goal_id else self._goal_node()
        if not goal:
            return {}
        task_contract = self._task_contract_snapshot(goal.get("id"))
        from tools import report_tools

        contract = task_contract.get("task_contract") or {}
        frontiers = [
            {
                "id": frontier.get("id"),
                "frontier_type": frontier.get("frontier_type"),
                "description": frontier.get("description"),
                "status": frontier.get("status"),
                "target_slot_keys": frontier.get("target_slot_keys") or [],
            }
            for frontier in graph_tools.get_frontiers()
            if frontier.get("status") not in {"resolved", "blocked"}
        ]
        conflicts = [
            {
                "id": conflict.get("id"),
                "description": conflict.get("description"),
                "conflict_type": conflict.get("conflict_type"),
                "resolution_status": conflict.get("resolution_status"),
            }
            for conflict in graph_tools.search_nodes("conflict", {})
            if conflict.get("resolution_status") != "resolved"
        ]
        return {
            "goal": {
                key: goal.get(key)
                for key in (
                    "id", "request", "research_goal", "language", "time_window",
                    "region_scope", "source_preferences",
                )
            } if goal else {},
            "task_contract": contract,
            "required_sections": contract.get("required_sections") or [],
            "required_tables": contract.get("required_tables") or [],
            "slot_registry": task_contract.get("slot_registry") or [],
            "disclosed_frontiers": frontiers,
            "disclosed_conflicts": conflicts or report_tools.get_disclosed_conflicts(),
            "reference_registry": report_tools.build_reference_registry(),
            "writing_hints": {
                "default_structure": "section -> slot -> evidence bundle",
                "prefer_paragraph_prose": True,
                "avoid_references_as_section_title": True,
                "task_style": contract.get("deliverable_type") or goal.get("deliverable_type") or "research_report",
            },
        }

    def get_report_evidence(self, query_id: str, offset: int = 0, limit: int = 20) -> dict:
        """Return a compact, citation-ready page of one Query's evidence."""
        try:
            resolved = self._resolve_query_id(query_id)
        except AmbiguousQueryReference as exc:
            return {"error": str(exc)}
        if resolved is None:
            return {"error": f"Unknown query reference: {query_id!r}"}
        from tools import report_tools

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
        """Backward-compatible wrapper around task-contract + seed planning."""
        planned = self._plan_task_contract(user_request)
        seed = self._plan_seed_queries(planned)
        return {**planned, "initial_queries": seed.get("seed_queries") or []}

    def _plan_followup_queries(
        self,
        research_goal: str,
        parent_text: str,
        sibling_texts: list,
        gaps: Any,
        reason: str,
        max_new: int = 1,
    ) -> list:
        """Backward-compatible wrapper that routes to the horizontal planner."""
        parsed = self._plan_horizontal_queries(
            research_goal=research_goal,
            attach_parent={"text": parent_text},
            current_query={"text": parent_text},
            siblings=[{"text": text} for text in sibling_texts or []],
            frontiers=gaps if isinstance(gaps, list) else [],
            max_new=max_new,
        )
        queries = []
        for raw in parsed.get("queries") or []:
            text = str(raw.get("text") or "").strip()
            if not text or any(token in text for token in _CROSS_REF_TOKENS):
                continue
            queries.append({
                "text": text,
                "importance": raw.get("importance"),
                "acceptance_criteria": raw.get("acceptance_criteria") or [],
                "objective_keys": raw.get("objective_keys") or [],
            })
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
