"""Regression checks for stable Neo4j run contexts and rerun cleanup."""

import asyncio
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

repo_dir = Path(__file__).parent.parent
sys.path.insert(0, str(repo_dir / "src"))

from memory.graph import GraphManager  # noqa: E402
from tools import graph_manager_tools, graph_tools  # noqa: E402


class _FakeResult:
    async def consume(self):
        return None


class _FakeSession:
    def __init__(self, calls):
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def run(self, query, **params):
        self.calls.append((query, params))
        return _FakeResult()


def _test_graph_manager_clear_context():
    calls = []
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


def _test_configure_uses_stable_context_and_clears_each_rerun():
    contexts = []
    cleared = []
    events = []
    original_set_context = graph_tools.set_context
    original_clear = graph_tools.clear_current_context

    def set_context(context):
        contexts.append(context)
        events.append(("set", context))

    def clear_context():
        cleared.append(contexts[-1])
        events.append(("clear", contexts[-1]))

    try:
        graph_tools.set_context = set_context
        graph_tools.clear_current_context = clear_context
        from tools import convergence

        original_reset = convergence.reset
        convergence.reset = lambda: events.append(("reset", contexts[-1]))
        try:
            with TemporaryDirectory() as temp_dir:
                graph_manager_tools.configure(temp_dir)
                graph_manager_tools.configure(temp_dir)
        finally:
            convergence.reset = original_reset
    finally:
        graph_tools.set_context = original_set_context
        graph_tools.clear_current_context = original_clear

    assert len(contexts) == 2 and contexts[0] == contexts[1]
    assert all("::" not in context for context in contexts)
    assert cleared == contexts
    assert events == [
        ("set", contexts[0]),
        ("clear", contexts[0]),
        ("reset", contexts[0]),
        ("set", contexts[0]),
        ("clear", contexts[0]),
        ("reset", contexts[0]),
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
    _test_configure_uses_stable_context_and_clears_each_rerun()
    _test_clear_current_context_rejects_empty_context()
    print("ALL GRAPH CONTEXT CHECKS PASSED")


if __name__ == "__main__":
    main()
