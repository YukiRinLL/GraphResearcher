"""将样本级结果汇总为 JSON 和 Markdown."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    """按 Benchmark 计算成功样本的算术平均值."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        grouped[result["benchmark"]].append(result)
    benchmarks: dict[str, Any] = {}
    for benchmark, rows in grouped.items():
        evaluated = [row for row in rows if row.get("evaluation", {}).get("status") == "completed"]
        metric_names = sorted({name for row in evaluated for name in row.get("metrics", {})})
        averages = {
            name: _mean([
                float(row["metrics"][name])
                for row in evaluated
                if isinstance(row.get("metrics", {}).get(name), (int, float))
            ])
            for name in metric_names
        }
        run_times = [row["run"]["duration_seconds"] for row in rows if row.get("run", {}).get("status") == "completed"]
        evaluated_run_times = [
            row["run"]["duration_seconds"]
            for row in evaluated
            if isinstance(row.get("run", {}).get("duration_seconds"), (int, float))
        ]
        eval_times = [row["evaluation"]["duration_seconds"] for row in evaluated]
        benchmarks[benchmark] = {
            "selected": len(rows),
            "generated": sum(row.get("run", {}).get("status") == "completed" for row in rows),
            "evaluated": len(evaluated),
            "failed": sum(
                row.get("run", {}).get("status") not in {"completed", "skipped"}
                or row.get("evaluation", {}).get("status") == "failed"
                for row in rows
            ),
            "average_run_seconds": _mean(run_times),
            "average_evaluated_run_seconds": _mean(evaluated_run_times),
            "average_evaluation_seconds": _mean(eval_times),
            "average_metrics": averages,
            "samples": evaluated,
            "all_samples": rows,
        }
    return {"benchmarks": benchmarks}


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def render_markdown(summary: dict[str, Any], run_id: str, seed: int, mode: str) -> str:
    """生成仅包含平均值的 Markdown 报告."""
    lines = [
        "# GraphResearcher Benchmark 评估报告",
        "",
        f"- Run ID: `{run_id}`",
        f"- Seed: `{seed}`",
        f"- Mode: `{mode}`",
        "",
        "## 执行概览",
        "",
        "| Benchmark | 选中 | 已生成 | 已评测 | 失败 | 平均运行时间（秒） | 平均评测时间（秒） |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, data in summary["benchmarks"].items():
        lines.append(
            f"| {name} | {data['selected']} | {data['generated']} | {data['evaluated']} | "
            f"{data['failed']} | {_fmt(data['average_run_seconds'])} | {_fmt(data['average_evaluation_seconds'])} |"
        )
    for name, data in summary["benchmarks"].items():
        lines.extend(["", f"## {name}", ""])
        metrics = list(data["average_metrics"])
        samples = data["samples"]
        if samples and data["selected"] < 10:
            headings = ["ID / 名称", *metrics, "运行时间（秒）", "评测时间（秒）"]
            lines.append("| " + " | ".join(headings) + " |")
            lines.append("|---" + "|---:" * (len(headings) - 1) + "|")
            for sample in samples:
                values = [sample.get("display_name") or sample["sample_id"]]
                values.extend(_fmt(sample.get("metrics", {}).get(metric)) for metric in metrics)
                values.extend([
                    _fmt(sample.get("run", {}).get("duration_seconds")),
                    _fmt(sample.get("evaluation", {}).get("duration_seconds")),
                ])
                lines.append("| " + " | ".join(values) + " |")
            averages = [f"**平均值（N={len(samples)}）**"]
            averages.extend(f"**{_fmt(data['average_metrics'].get(metric))}**" for metric in metrics)
            averages.extend([
                f"**{_fmt(data['average_evaluated_run_seconds'])}**",
                f"**{_fmt(data['average_evaluation_seconds'])}**",
            ])
            lines.append("| " + " | ".join(averages) + " |")
        else:
            headings = ["有效样本数", *metrics, "平均运行时间（秒）", "平均评测时间（秒）"]
            values = [str(len(samples))]
            values.extend(_fmt(data["average_metrics"].get(metric)) for metric in metrics)
            values.extend([
                _fmt(data["average_evaluated_run_seconds"]),
                _fmt(data["average_evaluation_seconds"]),
            ])
            lines.append("| " + " | ".join(headings) + " |")
            lines.append("|" + "---:|" * len(headings))
            lines.append("| " + " | ".join(values) + " |")
    failures = []
    for data in summary["benchmarks"].values():
        for sample in data["all_samples"]:
            run_failed = sample.get("run", {}).get("status") not in {"completed", "skipped"}
            evaluation_failed = mode != "run" and sample.get("evaluation", {}).get("status") != "completed"
            if run_failed or evaluation_failed:
                failures.append(sample)
    if failures:
        lines.extend(["", "## 失败项", "", "| Benchmark | 样本 | 错误 |", "|---|---|---|"])
        for sample in failures:
            error = sample.get("evaluation", {}).get("error") or sample.get("run", {}).get("error") or "未知错误"
            lines.append(f"| {sample['benchmark']} | {sample['display_name']} | {str(error).replace('|', '/')} |")
    return "\n".join(lines) + "\n"
