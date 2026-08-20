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
from urllib.parse import urlsplit

import config
import prompts.memory_manager_prompts as mm_prompts
from memory.graph import EdgeType, NodeType
from tools import graph_tools

logger = logging.getLogger(__name__)
AmbiguousQueryReference = graph_tools.AmbiguousQueryReference


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
_CROSS_REF_TOKENS = (
    "调研", "梳理", "整理", "分析", "上述", "前述", "该", "这些", "上文", "前文",
    "the above", "aforementioned",
)
_QUERY_INSTRUCTION_RE = re.compile(
    r"^\s*(?:write|provide|ensure|explain|describe|analy[sz]e|research)\b",
    re.IGNORECASE,
)
_REPORT_QUERY_RE = re.compile(
    r"\b(?:wikipedia-style article|references section|all factual claims|citation format)\b",
    re.IGNORECASE,
)
_QUERY_MAX_CHARS = 400
_ABSOLUTE_INITIAL_QUERY_CAP = 8
_GAP_EVIDENCE_TYPES = {
    NodeType.SOURCE.value,
    NodeType.STATEMENT.value,
    NodeType.CLAIM.value,
    NodeType.EVIDENCE.value,
    NodeType.CONFLICT.value,
}

OBJECTIVE_COVERAGE_THRESHOLD = 0.60
OBJECTIVE_CONFIDENCE_THRESHOLD = 0.50
EXPANSION_UTILITY_THRESHOLD = 0.05
EXPANSION_UTILITY_THRESHOLD_REDUNDANT = 0.03
MIN_SUCCESSFUL_ROUNDS_BEFORE_BEST_EFFORT = 4
LOW_REALIZED_GAIN_THRESHOLD = 0.05
LOW_GAIN_WINDOW = 2
# When remaining search rounds drop to this threshold or below, the system
# enters "completion mode": no new child queries are created, and queries
# needing expansion are deferred so the remaining budget is spent finishing
# in-flight work instead of starting new branches.
_BUDGET_RESERVE_FOR_COMPLETION = 5
_ACTIVE_QUERY_WORK_STATUSES = {
    "searching",
    "assessing",
    "needs_expansion",
    "waiting_children",
}
_BLOCKING_GAP_WORK_STATUSES = {"selected", "assigned"}
_GAP_CATEGORIES = {
    "missing_core_evidence",
    "fatal_conflict",
    "enrichment",
    "additional_example",
    "verification",
    "detail",
}

# Dimension-coverage gate: prevent premature convergence when evidence/sources/
# expanded queries are too thin. Thresholds calibrated from V25 baseline
# (3 sources, 14 queries, 33 evidence → 21.65% coverage).
_MIN_EVIDENCE_FOR_CONVERGENCE = 15
_MIN_SOURCES_FOR_CONVERGENCE = 5
_MIN_EXPANDED_QUERIES_FOR_CONVERGENCE = 3
# Depth-breadth balance: gradually discount the marginal utility of gaps on
# deep query chains so the portfolio prefers breadth over excessive vertical
# drilling. Not a hard cap — a gap with high raw utility (e.g. fatal conflict)
# can still be selected at depth 6; it just needs ~2x the raw utility of a
# shallow gap to clear the same threshold.
_DEPTH_FREE_TIER = 3          # levels 1-3 incur no penalty (root + 2 expansions)
_DEPTH_PENALTY_FACTOR = 0.3   # each level beyond free tier: discount = 1/(1+0.3*n)


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
    """Return the planner-authored fields from a query item.

    Legacy planner output may still contain ``importance``; it is intentionally
    ignored because Query priority is derived by the runtime.

    Args:
        item: One element of a planner's query list.

    Returns:
        A ``(text, acceptance_criteria, objective_keys)`` tuple.
    """
    if isinstance(item, dict):
        criteria = item.get("acceptance_criteria")
        objective_keys = item.get("objective_keys")
        return (
            item.get("text"),
            criteria if isinstance(criteria, list) else [],
            objective_keys if isinstance(objective_keys, list) else [],
        )
    return item, [], []


def _initial_query_limit(max_search_rounds: int) -> int:
    """Return a budget-aware hard limit for discovery Queries."""
    if max_search_rounds <= 0:
        return _ABSOLUTE_INITIAL_QUERY_CAP
    return max(1, min(_ABSOLUTE_INITIAL_QUERY_CAP, (max_search_rounds + 1) // 2))


def _gap_key(description: str) -> str:
    """Return a stable normalized fingerprint for one atomic knowledge gap."""
    normalized = " ".join((description or "").lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]


def _string_list(value: Any) -> list[str]:
    """按输入顺序返回非空且不重复的字符串."""
    if not isinstance(value, list):
        return []
    strings = [str(item).strip() for item in value if item is not None]
    return list(dict.fromkeys(item for item in strings if item))


def _normalize_domain(value: str) -> Optional[str]:
    """规范化域名或 ``-site:`` 操作数."""
    text = str(value or "").strip().lower()
    if text.startswith("-site:"):
        text = text[6:]
    if "://" in text:
        text = urlsplit(text).hostname or ""
    return text.strip("./") or None


def _normalize_query_text(text: str) -> str:
    """生成用于精确去重的稳定检索词."""
    return " ".join((text or "").lower().split())


def _query_text_issue(text: Any) -> Optional[str]:
    """检查候选 Query 是否为可直接提交的网页检索词."""
    if not isinstance(text, str) or not text.strip():
        return "query text is empty"
    compact = " ".join(text.split())
    if len(compact) > _QUERY_MAX_CHARS:
        return f"query text exceeds {_QUERY_MAX_CHARS} characters"
    if any(token.lower() in compact.lower() for token in _CROSS_REF_TOKENS):
        return "query text contains an agent instruction or contextual reference"
    if _QUERY_INSTRUCTION_RE.search(compact) or _REPORT_QUERY_RE.search(compact):
        return "query text is a report task rather than a search phrase"
    return None


class MemoryManager:
    """LLM-powered manager of the Research Graph."""

    def __init__(
        self,
        model: Optional[Any] = None,
        cache_dir: Optional[str] = None,
        user_request: Optional[str] = None,
    ):
        """Initialize the manager.

        Args:
            model: A chat model; defaults to ``config.build_model()``.
            cache_dir: Graph storage directory passed through to the toolkit.
            user_request: The verbatim request captured at the run boundary.
        """
        self.cache_dir = cache_dir
        self.model = model if model is not None else config.build_model()
        self.user_request = user_request
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
    def init_research(self) -> dict:
        """Parse the user request and seed the Research Graph.

        Creates a ``user_request`` node and a set of parallel initial ``query``
        nodes under it.

        Returns:
            dict with ``goal_id``, ``research_goal``, ``language`` and the list
            of created ``queries`` (each ``{id, text}``).
        """
        from tools import middleware, research_state

        user_request = self.user_request
        if not isinstance(user_request, str) or not user_request:
            return {"error": "The run context has no canonical User Request"}

        with self._state_lock:
            existing_goals = graph_tools.search_nodes("user_request", {})
            if existing_goals:
                return {
                    "error": "Research is already initialized in this run context",
                    "existing_goal_id": existing_goals[0]["id"],
                }

            max_search_rounds = middleware.get_max_search_rounds()
            initial_query_limit = _initial_query_limit(max_search_rounds)
            parsed = self._plan_initial_queries(user_request, initial_query_limit)
            excluded_domains = list(dict.fromkeys(filter(None, (
                _normalize_domain(item) for item in _string_list(parsed.get("excluded_domains"))
            ))))
            initial_queries = self._select_initial_queries(
                parsed.get("initial_queries"),
                limit=initial_query_limit,
            )
            if not initial_queries:
                parsed = self._plan_initial_queries(
                    user_request,
                    initial_query_limit,
                    correction=(
                        "The previous response contained no valid literal web-search query. "
                        "Return the full JSON object again with a bounded set of short, concrete, "
                        "self-contained search phrases and no report-writing instructions."
                    ),
                )
                excluded_domains = list(dict.fromkeys(filter(None, (
                    _normalize_domain(item) for item in _string_list(parsed.get("excluded_domains"))
                ))))
                initial_queries = self._select_initial_queries(
                    parsed.get("initial_queries"),
                    limit=initial_query_limit,
                )
            if not initial_queries:
                return {
                    "error": "Initial query planner returned no valid literal web-search query after one retry",
                }

            goal_id = graph_tools.create_user_request(
                request=user_request,
                research_goal=parsed.get("research_goal"),
                language=parsed.get("language"),
                time_window=parsed.get("time_window"),
                region_scope=parsed.get("region_scope"),
                source_preferences=_string_list(parsed.get("source_preferences")),
                excluded_domains=excluded_domains,
                excluded_urls=_string_list(parsed.get("excluded_urls")),
                research_state="INITIALIZING",
                max_search_rounds=max_search_rounds,
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
                state_contract_version=4,
                report_completeness_score=0.0,
            )

        objectives = self._create_objectives(goal_id, parsed.get("objectives"), user_request)
        queries = []
        objective_by_key = {o["objective_key"]: o for o in objectives}
        for item in initial_queries:
            text, criteria, objective_keys = _query_spec(item)
            if not isinstance(text, str) or not text.strip():
                continue
            query_id = graph_tools.create_query_child(
                parent_id=goal_id,
                text=text,
                importance="core",
                acceptance_criteria=criteria,
                objective_keys=[key for key in objective_keys if key in objective_by_key],
                required_for_parent=False,
                query_role="discovery",
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
    def _select_initial_queries(
        candidates: Any,
        limit: int,
    ) -> list[dict]:
        """Keep a bounded set of distinct valid discovery Queries."""
        if not isinstance(candidates, list):
            return []
        limit = max(1, int(limit))
        selected: list[dict] = []
        seen: set[str] = set()
        for item in candidates or []:
            if not isinstance(item, (dict, str)):
                continue
            text, criteria, objective_keys = _query_spec(item)
            if _query_text_issue(text):
                continue
            key = _normalize_query_text(text)
            if key in seen:
                continue
            seen.add(key)
            selected.append({
                "text": text,
                "acceptance_criteria": criteria,
                "objective_keys": objective_keys,
            })
            if len(selected) >= limit:
                break
        return selected

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

        gaps = graph_tools.search_nodes("analysis", {"analysis_type": "gap"})
        selected_by_owner: dict[str, list[str]] = {}
        for gap in gaps:
            owner_id = gap.get("expansion_parent_id")
            if not owner_id:
                continue
            status = gap.get("status")
            if status == "selected":
                selected_by_owner.setdefault(owner_id, []).append(gap["id"])
            elif status == "candidate":
                owner_node = graph_tools.get_node(owner_id)
                if owner_node.get("status") == "needs_expansion":
                    selected_by_owner.setdefault(owner_id, []).append(gap["id"])
        # Completion mode: when remaining budget is at or below the reserve
        # threshold, stop creating new child queries so the remaining rounds
        # are spent finishing in-flight work.
        _remaining_for_mode = research_state.remaining_budget()
        in_completion_mode = (
            _remaining_for_mode is not None
            and _remaining_for_mode <= _BUDGET_RESERVE_FOR_COMPLETION
        )
        if not in_completion_mode:
            for owner_id, gap_ids in selected_by_owner.items():
                owner = graph_tools.get_node(owner_id)
                if owner.get("type") not in {NodeType.QUERY.value, NodeType.USER_REQUEST.value}:
                    continue
                is_query = owner.get("type") == NodeType.QUERY.value
                actions.append({
                    "action": "expand_gaps",
                    "parent_id": owner_id,
                    "query_id": owner_id if is_query else None,
                    "query_handle": owner.get("handle"),
                    "goal_id": None if is_query else owner_id,
                    "priority": owner.get("priority", 1.0 if not is_query else 0.0),
                    "required_for_parent": owner.get("required_for_parent", False),
                    "required_path": research_state.is_required_path(owner_id) if is_query else False,
                    "semantic_importance": owner.get("sem", 1.0 if not is_query else 0.0),
                    "gap_ids": gap_ids,
                    "reason": "globally selected gaps await a grounded search query",
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

        # 优先完成已有查询（dispatch_searcher）再创建新查询（expand_gaps），
        # 实现类似广度优先的子查询创建：各分支查询相对均匀推进，避免预算
        # 耗尽时仍有大量活跃查询未完成。
        action_rank = {
            "assess_query": 0,
            "evaluate_research_portfolio": 1,
            "dispatch_searcher": 2,
            "expand_gaps": 3,
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
        dispatch_pending = any(action["action"] == "dispatch_searcher" for action in actions)
        must = [
            objective
            for objective in self.get_research_objectives(goal.get("id"))
            if objective.get("requirement") == "must"
        ]
        objectives_ready = bool(must) and all(
            objective.get("status") == "satisfied" for objective in must
        )
        portfolio_current = int(goal.get("evaluated_portfolio_revision") or 0) >= int(
            goal.get("portfolio_revision") or 0
        )
        has_active_queries = any(
            query.get("status") in _ACTIVE_QUERY_WORK_STATUSES
            for query in queries
        )
        has_blocking_gap_work = any(
            gap.get("status") in _BLOCKING_GAP_WORK_STATUSES for gap in gaps
        )
        if (
            remaining > 0
            and goal.get("scope_mode") == "exhaustive"
            and portfolio_current
            and objectives_ready
            and dispatch_pending
            and not has_active_queries
            and not has_blocking_gap_work
            and all(action["action"] == "dispatch_searcher" for action in actions)
        ):
            return [{
                "action": "assess_convergence",
                "query_id": None,
                "goal_id": goal.get("id"),
                "priority": 1.0,
                "required_for_parent": False,
                "required_path": False,
                "semantic_importance": 1.0,
                "gap_ids": [],
                "reason": "must Objectives are satisfied; assess convergence before optional pending work",
            }]
        if remaining == 0 and dispatch_pending:
            if must and all(objective.get("status") == "satisfied" for objective in must):
                return [{
                    "action": "assess_convergence",
                    "query_id": None,
                    "goal_id": goal.get("id"),
                    "priority": 1.0,
                    "required_for_parent": False,
                    "required_path": False,
                    "semantic_importance": 1.0,
                    "gap_ids": [],
                    "reason": "must Objectives are satisfied; defer optional pending work before reporting",
                }]
            research_state.mark_budget_exhausted()
            return []
        return actions[:limit]

    def _recover_unactionable_research(self, goal: dict, queries: list[dict]) -> Optional[dict]:
        """Create one Objective-grounded recovery Gap or close an exhausted Objective."""
        from tools import research_state

        if int(goal.get("evaluated_portfolio_revision") or 0) < int(goal.get("portfolio_revision") or 0):
            return None
        open_must = [
            objective
            for objective in self.get_research_objectives(goal.get("id"))
            if objective.get("requirement") == "must"
            and objective.get("status") not in {"satisfied", "blocked"}
        ]
        if not open_must:
            return None
        if research_state.remaining_budget(goal.get("id")) == 0:
            research_state.mark_budget_exhausted(goal.get("id"))
            return None

        for objective in open_must:
            key = objective.get("objective_key")
            prior = [
                graph_tools.get_node(gap_id)
                for gap_id in self._query_gap_ids(goal["id"])
                if graph_tools.get_node(gap_id).get("recovery_objective_key") == key
            ]
            if prior:
                recovery_queries = [
                    graph_tools.get_node(edge.get("source"))
                    for gap in prior
                    for edge in graph_tools.get_node_edges(gap["id"], direction="in")
                    if str(edge.get("type") or "").lower() == "addresses_gap"
                    and graph_tools.get_node(edge.get("source")).get("type") == NodeType.QUERY.value
                ]
                recovery_completed = any(
                    query.get("status") in {"sufficient", "blocked", "failed"}
                    for query in recovery_queries
                )
                if not recovery_completed:
                    if any(
                        query.get("status") in {"pending", "searching", "assessing", "needs_expansion", "waiting_children"}
                        for query in recovery_queries
                    ):
                        return None
                    graph_tools.upsert_node(NodeType.ANALYSIS, {
                        "status": "candidate",
                        "resolution_reason": None,
                    }, prior[0]["id"])
                    self._bump_portfolio_revision()
                    return {
                        "action": "evaluate_research_portfolio",
                        "query_id": None,
                        "goal_id": goal.get("id"),
                        "priority": 1.0,
                        "required_for_parent": False,
                        "required_path": False,
                        "semantic_importance": 1.0,
                        "gap_ids": [],
                        "reason": f"reopened incomplete targeted recovery for Objective {key}",
                    }
                if goal.get("scope_mode") == "bounded":
                    graph_tools.upsert_node(NodeType.ANALYSIS, {
                        "status": "blocked",
                        "resolution_reason": "targeted recovery query did not satisfy the objective",
                    }, objective["id"])
                    continue
                research_state.update_goal({
                    "research_state": research_state.FAILED,
                    "last_error": f"Exhaustive objective remained open after targeted recovery: {key}",
                }, goal.get("id"))
                return None

            description = f"Missing report evidence for Objective {key}: {objective.get('description') or objective.get('text') or ''}"
            gap_id = graph_tools.create_analysis(
                text=description,
                query_id=goal["id"],
                analysis_type="gap",
                description=description,
                gap_key=_gap_key(description),
                importance="core",
                required_for_parent=False,
                status="candidate",
                gap_category="missing_core_evidence",
                objective_keys=[key],
                search_subject_key=f"objective-{key}",
                decision_impact=float(objective.get("weight") or 1.0),
                confidence_gain=1.0,
                estimated_search_rounds=1,
                acceptance_criteria=objective.get("acceptance_criteria") or [],
                expansion_mode="horizontal",
                expansion_parent_id=goal["id"],
                trigger_type="delivery_requirement",
                trigger_refs=[objective["id"]],
                recovery_objective_key=key,
            )
            graph_tools.add_edge(gap_id, objective["id"], EdgeType.IMPACTS_OBJECTIVE)
            self._bump_portfolio_revision()
            return {
                "action": "evaluate_research_portfolio",
                "query_id": None,
                "goal_id": goal.get("id"),
                "priority": 1.0,
                "required_for_parent": False,
                "required_path": False,
                "semantic_importance": 1.0,
                "gap_ids": [],
                "reason": f"created a delivery-requirement Gap for uncovered Objective {key}",
            }
        return None

    def _query_gap_ids(self, query_id: str, statuses: Optional[set[str]] = None) -> list[str]:
        """Return gaps owned by a Query/UserRequest, optionally filtered by status."""
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

    def _gap_owner_id(self, gap_id: str) -> Optional[str]:
        """Return the Query or UserRequest that originally identified a Gap."""
        for edge in graph_tools.get_node_edges(gap_id, direction="in"):
            if str(edge.get("type", "")).lower() != "has_gap":
                continue
            owner = graph_tools.get_node(edge.get("source"))
            if owner.get("type") in {NodeType.QUERY.value, NodeType.USER_REQUEST.value}:
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
                    if statement["id"] in (
                        item.get("statement_refs")
                        or ([item.get("statement_ref")] if item.get("statement_ref") else [])
                    )
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

        # Build source credibility lookup
        source_credibility = {}
        for node in nodes:
            if node.get("type") == NodeType.SOURCE.value:
                source_credibility[node.get("id")] = node.get("credibility_score", 0.5)

        def _get_source_credibility(source_id: Optional[str]) -> float:
            if source_id and source_id in source_credibility:
                return source_credibility[source_id]
            return 0.5  # Default moderate credibility

        compact = {
            "statements": [
                {
                    "id": item.get("id"),
                    "text": item.get("text") or item.get("statement"),
                    "document_id": item.get("document_id"),
                    "source_id": item.get("source_id"),
                    "source_credibility": _get_source_credibility(item.get("source_id")),
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
                    "source_credibility": _get_source_credibility(item.get("source_id")),
                    "statement_ref": item.get("statement_ref"),
                    "statement_refs": item.get("statement_refs") or [],
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

        normalization = self.normalize_claims(resolved)
        evaluation = graph_tools.get_query_evaluation_subgraph(resolved)
        goal = research_state.get_goal()
        objectives = self.get_research_objectives(goal.get("id"))
        objective_by_id = {item["id"]: item for item in objectives}
        objective_by_key = {item["objective_key"]: item for item in objectives}
        request_context = {
            key: goal.get(key)
            for key in (
                "request", "research_goal", "language", "time_window", "region_scope",
                "source_preferences", "excluded_domains", "excluded_urls", "scope_mode",
            )
        }
        prompt = (
            mm_prompts.assess_query.replace("{query}", json.dumps({
                "text": query.get("text"),
                "query_role": query.get("query_role") or "research",
                "objective_keys": query.get("objective_keys") or [],
                "acceptance_criteria": query.get("acceptance_criteria") or [],
                "normalized_claims": normalization,
            }, ensure_ascii=False))
            .replace("{request_context}", json.dumps(request_context, ensure_ascii=False))
            .replace("{objectives}", json.dumps(objectives, ensure_ascii=False))
            .replace("{existing_queries}", json.dumps([
                {"id": item.get("id"), "text": item.get("text"), "status": item.get("status")}
                for item in graph_tools.search_nodes("query", {})
            ], ensure_ascii=False))
            .replace("{evaluation_subgraph}", json.dumps(evaluation, ensure_ascii=False))
        )
        verdict = self._invoke_json(prompt)
        acceptance_criteria = [
            str(item).strip()
            for item in query.get("acceptance_criteria") or []
            if str(item).strip()
        ]
        if not verdict or (acceptance_criteria and not verdict.get("criteria")):
            verdict = self._invoke_json(
                prompt
                + "\n\nCorrection: return the complete valid JSON response. Include one "
                "criteria result for every acceptance criterion and copy its text exactly."
            )
        criterion_results = self._validate_criterion_results(
            acceptance_criteria,
            verdict.get("criteria"),
            evaluation,
        )
        criteria_satisfied = all(
            item["status"] == "satisfied" for item in criterion_results
        )
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
        evaluation_nodes = {
            item.get("id"): item
            for item in evaluation.get("nodes", [])
            if item.get("id")
        }
        for raw in raw_gaps:
            if not isinstance(raw, dict):
                continue
            spec = raw
            description = str(spec.get("description") or "").strip()
            if not description:
                continue
            expansion_mode = spec.get("expansion_mode")
            trigger_type = spec.get("trigger_type")
            trigger_refs = _string_list(spec.get("trigger_refs"))
            if expansion_mode not in {"horizontal", "vertical"}:
                continue
            if trigger_type == "graph_evidence":
                if not trigger_refs or any(
                    evaluation_nodes.get(ref, {}).get("type") not in _GAP_EVIDENCE_TYPES
                    for ref in trigger_refs
                ):
                    continue
            elif trigger_type == "delivery_requirement":
                if not trigger_refs or any(
                    ref not in objective_by_id
                    or objective_by_id[ref].get("status") in {"satisfied", "blocked"}
                    for ref in trigger_refs
                ):
                    continue
            else:
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
            objective_keys = [key for key in objective_keys if key in objective_by_key]
            if trigger_type == "delivery_requirement":
                objective_keys = list(dict.fromkeys([
                    *objective_keys,
                    *(objective_by_id[ref]["objective_key"] for ref in trigger_refs),
                ]))
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
                expansion_mode=expansion_mode,
                expansion_parent_id=resolved,
                trigger_type=trigger_type,
                trigger_refs=trigger_refs,
            )
            existing[key] = gap_id
            created_gaps.append(gap_id)
            for objective_key in objective_keys:
                graph_tools.add_edge(gap_id, objective_by_key[objective_key]["id"], EdgeType.IMPACTS_OBJECTIVE)

        recommendation = verdict.get("recommendation")
        open_gap_ids = self._query_gap_ids(resolved, {"candidate", "selected"})
        if (
            recommendation == "sufficient"
            and score >= 0.7
            and criteria_satisfied
            and not open_gap_ids
        ):
            new_status = "sufficient"
        elif open_gap_ids:
            # Completion mode: if remaining budget is at or below the reserve
            # threshold, defer expansion instead of creating new child queries
            # so the remaining rounds are spent finishing in-flight work.
            from tools import research_state
            remaining_budget = research_state.remaining_budget()
            if (
                remaining_budget is not None
                and remaining_budget <= _BUDGET_RESERVE_FOR_COMPLETION
            ):
                new_status = "deferred"
            else:
                new_status = "needs_expansion"
        else:
            new_status = "blocked"

        graph_tools.transition_query(
            resolved,
            new_status,
            sufficiency_score=score,
            criterion_results=criterion_results,
            covered=verdict.get("covered") or [],
            assessment_reason=verdict.get("reason") or "",
        )
        if new_status in {"sufficient", "blocked", "deferred"}:
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
            "criterion_results": criterion_results,
            "status": new_status,
            "created_gaps": created_gaps,
            "next_action": "evaluate_research_portfolio" if new_status == "needs_expansion" else "get_next_actions",
        }

    @staticmethod
    def _validate_criterion_results(
        criteria: list[str],
        raw_results: Any,
        evaluation: dict,
    ) -> list[dict]:
        """Keep only direct, Query-owned, URL-backed support for each criterion."""
        nodes = {
            item.get("id"): item
            for item in evaluation.get("nodes", [])
            if item.get("id")
        }
        edges = evaluation.get("edges", [])
        source_ids = {
            node_id for node_id, node in nodes.items()
            if node.get("type") == NodeType.SOURCE.value and node.get("url")
        }

        def is_unsupported_nonmention(item_id: str) -> bool:
            text = str(
                nodes.get(item_id, {}).get("canonical_text")
                or nodes.get(item_id, {}).get("statement")
                or nodes.get(item_id, {}).get("claim")
                or nodes.get(item_id, {}).get("text")
                or ""
            ).casefold()
            explicit_absence = (
                "未公开", "未知", "无法获得", "不可用", "不存在",
                "not public", "not disclosed", "unknown", "unavailable",
                "does not exist", "did not exist",
            )
            mere_nonmention = (
                "未提及", "没有提及", "未说明", "没有说明",
                "does not mention", "did not mention", "not mentioned",
            )
            return any(term in text for term in mere_nonmention) and not any(
                term in text for term in explicit_absence
            )

        def has_source(item_id: str) -> bool:
            frontier = {item_id}
            visited = set(frontier)
            for _ in range(4):
                parents = {
                    edge.get("source")
                    for edge in edges
                    if edge.get("target") in frontier and edge.get("source") in nodes
                }
                if parents & source_ids:
                    return True
                frontier = parents - visited
                visited.update(frontier)
                if not frontier:
                    break
            return False

        indexed = {
            str(item.get("criterion") or "").strip(): item
            for item in raw_results or []
            if isinstance(item, dict) and str(item.get("criterion") or "").strip()
        }
        results = []
        for criterion in criteria:
            raw = indexed.get(criterion, {})
            refs = [
                ref
                for ref in dict.fromkeys(_string_list(raw.get("supporting_refs")))
                if nodes.get(ref, {}).get("type") in {
                    NodeType.CLAIM.value,
                    NodeType.EVIDENCE.value,
                }
                and has_source(ref)
                and not is_unsupported_nonmention(ref)
            ]
            satisfied = raw.get("status") == "satisfied" and bool(refs)
            results.append({
                "criterion": criterion,
                "status": "satisfied" if satisfied else "unmet",
                "supporting_refs": refs if satisfied else [],
                "reason": str(raw.get("reason") or "").strip(),
            })
        return results

    def _query_depth(self, query_id: str) -> int:
        """Return the depth of a query in the query tree (root initial queries = 1).

        Counts Query nodes along the ancestor chain (including ``query_id``
        itself) by following inbound ``HAS_QUERY`` / ``PARENT_OF`` edges until
        the ``user_request`` goal is reached. Used for depth-breadth balancing
        so the portfolio prefers breadth expansion on shallower parents.
        """
        depth = 0
        current = query_id
        seen: set[str] = set()
        while current and current not in seen:
            seen.add(current)
            node = graph_tools.get_node(current)
            if not node or node.get("type") != NodeType.QUERY.value:
                break
            depth += 1
            current = graph_tools.get_query_parent(current)
        return depth

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

    @staticmethod
    def _portfolio_query_view(query: dict) -> dict:
        """把 Query 投影成由证据支撑的紧凑组合评估输入."""
        evaluation = graph_tools.get_query_evaluation_subgraph(query["id"])
        nodes = evaluation.get("nodes", [])
        return {
            "id": query.get("id"),
            "handle": query.get("handle"),
            "text": query.get("text"),
            "objective_keys": query.get("objective_keys") or [],
            "status": query.get("status"),
            "sufficiency_score": query.get("sufficiency_score"),
            "criterion_results": query.get("criterion_results") or [],
            "covered": query.get("covered") or [],
            "assessment_reason": query.get("assessment_reason") or "",
            "claims": [
                {
                    "id": node.get("id"),
                    "text": node.get("canonical_text") or node.get("statement"),
                    "confidence": node.get("confidence"),
                    "objective_keys": node.get("objective_keys") or [],
                }
                for node in nodes if node.get("type") == NodeType.CLAIM.value
            ],
            "evidence": [
                {
                    "id": node.get("id"),
                    "text": node.get("claim") or node.get("text"),
                    "confidence": node.get("confidence"),
                }
                for node in nodes if node.get("type") == NodeType.EVIDENCE.value
            ],
            "conflicts": [
                {
                    "id": node.get("id"),
                    "description": node.get("description"),
                    "resolution_status": node.get("resolution_status"),
                }
                for node in nodes if node.get("type") == NodeType.CONFLICT.value
            ],
            "sources": [
                {
                    "id": node.get("id"),
                    "url": node.get("url"),
                    "published_at": node.get("published_at") or node.get("publication_date"),
                }
                for node in nodes if node.get("type") == NodeType.SOURCE.value
            ],
        }

    @staticmethod
    def _linked_criteria_complete(objective_key: str, queries: list[dict]) -> bool:
        """Return whether every Query linked to an Objective passed all criteria."""
        linked_queries = [
            query for query in queries
            if objective_key in (query.get("objective_keys") or [])
        ]

        def complete(query: dict) -> bool:
            criteria = query.get("acceptance_criteria") or []
            results = query.get("criterion_results") or []
            if criteria and len(results) != len(criteria):
                return False
            return all(result.get("status") == "satisfied" for result in results)

        return bool(linked_queries) and all(complete(query) for query in linked_queries)

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
                self._portfolio_query_view(query) for query in queries
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
            acceptance_criteria = [
                criterion
                for criterion in (objective.get("acceptance_criteria") or [])
                if isinstance(criterion, str)
            ]
            raw_unmet = item.get("unmet_acceptance_criteria")
            unmet_acceptance_criteria = (
                [criterion for criterion in acceptance_criteria if criterion in raw_unmet]
                if isinstance(raw_unmet, list)
                else list(acceptance_criteria)
            )
            linked_criteria_complete = self._linked_criteria_complete(key, queries)
            meets = (
                coverage >= OBJECTIVE_COVERAGE_THRESHOLD
                and confidence >= OBJECTIVE_CONFIDENCE_THRESHOLD
                and not unmet_acceptance_criteria
                and linked_criteria_complete
            )
            successful_rounds = int(goal.get("successful_search_rounds") or 0)
            last_evaluated_rounds = int(objective.get("last_evaluated_successful_rounds") or 0)
            streak = int(objective.get("low_gain_streak") or 0)
            new_successful_rounds = max(0, successful_rounds - last_evaluated_rounds)
            if new_successful_rounds and not meets:
                streak = streak + new_successful_rounds if realized_gain < LOW_REALIZED_GAIN_THRESHOLD else 0
            status = "satisfied" if meets else (
                "blocked" if objective.get("status") == "blocked" else "open"
            )
            covered_boundary = " ".join(
                str(summary).strip()
                for query in queries
                if key in (query.get("objective_keys") or [])
                for summary in (query.get("covered") or [])
                if str(summary).strip()
            )
            supported_boundary = str(
                item.get("supported_boundary")
                or objective.get("supported_boundary")
                or covered_boundary
                or ""
            ).strip()
            graph_tools.upsert_node(NodeType.ANALYSIS, {
                "coverage": coverage,
                "confidence": confidence,
                "status": status,
                "supported_boundary": supported_boundary,
                "unmet_acceptance_criteria": unmet_acceptance_criteria,
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
            if query.get("search_subject_key")
        }
        grouped_candidates: dict[tuple[str, str], list[dict]] = {}
        for gap in candidates:
            subject = str(gap.get("search_subject_key") or gap.get("gap_key") or gap["id"])
            mode = gap.get("expansion_mode") if gap.get("expansion_mode") in {"horizontal", "vertical"} else "vertical"
            grouped_candidates.setdefault((mode, subject), []).append(gap)
        for (mode, subject), group in grouped_candidates.items():
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
                if item.get("status") not in {"satisfied", "blocked"}
            ]
            deficit = max(deficits, default=0.0)
            is_redundant_subject = subject in existing_subjects
            decision_impact = max(float(gap.get("decision_impact") or 0.0) for gap in group)
            confidence_gain = max(float(gap.get("confidence_gain") or 0.0) for gap in group)
            rounds = max(1, max(int(gap.get("estimated_search_rounds") or 1) for gap in group))
            benefit = 0.7 * deficit + 0.2 * decision_impact + 0.1 * confidence_gain
            min_floor = 0.04 if (deficit > 0 or decision_impact > 0 or confidence_gain > 0) else 0.0
            owner_ids = {self._gap_owner_id(gap["id"]) for gap in group}
            # Depth-breadth balance: discount utility for gaps on deep query
            # chains so breadth expansion wins ties; fatal / force_expand
            # bypass this via the ``choose`` clause below.
            max_owner_depth = max(
                (self._query_depth(oid) for oid in owner_ids if oid),
                default=0,
            )
            depth_discount = 1.0 / (
                1.0 + _DEPTH_PENALTY_FACTOR
                * max(0, max_owner_depth - _DEPTH_FREE_TIER)
            )
            utility = max(benefit / rounds, min_floor) * depth_discount
            fatal = any(gap.get("gap_category") == "fatal_conflict" for gap in group)
            threshold = (
                EXPANSION_UTILITY_THRESHOLD_REDUNDANT
                if is_redundant_subject
                else EXPANSION_UTILITY_THRESHOLD
            )
            owners = [
                graph_tools.get_node(owner_id)
                for owner_id in owner_ids
                if owner_id
            ]
            force_expand = any(
                owner and owner.get("status") == "needs_expansion"
                for owner in owners
            )
            choose = fatal or force_expand or (utility >= threshold)
            new_status = "selected" if choose else "deferred_low_value"
            expansion_parent_id = (
                max(owners, key=lambda item: float(item.get("priority") or 0.0))["id"]
                if choose and owners else None
            )
            for gap in group:
                graph_tools.upsert_node(NodeType.ANALYSIS, {
                    "status": new_status,
                    "marginal_utility": utility,
                    "objective_deficit": deficit,
                    "depth_discount": depth_discount,
                    "owner_depth": max_owner_depth,
                    "expansion_parent_id": expansion_parent_id,
                    "expansion_mode": mode,
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
                if linked and all(item.get("status") in {"satisfied", "blocked"} for item in linked):
                    graph_tools.transition_query(query["id"], "deferred")
                    self._propagate_child_completion(query["id"], "deferred")

        objectives = self.get_research_objectives(goal_id)
        must = [item for item in objectives if item.get("requirement") == "must"]
        weighted_must = [
            (
                item,
                float(item["weight"]) if item.get("weight") is not None else 1.0,
            )
            for item in must
        ]
        total_must_weight = sum(weight for _, weight in weighted_must)
        completeness = (
            sum(
                weight
                * min(
                    float(item.get("coverage") or 0.0) / OBJECTIVE_COVERAGE_THRESHOLD,
                    float(item.get("confidence") or 0.0) / OBJECTIVE_CONFIDENCE_THRESHOLD,
                    1.0,
                )
                for item, weight in weighted_must
            )
            / total_must_weight
            if total_must_weight > 0.0
            else 0.0 if must else 1.0
        )
        revision = int(goal.get("portfolio_revision") or 0)
        max_utility = max(
            (float(item.get("marginal_utility") or 0.0) for item in selected + deferred),
            default=0.0,
        )
        graph_tools.upsert_node(NodeType.USER_REQUEST, {
            "evaluated_portfolio_revision": revision,
            "last_max_marginal_utility": max_utility,
            "report_completeness_score": completeness,
        }, goal["id"])
        return {
            "selected_gap_ids": [item["id"] for item in selected],
            "deferred_gap_ids": [item["id"] for item in deferred],
            "objectives": objectives,
            "report_completeness_score": completeness,
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
        """Create one grounded Query per selected expansion mode and subject."""
        from tools import research_state

        if research_state.get_status().get("research_state") != research_state.RESEARCHING:
            return {"error": "Gap expansion is only allowed while research_state is RESEARCHING"}
        parent = graph_tools.get_node(parent_id)
        if parent.get("type") == NodeType.USER_REQUEST.value:
            resolved = parent_id
        else:
            try:
                resolved = self._resolve_query_id(parent_id)
            except AmbiguousQueryReference as exc:
                return {"error": str(exc)}
            parent = graph_tools.get_node(resolved) if resolved else {}
        if not resolved or parent.get("type") not in {NodeType.QUERY.value, NodeType.USER_REQUEST.value}:
            return {"error": f"Unknown Query/UserRequest expansion owner: {parent_id!r}"}
        assigned_selected_gap_ids = {
            gap["id"]
            for gap in graph_tools.search_nodes("analysis", {"analysis_type": "gap"})
            if gap.get("status") in {"selected", "candidate"}
            and gap.get("expansion_parent_id") == resolved
        }
        candidates = gap_ids or list(assigned_selected_gap_ids)
        gaps = [
            graph_tools.get_node(gid) for gid in candidates
            if gid in assigned_selected_gap_ids
            and graph_tools.get_node(gid).get("analysis_type") == "gap"
            and graph_tools.get_node(gid).get("status") in {"selected", "candidate"}
        ]
        processed_ids = {gap["id"] for gap in gaps}
        for sid in assigned_selected_gap_ids - processed_ids:
            node = graph_tools.get_node(sid)
            if node and node.get("status") in {"selected", "candidate"}:
                graph_tools.upsert_node(NodeType.ANALYSIS, {
                    "status": "blocked",
                    "resolution_reason": "gap not found or filtered during expansion",
                }, sid)
        grouped: dict[tuple[str, str], list[dict]] = {}
        for gap in gaps:
            subject = str(gap.get("search_subject_key") or gap.get("gap_key") or gap["id"])
            default_mode = "horizontal" if parent.get("type") == NodeType.USER_REQUEST.value else "vertical"
            mode = gap.get("expansion_mode") if gap.get("expansion_mode") in {"horizontal", "vertical"} else default_mode
            grouped.setdefault((mode, subject), []).append(gap)
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
        existing_query_texts = [
            query.get("text") for query in graph_tools.search_nodes("query", {}) if query.get("text")
        ]
        research_constraints = {
            key: goal.get(key)
            for key in (
                "request", "language", "time_window", "region_scope", "source_preferences",
                "excluded_domains", "excluded_urls", "scope_mode",
            )
        }
        objective_by_key = {item["objective_key"]: item for item in self.get_research_objectives()}
        for (mode, subject), group in grouped.items():
            if (
                parent.get("type") == NodeType.QUERY.value
                and any(gap.get("gap_key") and self._gap_key_in_ancestors(resolved, gap.get("gap_key")) for gap in group)
            ):
                for gap in group:
                    graph_tools.upsert_node(NodeType.ANALYSIS, {
                        "status": "blocked",
                        "resolution_reason": "duplicate gap_key already exists on the ancestor path",
                    }, gap["id"])
                continue
            if mode == "horizontal":
                attach_parent_id = (
                    graph_tools.get_query_parent(resolved)
                    if parent.get("type") == NodeType.QUERY.value
                    else resolved
                )
            else:
                attach_parent_id = resolved if parent.get("type") == NodeType.QUERY.value else None
            if not attach_parent_id:
                for gap in group:
                    graph_tools.upsert_node(NodeType.ANALYSIS, {
                        "status": "blocked",
                        "resolution_reason": "expansion mode has no valid strict-tree attach point",
                    }, gap["id"])
                continue
            followups = self._plan_followup_queries(
                research_goal=goal.get("research_goal") or goal.get("request") or "",
                parent_text=parent.get("text") or parent.get("request") or "",
                research_constraints=research_constraints,
                existing_query_texts=existing_query_texts,
                gaps=[
                    {
                        "id": gap["id"],
                        "description": gap.get("description") or gap.get("text"),
                        "acceptance_criteria": gap.get("acceptance_criteria") or [],
                    }
                    for gap in group
                ],
                reason=f"Globally selected {mode} search subject: {subject}",
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
                parent_id=attach_parent_id,
                text=spec["text"],
                importance=importance,
                acceptance_criteria=spec.get("acceptance_criteria") or [
                    criterion for gap in group for criterion in (gap.get("acceptance_criteria") or [])
                ],
                gap_ids=[gap["id"] for gap in group],
                objective_keys=objective_keys,
                required_for_parent=False,
                search_subject_key=subject,
                expansion_mode=mode,
                query_role="evidence_gap",
            )
            for key in objective_keys:
                graph_tools.add_edge(child_id, objective_by_key[key]["id"], EdgeType.COVERS_OBJECTIVE)
            child = graph_tools.get_node(child_id)
            for gap in group:
                graph_tools.upsert_node(NodeType.ANALYSIS, {
                    "status": "expanded",
                    "resolution_reason": f"child query created: {child.get('handle')}",
                }, gap["id"])
            created.append({
                "id": child_id,
                "handle": child.get("handle"),
                "text": child.get("text"),
                "gap_ids": [gap["id"] for gap in group],
                "expansion_mode": mode,
                "attach_parent_id": attach_parent_id,
            })
            existing_query_texts.append(child.get("text"))

        next_status = parent.get("status")
        if parent.get("type") == NodeType.QUERY.value and parent.get("status") == "needs_expansion":
            if any(item.get("expansion_mode") == "vertical" for item in created):
                next_status = "waiting_children"
            elif created:
                next_status = "sufficient"
            else:
                next_status = "blocked"
            graph_tools.transition_query(resolved, next_status)
            if next_status in {"sufficient", "blocked"}:
                self._propagate_child_completion(resolved, next_status)
        self._bump_portfolio_revision()
        return {
            "parent_id": resolved,
            "parent_handle": parent.get("handle"),
            "parent_status": next_status,
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
                "converged": current_state in {
                    research_state.REPORT_READY,
                    research_state.LIMITED_REPORT_READY,
                    research_state.BUDGET_EXHAUSTED,
                },
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

        with self._state_lock:
            goal = research_state.get_goal(goal_id)
            portfolio_stale = int(goal.get("evaluated_portfolio_revision") or 0) < int(
                goal.get("portfolio_revision") or 0
            )
            if portfolio_stale:
                portfolio = self.evaluate_research_portfolio(goal_id)
                if portfolio.get("error"):
                    return {
                        "error": f"Portfolio refresh before convergence failed: {portfolio['error']}",
                        "converged": False,
                        "recommendation": "continue",
                        "research_state": research_state.RESEARCHING,
                        "next_actions": [{
                            "action": "evaluate_research_portfolio",
                            "query_id": None,
                            "goal_id": goal.get("id"),
                            "reason": "portfolio refresh failed before convergence",
                        }],
                    }
                all_queries = graph_tools.search_nodes("query", {})

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
        objective_by_key = {
            item["objective_key"]: item for item in self.get_research_objectives(goal_id)
        }
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
            description = f"Independent evidence needed to resolve or scope conflict: {fatal_description}"
            key = _gap_key(description)
            owner = graph_tools.get_node(owner_id)
            gap_parent_id = owner_id
            if key not in {
                graph_tools.get_node(gid).get("gap_key") for gid in self._query_gap_ids(gap_parent_id)
            }:
                gap_id = graph_tools.create_analysis(
                    text=description,
                    query_id=gap_parent_id,
                    analysis_type="gap",
                    description=description,
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
                    expansion_mode="vertical",
                    expansion_parent_id=gap_parent_id,
                    trigger_type="graph_evidence",
                    trigger_refs=[conflict["id"]],
                )
                created_fatal_gaps.append(gap_id)
                for objective_key in graph_tools.get_node(gap_id).get("objective_keys") or []:
                    objective = objective_by_key.get(objective_key)
                    if objective:
                        graph_tools.add_edge(gap_id, objective["id"], EdgeType.IMPACTS_OBJECTIVE)
                if owner.get("status") == "assessing":
                    graph_tools.transition_query(owner_id, "needs_expansion")
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
            item.get("status") == "satisfied"
            for item in must
        )
        objectives_limited = (
            bool(must)
            and any(item.get("status") == "blocked" for item in must)
            and all(item.get("status") in {"satisfied", "blocked"} for item in must)
        )
        remaining = research_state.remaining_budget(goal_id)

        # Completion mode: when remaining budget is at or below the reserve
        # threshold, defer queries that still need expansion so the remaining
        # rounds are spent finishing in-flight searches rather than starting
        # new branches.
        if remaining is not None and remaining <= _BUDGET_RESERVE_FOR_COMPLETION:
            for query in all_queries:
                if query.get("status") == "needs_expansion":
                    graph_tools.transition_query(query["id"], "deferred")
                    self._propagate_child_completion(query["id"], "deferred")
            all_queries = graph_tools.search_nodes("query", {})

        # Budget-exhausted cleanup: when the budget is fully consumed, force
        # all still-active and pending queries into a terminal state so the
        # convergence gate can evaluate a clean tree.
        if remaining is not None and remaining == 0:
            for query in all_queries:
                status = query.get("status")
                if status in _ACTIVE_QUERY_WORK_STATUSES or status == "pending":
                    graph_tools.transition_query(query["id"], "deferred")
                    self._propagate_child_completion(query["id"], "deferred")
            all_queries = graph_tools.search_nodes("query", {})

        active = [
            query for query in all_queries
            if query.get("status") in _ACTIVE_QUERY_WORK_STATUSES
        ]
        pending = [
            query for query in all_queries
            if query.get("status") == "pending"
        ]
        selected_gaps = [
            gap for gap in graph_tools.search_nodes("analysis", {"analysis_type": "gap"})
            if gap.get("status") in _BLOCKING_GAP_WORK_STATUSES
        ]
        portfolio_current = int(goal.get("evaluated_portfolio_revision") or 0) >= int(goal.get("portfolio_revision") or 0)
        exhaustive_open = [
            query for query in all_queries
            if query.get("status") not in research_state.TERMINAL_QUERY_STATUSES
        ] if goal.get("scope_mode") == "exhaustive" else []

        # Dimension-coverage gate: prevent premature convergence when the evidence
        # base is too thin across sources and expanded dimensions.
        evidence_nodes = graph_tools.search_nodes("evidence", {})
        source_nodes = graph_tools.search_nodes("source", {})
        initial_query_ids = set(graph_tools.get_query_children(goal.get("id")) or [])
        expanded_queries = [
            q for q in all_queries
            if q.get("id") not in initial_query_ids
        ]
        dimension_coverage_adequate = (
            len(evidence_nodes) >= _MIN_EVIDENCE_FOR_CONVERGENCE
            and len(source_nodes) >= _MIN_SOURCES_FOR_CONVERGENCE
            and len(expanded_queries) >= _MIN_EXPANDED_QUERIES_FOR_CONVERGENCE
        )

        if active:
            research_state.update_goal({
                "research_state": research_state.RESEARCHING,
                "last_convergence_recommendation": "continue",
                "report_authorized_reason": None,
            }, goal_id)
            recommendation = "continue"
            state = research_state.RESEARCHING
        elif (
            tree["valid"]
            and portfolio_current
            and objectives_ready
            and dimension_coverage_adequate
            and not active
            and not selected_gaps
            and not fatal
            and not created_fatal_gaps
        ):
            for query in all_queries:
                if query.get("status") == "pending":
                    graph_tools.transition_query(query["id"], "deferred")
                    self._propagate_child_completion(query["id"], "deferred")
            for objective in objectives:
                if objective.get("requirement") == "should" and objective.get("status") == "open":
                    graph_tools.upsert_node(
                        NodeType.ANALYSIS,
                        {"status": "deferred"},
                        objective["id"],
                    )
            research_state.update_goal({
                "research_state": research_state.REPORT_READY,
                "last_convergence_recommendation": "stop",
                "report_authorized_reason": "report-level objectives reached marginal-utility convergence",
            }, goal_id)
            recommendation = "stop"
            state = research_state.REPORT_READY
        elif remaining == 0 and (
            selected_gaps
            or not objectives_ready
            or not dimension_coverage_adequate
            or exhaustive_open
        ):
            research_state.mark_budget_exhausted(goal_id)
            recommendation = "stop"
            state = research_state.BUDGET_EXHAUSTED
        elif (
            goal.get("scope_mode", "bounded") == "bounded"
            and tree["valid"]
            and portfolio_current
            and objectives_limited
            and not active
            and not pending
            and not selected_gaps
            and not fatal
            and not created_fatal_gaps
            and int(goal.get("successful_search_rounds") or 0) >= MIN_SUCCESSFUL_ROUNDS_BEFORE_BEST_EFFORT
        ):
            research_state.update_goal({
                "research_state": research_state.LIMITED_REPORT_READY,
                "last_convergence_recommendation": "stop",
                "report_authorized_reason": "bounded research reached best-effort convergence",
            }, goal_id)
            recommendation = "stop"
            state = research_state.LIMITED_REPORT_READY
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
            query_issue = _query_text_issue(query.get("text"))
            if query_issue:
                return {"error": f"Query is not a valid literal web-search string: {query_issue}"}
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
            requested_preferences = _string_list(source_preferences)
            extra_excluded_domains = [
                domain for domain in (
                    _normalize_domain(item)
                    for item in requested_preferences
                    if item.lower().startswith("-site:")
                )
                if domain
            ]
            preferences = list(dict.fromkeys([
                *_string_list(goal.get("source_preferences")),
                *(item for item in requested_preferences if not item.lower().startswith("-site:")),
            ]))
            excluded_domains = list(dict.fromkeys([
                *_string_list(goal.get("excluded_domains")),
                *extra_excluded_domains,
            ]))
            return {
                "search_run_id": run_id,
                "query_id": resolved,
                "query_handle": query.get("handle"),
                "query_text": query.get("text"),
                "query_role": query.get("query_role") or "evidence_gap",
                "acceptance_criteria": _string_list(query.get("acceptance_criteria")),
                "research_context": {
                    "research_goal": goal.get("research_goal") or "",
                    "time_window": goal.get("time_window"),
                    "region_scope": goal.get("region_scope"),
                },
                "source_preferences": preferences,
                "excluded_domains": excluded_domains,
                "excluded_urls": _string_list(goal.get("excluded_urls")),
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
        """Resolve a Query reference through the shared graph boundary."""
        return graph_tools.resolve_query_reference(query_id)

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
            statement_refs = evidence.get("statement_refs") or []
            if not isinstance(statement_refs, list) or any(
                not isinstance(ref, str) or not valid_ref(ref, NodeType.STATEMENT.value)
                for ref in statement_refs
            ):
                return "Evidence statement_refs must all reference valid Statements"
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
            statement_refs = list(dict.fromkeys(filter(None, (
                resolve(ref) for ref in evidence_item.get("statement_refs") or []
            ))))
            statement_ref = statement_refs[0] if statement_refs else None
            claim_ref = resolve(_first(evidence_item, "claim_ref", "normalized_claim_ref"))
            if legacy_ref and legacy_ref not in {"supports", "contradicts", "qualifies", "support", "contradict", "qualify"}:
                resolved_legacy = resolve(legacy_ref)
                legacy_node = graph_tools.get_node(resolved_legacy) if resolved_legacy else {}
                if legacy_node.get("type") == NodeType.STATEMENT.value:
                    statement_ref = resolved_legacy
                    if resolved_legacy not in statement_refs:
                        statement_refs.append(resolved_legacy)
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
                statement_refs=statement_refs,
                claim_ref=claim_ref,
                stance=_first(evidence_item, "stance") or (
                    legacy_ref if legacy_ref in {"supports", "contradicts", "qualifies"} else None
                ),
            )
            if evidence_item.get("local_ref"):
                ref_map[evidence_item["local_ref"]] = evidence_id
            for linked_statement_id in statement_refs:
                graph_tools.add_edge(evidence_id, linked_statement_id, EdgeType.SUPPORTED_BY)
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
            if attempts >= 2:
                # Second attempt also returned empty → blocked.
                # Restore the original text if a variant was used on attempt 2.
                original_text = query.get("original_text")
                if original_text:
                    graph_tools.upsert_node(
                        NodeType.QUERY,
                        {"text": original_text},
                        resolved_query_id,
                    )
                graph_tools.transition_query(
                    resolved_query_id,
                    "blocked",
                    block_reason="two SearchRuns completed without valid Source and Evidence",
                )
                self._propagate_child_completion(resolved_query_id, "blocked")
            else:
                # First attempt returned empty (all results rejected as
                # duplicates).  Reformulate the query text so the second
                # SearchRun searches from a different angle instead of
                # repeating the identical Tavily call.
                original_text = query.get("original_text") or query.get("text", "")
                existing_source_titles: list[str] = []
                try:
                    all_sources = graph_tools.search_nodes("source", {})
                    existing_source_titles = [
                        (s.get("title") or s.get("url") or "")
                        for s in all_sources
                        if (s.get("title") or s.get("url"))
                    ][:10]
                except Exception:
                    pass
                goal_node = graph_tools.get_node(
                    graph_tools.get_query_parent(resolved_query_id) or ""
                ) or {}
                research_goal = goal_node.get("research_goal") or goal_node.get("request") or ""
                new_text = self._reformulate_query_text(
                    original_text, research_goal, existing_source_titles
                )
                if new_text:
                    logger.info(
                        "Reformulating query %s: '%s' → '%s'",
                        resolved_query_id, original_text, new_text,
                    )
                    graph_tools.upsert_node(
                        NodeType.QUERY,
                        {
                            "text": new_text,
                            "original_text": original_text,
                        },
                        resolved_query_id,
                    )
                else:
                    logger.info(
                        "Could not reformulate query %s ('%s'); retrying as-is",
                        resolved_query_id, original_text,
                    )
                graph_tools.transition_query(resolved_query_id, "pending")

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
            "query_status": "assessing" if succeeded else ("blocked" if int(query.get("search_attempts") or 0) >= 2 else "pending"),
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
        from tools import report_tools, research_state

        request_text = goal.get("request", "")
        if request_text:
            logger.info(f"User Request passed to Reporter: {len(request_text)} characters")
        else:
            logger.warning("User Request is empty in export_report_context")

        authorization_state = goal.get("reporting_from_state") or goal.get("research_state")
        delivery_mode = (
            "complete"
            if authorization_state == research_state.REPORT_READY
            else "limited"
            if authorization_state in {
                research_state.LIMITED_REPORT_READY,
                research_state.BUDGET_EXHAUSTED,
            }
            else None
        )
        sorted_queries = sorted(
            graph_tools.search_nodes("query", {}),
            key=lambda query: (
                float(query.get("sem") or 0.0),
                float(query.get("priority") or 0.0),
                query.get("id") or "",
            ),
            reverse=True,
        )
        disclosed_conflicts = report_tools.get_disclosed_conflicts()
        substantive_uncertainties = [
            {
                "reader_facing_topic": conflict.get("conflict_type") or "source disagreement",
                "neutral_description": conflict.get("description"),
            }
            for conflict in disclosed_conflicts
            if conflict.get("description")
            and conflict.get("evidence_ids")
            and conflict.get("source_ids")
        ]
        return {
            "delivery_mode": delivery_mode,
            "goal": {
                key: goal.get(key)
                for key in ("request",)
            } if goal else {},
            "queries": [
                {
                    "ref": query.get("handle"),
                    "text": query.get("text"),
                    "importance": query.get("importance"),
                }
                for query in sorted_queries
            ],
            "substantive_uncertainties": substantive_uncertainties,
            "disclosed_conflicts": [
                {
                    "description": conflict.get("description"),
                    "conflict_type": conflict.get("conflict_type"),
                }
                for conflict in disclosed_conflicts
            ],
            "reference_registry": [
                {key: entry.get(key) for key in ("n", "title", "url", "source_type", "published_at")}
                for entry in report_tools.build_reference_registry()
            ],
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
    def _plan_initial_queries(
        self,
        user_request: str,
        initial_query_limit: int,
        correction: str = "",
    ) -> dict:
        """根据用户请求规划初始 Query.

        Args:
            user_request: The original research request.
            initial_query_limit: Runtime-enforced upper bound for discovery Queries.

        Returns:
            dict with ``research_goal``, ``language`` and ``initial_queries``.
        """
        prompt = (
            mm_prompts.init_research
            .replace("{user_request}", user_request)
            .replace("{initial_query_limit}", str(initial_query_limit))
        ) + (f"\n\nCorrection after validation failure: {correction}" if correction else "")
        return self._invoke_json(prompt)

    def _plan_followup_queries(
        self,
        research_goal: str,
        parent_text: str,
        research_constraints: dict,
        existing_query_texts: list,
        gaps: Any,
        reason: str,
        max_new: int = 1,
    ) -> list:
        """为已选 Gap 规划自包含的后续 Query.

        Drops any authored query that references another query (a
        self-containment violation) and retries once before giving up.

        Args:
            research_goal: The overall research goal, for context.
            parent_text: The parent query/goal text whose subject is inlined.
            research_constraints: Original scope and source constraints.
            existing_query_texts: Every existing Query text for exact dedup.
            gaps: Gaps (vertical) or missing dimensions (horizontal) to cover.
            reason: Why this expansion is needed.
            max_new: Maximum number of queries to author.

        Returns:
            A list of Query specs (cross-referencing ones dropped).
        """
        gaps_text = gaps if isinstance(gaps, str) else json.dumps(gaps or [], ensure_ascii=False)
        existing_keys = {
            _normalize_query_text(text)
            for text in existing_query_texts or []
            if isinstance(text, str) and text.strip()
        }

        def author(extra: str = "") -> list:
            prompt = (
                mm_prompts.plan_followup_query
                .replace("{research_goal}", research_goal or "")
                .replace("{parent_text}", parent_text or "")
                .replace("{research_constraints}", json.dumps(research_constraints or {}, ensure_ascii=False))
                .replace("{existing_query_texts}", json.dumps(existing_query_texts or [], ensure_ascii=False))
                .replace("{gaps}", gaps_text)
                .replace("{reason}", reason or "")
                .replace("{max_new}", str(max_new))
            )
            parsed = self._invoke_json(prompt + extra)
            items = []
            raw_queries = parsed.get("queries") or []
            if not isinstance(raw_queries, list):
                raw_queries = []
            authored_keys: set[str] = set()
            for raw in raw_queries:
                text, criteria, objective_keys = _query_spec(raw)
                key = _normalize_query_text(text)
                if _query_text_issue(text) or key in existing_keys or key in authored_keys:
                    continue
                authored_keys.add(key)
                items.append({
                    "text": text,
                    "acceptance_criteria": criteria,
                    "objective_keys": objective_keys,
                })
            return items

        queries = author()
        if not queries:
            retry = (
                "\n\nValidation rejected the prior query. Return one short literal search phrase "
                "with concrete entities and constraints, no contextual references, report tasks, "
                "or agent instructions."
            )
            queries = author(retry)
        if not queries:
            fallback_text = f"{(parent_text or '').strip()}".strip()
            if fallback_text and not _query_text_issue(fallback_text):
                key = _normalize_query_text(fallback_text)
                if key not in existing_keys:
                    fallback_criteria = []
                    for gap in (gaps or []):
                        if isinstance(gap.get("acceptance_criteria"), list):
                            fallback_criteria.extend([
                                c for c in gap["acceptance_criteria"]
                                if isinstance(c, str)
                            ][:1])
                    queries = [{
                        "text": fallback_text,
                        "acceptance_criteria": fallback_criteria,
                        "objective_keys": [],
                    }]
        return queries[:max_new]

    def _reformulate_query_text(
        self,
        original_text: str,
        research_goal: str,
        existing_sources: list,
    ) -> Optional[str]:
        """Reformulate a query whose search returned only duplicate results.

        Asks the LLM to produce a variant query that searches from a different
        angle, to attract new sources that the original phrasing missed.

        Returns the new query text, or ``None`` if the LLM output is invalid or
        identical to the original.
        """
        prompt = (
            mm_prompts.reformulate_query
            .replace("{original_query}", original_text or "")
            .replace("{research_goal}", research_goal or "")
            .replace("{existing_sources}", json.dumps(existing_sources or [], ensure_ascii=False))
        )
        parsed = self._invoke_json(prompt)
        new_text = (parsed.get("query_text") or "").strip()
        if new_text and not _query_text_issue(new_text):
            if _normalize_query_text(new_text) != _normalize_query_text(original_text):
                return new_text
        return None

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
