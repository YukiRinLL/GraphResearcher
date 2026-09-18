"""统一评估抽样的独立回归测试。"""

import sys
from pathlib import Path

SRC_DIR = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from benchmarking.tasks import BenchmarkTask, select_tasks  # noqa: E402


def main() -> None:
    tasks = [BenchmarkTask("bench", str(index), str(index), f"prompt {index}", {}) for index in range(20)]
    first = select_tasks(tasks, 5, 1234, "bench")
    second = select_tasks(list(reversed(tasks)), 5, 1234, "bench")
    assert [task.sample_id for task in first] == [task.sample_id for task in second]
    assert len(first) == 5
if __name__ == "__main__":
    main()
