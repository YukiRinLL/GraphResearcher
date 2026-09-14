"""Regenerate and independently evaluate the two selected WLC articles."""

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
RUN_ROOT = GRAPH / "outputs" / "wlc_rerun_separate"


def main() -> None:
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    sequence_log = RUN_ROOT / "sequence.log"
    status_path = RUN_ROOT / "status.json"
    status = {"started_at": datetime.now(timezone.utc).isoformat(), "jobs": []}
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    with sequence_log.open("w", encoding="utf-8") as log:
        log.write(f"started_at={status['started_at']}\n")
        for item in (1, 2):
            log.write(f"START wlc-{item}\n")
            log.flush()
            result = subprocess.run(
                [
                    sys.executable,
                    str(LAUNCHER),
                    "--benchmark", "wlc",
                    "--item", str(item),
                    "--run-root", str(RUN_ROOT / f"article-{item}"),
                ],
                cwd=GRAPH,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            log.write(result.stdout)
            log.flush()
            if result.returncode != 0:
                log.write(f"LAUNCH_FAILED exit={result.returncode}\n{result.stderr}\n")
                status["jobs"].append({"item": item, "status": "launch_failed"})
                break
            manifest = json.loads(result.stdout)
            pid = int(manifest["jobs"]["wlc"]["pid"])
            while subprocess.run(
                ["powershell", "-NoProfile", "-Command", f"Get-Process -Id {pid} -ErrorAction SilentlyContinue"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            ).stdout.strip():
                time.sleep(10)
            log.write(f"END wlc-{item}\n")
            status["jobs"].append({"item": item, "status": "finished", "pid": pid})
            status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        status["finished_at"] = datetime.now(timezone.utc).isoformat()
        status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        log.write("SEQUENCE_FINISHED\n")


if __name__ == "__main__":
    main()
