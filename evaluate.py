"""统一运行并评测 GraphResearcher."""

import argparse
import logging
import sys
from pathlib import Path

SRC_DIR = Path(__file__).parent / "src"
sys.path.insert(0, str(SRC_DIR))

from benchmarking.orchestrator import execute  # noqa: E402


def main() -> None:
    """解析统一评估参数并启动编排器."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="运行 GraphResearcher 的统一 Benchmark 评估。")
    parser.add_argument("--config", type=Path, default=Path("evaluate.yaml"), help="评估 YAML 路径。")
    parser.add_argument("--check", action="store_true", help="只校验配置和数据，不调用 Agent 或评测 API。")
    args = parser.parse_args()
    try:
        execute(args.config.resolve(), check_only=args.check)
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
