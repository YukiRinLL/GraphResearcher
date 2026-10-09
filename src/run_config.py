"""解析可复现的运行参数，并映射到既有 runtime 的环境边界."""

from __future__ import annotations

import math
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

# 每项保存环境变量名和代码默认值。点号用于 models / reporter 两个嵌套字段。
# models.* 与 reporter.model / reporter.reviewer_model 默认空串，解析阶段会
# 回退到顶层 agent.model，因此这里不直接写具体模型名。
AGENT_SETTINGS = {
    "model": ("GR_MODEL", "gpt-5.1"),
    "model_timeout_seconds": ("GR_MODEL_TIMEOUT", 180.0),
    "max_retries": ("GR_MODEL_MAX_RETRIES", 3),
    "search_timeout_seconds": ("SEARCH_TIMEOUT", 30.0),
    "search_dispatch_concurrency": ("GR_SEARCH_DISPATCH_CONCURRENCY", 3),
    "source_extraction_concurrency": ("GR_SOURCE_EXTRACTION_CONCURRENCY", 3),
    "assess_query_concurrency": ("GR_ASSESS_QUERY_CONCURRENCY", 3),
    "models.planner": ("GR_PLANNER_MODEL", ""),
    "models.source_analyzer": ("GR_SOURCE_ANALYZER_MODEL", ""),
    "models.query_reformulator": ("GR_QUERY_REFORMULATOR_MODEL", ""),
    "models.claim_normalizer": ("GR_CLAIM_NORMALIZER_MODEL", ""),
    "models.query_assessor": ("GR_QUERY_ASSESSOR_MODEL", ""),
    "models.portfolio": ("GR_PORTFOLIO_MODEL", ""),
    "models.gap_expander": ("GR_GAP_EXPANDER_MODEL", ""),
    "models.convergence": ("GR_CONVERGENCE_MODEL", ""),
    "reporter.model": ("GR_REPORTER_GLOBAL_MODEL", ""),
    "reporter.reviewer_model": ("GR_REPORT_REVIEWER_MODEL", ""),
    "reporter.model_timeout_seconds": ("GR_REPORTER_GLOBAL_TIMEOUT", 600.0),
    "reporter.packet_tokens": ("GR_GLOBAL_PACKET_TOKENS", 48000),
    "reporter.output_tokens": ("GR_GLOBAL_WRITER_OUTPUT_TOKENS", 40000),
}
AGENT_DEFAULTS = {
    "name": "graphresearcher", "max_rounds": 30, "timeout_seconds": 7200.0,
    "max_workers": 1, "verbosity": "quiet",
}

# 评测器通过各自的 runtime 区块配置，使用既有的命名空间变量传入适配层。
BENCHMARK_SETTINGS = {
    "deep_research_bench": {
        "backend": ("DRB_LLM_BACKEND", "openai"),
        "race_model": ("DRB_RACE_MODEL", "gpt-5.5"),
        "fact_model": ("DRB_FACT_MODEL", "gpt-5.4-mini"),
        "model_timeout_seconds": ("DRB_LLM_HTTP_TIMEOUT", 600),
        "max_output_tokens": ("DRB_MAX_OUTPUT_TOKENS", 64000),
    },
    "wiki_live_challenge": {
        "extract_model": ("WLC_EXTRACT_MODEL", "gemini-2.5-flash"),
        "verifier_model": ("WLC_VERIFIER_MODEL", "gemini-2.5-flash"),
        "writing_model": ("WLC_WRITING_MODEL", "gemini-2.5-pro"),
        "embedding_model": ("WLC_EMBEDDING_MODEL", "text-embedding-3-small"),
        "model_timeout_seconds": ("WLC_API_TIMEOUT", 300.0),
        "max_retries": ("WLC_MAX_RETRIES", 3),
        "concurrency": ("WLC_CONCURRENCY", 10),
    },
    "deep_research_bench_ii": {
        "model": ("DRB2_OPENAI_MODEL", "gpt-5.5"),
        "reasoning_effort": ("DRB2_REASONING_EFFORT", "medium"),
        "max_output_tokens": ("DRB2_MAX_OUTPUT_TOKENS", 32768),
        "model_timeout_seconds": ("DRB2_TIMEOUT", 600),
    },
}


def read_config_file(path: Path) -> dict[str, Any]:
    """读取 YAML 映射，保留未填写的字段以便后续进行环境回退."""
    if not path.is_file():
        raise ValueError(f"配置文件不存在：{path}")
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"YAML 格式错误：{path}") from exc
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError("配置文件的顶层必须是映射。")
    return value


def _validated(value: Any, default: Any, field: str) -> Any:
    if isinstance(default, str):
        # 默认值为空串的字段（reporter.model、reporter.reviewer_model、
        # models.*）允许留空，留空时在 resolve_agent_config 中回退到
        # 顶层 agent.model；其余字符串字段必须非空。
        allow_empty = default == ""
        if not isinstance(value, str) or (not value.strip() and not allow_empty):
            raise ValueError(f"{field} 必须是非空字符串。")
        return value.strip()
    integer = isinstance(default, int)
    if isinstance(value, bool) or not isinstance(value, int if integer else (int, float)):
        raise ValueError(f"{field} 必须是{'整数' if integer else '数值'}。")
    if not math.isfinite(value):
        raise ValueError(f"{field} 必须是有限数值。")
    if field.endswith(".timeout_seconds") and value == -1:
        return value
    minimum = 0 if field.rsplit(".", 1)[-1] in {"max_rounds", "max_retries"} else 1
    if value < 0 or (minimum == 1 and value <= 0):
        raise ValueError(f"{field} 必须{'非负' if minimum == 0 else '大于 0'}。")
    return value


def _resolve_fields(raw: dict, settings: dict, env: Mapping[str, str], prefix: str) -> dict:
    result = {}
    for field, (env_name, default) in settings.items():
        if field in raw:
            value = raw[field]
        elif env.get(env_name):
            try:
                value = type(default)(env[env_name])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{env_name} 的类型无效。") from exc
        else:
            value = default
        result[field] = _validated(value, default, f"{prefix}.{field}")
    return result


def resolve_agent_config(
    raw: dict, environ: Mapping[str, str], overrides: dict | None = None,
) -> dict:
    """按显式 CLI、YAML、兼容环境和默认值的顺序解析 Agent 参数."""
    if not isinstance(raw, dict):
        raise ValueError("agent 必须是映射。")
    supplied = {**raw, **(overrides or {})}
    reporter = supplied.get("reporter", {})
    if not isinstance(reporter, dict):
        raise ValueError("agent.reporter 必须是映射。")
    models = supplied.get("models", {})
    if models is None:
        models = {}
    if not isinstance(models, dict):
        raise ValueError("agent.models 必须是映射。")
    flattened = {
        key: value
        for key, value in supplied.items()
        if key not in {"reporter", "models"}
    }
    flattened.update({f"reporter.{key}": value for key, value in reporter.items()})
    flattened.update({f"models.{key}": value for key, value in models.items()})
    unknown = set(flattened) - AGENT_SETTINGS.keys() - AGENT_DEFAULTS.keys()
    if unknown:
        raise ValueError(f"未知 Agent 配置字段：{', '.join(sorted(unknown))}")
    values = _resolve_fields(flattened, AGENT_SETTINGS, environ, "agent")
    values.update({
        key: _validated(supplied.get(key, default), default, f"agent.{key}")
        for key, default in AGENT_DEFAULTS.items()
    })
    if values["verbosity"] not in {"quiet", "normal", "debug"}:
        raise ValueError("agent.verbosity 必须是 quiet、normal 或 debug。")
    nested_prefixes = ("reporter.", "models.")
    result = {
        key: value for key, value in values.items()
        if not any(key.startswith(prefix) for prefix in nested_prefixes)
    }
    result["reporter"] = {
        key.split(".", 1)[1]: value
        for key, value in values.items() if key.startswith("reporter.")
    }
    result["models"] = {
        key.split(".", 1)[1]: value
        for key, value in values.items() if key.startswith("models.")
    }
    # 留空的模型选择统一回退到顶层 agent.model，让快照里保存的就是
    # 本次运行实际生效的模型，避免环境变量层面再出现二次回退歧义。
    result["reporter"]["model"] = result["reporter"]["model"] or result["model"]
    result["reporter"]["reviewer_model"] = result["reporter"]["reviewer_model"] or result["model"]
    for purpose in list(result["models"]):
        if not result["models"][purpose]:
            result["models"][purpose] = result["model"]
    return result


def agent_environment(agent: dict) -> dict[str, str]:
    """将已解析的 Agent 参数转换为 runtime 环境变量，不携带服务凭据."""
    values = {
        **agent,
        **{f"reporter.{key}": value for key, value in agent.get("reporter", {}).items()},
        **{f"models.{key}": value for key, value in agent.get("models", {}).items()},
    }
    return {env_name: str(values[field]) for field, (env_name, _) in AGENT_SETTINGS.items()}


def resolve_benchmark_config(benchmark: str, raw: dict, environ: Mapping[str, str]) -> dict:
    """解析一套评测器的运行参数，保留各自的重试和并发语义."""
    if not isinstance(raw, dict):
        raise ValueError(f"benchmarks.{benchmark}.runtime 必须是映射。")
    settings = BENCHMARK_SETTINGS[benchmark]
    unknown = set(raw) - settings.keys()
    if unknown:
        raise ValueError(f"未知 {benchmark}.runtime 配置字段：{', '.join(sorted(unknown))}")
    result = _resolve_fields(raw, settings, environ, f"benchmarks.{benchmark}.runtime")
    if benchmark == "deep_research_bench":
        result["backend"] = result["backend"].lower()
        if result["backend"] not in {"openai", "openrouter"}:
            raise ValueError("deep_research_bench.runtime.backend 必须是 openai 或 openrouter。")
    return result


def benchmark_runtime_environment(benchmark: str, runtime: dict) -> dict[str, str]:
    """将已解析的评测参数转换为既有命名空间变量."""
    return {env_name: str(runtime[field]) for field, (env_name, _) in BENCHMARK_SETTINGS[benchmark].items()}


def resolve_run_config(config: dict, environ: Mapping[str, str]) -> dict:
    """解析一次评测运行的所有行为参数，不修改输入配置或环境."""
    result = deepcopy(config)
    result["agent"] = resolve_agent_config(config.get("agent", {}), environ)
    for name, settings in result.get("benchmarks", {}).items():
        settings["runtime"] = resolve_benchmark_config(name, settings.get("runtime", {}), environ)
    return result


def write_agent_snapshot(path: Path, agent: dict) -> None:
    """保存经过白名单解析的有效 Agent 参数，供复现和子进程启动使用."""
    safe_agent = resolve_agent_config(agent, {})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"version": 1, "agent": safe_agent}, allow_unicode=True, sort_keys=False), encoding="utf-8")
