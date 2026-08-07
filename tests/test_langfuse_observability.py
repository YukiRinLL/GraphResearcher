"""Standalone regression checks for optional Langfuse observability."""

# ruff: noqa: T201

import sys
import types
from pathlib import Path

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

import observability  # noqa: E402


class FakeClient:
    """Capture flush calls without talking to a Langfuse server."""

    def __init__(self, error: Exception | None = None):
        self.error = error
        self.flush_calls = 0

    def flush(self):
        self.flush_calls += 1
        if self.error:
            raise self.error


class FakeCallbackHandler:
    """Stand in for Langfuse's LangChain callback."""


def _install_fake_langfuse(client: FakeClient) -> tuple[object | None, object | None]:
    """Install a minimal SDK surface and return the previous module entries."""
    old_root = sys.modules.get("langfuse")
    old_langchain = sys.modules.get("langfuse.langchain")
    root = types.ModuleType("langfuse")
    root.get_client = lambda: client
    langchain = types.ModuleType("langfuse.langchain")
    langchain.CallbackHandler = FakeCallbackHandler
    sys.modules["langfuse"] = root
    sys.modules["langfuse.langchain"] = langchain
    return old_root, old_langchain


def _restore_module(name: str, original: object | None) -> None:
    """Restore a module entry after an SDK-isolation test."""
    if original is None:
        sys.modules.pop(name, None)
    else:
        sys.modules[name] = original


def _test_unconfigured_run_is_inert():
    run = observability.start_langfuse_run(
        Path("outputs/example"),
        max_search_rounds=4,
        model_name="test-model",
        environ={},
    )
    assert not run.enabled
    assert run.langchain_config() == {}
    run.flush()


def _test_configured_run_builds_callback_and_metadata():
    client = FakeClient()
    old_root, old_langchain = _install_fake_langfuse(client)
    try:
        run = observability.start_langfuse_run(
            Path("outputs/example"),
            max_search_rounds=4,
            model_name="test-model",
            environ={"LANGFUSE_PUBLIC_KEY": "pk-test", "LANGFUSE_SECRET_KEY": "sk-test"},
        )
        config = run.langchain_config()
        assert run.enabled and len(run.session_id or "") == 32
        assert isinstance(config["callbacks"][0], FakeCallbackHandler)
        assert config["run_name"] == "graphresearcher.research"
        assert config["metadata"]["langfuse_session_id"] == run.session_id
        assert config["metadata"]["langfuse_tags"] == ["graphresearcher"]
        assert config["metadata"]["graphresearcher_model"] == "test-model"
        assert config["metadata"]["graphresearcher_max_search_rounds"] == 4
        assert config["metadata"]["graphresearcher_output_dir"] == "example"
        run.flush()
        assert client.flush_calls == 1
    finally:
        _restore_module("langfuse", old_root)
        _restore_module("langfuse.langchain", old_langchain)


def _test_flush_failure_does_not_escape():
    run = observability.LangfuseRun(client=FakeClient(RuntimeError("offline")))
    run.flush()


if __name__ == "__main__":
    _test_unconfigured_run_is_inert()
    _test_configured_run_builds_callback_and_metadata()
    _test_flush_failure_does_not_escape()
    print("All Langfuse observability tests passed.")
