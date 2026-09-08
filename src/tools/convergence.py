"""Deterministic convergence metrics for the Research Graph.

Computes cheap, LLM-free signals over the current graph — query-status rollup,
conflict tally, source diversity, and round-over-round evidence novelty — that
back the Orchestrator's stop decision and feed the global ``assess_convergence``
judgment. All graph access goes through the synchronous wrappers in
``tools/graph_tools.py``; the graph is already scoped to the current run via
``graph_tools.set_context``.
"""

import logging
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Query statuses that count as resolved for convergence (mirrors the gate the
# middleware enforces before allowing further Searcher dispatches).
_RESOLVED_STATUSES = {"sufficient", "blocked", "failed", "deferred", "paused"}

# --- Priority model -------------------------------------------------------
# A query's priority blends a SEMANTIC signal (how central its topic is to the
# research goal, judged by the Query Planner at creation) with a STRUCTURAL
# signal (its position in the query tree, inheriting a decayed share of its
# parent's priority). The blend is tiered into high/low to drive convergence:
# high-priority queries must be answered; low-priority gaps only get a
# core-impact check. All weights are tunable here.
SEM_MAP = {"core": 1.0, "supporting": 0.6, "peripheral": 0.3}
_DEFAULT_SEM = "supporting"
W_SEM = 0.6          # weight of the semantic signal
W_STRUCT = 0.4       # weight of the structural signal
GAMMA = 0.85         # per-depth decay of inherited parent priority
TAU_HIGH = 0.65      # priority >= TAU_HIGH -> "high" tier
SCORE_THRESHOLD = 0.7  # sufficiency_score a high-priority query must reach

# Per-run novelty state, cleared by ``reset`` at the start of each run.
_accounted_evidence_ids: set[str] = set()
_seen_evidence_keys: set[str] = set()
_novelty_history: list[float] = []


def reset() -> None:
    """Clear per-run novelty bookkeeping so a fresh run starts from zero."""
    _accounted_evidence_ids.clear()
    _seen_evidence_keys.clear()
    _novelty_history.clear()


def is_diminishing() -> bool:
    """Legacy stub — always returns False.

    The hard-threshold diminishing-returns check has been removed. The full
    novelty ratio history is still collected and passed to the portfolio
    evaluator so the LLM can judge whether returns are diminishing based on
    both the ratio trend and the nature of the new evidence.
    """
    return False


def compute_priority(sem_label: Optional[str], parent_id: Optional[str]) -> tuple:
    """Blend a query's semantic and structural signals into a priority.

    The structural share inherits a depth-decayed fraction of the parent's
    priority; an initial query (whose parent is the research goal and carries no
    priority of its own) takes the full structural weight.

    Args:
        sem_label: Planner-assigned importance (``core``/``supporting``/
            ``peripheral``); unknown values fall back to ``supporting``.
        parent_id: The structural parent (attach point) of the new query.

    Returns:
        A ``(score, tier, sem_value)`` tuple: priority float in [0, 1], the
        ``high``/``low`` tier, and the resolved semantic float.
    """
    from tools import graph_tools

    sem_value = SEM_MAP.get(sem_label or _DEFAULT_SEM, SEM_MAP[_DEFAULT_SEM])
    parent = graph_tools.get_node(parent_id) if parent_id else {}
    parent_priority = (parent or {}).get("priority")
    struct = 1.0 if parent_priority is None else GAMMA * float(parent_priority)
    score = W_SEM * sem_value + W_STRUCT * struct
    # Scheduling priority is strictly depth-decayed. Whether a child is
    # required for convergence is represented separately by
    # ``required_for_parent`` and must not be encoded by raising its score.
    if parent_priority is not None:
        score = min(score, struct)
    score = max(0.0, min(1.0, score))
    tier = "high" if score >= TAU_HIGH else "low"
    return score, tier, sem_value


def structurally_converged() -> bool:
    """Report whether report-level objectives have reached a terminal state.

    New runs converge on must Objectives. The required-path fallback remains
    only for legacy diagnostic graphs that do not contain Objective nodes.

    Returns:
        True when the deterministic, priority-weighted part of convergence is
        met; False otherwise.
    """
    from tools import graph_tools, research_state

    objectives = graph_tools.search_nodes("analysis", {"analysis_type": "objective"})
    must = [objective for objective in objectives if objective.get("requirement") == "must"]
    if must:
        return all(objective.get("status") == "satisfied" for objective in must)

    queries = graph_tools.search_nodes("query", {})
    required = [q for q in queries if research_state.is_required_path(q["id"])]
    if not required:
        return bool(queries)
    return all(
        q.get("status") == "blocked"
        or (
            q.get("status") == "sufficient"
            and float(q.get("sufficiency_score") or 0.0) >= SCORE_THRESHOLD
        )
        for q in required
    )


def _normalize(text: Optional[str]) -> str:
    """Return a whitespace-collapsed, lowercased key for evidence-text dedup."""
    return " ".join((text or "").split()).lower()


def _novelty_metrics(advance: bool = True) -> dict:
    """Score how much genuinely new evidence arrived since the last round.

    Looks only at evidence not yet accounted in a prior round, then measures the
    fraction whose normalized text was never seen before. Re-collecting known
    facts drives the ratio down; a round that adds no evidence scores zero.

    Args:
        advance: When True, fold this round's evidence into the seen sets and
            append the ratio to history (the once-per-round update). When False,
            return a read-only snapshot of the last recorded round without
            mutating any bookkeeping.

    Returns:
        dict with ``ratio``, ``new_total``, ``new_unique`` and a short
        ``history_tail`` of recent novelty ratios for the portfolio evaluator.
    """
    if not advance:
        return {
            "ratio": _novelty_history[-1] if _novelty_history else None,
            "new_total": None,
            "new_unique": None,
            "history_tail": _novelty_history[-3:],
        }

    from tools import graph_tools

    evidence = graph_tools.search_nodes("evidence", {})
    new_unique = 0
    new_total = 0
    for item in evidence:
        node_id = item.get("id")
        if not node_id or node_id in _accounted_evidence_ids:
            continue
        new_total += 1
        key = _normalize(item.get("claim"))
        if key and key not in _seen_evidence_keys:
            new_unique += 1
        if key:
            _seen_evidence_keys.add(key)
        _accounted_evidence_ids.add(node_id)

    # A round that added no evidence yet (searches still in flight) is not a
    # diminishing-returns signal — skip it so the cold start cannot register as
    # low novelty before any evidence has landed.
    ratio = new_unique / new_total if new_total else None
    if ratio is not None:
        _novelty_history.append(ratio)
    return {
        "ratio": ratio,
        "new_total": new_total,
        "new_unique": new_unique,
        "history_tail": _novelty_history[-3:],
    }


def observe_round() -> dict:
    """Advance novelty bookkeeping by one round and return full metrics.

    Call once per Searcher dispatch (the natural round boundary) so the novelty
    trend tracks per-round yield. Use :func:`compute_metrics` for read-only
    inspection elsewhere.

    Returns:
        The same dict shape as :func:`compute_metrics`, with novelty advanced.
    """
    return compute_metrics(advance_novelty=True)


def compute_metrics(advance_novelty: bool = False) -> dict:
    """Compute the deterministic convergence signals over the current graph.

    Args:
        advance_novelty: When True, advance the per-round novelty bookkeeping
            (use :func:`observe_round`). Defaults to a read-only snapshot so
            inspection from the boundary judgment does not perturb the trend.

    Returns:
        A flat dict with ``status_counts``, ``all_resolved``, ``priority``,
        ``score_min``, ``score_mean``, ``conflicts``, ``sources`` and
        ``novelty``.
    """
    from tools import graph_tools

    queries = graph_tools.search_nodes("query", {})
    status_counts: dict[str, int] = {}
    tier_counts: dict[str, int] = {}
    scores: list[float] = []
    pending_high = False
    for query in queries:
        status = query.get("status")
        if status is not None:
            status_counts[status] = status_counts.get(status, 0) + 1
        tier = query.get("priority_tier")
        if tier is not None:
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
        if tier == "high" and status == "pending":
            pending_high = True
        score = query.get("sufficiency_score")
        if isinstance(score, (int, float)):
            scores.append(float(score))
    all_resolved = bool(queries) and all(
        status in _RESOLVED_STATUSES for status in status_counts
    )

    conflicts = graph_tools.search_nodes("conflict", {})
    by_type: dict[str, int] = {}
    unresolved = 0
    for conflict in conflicts:
        ctype = conflict.get("conflict_type") or "factual"
        by_type[ctype] = by_type.get(ctype, 0) + 1
        if conflict.get("resolution_status") != "resolved":
            unresolved += 1

    sources = graph_tools.search_nodes("source", {})
    domains: set[str] = set()
    for source in sources:
        netloc = urlparse(source.get("url") or "").netloc
        if netloc:
            domains.add(netloc)
    source_count = len(sources)
    domain_count = len(domains)

    return {
        "status_counts": status_counts,
        "all_resolved": all_resolved,
        "priority": {
            "tier_counts": tier_counts,
            "structurally_converged": structurally_converged(),
            "pending_high_priority": pending_high,
        },
        "score_min": min(scores) if scores else None,
        "score_mean": sum(scores) / len(scores) if scores else None,
        "conflicts": {
            "total": len(conflicts),
            "unresolved": unresolved,
            "by_type": by_type,
        },
        "sources": {
            "count": source_count,
            "domains": domain_count,
            "diversity_ratio": domain_count / source_count if source_count else 0.0,
        },
        "novelty": _novelty_metrics(advance=advance_novelty),
    }
