"""加载、过滤并稳定抽取 Benchmark 任务."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BenchmarkTask:
    """统一的 Benchmark 任务视图."""

    benchmark: str
    sample_id: str
    display_name: str
    prompt: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """转换为可写入 manifest 的字典."""
        return asdict(self)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_tasks(repo_root: Path, benchmark: str, settings: dict[str, Any]) -> list[BenchmarkTask]:
    """从原生数据集加载并过滤任务."""
    selection = settings.get("selection", {})
    if benchmark == "deep_research_bench":
        path = repo_root / "Benchmark/deep_research_bench/data/prompt_data/query.jsonl"
        rows = _read_jsonl(path)
        languages = set(selection.get("languages") or [])
        topics = set(selection.get("topics") or [])
        rows = [row for row in rows if not languages or row.get("language") in languages]
        rows = [row for row in rows if not topics or row.get("topic") in topics]
        return [
            BenchmarkTask(benchmark, str(row["id"]), str(row["id"]), row["prompt"], row)
            for row in rows
        ]
    if benchmark == "wiki_live_challenge":
        dataset = selection.get("dataset", "2025_Mar_Nov")
        path = repo_root / f"Benchmark/Wiki_Live_Challenge/data/{dataset}/wiki_data/ga_100.json"
        rows = json.loads(path.read_text(encoding="utf-8"))
        categories = set(selection.get("categories") or [])
        rows = [row for row in rows if not categories or row.get("category") in categories]
        return [
            BenchmarkTask(benchmark, str(row["id"]), row["title"], row["question"], {**row, "dataset": dataset})
            for row in rows
        ]
    if benchmark == "deep_research_bench_ii":
        path = repo_root / "Benchmark/DeepResearch-Bench-II/tasks_and_rubrics.jsonl"
        rows = _read_jsonl(path)
        languages = set(selection.get("languages") or [])
        themes = set(selection.get("themes") or [])
        rows = [row for row in rows if not languages or row.get("language") in languages]
        rows = [row for row in rows if not themes or row.get("theme") in themes]
        return [
            BenchmarkTask(benchmark, str(row["idx"]), f"idx-{row['idx']}", row["prompt"], row)
            for row in rows
        ]
    raise ValueError(f"不支持的 Benchmark：{benchmark}")


def select_tasks(tasks: list[BenchmarkTask], count: int | None, seed: int, benchmark: str) -> list[BenchmarkTask]:
    """使用 Benchmark 独立种子进行无放回抽样."""
    ordered = sorted(tasks, key=lambda task: (int(task.sample_id) if task.sample_id.isdigit() else task.sample_id))
    if count is None:
        return ordered
    if count > len(ordered):
        raise ValueError(f"{benchmark} 过滤后只有 {len(ordered)} 个样本，无法抽取 {count} 个。")
    digest = hashlib.sha256(f"{seed}:{benchmark}".encode()).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    selected_ids = {task.sample_id for task in rng.sample(ordered, count)}
    return [task for task in ordered if task.sample_id in selected_ids]
