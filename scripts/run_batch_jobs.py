"""Run ten unique randomly sampled jobs in waves of five."""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARKS = {
    "drb": {
        "source": ROOT.parent / "deep_research_bench" / "data" / "prompt_data" / "query.jsonl",
        "key": "id",
    },
    "drb2": {
        "source": ROOT.parent / "DeepResearch-Bench-II" / "tasks_and_rubrics.jsonl",
        "key": "idx",
    },
    "wlc": {
        "source": ROOT.parent / "WLC-bench" / "data" / "2025_Mar_Nov" / "wiki_data" / "ga_100.json",
        "key": "id",
    },
}
LEGACY_BATCH_BENCHMARK = {1: "drb", 2: "drb", 3: "drb2", 4: "drb2", 5: "wlc", 6: "wlc"}


def load_ids(benchmark: str) -> list[int]:
    config = BENCHMARKS[benchmark]
    source = config["source"]
    if benchmark == "wlc":
        records = json.loads(source.read_text(encoding="utf-8"))
    else:
        records = [
            json.loads(line)
            for line in source.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    return [int(record[config["key"]]) for record in records if record.get(config["key"]) is not None]


def run_batch(batch: int) -> None:
    """Compatibility entry point for the former six fixed-batch wrappers."""
    benchmark = LEGACY_BATCH_BENCHMARK.get(batch)
    if benchmark is None:
        raise SystemExit(f"Unknown legacy batch: {batch}")
    run_jobs(benchmark, sample_size=10, seed=None, run_root=None, max_rounds=40, verbose="debug")


def run_jobs(benchmark: str, sample_size: int, seed: int | None, run_root: Path | None, max_rounds: int, verbose: str) -> None:
    if sample_size <= 0:
        raise SystemExit("--sample-size must be positive")

    item_ids = load_ids(benchmark)
    if len(item_ids) < sample_size:
        raise SystemExit(f"{benchmark} contains only {len(item_ids)} items")
    rng = random.Random(seed)
    selected = sorted(rng.sample(item_ids, sample_size))
    print(json.dumps({"benchmark": benchmark, "seed": seed, "items": selected}, ensure_ascii=False))

    for wave_start in range(0, len(selected), 5):
        wave = selected[wave_start : wave_start + 5]
        processes = []
        print(json.dumps({"benchmark": benchmark, "wave": wave_start // 5 + 1, "items": wave}, ensure_ascii=False))
        for item in wave:
            command = [
                sys.executable,
                "-u",
                str(ROOT / "scripts" / "run_sampled_benchmark_job.py"),
                "--benchmark",
                benchmark,
                "--item",
                str(item),
                "--max-rounds",
                str(max_rounds),
                "--verbose",
                verbose,
            ]
            if run_root:
                command.extend(["--run-root", str(run_root)])
            processes.append(subprocess.Popen(command, cwd=ROOT))
        codes = [process.wait() for process in processes]
        if max(codes):
            raise SystemExit(max(codes))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", choices=sorted(BENCHMARKS), required=True)
    parser.add_argument("--sample-size", type=int, default=10)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--run-root", type=Path, default=None)
    parser.add_argument("--max-rounds", type=int, default=40)
    parser.add_argument("--verbose", choices=["quiet", "normal", "debug"], default="debug")
    args = parser.parse_args()
    run_jobs(args.benchmark, args.sample_size, args.seed, args.run_root, args.max_rounds, args.verbose)


if __name__ == "__main__":
    main()
