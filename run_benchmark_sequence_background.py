"""Run benchmark articles one at a time and advance after each child exits."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
GRAPH = ROOT / "GraphResearcher"
LAUNCHER = GRAPH / "run_selected_benchmarks_background.py"
RUN_ROOT = GRAPH / "outputs" / "benchmark_six_runs"
PYTHON = sys.executable

SEQUENCE = [
    ("drb", 19),
    ("drb2", 1),
    ("drb2", 2),
    ("wlc", 1),
    ("wlc", 2),
]


def append(log: Path, text: str) -> None:
    with log.open("a", encoding="utf-8") as file:
        file.write(text + "\n")


def main() -> None:
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    log = RUN_ROOT / "sequence.log"
    append(log, f"started_at={datetime.now(timezone.utc).isoformat()}")
    status: dict[str, object] = {"started_at": datetime.now(timezone.utc).isoformat(), "jobs": []}
    (RUN_ROOT / "sequence_status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")

    for benchmark, item in SEQUENCE:
        label = f"{benchmark}-{item}"
        append(log, f"START {label}")
        launcher = subprocess.run(
            [PYTHON, str(LAUNCHER), "--benchmark", benchmark, "--item", str(item)],
            cwd=GRAPH,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        append(log, launcher.stdout.rstrip())
        if launcher.returncode != 0:
            append(log, f"LAUNCH_FAILED {label} exit={launcher.returncode} stderr={launcher.stderr}")
            status["jobs"].append({"benchmark": benchmark, "item": item, "status": "launch_failed"})
            break
        try:
            manifest = json.loads(launcher.stdout)
            pid = int(manifest["jobs"][benchmark]["pid"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            append(log, f"MANIFEST_FAILED {label}: {exc}")
            break
        while True:
            try:
                completed = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", f"Get-Process -Id {pid} -ErrorAction SilentlyContinue"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                )
            except OSError:
                completed = None
            if completed is None or not completed.stdout.strip():
                break
            time.sleep(10)
        append(log, f"END {label}")
        status["jobs"].append({"benchmark": benchmark, "item": item, "status": "finished", "pid": pid})
        (RUN_ROOT / "sequence_status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    status["finished_at"] = datetime.now(timezone.utc).isoformat()
    (RUN_ROOT / "sequence_status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    append(log, "SEQUENCE_FINISHED")


if __name__ == "__main__":
    main()
