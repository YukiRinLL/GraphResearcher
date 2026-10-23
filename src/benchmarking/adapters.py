"""三套 Benchmark 的原生格式和评测命令适配."""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from benchmarking.runtime import benchmark_environment, read_json, run_command
from benchmarking.tasks import BenchmarkTask


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _run(
    command: list[str],
    cwd: Path,
    env: dict[str, str],
    output_dir: Path,
    phase: str,
) -> tuple[float, str | None]:
    return run_command(command, cwd, env, output_dir / "evaluation.log", timeout=None)


def evaluate_sample(
    repo_root: Path,
    task: BenchmarkTask,
    report_path: Path,
    output_dir: Path,
    settings: dict[str, Any],
    root_env: dict[str, str],
) -> tuple[dict[str, float], dict[str, float]]:
    """调用与任务对应的原生评测器."""
    output_dir.mkdir(parents=True, exist_ok=True)
    if task.benchmark == "deep_research_bench":
        return _evaluate_drb(repo_root, task, report_path, output_dir, settings, root_env)
    if task.benchmark == "wiki_live_challenge":
        return _evaluate_wlc(repo_root, task, report_path, output_dir, settings, root_env)
    if task.benchmark == "deep_research_bench_ii":
        return _evaluate_drb2(repo_root, task, report_path, output_dir, settings, root_env)
    raise ValueError(f"不支持的 Benchmark：{task.benchmark}")


def _evaluate_drb(
    repo_root: Path,
    task: BenchmarkTask,
    report_path: Path,
    output_dir: Path,
    settings: dict[str, Any],
    root_env: dict[str, str],
) -> tuple[dict[str, float], dict[str, float]]:
    bench = repo_root / "Benchmark/deep_research_bench"
    env = benchmark_environment(root_env, task.benchmark, settings.get("runtime"))
    evaluation = settings.get("evaluation", {})
    dimensions = set(evaluation.get("dimensions", ["race", "fact"]))
    workers = int(evaluation.get("max_workers", 5))
    native = output_dir / "native"
    raw_dir = native / "raw"
    cleaned_dir = native / "cleaned"
    raw_dir.mkdir(parents=True, exist_ok=True)
    cleaned_dir.mkdir(parents=True, exist_ok=True)
    query_path = native / "query.jsonl"
    target_path = raw_dir / "graphresearcher.jsonl"
    record = {"id": task.metadata["id"], "prompt": task.prompt, "article": report_path.read_text(encoding="utf-8")}
    query_path.write_text(json.dumps(task.metadata, ensure_ascii=False) + "\n", encoding="utf-8")
    target_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    metrics: dict[str, float] = {}
    phases: dict[str, float] = {}

    if "race" in dimensions:
        race_dir = output_dir / "race"
        command = [
            sys.executable,
            "-c",
            (
                "import runpy, sys; "
                "script = sys.argv[1]; "
                "sys.path.insert(0, __import__('os').path.dirname(script)); "
                "sys.argv = sys.argv[1:]; "
                "runpy.run_path(script, run_name='__main__')"
            ),
            str(bench / "deepresearch_bench_race.py"),
            "graphresearcher",
            "--raw_data_dir",
            str(raw_dir),
            "--cleaned_data_dir",
            str(cleaned_dir),
            "--max_workers",
            str(workers),
            "--query_file",
            str(query_path),
            "--output_dir",
            str(race_dir),
            "--force",
        ]
        phases["race"], error = _run(command, bench, env, output_dir, "race")
        if error:
            raise RuntimeError(f"RACE 评测失败：{error}")
        rows = _jsonl(race_dir / "raw_results.jsonl")
        if not rows or "error" in rows[0]:
            raise RuntimeError(f"RACE 未产生有效分数：{rows[:1]}")
        row = rows[0]
        for name in ("comprehensiveness", "insight", "instruction_following", "readability", "overall_score"):
            if isinstance(row.get(name), (int, float)):
                metrics[f"race.{name}"] = float(row[name])

    if "fact" in dimensions:
        fact_dir = output_dir / "fact"
        fact_dir.mkdir(parents=True, exist_ok=True)
        stage_files = [
            ("extract", target_path, fact_dir / "extracted.jsonl", True),
            ("deduplicate", fact_dir / "extracted.jsonl", fact_dir / "deduplicated.jsonl", True),
            ("scrape", fact_dir / "deduplicated.jsonl", fact_dir / "scraped.jsonl", False),
            ("validate", fact_dir / "scraped.jsonl", fact_dir / "validated.jsonl", True),
        ]
        fact_started = time.perf_counter()
        for module, source, destination, needs_query in stage_files:
            command = [
                sys.executable,
                "-m",
                f"utils.{module}",
                "--raw_data_path",
                str(source),
                "--output_path",
                str(destination),
                "--n_total_process",
                str(int(evaluation.get("fact", {}).get("processes", 1))),
            ]
            if needs_query:
                command.extend(["--query_data_path", str(query_path)])
            _, error = _run(command, bench, env, output_dir, f"fact.{module}")
            if error:
                raise RuntimeError(f"FACT {module} 失败：{error}")
        phases["fact"] = time.perf_counter() - fact_started
        rows = _jsonl(fact_dir / "validated.jsonl")
        if not rows:
            raise RuntimeError("FACT 未产生 validated.jsonl 记录。")
        citations = rows[0].get("citations_deduped", {})
        judged = [
            verdict
            for citation in citations.values()
            if citation.get("validate_error") is None
            for verdict in citation.get("validate_res", [])
            if verdict.get("result") != "unknown"
        ]
        supported = sum(verdict.get("result") == "supported" for verdict in judged)
        metrics["fact.total_citations"] = float(len(judged))
        metrics["fact.valid_citations"] = float(supported)
        metrics["fact.valid_rate"] = supported / len(judged) if judged else 0.0
    return metrics, phases


def _evaluate_wlc(
    repo_root: Path,
    task: BenchmarkTask,
    report_path: Path,
    output_dir: Path,
    settings: dict[str, Any],
    root_env: dict[str, str],
) -> tuple[dict[str, float], dict[str, float]]:
    bench = repo_root / "Benchmark/Wiki_Live_Challenge"
    env = benchmark_environment(root_env, task.benchmark, settings.get("runtime"))
    evaluation = settings.get("evaluation", {})
    dimensions = set(evaluation.get("dimensions", ["writing", "verifiability", "citation"]))
    preprocessing = settings.get("preprocessing", {})
    generated_markdown = output_dir / "native" / f"{task.display_name}.md"
    generated_json = output_dir / "native" / f"{task.display_name}.json"
    generated_json.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(report_path, generated_markdown)
    phases: dict[str, float] = {}
    if preprocessing.get("normalize_markdown", True):
        normalize_command = [
            sys.executable,
            str(bench / "scripts/preprocess_md.py"),
            "--input",
            str(generated_markdown),
            "--in-place",
        ]
        phases["normalize"], error = _run(normalize_command, repo_root, env, output_dir, "normalize")
        if error:
            raise RuntimeError(f"Wiki Live Challenge Markdown 规范化失败：{error}")
    steps = ",".join(preprocessing.get("steps", ["extract", "fetch"]))
    command = [
        sys.executable,
        str(bench / "scripts/generate_json.py"),
        "--input",
        str(generated_markdown),
        "--output",
        str(generated_json),
        "--steps",
        steps,
        "--env",
        str(repo_root / ".env"),
        "--force",
    ]
    phases["preprocessing"], error = _run(command, repo_root, env, output_dir, "preprocessing")
    if error or not generated_json.is_file():
        raise RuntimeError(f"Wiki Live Challenge 预处理失败：{error or '未生成 JSON'}")
    dataset = task.metadata.get("dataset", "2025_Mar_Nov")
    gt_path = bench / f"data/{dataset}/wiki_data/cleaned_data/article/{task.display_name}.md"
    metrics: dict[str, float] = {}
    workers = str(int(evaluation.get("max_workers", 5)))
    for dimension in ("writing", "verifiability", "citation"):
        if dimension not in dimensions:
            continue
        dimension_dir = output_dir / dimension
        command = [
            sys.executable,
            str(bench / "scripts/run_evaluation.py"),
            dimension,
            "--gen",
            str(generated_json),
            "--output",
            str(dimension_dir),
            "--max-workers",
            workers,
        ]
        if dimension != "citation":
            command.extend(["--gt", str(gt_path)])
        if dimension == "writing" and evaluation.get("writing", {}).get("allow_tie", False):
            command.append("--allow-tie")
        if dimension == "writing" and evaluation.get("writing", {}).get("categories"):
            command.extend(["--categories", *evaluation["writing"]["categories"]])
        if dimension == "verifiability":
            command.extend(["--top-k", str(evaluation.get("verifiability", {}).get("top_k", 10))])
        phases[dimension], error = _run(command, repo_root, env, output_dir, dimension)
        if error:
            raise RuntimeError(f"Wiki Live Challenge {dimension} 失败：{error}")
        result_path = dimension_dir / f"{task.display_name}_{dimension}.json"
        result = read_json(result_path)
        if dimension == "writing":
            overall = result.get("aggregate", {}).get("overall", {})
            metrics["writing.gen_win_rate"] = float(overall.get("gen_win_rate", 0))
        elif dimension == "verifiability":
            for name in ("gen_supported_by_wiki_ratio", "gen_conflict_with_wiki_ratio", "wiki_covered_by_gen_ratio"):
                metrics[f"verifiability.{name}"] = float(result.get(name, 0))
        else:
            for name in ("support_ratio", "conflict_ratio"):
                metrics[f"citation.{name}"] = float(result.get(name, 0))
    return metrics, phases


def _evaluate_drb2(
    repo_root: Path,
    task: BenchmarkTask,
    report_path: Path,
    output_dir: Path,
    settings: dict[str, Any],
    root_env: dict[str, str],
) -> tuple[dict[str, float], dict[str, float]]:
    bench = repo_root / "Benchmark/DeepResearch-Bench-II"
    env = benchmark_environment(root_env, task.benchmark, settings.get("runtime"))
    evaluation = settings.get("evaluation", {})
    report_dir = output_dir / "native" / "report" / "graphresearcher"
    report_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(report_path, report_dir / f"idx-{task.sample_id}.md")
    result_path = output_dir / "result.jsonl"
    command = [
        sys.executable,
        str(bench / "run_evaluation.py"),
        "--pdf_dir",
        str(report_dir.parent),
        "--out_jsonl",
        str(result_path),
        "--tasks_jsonl",
        str(bench / "tasks_and_rubrics.jsonl"),
        "--chunk_size",
        str(evaluation.get("chunk_size", 50)),
        "--max_workers",
        str(evaluation.get("max_workers", 5)),
        "--max_retries",
        str(evaluation.get("max_retries", 10)),
        "--max_paper_chars",
        str(evaluation.get("max_paper_chars", 150000)),
        "--log_file",
        str(output_dir / "native_evaluator.log"),
    ]
    duration, error = _run(command, repo_root, env, output_dir, "rubric")
    if error:
        raise RuntimeError(f"DeepResearch Bench II 评测失败：{error}")
    rows = _jsonl(result_path)
    if not rows:
        raise RuntimeError("DeepResearch Bench II 未产生分数。")
    payload = rows[0].get("result", {})
    scores = payload.get("scores", {})
    metrics: dict[str, float] = {}
    all_scores: list[float] = []
    blocked = 0
    for source, target in (("info_recall", "information_recall"), ("analysis", "analysis"), ("presentation", "presentation")):
        values = [item.get("score") for item in (scores.get(source) or {}).values() if isinstance(item.get("score"), (int, float))]
        if values:
            metrics[target] = sum(value == 1 for value in values) / len(values)
            all_scores.extend(values)
            blocked += sum(value == -1 for value in values)
    if all_scores:
        metrics["total"] = sum(value == 1 for value in all_scores) / len(all_scores)
        metrics["blocked_rate"] = blocked / len(all_scores)
    return metrics, {"rubric": duration}
