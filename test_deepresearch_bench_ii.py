"""Batch-run GraphResearcher on DeepResearch Bench II tasks.

The generator reads the benchmark JSONL, sends each record's top-level
``prompt`` to GraphResearcher, and writes reports using the official
``report/<model>/idx-<n>.md`` layout. Optional evaluation delegates scoring and
aggregation to the scripts shipped with DeepResearch Bench II.
"""

# ruff: noqa: T201

from __future__ import annotations

import argparse
import datetime as dt
import inspect
import json
import os
import random
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import dotenv
from tqdm import tqdm

from main import VERBOSITY_PRESETS, resolve_log_options, run
from tools.drb2_diagnostics import build_drb2_research_plan

dotenv.load_dotenv(".env")

# =========================
# 测试运行配置
# =========================
BENCH_ROOT = Path("/Users/yindq/projects/DeepResearch/DeepResearch-Bench-II")
OUTPUT_PATH = Path("outputs/deepresearch_bench_ii")
MODEL_NAME = "GraphResearcher"
SAMPLE_SIZE = 5
MAX_ROUNDS = 12
VERBOSE = "debug"
RANDOM_SEED: int | None = None

_SAFE_NAME_RE = re.compile(r'[^\w.-]+', re.UNICODE)
_REPORT_NAME_RE = re.compile(r"^idx-(\d+)\.md$", re.IGNORECASE)


def safe_name(value: str) -> str:
    """Return a compact filesystem-safe name for a run directory."""
    name = _SAFE_NAME_RE.sub("-", value).strip(".-")
    return name or "task"


def validate_model_name(model_name: str) -> str:
    """Validate a model identifier used as one directory component."""
    if not model_name or model_name in {".", ".."} or Path(model_name).name != model_name:
        raise ValueError(f"Invalid model name: {model_name!r}")
    return model_name


def _normalize_item(value: Any, line_number: int) -> dict[str, Any] | None:
    """Validate one benchmark record and normalize its numeric index."""
    if not isinstance(value, dict):
        print(f"Skip line {line_number}: expected a JSON object")
        return None

    raw_idx = value.get("idx")
    try:
        if isinstance(raw_idx, bool):
            raise ValueError
        idx = int(raw_idx)
    except (TypeError, ValueError):
        print(f"Skip line {line_number}: invalid idx={raw_idx!r}")
        return None
    if idx <= 0:
        print(f"Skip line {line_number}: idx must be positive, got {idx}")
        return None

    prompt = value.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        print(f"Skip line {line_number}: missing or empty prompt for idx={idx}")
        return None

    return {**value, "idx": idx, "prompt": prompt}


def load_items(path: Path) -> list[dict[str, Any]]:
    """Load and validate DeepResearch Bench II JSONL records."""
    items: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"Skip line {line_number}: invalid JSON ({exc.msg})")
                continue
            item = _normalize_item(value, line_number)
            if item is not None:
                items.append(item)
    return items


def sample_items(items: list[dict[str, Any]], sample_size: int, seed: int | None) -> list[dict[str, Any]]:
    """Randomly sample at most ``sample_size`` records."""
    if sample_size <= 0 or len(items) <= sample_size:
        return items
    return random.Random(seed).sample(items, sample_size)


def _input_snapshot(item: dict[str, Any]) -> dict[str, Any]:
    """Project a benchmark record into the per-run input snapshot."""
    keys = ("id", "idx", "language", "theme", "description", "prompt")
    return {key: item[key] for key in keys if key in item}


def run_one(
    item: dict[str, Any],
    output_dir: Path,
    model_name: str,
    max_rounds: int,
    opts: dict[str, Any],
) -> Path | None:
    """Run one benchmark item and publish its official-format report."""
    idx = int(item["idx"])
    prompt = str(item["prompt"])
    task_id = str(item.get("id") or f"task-{idx}")

    model_dir = output_dir / "report" / model_name
    out_file = model_dir / f"idx-{idx}.md"
    if out_file.exists():
        print(f"Skip existing file: {out_file}")
        return out_file

    run_dir = output_dir / "_runs" / f"idx-{idx}-{safe_name(task_id)}"
    run_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "input.json").write_text(
        json.dumps(_input_snapshot(item), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Processing: idx={idx}, id={task_id}")
    print(f"Detailed artifacts: {run_dir}")
    run_plan = build_drb2_research_plan(item) if isinstance(item.get("content"), dict) else None
    if run_plan and "run_plan" in inspect.signature(run).parameters:
        run(prompt, run_dir, max_rounds, opts, run_plan=run_plan)
    else:
        # Keep the generic batch helper compatible with lightweight test doubles
        # and non-DRB2 callers that do not provide rubric metadata.
        run(prompt, run_dir, max_rounds, opts)

    report_path = run_dir / "report.md"
    if not report_path.exists():
        print(f"Warning: missing report.md for idx={idx}, id={task_id}")
        return None

    shutil.copyfile(report_path, out_file)
    return out_file


def reset_dir(path: Path) -> None:
    """Replace a staging directory with an empty directory."""
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def load_successful_evaluations(path: Path) -> set[tuple[str, int]]:
    """Load model/index pairs whose accumulated evaluation has no error."""
    successful: set[tuple[str, int]] = set()
    if not path.exists():
        return successful

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            try:
                record = json.loads(line)
                model = record.get("model")
                idx = int(record.get("idx"))
                result = record.get("result", record.get("new_content"))
                if isinstance(result, str):
                    result = json.loads(result)
            except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if isinstance(model, str) and isinstance(result, dict) and "error" not in result:
                successful.add((model, idx))
    return successful


def discover_reports(model_dir: Path) -> list[tuple[int, Path]]:
    """Return official Markdown reports in numeric task order."""
    reports: list[tuple[int, Path]] = []
    if not model_dir.exists():
        return reports
    for path in model_dir.iterdir():
        match = _REPORT_NAME_RE.fullmatch(path.name) if path.is_file() else None
        if match:
            reports.append((int(match.group(1)), path))
    return sorted(reports, key=lambda entry: entry[0])


def stage_pending_reports(
    reports: list[tuple[int, Path]],
    completed: set[tuple[str, int]],
    model_name: str,
    staging_report_dir: Path,
) -> list[Path]:
    """Stage only reports that have not received a successful evaluation."""
    reset_dir(staging_report_dir)
    target_model_dir = staging_report_dir / model_name
    pending = [(idx, path) for idx, path in reports if (model_name, idx) not in completed]
    if not pending:
        return []

    target_model_dir.mkdir(parents=True, exist_ok=True)
    staged: list[Path] = []
    for _, report_path in pending:
        target = target_model_dir / report_path.name
        shutil.copyfile(report_path, target)
        staged.append(target)
    return staged


def bench_subprocess_env(bench_root: Path) -> dict[str, str]:
    """读取评测仓库配置，供子进程覆盖同名环境变量。"""  # noqa: D415
    env_file = bench_root / ".env"
    if not env_file.is_file():
        raise FileNotFoundError(f"Benchmark environment file not found: {env_file}")
    return {key: value for key, value in dotenv.dotenv_values(env_file).items() if value is not None}


def run_command_tee(
    command: list[str], cwd: Path, log_path: Path, env: dict[str, str] | None = None,
) -> None:
    """Run a command and mirror combined output to the terminal and a log."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    header = "\n" + "=" * 80 + "\n"
    header += f"[{dt.datetime.now().isoformat(timespec='seconds')}] cwd={cwd}\n"
    header += f"$ {' '.join(command)}\n"
    header += "=" * 80 + "\n"

    print(header, end="")
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(header)
        log_file.flush()
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env={**os.environ, **(env or {}), "PYTHONUNBUFFERED": "1"},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
            log_file.write(line)
            log_file.flush()

        return_code = process.wait()
        if return_code != 0:
            raise RuntimeError(f"Command failed with exit code {return_code}: {' '.join(command)}")


def _bench_python_command(bench_root: Path) -> list[str]:
    """Build the isolated uv prefix used for official benchmark scripts."""
    return ["uv", "run", "--project", str(bench_root), "--isolated", "python"]


def run_bench_evaluation(
    output_dir: Path,
    bench_root: Path,
    model_name: str,
    tasks_path: Path | None = None,
    python_bin: str | None = None,
) -> None:
    """Evaluate unscored reports and aggregate all accumulated results."""
    bench_root = bench_root.resolve()
    output_dir = output_dir.resolve()
    tasks_path = (tasks_path or bench_root / "tasks_and_rubrics.jsonl").resolve()
    evaluation_script = bench_root / "run_evaluation.py"
    aggregate_script = bench_root / "aggregate_scores.py"
    for required in (tasks_path, evaluation_script, aggregate_script):
        if not required.exists():
            raise FileNotFoundError(f"Required DeepResearch Bench II file not found: {required}")

    subprocess_env = bench_subprocess_env(bench_root)
    if not subprocess_env.get("OPENAI_API_KEY"):
        raise ValueError("Missing OPENAI_API_KEY in benchmark .env")

    reports = discover_reports(output_dir / "report" / model_name)
    if not reports:
        raise RuntimeError(f"No reports found for model {model_name!r}; cannot run evaluation")

    result_path = output_dir / "result.jsonl"
    evaluation_dir = output_dir / "_evaluation"
    staging_report_dir = evaluation_dir / "staging" / "report"
    log_path = evaluation_dir / "run_evaluation.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("", encoding="utf-8")

    completed = load_successful_evaluations(result_path)
    staged = stage_pending_reports(reports, completed, model_name, staging_report_dir)
    command_prefix = [python_bin] if python_bin else _bench_python_command(bench_root)
    wrapper = Path(__file__).resolve().parent / "run_benchmark_background.py"

    if staged:
        print(f"Staged {len(staged)} pending report(s): {staging_report_dir}")
        evaluation_command = [
            *([python_bin, str(wrapper), "--env-file", str(bench_root / ".env"), str(evaluation_script)] if python_bin else command_prefix + [str(evaluation_script)]),
            "--pdf_dir",
            str(staging_report_dir),
            "--out_jsonl",
            str(result_path),
            "--tasks_jsonl",
            str(tasks_path),
            "--log_file",
            "",
        ]
        run_command_tee(evaluation_command, bench_root, log_path, env=subprocess_env)
    else:
        print(f"All {len(reports)} report(s) for {model_name} already have successful evaluations.")

    aggregate_command = [
        *([python_bin, str(wrapper), "--env-file", str(bench_root / ".env"), str(aggregate_script)] if python_bin else command_prefix + [str(aggregate_script)]),
        "--input",
        str(result_path),
        "--tasks-file",
        str(tasks_path),
        "--output-prefix",
        str(output_dir / "agg_scores"),
    ]
    run_command_tee(aggregate_command, bench_root, log_path, env=subprocess_env)
    print(f"Evaluation results: {result_path}")
    print(f"Aggregated scores: {output_dir / 'agg_scores_*.csv'}")


def parse_args() -> argparse.Namespace:
    """Parse generation and optional evaluation arguments."""
    parser = argparse.ArgumentParser(description="Batch-test GraphResearcher on DeepResearch Bench II.")
    parser.add_argument("--prompt-path", type=Path, default=None, help="Tasks JSONL; defaults to tasks_and_rubrics.jsonl under --bench-root.")
    parser.add_argument("--output-path", type=Path, default=OUTPUT_PATH, help="Output root for reports and artifacts.")
    parser.add_argument("--sample-size", type=int, default=SAMPLE_SIZE, help="Random sample size; <=0 means all.")
    parser.add_argument("--seed", type=int, default=RANDOM_SEED, help="Optional random seed for sampling.")
    parser.add_argument("--item", type=int, default=None, help="Run exactly one benchmark idx.")
    parser.add_argument("--model-name", default=MODEL_NAME, help="Official evaluator model directory name.")
    parser.add_argument("--bench-root", type=Path, default=BENCH_ROOT, help="DeepResearch Bench II repository root.")
    parser.add_argument("--evaluate", action="store_true", help="Run official scoring and aggregation after generation.")
    parser.add_argument("--evaluate-only", action="store_true", help="Evaluate accumulated reports without running the agent.")
    parser.add_argument("--bench-python", default=None, help="Existing Python executable for evaluation; defaults to the existing uv project command.")
    parser.add_argument(
        "-r",
        "--max-rounds",
        type=int,
        default=MAX_ROUNDS,
        help="Maximum Searcher dispatches per item; 0 means unlimited.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        choices=list(VERBOSITY_PRESETS),
        default=VERBOSE,
        help="GraphResearcher verbosity preset.",
    )
    args = parser.parse_args()
    args.prompt_path = args.prompt_path or args.bench_root / "tasks_and_rubrics.jsonl"
    args.show_tool_calls = None
    args.subgraphs = None
    args.log_level = None
    args.truncate = None
    return args


def main() -> None:
    """Generate sampled reports and optionally invoke the official evaluator."""
    args = parse_args()
    model_name = validate_model_name(args.model_name)
    args.output_path.mkdir(parents=True, exist_ok=True)

    if not args.evaluate_only:
        items = load_items(args.prompt_path)
        if args.item is not None:
            items = [item for item in items if item["idx"] == args.item]
            if not items:
                raise ValueError(f"No DRB2 task found for idx={args.item}")
        else:
            items = sample_items(items, args.sample_size, args.seed)
        opts = resolve_log_options(args)
        for item in tqdm(items, desc="Processing items"):
            try:
                run_one(item, args.output_path, model_name, args.max_rounds, opts)
            except Exception as exc:  # noqa: BLE001 - keep long benchmark runs moving
                print(f"Error processing idx={item.get('idx')}, id={item.get('id')}: {exc}")

    if args.evaluate or args.evaluate_only:
        run_bench_evaluation(
            args.output_path, args.bench_root, model_name, args.prompt_path, args.bench_python,
        )


if __name__ == "__main__":
    main()
