"""Score existing WLC reports one at a time in isolated directories."""

from __future__ import annotations

import subprocess
import sys
import time
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
GRAPH = ROOT / "GraphResearcher"
WLC_ROOT = ROOT / "WLC-bench"
SOURCE_ROOT = GRAPH / "outputs" / "benchmark_six_runs" / "outputs" / "wlc" / "_runs"
TARGET_ROOT = GRAPH / "outputs" / "wlc_rescore"


def main() -> None:
    TARGET_ROOT.mkdir(parents=True, exist_ok=True)
    log_path = TARGET_ROOT / "sequence.log"
    with log_path.open("w", encoding="utf-8") as log:
        for item, folder in (
            (1, "1-Dulles_International_Airport_Main_Terminal"),
            (2, "2-Sima_de_los_Huesos_hominins"),
        ):
            report = SOURCE_ROOT / folder / "report.md"
            work_dir = TARGET_ROOT / f"article-{item}"
            eval_log = work_dir / "official_output.log"
            if not report.is_file():
                raise FileNotFoundError(report)
            title = "Dulles_International_Airport_Main_Terminal" if item == 1 else "Sima_de_los_Huesos_hominins"
            named_report = report.parent / f"{title}.md"
            shutil.copyfile(report, named_report)
            command = [
                sys.executable,
                "-c",
                (
                    "import sys; "
                    f"sys.path.insert(0, r'{GRAPH}'); "
                    "from pathlib import Path; "
                    "from test_wlc import run_wlc_evaluation; "
                    f"run_wlc_evaluation([Path(r'{named_report}')], Path(r'{WLC_ROOT}'), "
                    f"'2025_Mar_Nov', Path(r'{work_dir}'), Path(r'{eval_log}'), "
                    f"r'{sys.executable}', 'extract,fetch', None, 2, 10, False)"
                ),
            ]
            log.write(f"START item={item}\n")
            log.flush()
            process = subprocess.Popen(
                command,
                cwd=GRAPH,
                stdout=log,
                stderr=subprocess.STDOUT,
                env={**__import__("os").environ, "PYTHONUNBUFFERED": "1", "PYTHONUTF8": "1"},
            )
            while process.poll() is None:
                time.sleep(5)
            log.write(f"END item={item} exit={process.returncode}\n")
            log.flush()
            if process.returncode != 0:
                raise SystemExit(process.returncode)
        log.write("SEQUENCE_FINISHED\n")


if __name__ == "__main__":
    main()
