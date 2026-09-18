"""统一评估配置的独立回归测试。"""

import sys
import tempfile
from pathlib import Path

SRC_DIR = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from benchmarking.config import load_config  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "evaluate.yaml"
        path.write_text(
            """version: 1
mode: run
seed: 7
sample_count: 2
benchmarks:
  deep_research_bench:
    enabled: true
""",
            encoding="utf-8",
        )
        config = load_config(path)
        assert config["seed"] == 7
        assert config["agent"]["max_rounds"] == 30
        assert config["output"]["markdown_summary"] is True
if __name__ == "__main__":
    main()
