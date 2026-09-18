"""批量生成 DeepResearch Bench 报告，并调用官方 RACE 与 FACT 评测。"""

# 中文文档字符串使用中文句号。
# ruff: noqa: T201, D415

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import dotenv
from tqdm import tqdm

from main import VERBOSITY_PRESETS, resolve_log_options, run
from test_wlc import run_command_tee, sample_items

BENCH_ROOT = Path(__file__).resolve().parent.parent / "deep_research_bench"
OUTPUT_PATH = Path("outputs/deepresearch_bench")
MODEL_NAME = "GraphResearcher"
SAMPLE_SIZE = 10
MAX_ROUNDS = 40
VERBOSE = "debug"


def validate_model_name(value: str) -> str:
    """验证用作目录名和提交文件名的模型标识。"""
    if not value or value in {".", ".."} or Path(value).name != value or "\\" in value:
        raise ValueError(f"Invalid model name: {value!r}")
    return value


def load_items(path: Path) -> list[dict[str, Any]]:
    """读取官方任务 JSONL，检查用于评测对齐的标识、语言和提示词。"""
    items: list[dict[str, Any]] = []
    seen: set[int] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict):
            raise ValueError(f"Expected an object at {path}:{line_number}")
        task_id = item.get("id")
        if type(task_id) is not int or task_id <= 0:
            raise ValueError(f"Expected a positive integer id at {path}:{line_number}")
        if task_id in seen:
            raise ValueError(f"Duplicate task id={task_id} in {path}")
        if not isinstance(item.get("prompt"), str) or not item["prompt"].strip():
            raise ValueError(f"Missing prompt for id={task_id}")
        if item.get("language") not in {"en", "zh"}:
            raise ValueError(f"Invalid language for id={task_id}; expected en or zh")
        seen.add(task_id)
        items.append(item)
    if not items:
        raise ValueError(f"No tasks found in {path}")
    return items


def run_one(
    item: dict[str, Any], output_dir: Path, model_name: str, max_rounds: int, opts: dict[str, Any],
) -> Path | None:
    """生成一题报告，并保存独立的日志、输入快照和图谱导出。"""
    report_path = output_dir / "report" / model_name / f"id-{item['id']}.md"
    if report_path.is_file() and report_path.read_text(encoding="utf-8").strip():
        print(f"Skip existing file: {report_path}")
        return report_path

    run_dir = output_dir / "_runs" / model_name / f"id-{item['id']}"
    run_dir.mkdir(parents=True, exist_ok=True)
    snapshot = {key: item[key] for key in ("id", "topic", "language", "prompt") if key in item}
    (run_dir / "input.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    # 重试时移除上次未发布的正文，避免把旧文件误认为本次生成结果。
    generated = run_dir / "report.md"
    generated.unlink(missing_ok=True)
    print(f"Processing id={item['id']}; detailed artifacts: {run_dir}")
    run(item["prompt"], run_dir, max_rounds, opts)
    if not generated.is_file() or not generated.read_text(encoding="utf-8").strip():
        print(f"Warning: missing or empty report for id={item['id']}")
        return None
    report_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(generated, report_path)
    return report_path


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """先写临时文件，再替换完整的 JSONL 导出。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".jsonl.tmp")
    temporary.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8",
    )
    temporary.replace(path)


def export_reports(items: list[dict[str, Any]], output_dir: Path, model_name: str) -> tuple[Path, Path]:
    """导出已生成的全部任务，并为官方评测构造对应的任务清单。"""
    reports = []
    queries = []
    for item in items:
        path = output_dir / "report" / model_name / f"id-{item['id']}.md"
        if not path.is_file():
            continue
        article = path.read_text(encoding="utf-8")
        if not article.strip():
            continue
        reports.append({"id": item["id"], "prompt": item["prompt"], "article": article})
        queries.append({key: item[key] for key in ("id", "topic", "language", "prompt") if key in item})
    if not reports:
        raise RuntimeError("No non-empty reports found; cannot export or evaluate")
    raw_path = output_dir / "raw_data" / f"{model_name}.jsonl"
    query_path = output_dir / "_evaluation" / model_name / "query.jsonl"
    write_jsonl(raw_path, reports)
    write_jsonl(query_path, queries)
    print(f"Exported {len(reports)} report(s): {raw_path}")
    return raw_path, query_path


def bench_subprocess_env(bench_root: Path, mode: str) -> dict[str, str]:
    """读取评测仓库配置，并按所选评测流程检查必需凭据。"""
    env_path = bench_root / ".env"
    if not env_path.is_file():
        raise FileNotFoundError(f"Benchmark environment file not found: {env_path}")
    values = {key: value for key, value in dotenv.dotenv_values(env_path).items() if value is not None}
    backend = values.get("LLM_BACKEND", "openrouter").lower()
    if backend not in {"openai", "openrouter"}:
        raise ValueError("LLM_BACKEND must be openai or openrouter in benchmark .env")
    values["LLM_BACKEND"] = backend
    key_name = "OPENAI_API_KEY" if backend == "openai" else "OPENROUTER_API_KEY"
    required = [key_name, *(["JINA_API_KEY"] if mode in {"all", "fact"} else [])]
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise ValueError(f"Missing benchmark .env configuration: {', '.join(missing)}")
    return values


def stage_race_queries(query_path: Path, result_path: Path, pending_path: Path) -> Path:
    """筛出尚未成功评分的任务，避免官方 RACE 续跑时重复追加结果。"""
    completed = set()
    if result_path.is_file():
        for line in result_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            result = json.loads(line)
            if "error" not in result:
                completed.add(result["id"])
    queries = [json.loads(line) for line in query_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    write_jsonl(pending_path, [item for item in queries if item["id"] not in completed])
    return pending_path


def run_bench_evaluation(
    output_dir: Path, bench_root: Path, model_name: str,
    mode: str = "all", python_bin: str = sys.executable, max_workers: int = 5,
) -> None:
    """调用官方清洗、RACE 和 FACT 流程，将可变产物保存在输出目录。"""
    bench_root = bench_root.resolve()
    output_dir = output_dir.resolve()
    # Official FACT modules are imported as ``utils.*`` from the benchmark root.
    if str(bench_root) not in sys.path:
        sys.path.insert(0, str(bench_root))
    env = bench_subprocess_env(bench_root, mode)
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(bench_root), env.get("PYTHONPATH", "")])
    )
    wrapper = Path(__file__).resolve().parent / "run_benchmark_background.py"
    raw_path = output_dir / "raw_data" / f"{model_name}.jsonl"
    work_dir = output_dir / "_evaluation" / model_name
    query_path = work_dir / "query.jsonl"
    required = [raw_path, query_path]
    if mode in {"all", "race"}:
        required.extend(bench_root / name for name in (
            "deepresearch_bench_race.py", "data/criteria_data/criteria.jsonl",
            "data/test_data/cleaned_data/reference.jsonl",
        ))
    if mode in {"all", "fact"}:
        required.extend(bench_root / "utils" / f"{name}.py" for name in (
            "extract", "deduplicate", "scrape", "validate", "stat",
        ))
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(f"Required benchmark file not found: {path}")

    log_path = work_dir / "official_output.log"
    if mode in {"all", "race"}:
        race_dir = output_dir / "results" / "race" / model_name
        race_dir.mkdir(parents=True, exist_ok=True)
        race_query_path = stage_race_queries(query_path, race_dir / "raw_results.jsonl", work_dir / "race_query.jsonl")
        run_command_tee([
            python_bin, str(wrapper), "--env-file", str(bench_root / ".env"),
            str(bench_root / "deepresearch_bench_race.py"), model_name,
            "--raw_data_dir", str(raw_path.parent),
            "--cleaned_data_dir", str(output_dir / "cleaned_data"),
            "--query_file", str(race_query_path), "--output_dir", str(race_dir),
            "--max_workers", str(max_workers),
        ], bench_root, log_path, env=env)

    if mode in {"all", "fact"}:
        fact_dir = output_dir / "results" / "fact" / model_name
        fact_dir.mkdir(parents=True, exist_ok=True)
        previous = raw_path
        for module, filename in (
            ("extract", "extracted.jsonl"), ("deduplicate", "deduplicated.jsonl"),
            ("scrape", "scraped.jsonl"), ("validate", "validated.jsonl"),
        ):
            target = fact_dir / filename
            command = [
                python_bin, "-m", f"utils.{module}", "--raw_data_path", str(previous),
                "--output_path", str(target), "--n_total_process", str(max_workers),
            ]
            if module != "scrape":
                command.extend(["--query_data_path", str(query_path)])
            run_command_tee(command, bench_root, log_path, env=env)
            previous = target
        run_command_tee([
            python_bin, "-m", "utils.stat", "--input_path", str(previous),
            "--output_path", str(fact_dir / "fact_result.txt"),
        ], bench_root, log_path, env=env)
    print(f"Official evaluation outputs: {output_dir / 'results'}; log: {log_path}")


def parse_args() -> argparse.Namespace:
    """解析生成和官方评测参数。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bench-root", type=Path, default=BENCH_ROOT, help="Official deep_research_bench repository.")
    parser.add_argument("--prompt-path", type=Path, help="Defaults to data/prompt_data/query.jsonl under --bench-root.")
    parser.add_argument("--output-path", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--model-name", default=MODEL_NAME)
    parser.add_argument("--sample-size", type=int, default=SAMPLE_SIZE, help="Random sample size; <=0 means all.")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("-r", "--max-rounds", type=int, default=MAX_ROUNDS, help="Searcher dispatch budget; 0 means unlimited.")
    parser.add_argument("-v", "--verbose", choices=list(VERBOSITY_PRESETS), default=VERBOSE)
    parser.add_argument("--evaluate", action="store_true", help="Evaluate accumulated reports after generation.")
    parser.add_argument("--evaluate-only", action="store_true", help="Export and evaluate existing reports without running the agent.")
    parser.add_argument("--eval-mode", choices=["all", "race", "fact"], default="all")
    parser.add_argument("--bench-python", default=sys.executable, help="Existing Python executable for official scripts.")
    parser.add_argument("--eval-max-workers", type=int, default=10)
    args = parser.parse_args()
    if args.eval_max_workers <= 0:
        parser.error("--eval-max-workers must be positive")
    args.prompt_path = args.prompt_path or args.bench_root / "data" / "prompt_data" / "query.jsonl"
    args.show_tool_calls = None
    args.subgraphs = None
    args.log_level = None
    args.truncate = None
    return args


def main() -> None:
    """生成抽样报告，导出累计提交文件，并按需启动评测。"""
    args = parse_args()
    model_name = validate_model_name(args.model_name)
    items = load_items(args.prompt_path)
    if args.evaluate or args.evaluate_only:
        bench_subprocess_env(args.bench_root, args.eval_mode)
    if not args.evaluate_only:
        opts = resolve_log_options(args)
        selected = sample_items(items, args.sample_size, args.seed)
        with ProcessPoolExecutor(max_workers=5) as pool:
            futures = {
                pool.submit(run_one, item, args.output_path, model_name, args.max_rounds, opts): item
                for item in selected
            }
            for future in tqdm(as_completed(futures), total=len(futures), desc="Processing items"):
                item = futures[future]
                try:
                    future.result()
                except Exception as exc:  # noqa: BLE001
                    print(f"Error processing id={item['id']}: {exc}")
    export_reports(items, args.output_path, model_name)
    if args.evaluate or args.evaluate_only:
        run_bench_evaluation(
            args.output_path, args.bench_root, model_name,
            args.eval_mode, args.bench_python, args.eval_max_workers,
        )


if __name__ == "__main__":
    main()
