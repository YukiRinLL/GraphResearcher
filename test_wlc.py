"""Batch-run GraphResearcher on Wiki Live Challenge style inputs.

The input JSON is expected to be a list of items with ``id``, ``question``,
and ``title`` fields. Each completed item writes one markdown report named
``{title}.md`` under ``OUTPUT_PATH``, matching the shape of the reference
``test_wlc.py`` script.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
from pathlib import Path
from typing import Any

import dotenv
from tqdm import tqdm

from main import VERBOSITY_PRESETS, resolve_log_options, run

dotenv.load_dotenv(".env")

# =========================
# 测试运行配置
# =========================
# 输入数据路径：
#   需要是一个 JSON list，每条数据至少包含 id / question / title。
#   默认沿用 Wiki Live Challenge 的 ga_100.json；如需临时切换数据集，
#   优先使用命令行参数 --prompt-path，避免频繁改代码。
PROMPT_PATH = Path("/mnt/h/projects/Wiki_Live_Challenge/data/2025_Mar_Nov/wiki_data/ga_100.json")

# 输出目录：
#   顶层会保存与参考脚本一致的 `{title}.md`，方便直接评测最终报告。
#   每条数据的完整运行产物会保存在 `OUTPUT_PATH/_runs/{id}-{title}/`：
#     - run.log：最重要的详细日志，包含 console 输出、tool call、子图步骤、异常栈等。
#     - report.md：该条数据的最终报告原件。
#     - research_graph.jsonl：该条数据导出的研究图，便于用 graph_viewer.html 复盘。
#     - input.json：该条数据的原始 id/title/question 快照，便于把日志和输入对齐。
OUTPUT_PATH = Path("outputs/wlc_reports")

# 抽样数量：
#   测试阶段建议保持较小，例如 5；设置为 <=0 表示跑完整数据集。
#   如果数据量大且调用真实模型，建议先用小样本确认日志和输出格式。
SAMPLE_SIZE = 5

# 每条数据允许的 Searcher 调度轮数：
#   测试阶段设置为 1 可以快速检查流程、日志和文件输出。
#   正式跑质量评测时可调大，例如 6、12；设置为 0 表示不限制轮数。
MAX_ROUNDS = 1

# 日志详细程度：
#   debug 会在每条 run.log 中保留最完整的信息：
#     - Orchestrator 顶层消息
#     - Searcher / Reporter 子图消息
#     - tool call 参数与 tool result
#     - INFO 级 Python logging
#     - 不截断单条消息内容
#   如果只想快速看最终报告，可用命令行覆盖为 -v quiet。
VERBOSE = "debug"

# 随机种子：
#   None 表示每次随机抽样可能不同。
#   如需可复现实验，请设置固定整数，或使用命令行 --seed 42。
RANDOM_SEED: int | None = None

_SAFE_NAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def safe_filename(title: str) -> str:
    """Return a filesystem-safe markdown stem while preserving readability."""
    name = _SAFE_NAME_RE.sub("-", title).strip().strip(".")
    return name or "untitled"


def load_items(path: Path) -> list[dict[str, Any]]:
    """Load WLC-style JSON records from ``path``."""
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list in {path}")
    return data


def sample_items(items: list[dict[str, Any]], sample_size: int, seed: int | None) -> list[dict[str, Any]]:
    """Randomly sample at most ``sample_size`` records."""
    if sample_size <= 0 or len(items) <= sample_size:
        return items
    rng = random.Random(seed)
    return rng.sample(items, sample_size)


def run_one(item: dict[str, Any], output_dir: Path, max_rounds: int, opts: dict[str, Any]) -> Path | None:
    """Run one item and copy its final report to ``{title}.md``."""
    id_ = str(item["id"])
    prompt = str(item["question"])
    title = str(item["title"])
    safe_title = safe_filename(title)

    out_file = output_dir / f"{safe_title}.md"
    if out_file.exists():
        print(f"Skip existing file: {out_file}")
        return out_file

    run_dir = output_dir / "_runs" / f"{id_}-{safe_title}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "input.json").write_text(
        json.dumps({"id": id_, "title": title, "question": prompt}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Processing: id={id_}, title={title}")
    print(f"Detailed artifacts: {run_dir}")
    run(prompt, run_dir, max_rounds, opts)

    report_path = run_dir / "report.md"
    if not report_path.exists():
        print(f"Warning: missing report.md for id={id_}, title={title}")
        return None

    shutil.copyfile(report_path, out_file)
    return out_file


def parse_args() -> argparse.Namespace:
    """Parse command-line overrides while keeping reference-script defaults."""
    parser = argparse.ArgumentParser(description="Batch-test GraphResearcher on WLC-style JSON data.")
    parser.add_argument("--prompt-path", type=Path, default=PROMPT_PATH, help="Input JSON path.")
    parser.add_argument("--output-path", type=Path, default=OUTPUT_PATH, help="Directory for markdown reports.")
    parser.add_argument("--sample-size", type=int, default=SAMPLE_SIZE, help="Random sample size; <=0 means all.")
    parser.add_argument("--seed", type=int, default=RANDOM_SEED, help="Optional random seed for sampling.")
    parser.add_argument(
        "-r",
        "--max-rounds",
        type=int,
        default=MAX_ROUNDS,
        help="Maximum Searcher dispatches per item; 0 means unlimited.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        choices=list(VERBOSITY_PRESETS),
        default=VERBOSE,
        help="GraphResearcher verbosity preset.",
    )
    args = parser.parse_args()
    # main.resolve_log_options expects these fields because main.py supports
    # fine-grained log overrides. This batch script only exposes the preset
    # (`-v/--verbose`) to keep the test command simple; None means "use preset".
    args.show_tool_calls = None
    args.subgraphs = None
    args.log_level = None
    args.truncate = None
    return args


def main() -> None:
    """Run the batch test."""
    args = parse_args()
    args.output_path.mkdir(parents=True, exist_ok=True)

    items = sample_items(load_items(args.prompt_path), args.sample_size, args.seed)
    opts = resolve_log_options(args)

    for item in tqdm(items, desc="Processing items"):
        try:
            run_one(item, args.output_path, args.max_rounds, opts)
        except KeyError as exc:
            print(f"Skip malformed item missing {exc!s}: {item}")
        except Exception as exc:  # noqa: BLE001 - keep long batch runs moving
            print(f"Error processing id={item.get('id')}, title={item.get('title')}: {exc}")


if __name__ == "__main__":
    main()
