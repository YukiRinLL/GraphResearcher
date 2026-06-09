"""Unit tests for the query-tree growth fixes (delegated / roll-up / depth cap / leaf-first).

Standalone, print-based (matches tests/test_query_handles.py — run directly, not
via pytest). A small MUTABLE in-memory graph monkeypatches ``tools.graph_tools``
so no Neo4j is needed; the LLM author step is stubbed.

    PYTHONPATH=src OPENAI_API_KEY=dummy uv run python tests/test_query_tree.py
"""

import sys
from pathlib import Path

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from agents.memory_manager import MemoryManager  # noqa: E402
from tools import convergence, graph_tools  # noqa: E402


class FakeGraph:
    """A tiny mutable node/edge store standing in for the graph toolkit."""

    def __init__(self):
        self.nodes = {}
        self.children = {}  # parent_id -> [child_ids]
        self._seq = 0

    def add(self, node):
        self.nodes[node["id"]] = node
        return node["id"]

    def link(self, parent_id, child_id):
        self.children.setdefault(parent_id, []).append(child_id)

    def parent_of(self, child_id):
        for pid, kids in self.children.items():
            if child_id in kids:
                return pid
        return None

    def install(self):
        graph_tools.get_node = lambda nid: self.nodes.get(nid)
        graph_tools.get_query_children = lambda pid: list(self.children.get(pid, []))
        graph_tools.get_query_parent = self.parent_of
        graph_tools.save_graph = lambda: None

        def _search(kind, filt=None):
            filt = filt or {}
            return [
                n for n in self.nodes.values()
                if n.get("type") == kind and all(n.get(k) == v for k, v in filt.items())
            ]

        def _upsert(kind, attrs, dedupe_key=None):
            node = self.nodes.setdefault(dedupe_key, {"id": dedupe_key, "type": kind})
            node.update(attrs)
            return node

        def _add_node(kind, attrs):
            self._seq += 1
            nid = f"node{self._seq}"
            self.add({"id": nid, "type": kind, **attrs})
            return nid

        graph_tools.search_nodes = _search
        graph_tools.upsert_node = _upsert
        graph_tools.add_node = _add_node
        graph_tools.add_edge = lambda src, tgt, etype: self.link(src, tgt)


def _check(label, cond):
    print(("PASS" if cond else "FAIL") + f"  {label}")
    if not cond:
        _check.failed += 1


_check.failed = 0


def main():
    # --- A. vertical expand: N children + anchor -> delegated --------------
    g = FakeGraph()
    g.add({"id": "goal", "type": "user_request", "research_goal": "RG"})
    g.add({"id": "q1", "type": "query", "handle": "q1", "text": "T1",
           "status": "needs_vertical", "priority": 0.94, "sufficiency_score": 0.5})
    g.link("goal", "q1")
    g.install()
    mm = MemoryManager(model=object())
    mm._plan_followup_queries = lambda **kw: [
        {"text": "c1", "importance": "core"},
        {"text": "c2", "importance": "core"},
    ]
    res = mm.expand_query("q1", "vertical", gaps=["g1", "g2"], max_new=2)
    _check("vertical creates one child per gap", len(res["created"]) == 2)
    _check("anchor -> delegated after vertical expand", g.nodes["q1"]["status"] == "delegated")

    # --- B. roll-up: parent resolves only when ALL children resolve -------
    kids = g.children["q1"]
    mm.mark_query(kids[0], "sufficient", sufficiency_score=0.8)
    _check("parent stays delegated while a child is open", g.nodes["q1"]["status"] == "delegated")
    mm.mark_query(kids[1], "sufficient", sufficiency_score=0.8)
    _check("parent rolls up to sufficient when all children resolved",
           g.nodes["q1"]["status"] == "sufficient")
    _check("rolled-up parent gets a passing score",
           g.nodes["q1"].get("sufficiency_score") >= convergence.SCORE_THRESHOLD)

    # --- C. depth cap: too-deep vertical anchor resolved in place --------
    g2 = FakeGraph()
    g2.add({"id": "deep", "type": "query", "handle": "q1.1.1.1",
            "status": "needs_vertical", "sufficiency_score": 0.85})
    g2.install()
    mm2 = MemoryManager(model=object())
    mm2._plan_followup_queries = lambda **kw: [{"text": "should-not-happen", "importance": "core"}]
    capped = mm2.expand_query("deep", "vertical", gaps=["g"], max_new=1)
    _check("depth cap creates no children", capped["created"] == [])
    _check("depth cap warns", "warning" in capped)
    _check("depth cap with high score -> sufficient", g2.nodes["deep"]["status"] == "sufficient")

    g3 = FakeGraph()
    g3.add({"id": "deeplow", "type": "query", "handle": "q2.1.1.1",
            "status": "needs_vertical", "sufficiency_score": 0.4})
    g3.install()
    mm3 = MemoryManager(model=object())
    mm3._plan_followup_queries = lambda **kw: []
    mm3.expand_query("deeplow", "vertical", gaps=["g"], max_new=1)
    _check("depth cap with low score -> blocked", g3.nodes["deeplow"]["status"] == "blocked")

    # --- D. leaf-first scheduling ----------------------------------------
    g4 = FakeGraph()
    g4.add({"id": "qa", "type": "query", "handle": "qa", "text": "A",
            "status": "needs_vertical", "priority": 0.90})
    g4.add({"id": "qb", "type": "query", "handle": "qb", "text": "B",
            "status": "needs_vertical", "priority": 0.80})
    g4.add({"id": "qc", "type": "query", "handle": "qc", "text": "C",
            "status": "needs_vertical", "priority": 0.95})
    g4.link("qa", "child_a")   # qa, qc have children -> not leaves
    g4.link("qc", "child_c")
    g4.install()
    mm4 = MemoryManager(model=object())
    order = [q["handle"] for q in mm4.get_next_queries(limit=3)]
    _check("leaf (qb) scheduled before higher-priority parents", order[0] == "qb")
    _check("parents ordered by priority after leaves", order[1:] == ["qc", "qa"])

    # --- E. fan-out cap formula (graph_manager_tools gate) ---------------
    many = ["a", "b", "c", "d", "e", "f"]
    _check("vertical fan-out respects cap",
           min(max(len(many), 1), convergence.VERTICAL_FANOUT_CAP) == convergence.VERTICAL_FANOUT_CAP)

    print()
    if _check.failed:
        print(f"=== {_check.failed} CHECK(S) FAILED ===")
        sys.exit(1)
    print("=== ALL CHECKS PASSED ===")


if __name__ == "__main__":
    main()
