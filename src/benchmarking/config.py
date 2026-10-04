"""加载并校验统一评估配置."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

BENCHMARK_NAMES = (
    "deep_research_bench",
    "wiki_live_challenge",
    "deep_research_bench_ii",
)
VALID_MODES = {"run", "evaluate", "run_and_evaluate"}

DEFAULTS: dict[str, Any] = {
    "version": 1,
    "mode": "run_and_evaluate",
    "seed": 42,
    "sample_count": None,
    "agent": {
        "name": "graphresearcher",
        "max_rounds": 30,
        "timeout_seconds": 7200,
        "max_retries": 3,
        "max_workers": 1,
        "verbosity": "quiet",
    },
    "execution": {"resume": True, "fail_fast": False, "evaluation_max_workers": 1},
    "output": {"root": "outputs/evaluations", "run_id": None, "markdown_summary": True},
    "input": {
        "run_dir": None,
        "native": {
            "deep_research_bench_jsonl": None,
            "wiki_live_challenge_markdown_dir": None,
            "deep_research_bench_ii_report_dir": None,
        },
    },
    "benchmarks": {},
}


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: Path) -> dict[str, Any]:
    """从 YAML 读取配置并补齐稳定默认值."""
    if not path.is_file():
        raise ValueError(f"配置文件不存在：{path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("evaluate.yaml 的顶层必须是映射。")
    config = _merge(DEFAULTS, raw)
    validate_config(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    """校验会改变执行语义的配置字段."""
    if config.get("version") != 1:
        raise ValueError("当前只支持 evaluate.yaml version: 1。")
    if config.get("mode") not in VALID_MODES:
        raise ValueError(f"mode 必须是 {sorted(VALID_MODES)} 之一。")
    count = config.get("sample_count")
    if count is not None and (not isinstance(count, int) or count <= 0):
        raise ValueError("sample_count 必须是正整数或 null。")
    unknown = set(config.get("benchmarks", {})) - set(BENCHMARK_NAMES)
    if unknown:
        raise ValueError(f"未知 Benchmark：{sorted(unknown)}")
    enabled = [name for name, value in config.get("benchmarks", {}).items() if value.get("enabled", False)]
    if not enabled:
        raise ValueError("至少需要启用一个 Benchmark。")
    for name in enabled:
        local_count = config["benchmarks"][name].get("sample_count")
        if local_count is not None and (not isinstance(local_count, int) or local_count <= 0):
            raise ValueError(f"{name}.sample_count 必须是正整数或 null。")
    if config["agent"]["max_workers"] <= 0:
        raise ValueError("agent.max_workers 必须大于 0。")
    timeout = config["agent"]["timeout_seconds"]
    if timeout != -1 and timeout <= 0:
        raise ValueError("agent.timeout_seconds 必须大于 0，或设为 -1 取消总耗时限制。")
    max_retries = config["agent"]["max_retries"]
    if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 0:
        raise ValueError("agent.max_retries 必须是非负整数，0 表示不重试。")
    if config["execution"]["evaluation_max_workers"] <= 0:
        raise ValueError("execution.evaluation_max_workers 必须大于 0。")
    if config["mode"] == "evaluate":
        native = config["input"]["native"]
        if not config["input"].get("run_dir") and not any(native.values()):
            raise ValueError("evaluate 模式需要 input.run_dir 或至少一个 input.native 路径。")
