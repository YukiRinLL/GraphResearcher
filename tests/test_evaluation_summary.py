"""Markdown 评估汇总的独立回归测试。"""

import sys
from pathlib import Path

SRC_DIR = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from benchmarking.summary import build_summary, render_markdown  # noqa: E402


def result(index: int) -> dict:
    return {
        "benchmark": "demo",
        "sample_id": str(index),
        "display_name": f"item-{index}",
        "run": {"status": "completed", "duration_seconds": 10.0},
        "evaluation": {"status": "completed", "duration_seconds": 2.0},
        "metrics": {"score": float(index)},
    }


def main() -> None:
    small = build_summary([result(index) for index in range(1, 4)])
    small_markdown = render_markdown(small, "run", 1, "run_and_evaluate")
    assert "item-1" in small_markdown
    assert "**平均值（N=3）**" in small_markdown
    assert "2.0000" in small_markdown

    large = build_summary([result(index) for index in range(1, 11)])
    large_markdown = render_markdown(large, "run", 1, "run_and_evaluate")
    assert "item-1" not in large_markdown
    assert "5.5000" in large_markdown
    assert "中位数" not in large_markdown
    assert "最大值" not in large_markdown
if __name__ == "__main__":
    main()
