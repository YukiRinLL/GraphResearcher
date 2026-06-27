"""Regression checks for stable Neo4j run contexts and rerun cleanup."""

import asyncio
import sys
from pathlib import Path

repo_dir = Path(__file__).parent.parent
sys.path.insert(0, str(repo_dir / "src"))

import memory.graph as graph_module  # noqa: E402
from memory.graph import GraphManager  # noqa: E402
from tools import graph_tools  # noqa: E402


class _FakeResult:
    def __init__(self, record=None, records=None):
        self.record = record
        self.records = records or []

    async def consume(self):
        return None

    async def single(self):
        return self.record

    def __aiter__(self):
        async def _iterate():
            for record in self.records:
                yield record
        return _iterate()


class _FakeSession:
    def __init__(self, calls, result_factory=None):
        self.calls = calls
        self.result_factory = result_factory or (lambda query, params: _FakeResult())

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def run(self, query, **params):
        self.calls.append((query, params))
        return self.result_factory(query, params)


class _FakeNode(dict):
    pass


def _test_graph_manager_clear_context():
    calls = []
    original_available = graph_module.NEO4J_AVAILABLE
    try:
        graph_module.NEO4J_AVAILABLE = True
        manager = GraphManager(context="outputs/rag_run22")

        async def get_session():
            return _FakeSession(calls)

        manager._get_session = get_session
        asyncio.run(manager.clear_context())

        query, params = calls[0]
        assert "n.context = $context" in query
        assert "STARTS WITH" not in query
        assert params == {"context": "outputs/rag_run22"}

        empty = GraphManager(context=None)
        try:
            asyncio.run(empty.clear_context())
        except ValueError:
            pass
        else:
            raise AssertionError("clear_context must reject an empty context")
    finally:
        graph_module.NEO4J_AVAILABLE = original_available


def _test_graph_property_round_trip_helpers():
    original = {
        "report_delivery_mode": "compiled_reporter",
        "report_validation_issues": ["one", "two"],
        "report_attempt_summary": {
            "accepted": True,
            "issues": [{
                "code": "quality_gate_failed",
                "severity": "soft",
                "message": "report contains multiple or variant references sections",
            }],
        },
    }
    encoded = graph_module._encode_properties(original)
    assert encoded["report_validation_issues"] == ["one", "two"]
    assert isinstance(encoded["report_attempt_summary"], str)
    assert encoded["report_attempt_summary"].startswith(graph_module._JSON_SENTINEL)
    assert graph_module._decode_properties(encoded) == original


def _test_graph_manager_add_node_encodes_complex_properties():
    calls = []
    original_available = graph_module.NEO4J_AVAILABLE
    try:
        graph_module.NEO4J_AVAILABLE = True
        manager = GraphManager(context="outputs/rag_run22")

        async def get_session():
            return _FakeSession(calls, lambda query, params: _FakeResult({"n.id": params["id"]}))

        manager._get_session = get_session
        asyncio.run(manager.add_node("UserRequest", {
            "report_attempt_summary": {
                "accepted": True,
                "issues": [{"code": "quality_gate_failed", "message": "x"}],
            },
            "report_validation_issues": ["warning"],
        }, node_id="goal"))

        _, params = calls[0]
        assert params["properties"]["report_validation_issues"] == ["warning"]
        assert isinstance(params["properties"]["report_attempt_summary"], str)
        assert params["properties"]["report_attempt_summary"].startswith(graph_module._JSON_SENTINEL)
    finally:
        graph_module.NEO4J_AVAILABLE = original_available


def _test_graph_manager_upsert_node_encodes_complex_properties():
    calls = []
    original_available = graph_module.NEO4J_AVAILABLE
    try:
        graph_module.NEO4J_AVAILABLE = True
        manager = GraphManager(context="outputs/rag_run22")

        async def get_session():
            return _FakeSession(calls, lambda query, params: _FakeResult({"n.id": params["id"]}))

        manager._get_session = get_session
        asyncio.run(manager.upsert_node("UserRequest", {
            "report_attempt_summary": {
                "accepted": True,
                "issues": [{"code": "quality_gate_failed", "message": "x"}],
            },
        }, dedupe_key="goal"))

        _, params = calls[0]
        assert isinstance(params["properties"]["report_attempt_summary"], str)
        assert params["properties"]["report_attempt_summary"].startswith(graph_module._JSON_SENTINEL)
    finally:
        graph_module.NEO4J_AVAILABLE = original_available


def _test_graph_manager_get_node_decodes_complex_properties():
    calls = []
    original_available = graph_module.NEO4J_AVAILABLE
    try:
        graph_module.NEO4J_AVAILABLE = True
        manager = GraphManager(context="outputs/rag_run22")
        encoded_summary = graph_module._encode_property_value({
            "accepted": True,
            "issues": [{"code": "quality_gate_failed", "message": "x"}],
        })

        async def get_session():
            return _FakeSession(
                calls,
                lambda query, params: _FakeResult({
                    "n": _FakeNode({
                        "id": "goal",
                        "context": "outputs/rag_run22",
                        "report_attempt_summary": encoded_summary,
                        "report_validation_issues": ["warning"],
                    }),
                    "labels": ["UserRequest"],
                }),
            )

        manager._get_session = get_session
        node = asyncio.run(manager.get_node("goal"))

        assert node["report_validation_issues"] == ["warning"]
        assert node["report_attempt_summary"] == {
            "accepted": True,
            "issues": [{"code": "quality_gate_failed", "message": "x"}],
        }
    finally:
        graph_module.NEO4J_AVAILABLE = original_available


def _test_graph_manager_search_node_encodes_filter_values():
    calls = []
    original_available = graph_module.NEO4J_AVAILABLE
    try:
        graph_module.NEO4J_AVAILABLE = True
        manager = GraphManager(context="outputs/rag_run22")

        async def get_session():
            return _FakeSession(calls, lambda query, params: _FakeResult(records=[]))

        manager._get_session = get_session
        asyncio.run(manager.search_node("user_request", {
            "report_attempt_summary": {
                "accepted": True,
                "issues": [{"code": "quality_gate_failed"}],
            }
        }))

        _, params = calls[0]
        assert isinstance(params["param0"], str)
        assert params["param0"].startswith(graph_module._JSON_SENTINEL)
    finally:
        graph_module.NEO4J_AVAILABLE = original_available


def _test_configure_uses_stable_context_and_clears_each_rerun():
    try:
        from tools import graph_manager_tools  # noqa: E402
    except ImportError:
        return
    contexts = []
    cleared = []
    events = []
    original_set_context = graph_tools.set_context
    original_clear = graph_tools.clear_current_context
    original_compiled_report_path = graph_manager_tools._compiled_report_path

    def set_context(context):
        contexts.append(context)
        events.append(("set", context))

    def clear_context():
        cleared.append(contexts[-1])
        events.append(("clear", contexts[-1]))

    try:
        graph_tools.set_context = set_context
        graph_tools.clear_current_context = clear_context
        graph_manager_tools._compiled_report_path = lambda: None

        from tools import convergence

        original_reset = convergence.reset
        convergence.reset = lambda: events.append(("reset", contexts[-1]))
        try:
            graph_manager_tools.configure("outputs/rag_run22")
            graph_manager_tools.configure("outputs/rag_run22")
        finally:
            convergence.reset = original_reset
    finally:
        graph_tools.set_context = original_set_context
        graph_tools.clear_current_context = original_clear
        graph_manager_tools._compiled_report_path = original_compiled_report_path

    assert contexts == ["outputs/rag_run22", "outputs/rag_run22"]
    assert all("::" not in context for context in contexts)
    assert cleared == contexts
    assert events == [
        ("set", "outputs/rag_run22"),
        ("clear", "outputs/rag_run22"),
        ("reset", "outputs/rag_run22"),
        ("set", "outputs/rag_run22"),
        ("clear", "outputs/rag_run22"),
        ("reset", "outputs/rag_run22"),
    ]


def _test_clear_current_context_rejects_empty_context():
    original_context = graph_tools._context
    try:
        graph_tools._context = None
        try:
            graph_tools.clear_current_context()
        except ValueError:
            pass
        else:
            raise AssertionError("clear_current_context must reject an empty context")
    finally:
        graph_tools._context = original_context


def main():
    _test_graph_manager_clear_context()
    _test_graph_property_round_trip_helpers()
    _test_graph_manager_add_node_encodes_complex_properties()
    _test_graph_manager_upsert_node_encodes_complex_properties()
    _test_graph_manager_get_node_decodes_complex_properties()
    _test_graph_manager_search_node_encodes_filter_values()
    _test_configure_uses_stable_context_and_clears_each_rerun()
    _test_clear_current_context_rejects_empty_context()
    print("ALL GRAPH CONTEXT CHECKS PASSED")


if __name__ == "__main__":
    main()
