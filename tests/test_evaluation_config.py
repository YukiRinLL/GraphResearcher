"""统一评估配置的独立回归测试。"""

import sys
import tempfile
from pathlib import Path

SRC_DIR = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from benchmarking.config import load_config  # noqa: E402
from run_config import resolve_agent_config  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "evaluate.yaml"
        path.write_text(
            """version: 1
mode: run
seed: 7
sample_count: 2
benchmarks:
  deep_research_bench:
    enabled: true
""",
            encoding="utf-8",
        )
        config = load_config(path)
        assert config["seed"] == 7
        assert config["agent"]["max_rounds"] == 30
        assert config["agent"]["timeout_seconds"] == 7200
        assert "max_retries" not in config["agent"]
        assert resolve_agent_config(config["agent"], {})["max_retries"] == 3
        assert config["output"]["markdown_summary"] is True

        base_yaml = path.read_text(encoding="utf-8")
        for timeout in (-1, 1, 0.5, 7200):
            path.write_text(
                f"{base_yaml}agent:\n  timeout_seconds: {timeout}\n",
                encoding="utf-8",
            )
            assert load_config(path)["agent"]["timeout_seconds"] == timeout

        for timeout in (0, -2, -0.5):
            path.write_text(
                f"{base_yaml}agent:\n  timeout_seconds: {timeout}\n",
                encoding="utf-8",
            )
            try:
                load_config(path)
            except ValueError as exc:
                assert "agent.timeout_seconds" in str(exc)
            else:
                raise AssertionError(f"应拒绝无效超时配置：{timeout}")

        for max_retries in (0, 1, 3):
            path.write_text(
                f"{base_yaml}agent:\n  max_retries: {max_retries}\n",
                encoding="utf-8",
            )
            assert load_config(path)["agent"]["max_retries"] == max_retries

        for raw_value in ("-1", "0.5", "true", "false", "null", '"1"'):
            path.write_text(
                f"{base_yaml}agent:\n  max_retries: {raw_value}\n",
                encoding="utf-8",
            )
            try:
                load_config(path)
            except ValueError as exc:
                assert "agent.max_retries" in str(exc)
            else:
                raise AssertionError(f"应拒绝无效重试配置：{raw_value}")


if __name__ == "__main__":
    main()
