"""Offline checks for the API-consuming Reporter replay entry point."""

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

import replay_reporter_workflow as replay  # noqa: E402


class _FakeLangfuseRun:
    enabled = True
    session_id = "replay-session"

    def __init__(self):
        self.flushed = False

    def langchain_config(self):
        return {
            "callbacks": ["langfuse-callback"],
            "run_name": "graphresearcher.research",
            "metadata": {"langfuse_session_id": self.session_id},
        }

    def flush(self):
        self.flushed = True


def _write_source_run(path: Path) -> None:
    path.mkdir()
    (path / "input.json").write_text(
        json.dumps({"id": "fixture", "question": "Write a report."}),
        encoding="utf-8",
    )
    records = [
        {"type": "_graphresearcher", "source": "test"},
        {
            "kind": "node",
            "id": "goal",
            "type": "UserRequest",
            "request": "Write a report.",
            "research_state": "COMPLETED",
            "reporting_from_state": "REPORT_READY",
        },
    ]
    (path / "research_graph.jsonl").write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def test_replay_passes_langfuse_config_and_flushes():
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        source_run = temp_path / "source"
        output_dir = temp_path / "output"
        _write_source_run(source_run)
        langfuse_run = _FakeLangfuseRun()
        observed = {}

        def start_langfuse_run(**kwargs):
            observed["langfuse_start"] = kwargs
            return langfuse_run

        def run_report_workflow(*, runnable_config):
            observed["runnable_config"] = runnable_config
            replay.graph_manager_tools._compiled_report = "# Replayed report\n"
            return {
                "success": True,
                "delivered": True,
                "validated": True,
                "review_status": "passed",
                "fallback_reason": None,
                "error": None,
            }

        with (
            patch.object(replay, "start_langfuse_run", start_langfuse_run),
            patch.object(replay, "run_report_workflow", run_report_workflow),
        ):
            result = replay.run_replay(source_run, output_dir, enable_langfuse=True)

        assert observed["langfuse_start"]["output_dir"] == output_dir
        assert observed["runnable_config"]["callbacks"] == ["langfuse-callback"]
        assert (
            observed["runnable_config"]["run_name"] == "graphresearcher.reporter-replay"
        )
        assert observed["runnable_config"]["metadata"]["replay_source_run"] == "source"
        assert langfuse_run.flushed
        assert result["langfuse_enabled"]
        assert result["langfuse_session_id"] == "replay-session"
        assert (
            (output_dir / "report.md")
            .read_text(encoding="utf-8")
            .startswith("# Replayed")
        )
        replay_graph = [
            json.loads(line)
            for line in (output_dir / "research_graph.replay.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        replay_goal = next(
            record
            for record in replay_graph
            if record.get("kind") == "node" and record.get("type") == "UserRequest"
        )
        assert replay_goal["research_state"] == "COMPLETED"


def test_replay_records_failure_and_flushes():
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        source_run = temp_path / "source"
        output_dir = temp_path / "output"
        _write_source_run(source_run)
        langfuse_run = _FakeLangfuseRun()

        def fail_workflow(*, runnable_config):
            assert runnable_config["callbacks"] == ["langfuse-callback"]
            raise RuntimeError("provider unavailable")

        with (
            patch.object(replay, "start_langfuse_run", lambda **_kwargs: langfuse_run),
            patch.object(replay, "run_report_workflow", fail_workflow),
        ):
            try:
                replay.run_replay(source_run, output_dir, enable_langfuse=True)
            except RuntimeError as exc:
                assert str(exc) == "provider unavailable"
            else:
                raise AssertionError("Replay failure was not propagated")

        failure = json.loads(
            (output_dir / "replay_result.json").read_text(encoding="utf-8")
        )
        assert failure["status"] == "failed"
        assert failure["error"] == "RuntimeError: provider unavailable"
        assert failure["langfuse_session_id"] == "replay-session"
        assert (output_dir / "research_graph.replay.jsonl").is_file()
        assert langfuse_run.flushed


if __name__ == "__main__":
    test_replay_passes_langfuse_config_and_flushes()
    test_replay_records_failure_and_flushes()
    print("ALL REPORTER REPLAY CHECKS PASSED")  # noqa: T201
