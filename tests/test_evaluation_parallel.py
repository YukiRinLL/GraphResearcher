"""离线验证样本并发上限和独立输出，不调用模型或数据库。"""

import json
import sys
import tempfile
import time
from copy import deepcopy
from pathlib import Path
from threading import Barrier, Lock
from unittest.mock import patch

import yaml

SRC_DIR = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from benchmarking import orchestrator  # noqa: E402
from benchmarking.config import DEFAULTS  # noqa: E402
from benchmarking.tasks import BenchmarkTask  # noqa: E402


def check_parallel_run(root: Path, workers: int) -> None:
    config = deepcopy(DEFAULTS)
    config["mode"] = "run"
    config["sample_count"] = 5
    config["benchmarks"] = {"deep_research_bench": {"enabled": True}}
    config["output"]["root"] = str(root / "outputs")
    config["output"]["run_id"] = f"workers-{workers}"
    if workers != 1:
        config["agent"]["max_workers"] = workers
    else:
        del config["agent"]["max_workers"]
    config_path = root / f"config-{workers}.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    tasks = [BenchmarkTask("deep_research_bench", str(i), str(i), f"request-{i}", {}) for i in range(5)]
    activity = {"active": 0, "peak": 0, "entered": 0}
    lock = Lock()
    first_wave = Barrier(workers, timeout=5)

    def fake_run_command(command, cwd, env, log_path, timeout=None):
        with lock:
            activity["active"] += 1
            activity["entered"] += 1
            activity["peak"] = max(activity["peak"], activity["active"])
            synchronize = activity["entered"] <= workers
        try:
            if synchronize:
                first_wave.wait()
            time.sleep(0.02)
            output_dir = Path(command[command.index("--output-dir") + 1])
            assert output_dir == log_path.parent
            (output_dir / "report.md").write_text(command[2], encoding="utf-8")
            log_path.write_text(command[2], encoding="utf-8")
            return 0.02, None
        finally:
            with lock:
                activity["active"] -= 1

    with (
        patch.object(orchestrator, "load_root_environment", return_value={}),
        patch.object(orchestrator, "validate_evaluator_environment"),
        patch.object(orchestrator, "_warn_nested_envs"),
        patch.object(orchestrator, "_select", return_value=tasks),
        patch.object(orchestrator, "_git_commit", return_value="test"),
        patch.object(orchestrator, "_dataset_hashes", return_value={}),
        patch.object(orchestrator, "run_command", side_effect=fake_run_command),
    ):
        orchestrator.execute(config_path)

    assert activity == {"active": 0, "peak": workers, "entered": 5}, activity
    run_dir = Path(config["output"]["root"]) / config["output"]["run_id"]
    for task in tasks:
        sample_dir = run_dir / "samples" / task.benchmark / task.display_name
        assert (sample_dir / "report.md").read_text(encoding="utf-8") == task.prompt
        assert (sample_dir / "agent_process.log").read_text(encoding="utf-8") == task.prompt
        request = json.loads((sample_dir / "request.json").read_text(encoding="utf-8"))
        assert request["sample_id"] == task.sample_id
        result = json.loads((sample_dir / "sample_result.json").read_text(encoding="utf-8"))
        assert result["sample_id"] == task.sample_id
        assert result["run"]["status"] == "completed"
        assert result["run"]["report_path"] == str((sample_dir / "report.md").relative_to(run_dir))


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        for workers in (1, 3):
            check_parallel_run(Path(directory), workers)


if __name__ == "__main__":
    main()
