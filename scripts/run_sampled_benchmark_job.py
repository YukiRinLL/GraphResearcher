"""Run one fixed benchmark sample with isolated artifacts and evaluation outputs."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ROOT = ROOT / "outputs" / "sampled_benchmark_runs"
BENCHMARKS = {"drb", "drb2", "wlc"}
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", choices=sorted(BENCHMARKS), required=True)
    parser.add_argument("--item", type=int, required=True)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--max-rounds", type=int, default=40)
    parser.add_argument("--verbose", choices=["quiet", "normal", "debug"], default="debug")
    return parser.parse_args()


def prepare_input(benchmark: str, item: int, run_root: Path) -> Path:
    input_dir = run_root / "inputs"
    input_dir.mkdir(parents=True, exist_ok=True)
    if benchmark == "drb":
        source = ROOT.parent / "deep_research_bench" / "data" / "prompt_data" / "query.jsonl"
        records = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
        selected = [record for record in records if record.get("id") == item]
        target = input_dir / "query.jsonl"
        target.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in selected) + "\n", encoding="utf-8")
        return target
    if benchmark == "drb2":
        source = ROOT.parent / "DeepResearch-Bench-II" / "tasks_and_rubrics.jsonl"
        records = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
        selected = [record for record in records if record.get("idx") == item]
        selected = [
            {key: record[key] for key in ("id", "idx", "language", "theme", "description", "prompt") if key in record}
            for record in selected
        ]
        target = input_dir / "tasks_and_rubrics.jsonl"
        target.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in selected) + "\n", encoding="utf-8")
        return target
    source = ROOT.parent / "WLC-bench" / "data" / "2025_Mar_Nov" / "wiki_data" / "ga_100.json"
    records = json.loads(source.read_text(encoding="utf-8"))
    selected = [record for record in records if record.get("id") == item]
    target = input_dir / "ga_100.json"
    target.write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def command_for(benchmark: str, item: int, output_root: Path, input_path: Path) -> tuple[list[str], Path]:
    python = sys.executable
    wrapper = ROOT / "run_benchmark_background.py"
    if benchmark == "drb":
        script = ROOT / "test_deepresearch_bench.py"
        bench_root = ROOT.parent / "deep_research_bench"
        output = output_root / "drb"
        return [
            python, "-u", str(wrapper), str(script), "--bench-root", str(bench_root),
            "--output-path", str(output), "--model-name", "GraphResearcher-sampled",
            "--prompt-path", str(input_path),
            "--sample-size", "0", "--max-rounds", str(ARGS.max_rounds),
            "--verbose", ARGS.verbose, "--evaluate", "--eval-mode", "all",
            "--eval-max-workers", "10",
        ], output
    if benchmark == "drb2":
        script = ROOT / "test_deepresearch_bench_ii.py"
        bench_root = ROOT.parent / "DeepResearch-Bench-II"
        output = output_root / "drb2"
        return [
            python, "-u", str(wrapper), str(script), "--bench-root", str(bench_root),
            "--output-path", str(output), "--model-name", "GraphResearcher-sampled",
            "--prompt-path", str(input_path),
            "--evaluation-tasks-path", str(bench_root / "tasks_and_rubrics.jsonl"),
            "--item", str(item), "--max-rounds", str(ARGS.max_rounds),
            "--verbose", ARGS.verbose, "--evaluate", "--bench-python", python,
        ], output
    script = ROOT / "test_wlc.py"
    bench_root = ROOT.parent / "WLC-bench"
    output = output_root / "wlc"
    work = output / "_wlc_eval"
    return [
        python, "-u", str(wrapper), str(script), "--wlc-root", str(bench_root),
        "--prompt-path", str(input_path),
        "--output-path", str(output), "--sample-size", "0", "--max-rounds", str(ARGS.max_rounds),
        "--verbose", ARGS.verbose, "--evaluate", "--eval-work-dir", str(work),
        "--eval-log-path", str(work / "official_output.log"), "--wlc-python", python,
        "--eval-max-workers", "10",
    ], output


def main() -> None:
    global ARGS
    ARGS = parse_args()
    run_root = ARGS.run_root.resolve() / f"{ARGS.benchmark}-{ARGS.item}"
    run_root.mkdir(parents=True, exist_ok=True)
    output_root = run_root / "outputs"
    input_path = prepare_input(ARGS.benchmark, ARGS.item, run_root)
    command, output = command_for(ARGS.benchmark, ARGS.item, output_root, input_path)
    manifest = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "benchmark": ARGS.benchmark,
        "item": ARGS.item,
        "sample_size": 10,
        "command": command,
        "run_root": str(run_root),
        "output_root": str(output),
        "input_path": str(input_path),
    }
    (run_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    log_path = run_root / "job.log"
    with log_path.open("w", encoding="utf-8") as log:
        log.write(json.dumps(manifest, ensure_ascii=False) + "\n")
        log.flush()
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            env={
                **os.environ,
                "PYTHONUNBUFFERED": "1",
                "PYTHONUTF8": "1",
                "PYTHONPATH": os.pathsep.join(
                    filter(None, [str(ROOT / "src"), str(ROOT), os.environ.get("PYTHONPATH", "")])
                ),
            },
        )
        return_code = process.wait()
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    manifest["return_code"] = return_code
    (run_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    raise SystemExit(return_code)


if __name__ == "__main__":
    main()
