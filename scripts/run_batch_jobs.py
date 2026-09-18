"""Shared runner for five-job benchmark batches."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BATCHES = {
    1: [("run_drb_01.py", 1), ("run_drb_02.py", 17), ("run_drb_03.py", 19), ("run_drb_04.py", 31), ("run_drb_05.py", 34)],
    2: [("run_drb_06.py", 40), ("run_drb_07.py", 72), ("run_drb_08.py", 79), ("run_drb_09.py", 84), ("run_drb_10.py", 97)],
    3: [("run_drb2_01.py", 6), ("run_drb2_02.py", 11), ("run_drb2_03.py", 32), ("run_drb2_04.py", 39), ("run_drb2_05.py", 54)],
    4: [("run_drb2_06.py", 55), ("run_drb2_07.py", 85), ("run_drb2_08.py", 96), ("run_drb2_09.py", 102), ("run_drb2_10.py", 124)],
    5: [("run_wlc_01.py", 1), ("run_wlc_02.py", 4), ("run_wlc_03.py", 21), ("run_wlc_04.py", 38), ("run_wlc_05.py", 64)],
    6: [("run_wlc_06.py", 68), ("run_wlc_07.py", 79), ("run_wlc_08.py", 80), ("run_wlc_09.py", 94), ("run_wlc_10.py", 98)],
}


def run_batch(batch: int) -> None:
    parser = argparse.ArgumentParser(description=f"Run batch {batch}: five jobs concurrently.")
    parser.add_argument("--run-root", type=Path, default=None)
    parser.add_argument("--max-rounds", type=int, default=40)
    parser.add_argument("--verbose", choices=["quiet", "normal", "debug"], default="debug")
    args = parser.parse_args()
    processes = []
    for script, _item in BATCHES[batch]:
        command = [sys.executable, "-u", str(ROOT / "scripts" / script), "--max-rounds", str(args.max_rounds), "--verbose", args.verbose]
        if args.run_root:
            command.extend(["--run-root", str(args.run_root)])
        processes.append(subprocess.Popen(command, cwd=ROOT))
    codes = [process.wait() for process in processes]
    raise SystemExit(max(codes))
