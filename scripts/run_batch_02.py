"""Run the second five fixed sample jobs concurrently."""

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_batch_jobs import run_batch

if __name__ == "__main__":
    run_batch(2)
