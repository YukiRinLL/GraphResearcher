"""Launch the selected benchmark runs as detached child processes.

The launcher itself exits after starting one process per benchmark. Each child
creates its own input subset, report directory, evaluation artifacts, and log.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
GRAPH = ROOT / "GraphResearcher"
RUN_ROOT = GRAPH / "outputs" / "benchmark_six_runs"
PYTHON = sys.executable


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def prepare_inputs() -> dict[str, Path]:
    drb_source = ROOT / "deep_research_bench" / "data" / "prompt_data" / "query.jsonl"
    drb_records = [
        json.loads(line)
        for line in drb_source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    drb_selected = [record for record in drb_records if record.get("id") in {18, 19}]

    drb2_source = ROOT / "DeepResearch-Bench-II" / "tasks_and_rubrics.jsonl"
    drb2_records = [
        json.loads(line)
        for line in drb2_source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    drb2_selected = [record for record in drb2_records if record.get("idx") in {1, 2}]

    wlc_source = ROOT / "WLC-bench" / "data" / "2025_Mar_Nov" / "wiki_data" / "ga_100.json"
    wlc_records = json.loads(wlc_source.read_text(encoding="utf-8"))
    wlc_selected = [record for record in wlc_records if record.get("id") in {1, 2}]

    if len(drb_selected) != 2 or len(drb2_selected) != 2 or len(wlc_selected) != 2:
        raise RuntimeError("Could not resolve exactly two records for each benchmark")

    input_root = RUN_ROOT / "inputs"
    paths = {
        "drb": input_root / "drb.jsonl",
        "drb2": input_root / "drb2.jsonl",
        "wlc": input_root / "wlc.json",
    }
    write_jsonl(paths["drb"], drb_selected)
    write_jsonl(paths["drb2"], drb2_selected)
    write_json(paths["wlc"], wlc_selected)
    return paths


def launch(name: str, command: list[str], cwd: Path, log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("w", encoding="utf-8")
    log.write(f"started_at={datetime.now(timezone.utc).isoformat()}\n")
    log.write(f"command={json.dumps(command, ensure_ascii=False)}\n")
    log.flush()
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=flags,
        env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONUTF8": "1"},
    )
    log.close()
    return process.pid


def main() -> None:
    global RUN_ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", choices=["drb", "drb2", "wlc"], required=True)
    parser.add_argument("--item", type=int, required=True)
    parser.add_argument("--run-root", type=Path, default=RUN_ROOT)
    args = parser.parse_args()
    RUN_ROOT = args.run_root.resolve()
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    inputs = prepare_inputs()
    output_root = RUN_ROOT / "outputs"
    common = [PYTHON, "-u"]
    jobs = {
        "drb": common + [
            str(GRAPH / "test_deepresearch_bench.py"),
            "--bench-root", str(ROOT / "deep_research_bench"),
            "--prompt-path", str(inputs["drb"]),
            "--output-path", str(output_root / "drb"),
            "--model-name", "GraphResearcher-six",
            "--sample-size", "0", "--max-rounds", "25", "--verbose", "debug",
            "--evaluate", "--eval-mode", "all", "--eval-max-workers", "2",
        ],
        "drb2": common + [
            str(GRAPH / "test_deepresearch_bench_ii.py"),
            "--bench-root", str(ROOT / "DeepResearch-Bench-II"),
            "--prompt-path", str(inputs["drb2"]),
            "--output-path", str(output_root / "drb2"),
            "--model-name", "GraphResearcher-six",
            "--sample-size", "0", "--max-rounds", "25", "--verbose", "debug",
            "--evaluate", "--bench-python", PYTHON,
        ],
        "wlc": common + [
            str(GRAPH / "test_wlc.py"),
            "--wlc-root", str(ROOT / "WLC-bench"),
            "--prompt-path", str(inputs["wlc"]),
            "--output-path", str(output_root / "wlc"),
            "--sample-size", "0", "--max-rounds", "25", "--verbose", "debug",
            "--evaluate", "--eval-work-dir", str(output_root / "wlc" / "_wlc_eval"),
            "--eval-log-path", str(output_root / "wlc" / "_wlc_eval" / "official_output.log"),
            "--wlc-python", PYTHON, "--eval-max-workers", "2",
        ],
    }
    item_key = {"drb": "id", "drb2": "idx", "wlc": "id"}[args.benchmark]
    source_path = inputs[args.benchmark]
    if args.benchmark == "wlc":
        records = json.loads(source_path.read_text(encoding="utf-8"))
        selected_records = [record for record in records if record.get(item_key) == args.item]
        write_json(source_path, selected_records)
    else:
        records = [json.loads(line) for line in source_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        selected_records = [record for record in records if record.get(item_key) == args.item]
        write_jsonl(source_path, selected_records)
    if len(selected_records) != 1:
        raise RuntimeError(f"Could not resolve one {args.benchmark} item={args.item}")
    manifest = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "selection": {"drb": [18, 19], "drb2": [1, 2], "wlc": [1, 2]},
        "jobs": {},
    }
    name = args.benchmark
    command = jobs[name]
    log_path = RUN_ROOT / "logs" / f"{name}-{args.item}.log"
    pid = launch(name, [PYTHON, str(GRAPH / "run_benchmark_background.py"), *command[2:]], ROOT, log_path)
    manifest["jobs"][name] = {"item": args.item, "pid": pid, "log": str(log_path), "status": "started"}
    write_json(RUN_ROOT / "status.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
