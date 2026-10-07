"""统一评估的抽样、Agent 运行、评测和汇总编排."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from benchmarking.adapters import evaluate_sample
from benchmarking.config import load_config
from benchmarking.runtime import (
    load_root_environment,
    now_iso,
    run_command,
    validate_evaluator_environment,
    write_json,
)
from benchmarking.summary import build_summary, render_markdown
from benchmarking.tasks import BenchmarkTask, load_tasks, select_tasks
from run_config import (
    agent_environment,
    benchmark_runtime_environment,
    resolve_agent_config,
    resolve_run_config,
    write_agent_snapshot,
)

logger = logging.getLogger(__name__)


def _run_id(config: dict[str, Any]) -> str:
    configured = config["output"].get("run_id")
    if configured:
        return str(configured)
    agent = config["agent"]["name"]
    return datetime.now().strftime(f"%Y%m%d-%H%M%S-{agent}")


def _git_commit(repo_root: Path) -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def _dataset_hashes(repo_root: Path, config: dict[str, Any]) -> dict[str, str]:
    wiki_dataset = config["benchmarks"].get("wiki_live_challenge", {}).get("selection", {}).get(
        "dataset", "2025_Mar_Nov"
    )
    paths = {
        "deep_research_bench": repo_root / "Benchmark/deep_research_bench/data/prompt_data/query.jsonl",
        "wiki_live_challenge": repo_root / f"Benchmark/Wiki_Live_Challenge/data/{wiki_dataset}/wiki_data/ga_100.json",
        "deep_research_bench_ii": repo_root / "Benchmark/DeepResearch-Bench-II/tasks_and_rubrics.jsonl",
    }
    return {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in paths.items()
        if path.is_file()
    }


def _evaluator_snapshot(config: dict[str, Any], env: dict[str, str]) -> dict[str, Any]:
    config = resolve_run_config(config, env)
    env = {
        **env,
        **{
            key: value
            for name, settings in config["benchmarks"].items()
            for key, value in benchmark_runtime_environment(name, settings["runtime"]).items()
        },
    }
    return {
        "benchmarks": config["benchmarks"],
        "models": {
            "deep_research_bench.race": env.get("DRB_RACE_MODEL", "gpt-5.5"),
            "deep_research_bench.fact": env.get("DRB_FACT_MODEL", "gpt-5.4-mini"),
            "wiki_live_challenge.extract": env.get("WLC_EXTRACT_MODEL", "gemini-2.5-flash"),
            "wiki_live_challenge.verifier": env.get("WLC_VERIFIER_MODEL", "gemini-2.5-flash"),
            "wiki_live_challenge.writing": env.get("WLC_WRITING_MODEL", "gemini-2.5-pro"),
            "wiki_live_challenge.embedding": env.get("WLC_EMBEDDING_MODEL", "text-embedding-3-small"),
            "deep_research_bench_ii": env.get("DRB2_OPENAI_MODEL", "gpt-5.5"),
        },
    }


def _task_from_dict(value: dict[str, Any]) -> BenchmarkTask:
    return BenchmarkTask(
        benchmark=value["benchmark"],
        sample_id=str(value["sample_id"]),
        display_name=value["display_name"],
        prompt=value["prompt"],
        metadata=value["metadata"],
    )


def _select(config: dict[str, Any], repo_root: Path) -> list[BenchmarkTask]:
    selected: list[BenchmarkTask] = []
    for benchmark, settings in config["benchmarks"].items():
        if not settings.get("enabled", False):
            continue
        count = settings.get("sample_count")
        if count is None:
            count = config.get("sample_count")
        selected.extend(select_tasks(load_tasks(repo_root, benchmark, settings), count, config["seed"], benchmark))
    return selected


def _sample_dir(run_dir: Path, task: BenchmarkTask) -> Path:
    safe_id = task.display_name.replace("/", "_").replace("\\", "_")
    return run_dir / "samples" / task.benchmark / safe_id


def _base_result(task: BenchmarkTask) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "benchmark": task.benchmark,
        "sample_id": task.sample_id,
        "display_name": task.display_name,
        "prompt_sha256": hashlib.sha256(task.prompt.encode()).hexdigest(),
        "run": {"status": "pending", "duration_seconds": None, "error": None},
        "evaluation": {"status": "pending", "duration_seconds": None, "phases": {}, "error": None},
        "metrics": {},
    }


def _read_result(path: Path, task: BenchmarkTask) -> dict[str, Any]:
    if not path.is_file():
        return _base_result(task)
    return json.loads(path.read_text(encoding="utf-8"))


def _run_agent(
    repo_root: Path,
    run_dir: Path,
    task: BenchmarkTask,
    config: dict[str, Any],
    env: dict[str, str],
) -> dict[str, Any]:
    sample_dir = _sample_dir(run_dir, task)
    sample_dir.mkdir(parents=True, exist_ok=True)
    result_path = sample_dir / "sample_result.json"
    result = _read_result(result_path, task)
    report_path = sample_dir / "report.md"
    if config["execution"]["resume"] and result["run"]["status"] == "completed" and report_path.is_file():
        return result
    write_json(sample_dir / "request.json", task.to_dict())
    started_at = now_iso()
    agent = resolve_agent_config(config["agent"], env)
    snapshot_path = sample_dir / "agent.effective.yaml"
    write_agent_snapshot(snapshot_path, agent)
    command = [
        sys.executable,
        str(repo_root / "main.py"),
        task.prompt,
        "--config",
        str(snapshot_path),
        "--output-dir",
        str(sample_dir),
        "--max-rounds",
        str(agent["max_rounds"]),
        "--verbose",
        agent["verbosity"],
    ]
    timeout = float(agent["timeout_seconds"])
    agent_env = {**env, **agent_environment(agent)}
    duration, error = run_command(
        command,
        repo_root,
        agent_env,
        sample_dir / "agent_process.log",
        timeout=None if timeout == -1 else timeout,
    )
    if error is None and not report_path.is_file():
        error = "Agent 进程结束后未生成 report.md。"
    result["run"] = {
        "status": "completed" if error is None else ("timeout" if error.startswith("超过") else "failed"),
        "started_at": started_at,
        "ended_at": now_iso(),
        "duration_seconds": duration,
        "report_path": str(report_path.relative_to(run_dir)) if report_path.is_file() else None,
        "error": error,
    }
    write_json(result_path, result)
    return result


def _native_report(config: dict[str, Any], task: BenchmarkTask, sample_dir: Path) -> Path | None:
    native = config["input"]["native"]
    destination = sample_dir / "report.md"
    if task.benchmark == "deep_research_bench" and native.get("deep_research_bench_jsonl"):
        source = Path(native["deep_research_bench_jsonl"]).resolve()
        rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
        row = next((item for item in rows if str(item.get("id")) == task.sample_id), None)
        if row:
            if row.get("prompt") != task.prompt:
                raise ValueError(f"DeepResearch Bench 样本 {task.sample_id} 的 prompt 与数据集不匹配。")
            destination.write_text(str(row.get("article", "")), encoding="utf-8")
            return destination
    if task.benchmark == "wiki_live_challenge" and native.get("wiki_live_challenge_markdown_dir"):
        source = Path(native["wiki_live_challenge_markdown_dir"]).resolve() / f"{task.display_name}.md"
        if source.is_file():
            shutil.copy2(source, destination)
            return destination
    if task.benchmark == "deep_research_bench_ii" and native.get("deep_research_bench_ii_report_dir"):
        source = Path(native["deep_research_bench_ii_report_dir"]).resolve() / f"idx-{task.sample_id}.md"
        if source.is_file():
            shutil.copy2(source, destination)
            return destination
    return destination if destination.is_file() else None


def _evaluate(
    repo_root: Path,
    run_dir: Path,
    evaluation_dir: Path,
    task: BenchmarkTask,
    config: dict[str, Any],
    env: dict[str, str],
) -> dict[str, Any]:
    sample_dir = _sample_dir(run_dir, task)
    sample_dir.mkdir(parents=True, exist_ok=True)
    result_path = sample_dir / "sample_result.json"
    result = _read_result(result_path, task)
    try:
        report_path = _native_report(config, task, sample_dir)
    except Exception as exc:  # noqa: BLE001 - 导入错误属于当前样本
        result["evaluation"] = {
            "status": "failed",
            "duration_seconds": 0.0,
            "phases": {},
            "error": str(exc),
        }
        write_json(result_path, result)
        write_json(evaluation_dir / "scores" / task.benchmark / f"{task.sample_id}.json", result)
        return result
    if report_path is None:
        result["evaluation"] = {
            "status": "failed",
            "duration_seconds": 0.0,
            "phases": {},
            "error": "未找到可评测的报告。",
        }
        write_json(result_path, result)
        return result
    if result["run"]["status"] == "pending":
        result["run"] = {"status": "skipped", "duration_seconds": None, "error": None}
    started_at = now_iso()
    started = time.perf_counter()
    try:
        metrics, phases = evaluate_sample(
            repo_root,
            task,
            report_path,
            evaluation_dir / task.benchmark / task.display_name,
            config["benchmarks"][task.benchmark],
            env,
        )
        result["metrics"] = metrics
        result["evaluation"] = {
            "status": "completed",
            "started_at": started_at,
            "ended_at": now_iso(),
            "duration_seconds": time.perf_counter() - started,
            "phases": phases,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 - 其他样本仍需继续评测
        result["evaluation"] = {
            "status": "failed",
            "started_at": started_at,
            "ended_at": now_iso(),
            "duration_seconds": time.perf_counter() - started,
            "phases": {},
            "error": str(exc),
        }
    write_json(result_path, result)
    write_json(evaluation_dir / "scores" / task.benchmark / f"{task.sample_id}.json", result)
    return result


def _warn_nested_envs(repo_root: Path) -> None:
    paths = [
        repo_root / "Benchmark/deep_research_bench/.env",
        repo_root / "Benchmark/Wiki_Live_Challenge/.env",
        repo_root / "Benchmark/DeepResearch-Bench-II/.env",
    ]
    existing = [str(path.relative_to(repo_root)) for path in paths if path.is_file()]
    if existing:
        logger.warning("已忽略 Benchmark 子目录的 .env：%s", ", ".join(existing))


def execute(config_path: Path, check_only: bool = False) -> None:
    """执行配置校验、Agent 运行、Benchmark 评测和汇总."""
    repo_root = Path(__file__).resolve().parents[2]
    config = load_config(config_path)
    env = load_root_environment(repo_root)
    config = resolve_run_config(config, env)
    validate_evaluator_environment(config, env)
    _warn_nested_envs(repo_root)

    source_run = config["input"].get("run_dir")
    if config["mode"] == "evaluate" and source_run:
        run_dir = Path(source_run).resolve()
        selection_path = run_dir / "selected_samples.jsonl"
        if not selection_path.is_file():
            raise ValueError(f"运行目录缺少 selected_samples.jsonl：{run_dir}")
        tasks = [_task_from_dict(json.loads(line)) for line in selection_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        tasks = [task for task in tasks if config["benchmarks"].get(task.benchmark, {}).get("enabled", False)]
    else:
        tasks = _select(config, repo_root)
        run_dir = Path(config["output"]["root"]).resolve() / _run_id(config)

    if check_only:
        counts: dict[str, int] = {}
        for task in tasks:
            counts[task.benchmark] = counts.get(task.benchmark, 0) + 1
        logger.info("配置校验通过，样本数：%s", counts)
        return

    run_dir.mkdir(parents=True, exist_ok=True)
    if not (run_dir / "selected_samples.jsonl").exists():
        with (run_dir / "selected_samples.jsonl").open("w", encoding="utf-8") as output:
            for task in tasks:
                output.write(json.dumps(task.to_dict(), ensure_ascii=False) + "\n")
    config_snapshot = run_dir / "config.snapshot.yaml"
    if not config_snapshot.exists():
        config_snapshot.write_text(config_path.read_text(encoding="utf-8"), encoding="utf-8")
    manifest_path = run_dir / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {
            "schema_version": 1,
            "run_id": run_dir.name,
            "mode": config["mode"],
            "seed": config["seed"],
            "git_commit": _git_commit(repo_root),
            "dataset_sha256": _dataset_hashes(repo_root, config),
            "started_at": now_iso(),
            "sample_count": len(tasks),
        }
    write_json(manifest_path, manifest)

    results: dict[tuple[str, str], dict[str, Any]] = {}
    if config["mode"] in {"run", "run_and_evaluate"}:
        with ThreadPoolExecutor(max_workers=int(config["agent"]["max_workers"])) as pool:
            futures = {pool.submit(_run_agent, repo_root, run_dir, task, config, env): task for task in tasks}
            for future in as_completed(futures):
                task = futures[future]
                try:
                    result = future.result()
                    results[(task.benchmark, task.sample_id)] = result
                    if config["execution"]["fail_fast"] and result["evaluation"]["status"] == "failed":
                        raise RuntimeError(result["evaluation"]["error"])
                except Exception as exc:  # noqa: BLE001 - 保留批次中其他样本
                    result = _base_result(task)
                    result["run"].update({"status": "failed", "error": str(exc)})
                    results[(task.benchmark, task.sample_id)] = result
                    write_json(_sample_dir(run_dir, task) / "sample_result.json", result)
                    if config["execution"]["fail_fast"]:
                        raise

    if config["mode"] in {"evaluate", "run_and_evaluate"}:
        evaluation_id = datetime.now().strftime("eval-%Y%m%d-%H%M%S-%f")
        evaluation_dir = run_dir / "evaluations" / evaluation_id
        evaluation_dir.mkdir(parents=True, exist_ok=True)
        write_json(evaluation_dir / "evaluator.snapshot.json", _evaluator_snapshot(config, env))
        evaluation_workers = int(config["execution"]["evaluation_max_workers"])
        with ThreadPoolExecutor(max_workers=evaluation_workers) as pool:
            futures = {
                pool.submit(_evaluate, repo_root, run_dir, evaluation_dir, task, config, env): task
                for task in tasks
                if _sample_dir(run_dir, task).joinpath("report.md").is_file()
                or config["mode"] == "evaluate"
            }
            for future in as_completed(futures):
                task = futures[future]
                try:
                    results[(task.benchmark, task.sample_id)] = future.result()
                except Exception as exc:  # noqa: BLE001 - 保留批次中其他样本
                    result = _read_result(_sample_dir(run_dir, task) / "sample_result.json", task)
                    result["evaluation"] = {
                        "status": "failed",
                        "duration_seconds": 0.0,
                        "phases": {},
                        "error": str(exc),
                    }
                    results[(task.benchmark, task.sample_id)] = result
                    write_json(_sample_dir(run_dir, task) / "sample_result.json", result)
                    if config["execution"]["fail_fast"]:
                        raise
        for task in tasks:
            key = (task.benchmark, task.sample_id)
            if key not in results:
                results[key] = _read_result(_sample_dir(run_dir, task) / "sample_result.json", task)
        summary = build_summary(list(results.values()))
        summary.update({"run_id": run_dir.name, "seed": config["seed"], "mode": config["mode"]})
        write_json(evaluation_dir / "summary.json", summary)
        if config["output"]["markdown_summary"]:
            (evaluation_dir / "summary.md").write_text(
                render_markdown(summary, run_dir.name, config["seed"], config["mode"]),
                encoding="utf-8",
            )
        manifest.setdefault("evaluations", []).append({"evaluation_id": evaluation_id, "completed_at": now_iso()})
        logger.info("评测完成：%s", evaluation_dir)
    else:
        summary = build_summary(list(results.values()))
        summary.update({"run_id": run_dir.name, "seed": config["seed"], "mode": config["mode"]})
        write_json(run_dir / "run_summary.json", summary)
        if config["output"]["markdown_summary"]:
            (run_dir / "run_summary.md").write_text(
                render_markdown(summary, run_dir.name, config["seed"], config["mode"]),
                encoding="utf-8",
            )
        logger.info("Agent 运行完成：%s", run_dir)
    manifest.setdefault("completed_at", now_iso())
    write_json(manifest_path, manifest)
