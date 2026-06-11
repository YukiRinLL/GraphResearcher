"""Unit tests for query handles + robust ID resolution (run14 follow-up).

Standalone, print-based (matches tests/test_graph_tools.py style — run directly,
not via pytest). Monkeypatches ``tools.graph_tools`` so no Neo4j is needed.

    PYTHONPATH=src OPENAI_API_KEY=dummy uv run python tests/test_query_handles.py
"""

import sys
from pathlib import Path

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from agents.memory_manager import MemoryManager  # noqa: E402
from tools import graph_tools  # noqa: E402

# --- Fake graph (3 queries; q3.1 is the run14 victim) --------------------
GOAL = {"id": "20260608000000000000_g0000000", "type": "user_request"}
Q1 = {"id": "20260608000000000001_aaaa1111", "type": "query", "handle": "q1", "text": "技术路线分类"}
Q2 = {"id": "20260608000000000002_bbbb2222", "type": "query", "handle": "q2", "text": "代表公司"}
Q31 = {"id": "20260608180955461049_e9241aa9", "type": "query", "handle": "q3.1", "text": "商业化落地"}
NODES = {n["id"]: n for n in (GOAL, Q1, Q2, Q31)}
QUERIES = [Q1, Q2, Q31]

_calls = {"create_analysis": 0, "add_node": 0}


def _install_fakes():
    graph_tools.get_node = lambda nid: NODES.get(nid)
    graph_tools.search_nodes = lambda kind, filt=None: list(QUERIES) if kind == "query" else []

    def _add_node(kind, attrs):
        _calls["add_node"] += 1
        return "new_node_id"

    def _create_analysis(text, query_id=None, analysis_type="insight", **attrs):
        _calls["create_analysis"] += 1
        return f"analysis-for-{query_id}"

    graph_tools.add_node = _add_node
    graph_tools.create_analysis = _create_analysis


def _check(label, cond):
    print(("PASS" if cond else "FAIL") + f"  {label}")
    if not cond:
        _check.failed += 1


_check.failed = 0


def main():
    _install_fakes()
    mm = MemoryManager(model=object())

    # --- _resolve_query_id -------------------------------------------------
    _check("handle 'q3.1' -> real id", mm._resolve_query_id("q3.1") == Q31["id"])
    _check("exact id -> itself", mm._resolve_query_id(Q1["id"]) == Q1["id"])
    # The run14 corruption: timestamp prefix mangled, _<uuid8> suffix intact.
    _check(
        "corrupted prefix '20220208...e9241aa9' recovered via suffix",
        mm._resolve_query_id("20220208180955461049_e9241aa9") == Q31["id"],
    )
    _check("pure garbage -> None", mm._resolve_query_id("totally-bogus") is None)
    _check("empty -> None", mm._resolve_query_id("") is None)

    # --- insight binding resolves handles and rejects unknown refs ----------
    _install_fakes()
    _calls["create_analysis"] = 0
    r = mm.create_insight("note", "totally-bogus")
    _check("create_insight(bogus) returns error", isinstance(r, dict) and "error" in r)
    _check("create_insight(bogus) wrote nothing", _calls["create_analysis"] == 0)
    r2 = mm.create_insight("note", "q3.1")
    _check("create_insight('q3.1') resolves real id", r2.get("query_id") == Q31["id"])

    # --- submit_search_result hard-fail (no orphan run) --------------------
    _install_fakes()
    _calls["add_node"] = 0
    out = mm.submit_search_result("missing-run", "totally-bogus", {})
    _check("submit(bogus) written all zero", out.get("written", {}).get("evidence") == 0)
    _check("submit(bogus) has error + no search_run", out.get("error") and out.get("search_run_id") is None)
    _check("submit(bogus) wrote NO node", _calls["add_node"] == 0)

    print()
    if _check.failed:
        print(f"=== {_check.failed} CHECK(S) FAILED ===")
        sys.exit(1)
    print("=== ALL CHECKS PASSED ===")


if __name__ == "__main__":
    main()
