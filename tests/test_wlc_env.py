"""Regression checks for the WLC subprocess environment."""

# ruff: noqa: T201

import os
import sys
import tempfile
from pathlib import Path

repo_dir = Path(__file__).parent.parent
sys.path.insert(0, str(repo_dir))

import test_wlc as batch  # noqa: E402


def _test_wlc_env_overrides_parent_environment() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        wlc_root = Path(temp_dir)
        (wlc_root / ".env").write_text(
            "OPENAI_API_KEY=wlc-key\nOPENAI_BASE_URL=https://wlc.example/v1\n",
            encoding="utf-8",
        )
        original_key = os.environ.get("OPENAI_API_KEY")
        try:
            os.environ["OPENAI_API_KEY"] = "graphresearcher-key"
            env = batch.wlc_subprocess_env(wlc_root)
        finally:
            if original_key is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = original_key

        assert env["OPENAI_API_KEY"] == "wlc-key"
        assert env["OPENAI_BASE_URL"] == "https://wlc.example/v1"


def _test_missing_wlc_env_is_an_error() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            batch.wlc_subprocess_env(Path(temp_dir))
        except FileNotFoundError:
            return
        raise AssertionError("Expected a missing WLC .env to fail")


def _test_wlc_commands_receive_wlc_environment() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        gt_dir = root / "data" / "benchmark" / "wiki_data" / "cleaned_data" / "article"
        gt_dir.mkdir(parents=True)
        (root / ".env").write_text("OPENAI_API_KEY=wlc-key\n", encoding="utf-8")
        report_path = root / "report.md"
        report_path.write_text("# Report\n", encoding="utf-8")

        calls = []
        original_runner = batch.run_command_tee
        try:
            batch.run_command_tee = lambda command, cwd, log_path, env=None: calls.append(env)
            batch.run_wlc_evaluation(
                report_paths=[report_path],
                wlc_root=root,
                benchmark="benchmark",
                work_dir=root / "work",
                log_path=root / "work" / "official_output.log",
                python_bin=sys.executable,
                json_steps="extract",
                json_concurrency=None,
                max_workers=1,
                top_k=1,
                allow_tie=False,
            )
        finally:
            batch.run_command_tee = original_runner

        assert calls == [{"OPENAI_API_KEY": "wlc-key"}] * 2


def main() -> None:
    _test_wlc_env_overrides_parent_environment()
    _test_missing_wlc_env_is_an_error()
    _test_wlc_commands_receive_wlc_environment()
    print("WLC environment regression checks passed.")


if __name__ == "__main__":
    main()
