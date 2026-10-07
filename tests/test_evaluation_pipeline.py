"""离线验证生成与评估的交接、独立并发和结果持久化。"""

import json
import sys
import tempfile
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from threading import Barrier, Event, Lock
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from benchmarking import orchestrator  # noqa: E402
from benchmarking.config import DEFAULTS  # noqa: E402
from benchmarking.tasks import BenchmarkTask  # noqa: E402


def setup(root, pipeline, generation_workers=1, evaluation_workers=1, mode="run_and_evaluate"):
    config = deepcopy(DEFAULTS)
    config["mode"] = mode
    config["agent"]["max_workers"] = generation_workers
    config["execution"].update(pipeline=pipeline, evaluation_max_workers=evaluation_workers)
    config["benchmarks"] = {"deep_research_bench": {"enabled": True}}
    config["output"].update(root=str(root), run_id="run")
    if mode == "evaluate":
        config["input"]["native"]["deep_research_bench_jsonl"] = str(root / "input.jsonl")
    path = root / "config.yaml"
    root.mkdir(parents=True)
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return config, path, root / "run"


def execute(path, tasks, generate, evaluate):
    with ExitStack() as stack:
        for name, value in {
            "load_root_environment": {}, "validate_evaluator_environment": None,
            "_warn_nested_envs": None, "_select": tasks,
            "_git_commit": "test", "_dataset_hashes": {},
        }.items():
            stack.enter_context(patch.object(orchestrator, name, return_value=value))
        stack.enter_context(patch.object(orchestrator, "run_command", side_effect=generate))
        stack.enter_context(patch.object(orchestrator, "evaluate_sample", side_effect=evaluate))
        orchestrator.execute(path)


def tasks_for(count):
    return [BenchmarkTask("deep_research_bench", str(i), str(i), f"prompt-{i}", {"id": i}) for i in range(count)]


def check_scheduling(root, pipeline, generation_workers, evaluation_workers):
    _, path, run_dir = setup(root, pipeline, generation_workers, evaluation_workers)
    tasks = tasks_for(generation_workers + evaluation_workers + 2)
    generation_wave = Barrier(generation_workers, timeout=5)
    evaluation_wave = Barrier(evaluation_workers, timeout=5)
    evaluation_started = Event()
    later_generation = Event()
    lock = Lock()
    active = {"generation": 0, "evaluation": 0}
    peak = dict(active)
    generated = set()
    evaluated = set()

    def enter(stage):
        with lock:
            active[stage] += 1
            peak[stage] = max(peak[stage], active[stage])

    def leave(stage):
        with lock:
            active[stage] -= 1

    def generate(command, _cwd, _env, log_path, timeout=None):
        sample_dir = log_path.parent
        index = int(sample_dir.name)
        enter("generation")
        try:
            # 报告提前出现也不能触发评分，必须等待本次生成任务返回并保存状态。
            (sample_dir / "report.md").write_text(f"report-{index}")
            if index < generation_workers:
                generation_wave.wait()
            if index >= evaluation_workers:
                if pipeline:
                    assert evaluation_started.wait(5), "评估必须能在后续生成结束前启动"
                later_generation.set()
            with lock:
                generated.add(index)
            return 0.01, None
        finally:
            leave("generation")

    def evaluate(_repo, task, report_path, output_dir, _settings, _env):
        index = int(task.sample_id)
        enter("evaluation")
        try:
            persisted = json.loads((report_path.parent / "sample_result.json").read_text())
            assert persisted["run"]["status"] == "completed"
            assert report_path.read_text() == f"report-{index}"
            assert (output_dir.parents[1] / "evaluator.snapshot.json").is_file()
            with lock:
                ordinal = len(evaluated)
                evaluated.add(index)
                assert index in generated
                if not pipeline:
                    assert len(generated) == len(tasks), "关闭流水线时应等待整批生成"
            if ordinal < evaluation_workers:
                evaluation_wave.wait()
                evaluation_started.set()
            if pipeline:
                assert later_generation.wait(5), "评分等待期间生成池应能继续执行"
            return {"race.overall_score": float(index)}, {"race": 0.01}
        finally:
            leave("evaluation")

    execute(path, tasks, generate, evaluate)
    assert generated == evaluated == set(range(len(tasks)))
    assert peak == {"generation": generation_workers, "evaluation": evaluation_workers}, peak
    assert active == {"generation": 0, "evaluation": 0}
    evaluation_dir, = (run_dir / "evaluations").iterdir()
    summary = json.loads((evaluation_dir / "summary.json").read_text())
    assert summary["benchmarks"]["deep_research_bench"]["evaluated"] == len(tasks)
    for task in tasks:
        result = json.loads((orchestrator._sample_dir(run_dir, task) / "sample_result.json").read_text())
        assert result["run"]["status"] == result["evaluation"]["status"] == "completed"
        assert result["metrics"] == {"race.overall_score": float(task.sample_id)}
        saved = json.loads((evaluation_dir / "scores" / task.benchmark / f"{task.sample_id}.json").read_text())
        assert saved == result


def check_resume_and_failures(root):
    _, path, run_dir = setup(root, True, 2, 2)
    tasks = tasks_for(5)
    resumed = tasks[0]
    sample_dir = orchestrator._sample_dir(run_dir, resumed)
    sample_dir.mkdir(parents=True)
    (sample_dir / "report.md").write_text("resumed")
    result = orchestrator._base_result(resumed)
    result["run"].update(status="completed", duration_seconds=42)
    orchestrator.write_json(sample_dir / "sample_result.json", result)
    generated, evaluated = set(), set()
    lock = Lock()

    def generate(_command, _cwd, _env, log_path, timeout=None):
        index = int(log_path.parent.name)
        assert index != 0, "已完成样本不应重新生成"
        with lock:
            generated.add(index)
        if index != 2:
            (log_path.parent / "report.md").write_text(f"report-{index}")
        return 0.01, "超过测试时限" if index == 1 else ("进程失败" if index == 2 else None)

    def evaluate(_repo, task, _report, _output, _settings, _env):
        with lock:
            evaluated.add(int(task.sample_id))
        if task.sample_id == "3":
            raise RuntimeError("离线评分失败")
        return {"score": 1.0}, {}

    execute(path, tasks, generate, evaluate)
    assert generated == {1, 2, 3, 4} and evaluated == {0, 1, 3, 4}
    for task, run_status, eval_status in zip(
        tasks, ("completed", "timeout", "failed", "completed", "completed"),
        ("completed", "completed", "pending", "failed", "completed"),
    ):
        result = json.loads((orchestrator._sample_dir(run_dir, task) / "sample_result.json").read_text())
        assert result["run"]["status"] == run_status, result
        assert result["evaluation"]["status"] == eval_status, result
        if task.sample_id == "0":
            assert result["run"]["duration_seconds"] == 42


def check_single_modes(root, mode):
    _, path, run_dir = setup(root, True, mode=mode)
    tasks = tasks_for(1)
    calls = []
    if mode == "evaluate":
        (root / "input.jsonl").write_text(json.dumps({"id": 0, "prompt": "prompt-0", "article": "native"}) + "\n")

    def generate(_command, _cwd, _env, log_path, timeout=None):
        calls.append("run")
        (log_path.parent / "report.md").write_text("generated")
        return 0.01, None

    def evaluate(_repo, _task, report, _output, _settings, _env):
        calls.append("evaluate")
        assert report.read_text() == "native"
        return {"score": 1.0}, {}

    execute(path, tasks, generate, evaluate)
    assert calls == [mode]
    assert (run_dir / "evaluations").exists() is (mode == "evaluate")


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for pipeline, generators, evaluators in ((True, 1, 1), (True, 2, 2), (True, 2, 1), (True, 1, 2), (False, 2, 2)):
            check_scheduling(root / f"{pipeline}-{generators}-{evaluators}", pipeline, generators, evaluators)
        check_resume_and_failures(root / "resume")
        for mode in ("run", "evaluate"):
            check_single_modes(root / mode, mode)


if __name__ == "__main__":
    main()
