"""用本地子进程验证样本总耗时限制，不调用模型或数据库。"""

import sys
import tempfile
from copy import deepcopy
from pathlib import Path

SRC_DIR = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from benchmarking.config import DEFAULTS  # noqa: E402
from benchmarking.orchestrator import _run_agent  # noqa: E402
from benchmarking.tasks import BenchmarkTask  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        repo_root = Path(directory)
        (repo_root / "main.py").write_text(
            """import sys
import time
from pathlib import Path

time.sleep(0.2)
output_dir = Path(sys.argv[sys.argv.index("--output-dir") + 1])
(output_dir / "report.md").write_text("本地测试报告", encoding="utf-8")
""",
            encoding="utf-8",
        )
        task = BenchmarkTask("deep_research_bench", "1", "1", "本地测试", {})
        for index, (timeout, expected_status) in enumerate(
            ((-1, "completed"), (5, "completed"), (0.05, "timeout"))
        ):
            config = deepcopy(DEFAULTS)
            config["agent"]["timeout_seconds"] = timeout
            run_dir = repo_root / f"run-{index}"
            result = _run_agent(repo_root, run_dir, task, config, {})
            assert result["run"]["status"] == expected_status, result
            assert result["run"]["duration_seconds"] >= 0
            if expected_status == "completed":
                assert result["run"]["error"] is None
                report_path = run_dir / result["run"]["report_path"]
                assert report_path.read_text(encoding="utf-8") == "本地测试报告"
            else:
                assert result["run"]["error"] == f"超过 {timeout} 秒时限"
                assert result["run"]["report_path"] is None


if __name__ == "__main__":
    main()
