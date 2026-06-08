"""Standalone checks for priority-weighted convergence.

Run directly (NOT pytest):  uv run python tests/test_convergence.py

Stubs ``graph_tools`` reads so the deterministic logic is exercised without a
live neo4j backend, and drives ``MemoryManager.assess_convergence`` with a fake
model to check the recommendation is composed correctly.
"""

import json
import sys
from pathlib import Path

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from tools import convergence, graph_tools  # noqa: E402

# Mutable fake graph the tests drive round by round.
_FAKE = {"query": [], "source": [], "evidence": [], "conflict": []}
_NODES: dict = {}


def _fake_search_nodes(node_type, _filter):
    return list(_FAKE.get(node_type, []))


def _fake_get_node(node_id):
    return _NODES.get(node_id, {})


graph_tools.search_nodes = _fake_search_nodes
graph_tools.get_node = _fake_get_node


def _set(queries=None, sources=None, evidence=None, conflicts=None):
    _FAKE["query"] = queries or []
    _FAKE["source"] = sources or []
    _FAKE["evidence"] = evidence or []
    _FAKE["conflict"] = conflicts or []


def ev(node_id, claim):
    return {"id": node_id, "type": "evidence", "claim": claim}


def src(node_id, url):
    return {"id": node_id, "type": "source", "url": url}


def q(node_id, status, score=None, tier=None, priority=None):
    n = {"id": node_id, "type": "query", "status": status}
    if score is not None:
        n["sufficiency_score"] = score
    if tier is not None:
        n["priority_tier"] = tier
    if priority is not None:
        n["priority"] = priority
    return n


class FakeModel:
    """Returns a fixed JSON payload from ``.invoke`` (the LLM verdict)."""

    def __init__(self, payload):
        self._payload = payload

    def invoke(self, _prompt):
        class _R:
            content = json.dumps(self._payload)

        return _R()


def test_compute_priority():
    convergence.reset()
    _NODES.clear()
    # Initial queries (parent = goal, no priority) -> struct = 1.0.
    _NODES["goal"] = {"id": "goal", "type": "user_request"}
    s_core, t_core, _ = convergence.compute_priority("core", "goal")
    s_sup, t_sup, _ = convergence.compute_priority("supporting", "goal")
    s_per, t_per, _ = convergence.compute_priority("peripheral", "goal")
    assert round(s_core, 2) == 1.00 and t_core == "high", (s_core, t_core)
    assert round(s_sup, 2) == 0.76 and t_sup == "high", (s_sup, t_sup)
    assert round(s_per, 2) == 0.58 and t_per == "low", (s_per, t_per)
    # Missing importance defaults to supporting -> high for an initial query.
    s_def, t_def, _ = convergence.compute_priority(None, "goal")
    assert round(s_def, 2) == 0.76 and t_def == "high"

    # Vertical child of a core query inherits a decayed structural floor.
    _NODES["qcore"] = {"id": "qcore", "type": "query", "priority": 1.0}
    s_child, t_child, _ = convergence.compute_priority("supporting", "qcore")
    assert round(s_child, 2) == 0.70 and t_child == "high", (s_child, t_child)
    # Peripheral detail under a peripheral parent stays low.
    _NODES["qper"] = {"id": "qper", "type": "query", "priority": 0.58}
    s_pp, t_pp, _ = convergence.compute_priority("peripheral", "qper")
    assert t_pp == "low", (s_pp, t_pp)
    print("compute_priority OK")


def test_structurally_converged():
    _NODES.clear()
    # One high not yet answered -> not converged; low queries never gate.
    _set(queries=[
        q("h1", "sufficient", 0.8, tier="high"),
        q("h2", "needs_vertical", 0.6, tier="high"),
        q("l1", "needs_vertical", 0.3, tier="low"),
    ])
    assert convergence.structurally_converged() is False
    # High below the score threshold -> not converged.
    _set(queries=[q("h1", "sufficient", 0.65, tier="high")])
    assert convergence.structurally_converged() is False
    # All high sufficient & >= threshold (low still open) -> converged.
    _set(queries=[
        q("h1", "sufficient", 0.8, tier="high"),
        q("l1", "needs_vertical", 0.2, tier="low"),
    ])
    assert convergence.structurally_converged() is True
    # A blocked high counts as best-effort (termination guarantee).
    _set(queries=[q("h1", "blocked", tier="high"), q("h2", "sufficient", 0.9, tier="high")])
    assert convergence.structurally_converged() is True
    print("structurally_converged OK")


def test_novelty_advance_vs_snapshot():
    convergence.reset()
    # Cold start: a round with no evidence yet must NOT register as low novelty.
    _set(evidence=[])
    m = convergence.observe_round()
    assert m["novelty"]["ratio"] is None and m["novelty"]["new_total"] == 0
    m = convergence.observe_round()
    assert m["novelty"]["diminishing"] is False, "empty rounds must not trigger diminishing"

    _set(evidence=[ev("e1", "fact one"), ev("e2", "fact two")])
    m = convergence.observe_round()  # advances
    assert m["novelty"]["new_total"] == 2 and m["novelty"]["new_unique"] == 2
    assert m["novelty"]["ratio"] == 1.0
    # Read-only snapshot does not advance or change history.
    snap = convergence.compute_metrics(advance_novelty=False)
    assert snap["novelty"]["new_total"] is None
    assert snap["novelty"]["ratio"] == 1.0  # last recorded
    # Two duplicate-only rounds -> diminishing.
    _FAKE["evidence"].append(ev("e3", "fact one"))
    convergence.observe_round()
    _FAKE["evidence"].append(ev("e4", "fact two"))
    m = convergence.observe_round()
    assert m["novelty"]["ratio"] == 0.0 and m["novelty"]["diminishing"] is True
    # priority block present in metrics.
    assert "priority" in m and "structurally_converged" in m["priority"]
    print("novelty advance/snapshot OK")


def test_assess_recommendation():
    from agents.memory_manager import MemoryManager

    saved = convergence.compute_metrics
    try:
        # Structurally converged, no fatal/core -> stop.
        _set(queries=[q("h1", "sufficient", 0.8, tier="high")], conflicts=[])
        convergence.compute_metrics = lambda advance_novelty=False: {
            "priority": {"structurally_converged": True, "tier_counts": {"high": 1}},
            "novelty": {"diminishing": False},
        }
        mm = MemoryManager(
            model=FakeModel({"fatal_unresolved_conflicts": [], "core_threatening_gaps": [], "reason": "ok"})
        )
        out = mm.assess_convergence()
        assert out["recommendation"] == "stop" and out["converged"] is True, out

        # Structurally converged but a fatal conflict -> continue.
        mm = MemoryManager(
            model=FakeModel({"fatal_unresolved_conflicts": ["X vs Y"], "core_threatening_gaps": [], "reason": "c"})
        )
        out = mm.assess_convergence()
        assert out["recommendation"] == "continue" and out["fatal_unresolved_conflicts"] == ["X vs Y"], out

        # Diminishing but a high-priority query still pending -> keep going
        # (no premature stop / deadlock while obvious work remains).
        convergence.compute_metrics = lambda advance_novelty=False: {
            "priority": {"structurally_converged": False, "tier_counts": {"high": 2}, "pending_high_priority": True},
            "novelty": {"diminishing": True},
        }
        mm = MemoryManager(
            model=FakeModel({"fatal_unresolved_conflicts": [], "core_threatening_gaps": ["gap"], "reason": "d"})
        )
        out = mm.assess_convergence()
        assert out["recommendation"] == "continue", out

        # Diminishing with no pending high-priority work -> stop and disclose.
        convergence.compute_metrics = lambda advance_novelty=False: {
            "priority": {"structurally_converged": False, "tier_counts": {"high": 2}, "pending_high_priority": False},
            "novelty": {"diminishing": True},
        }
        mm = MemoryManager(
            model=FakeModel({"fatal_unresolved_conflicts": [], "core_threatening_gaps": ["gap"], "reason": "d"})
        )
        out = mm.assess_convergence()
        assert out["recommendation"] == "stop", out
    finally:
        convergence.compute_metrics = saved
    print("assess_convergence recommendation OK")


def test_assembly():
    from tools.graph_manager_tools import ORCHESTRATOR_TOOLS

    names = {t.name for t in ORCHESTRATOR_TOOLS}
    assert "assess_convergence" in names, names
    print("assembly OK")


def main():
    test_compute_priority()
    test_structurally_converged()
    test_novelty_advance_vs_snapshot()
    test_assess_recommendation()
    test_assembly()
    print("\nALL CONVERGENCE CHECKS PASSED")


if __name__ == "__main__":
    main()
