"""评估进程、时间和环境边界."""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from run_config import benchmark_runtime_environment, resolve_benchmark_config

CONFIG_PREFIXES = ("DRB_", "DRB2_", "WLC_", "GR_", "NEO4J_", "LANGFUSE_")
CONFIG_NAMES = {
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "TAVILY_API_KEY",
    "SERPER_API_KEY",
    "JINA_API_KEY",
    "JINA_BASE_URL",
    "LLM_BACKEND",
    "OPENROUTER_API_KEY",
    "OPENROUTER_BASE_URL",
    "RACE_MODEL",
    "FACT_MODEL",
    "LLM_HTTP_TIMEOUT",
    "MAX_OUTPUT_TOKENS",
    "SEARCH_TIMEOUT",
    "API_TIMEOUT",
    "MAX_RETRIES",
    "CONCURRENCY",
    "EXTRACT_MODEL",
    "EXTRACT_API_KEY",
    "EXTRACT_BASE_URL",
    "VERIFIER_MODEL",
    "VERIFIER_API_KEY",
    "VERIFIER_BASE_URL",
    "WRITING_MODEL",
    "WRITING_API_KEY",
    "WRITING_BASE_URL",
    "EMBEDDING_MODEL",
    "OPENAI_API_URL",
    "OPENAI_MODEL",
    "OPENAI_REASONING_EFFORT",
    "OPENAI_MAX_OUTPUT_TOKENS",
    "OPENAI_TIMEOUT",
}


def now_iso() -> str:
    """返回带本地时区的 ISO 8601 时间."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_root_environment(repo_root: Path) -> dict[str, str]:
    """读取根目录服务凭据和兼容配置，并隔离外部评测环境."""
    env_path = repo_root / ".env"
    if not env_path.is_file():
        raise ValueError(f"缺少根目录环境文件：{env_path}")
    values = {key: value for key, value in dotenv_values(env_path).items() if value is not None}
    inherited = {
        key: value
        for key, value in os.environ.items()
        if key not in CONFIG_NAMES and not key.startswith(CONFIG_PREFIXES)
    }
    inherited.update(values)
    return inherited


def benchmark_environment(
    base: dict[str, str], benchmark: str, runtime: dict | None = None,
) -> dict[str, str]:
    """将 YAML 运行参数和根目录凭据映射为原生评测器变量."""
    resolved = resolve_benchmark_config(benchmark, runtime or {}, base)
    base = {**base, **benchmark_runtime_environment(benchmark, resolved)}
    env = dict(base)
    mappings = {
        "deep_research_bench": {
            "DRB_LLM_BACKEND": "LLM_BACKEND",
            "DRB_OPENAI_API_KEY": "OPENAI_API_KEY",
            "DRB_OPENAI_BASE_URL": "OPENAI_BASE_URL",
            "DRB_OPENROUTER_API_KEY": "OPENROUTER_API_KEY",
            "DRB_OPENROUTER_BASE_URL": "OPENROUTER_BASE_URL",
            "DRB_RACE_MODEL": "RACE_MODEL",
            "DRB_FACT_MODEL": "FACT_MODEL",
            "DRB_LLM_HTTP_TIMEOUT": "LLM_HTTP_TIMEOUT",
            "DRB_MAX_OUTPUT_TOKENS": "MAX_OUTPUT_TOKENS",
            "DRB_JINA_API_KEY": "JINA_API_KEY",
        },
        "wiki_live_challenge": {
            "WLC_JINA_API_KEY": "JINA_API_KEY",
            "WLC_JINA_BASE_URL": "JINA_BASE_URL",
            "WLC_EXTRACT_MODEL": "EXTRACT_MODEL",
            "WLC_EXTRACT_API_KEY": "EXTRACT_API_KEY",
            "WLC_EXTRACT_BASE_URL": "EXTRACT_BASE_URL",
            "WLC_VERIFIER_MODEL": "VERIFIER_MODEL",
            "WLC_VERIFIER_API_KEY": "VERIFIER_API_KEY",
            "WLC_VERIFIER_BASE_URL": "VERIFIER_BASE_URL",
            "WLC_WRITING_MODEL": "WRITING_MODEL",
            "WLC_WRITING_API_KEY": "WRITING_API_KEY",
            "WLC_WRITING_BASE_URL": "WRITING_BASE_URL",
            "WLC_EMBEDDING_MODEL": "EMBEDDING_MODEL",
            "WLC_EMBEDDING_API_KEY": "OPENAI_API_KEY",
            "WLC_EMBEDDING_BASE_URL": "OPENAI_BASE_URL",
            "WLC_API_TIMEOUT": "API_TIMEOUT",
            "WLC_MAX_RETRIES": "MAX_RETRIES",
            "WLC_CONCURRENCY": "CONCURRENCY",
        },
        "deep_research_bench_ii": {
            "DRB2_OPENAI_API_URL": "OPENAI_API_URL",
            "DRB2_OPENAI_API_KEY": "OPENAI_API_KEY",
            "DRB2_OPENAI_MODEL": "OPENAI_MODEL",
            "DRB2_REASONING_EFFORT": "OPENAI_REASONING_EFFORT",
            "DRB2_MAX_OUTPUT_TOKENS": "OPENAI_MAX_OUTPUT_TOKENS",
            "DRB2_TIMEOUT": "OPENAI_TIMEOUT",
        },
    }
    defaults = {
        "deep_research_bench": {
            "OPENAI_API_KEY": base.get("OPENAI_API_KEY", ""),
            "OPENAI_BASE_URL": base.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            "OPENROUTER_API_KEY": "",
            "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
            "JINA_API_KEY": base.get("JINA_API_KEY", ""),
        },
        "wiki_live_challenge": {
            "JINA_API_KEY": "",
            "JINA_BASE_URL": "https://r.jina.ai/",
            "EXTRACT_API_KEY": "",
            "EXTRACT_BASE_URL": "",
            "VERIFIER_API_KEY": "",
            "VERIFIER_BASE_URL": "",
            "WRITING_API_KEY": "",
            "WRITING_BASE_URL": "",
            "OPENAI_API_KEY": "",
            "OPENAI_BASE_URL": "https://api.openai.com/v1",
        },
        "deep_research_bench_ii": {
            "OPENAI_API_URL": "https://api.openai.com/v1/chat/completions",
            "OPENAI_API_KEY": base.get("OPENAI_API_KEY", ""),
        },
    }
    env.update(defaults.get(benchmark, {}))
    for source, target in mappings.get(benchmark, {}).items():
        if base.get(source):
            env[target] = base[source]
    return env


def validate_evaluator_environment(config: dict[str, Any], root_env: dict[str, str]) -> None:
    """在调用 API 前校验已启用评测器的密钥配置."""
    if config["mode"] in {"run", "run_and_evaluate"}:
        agent_required = ("OPENAI_API_KEY", "TAVILY_API_KEY", "NEO4J_PASSWORD")
        agent_missing = [name for name in agent_required if not root_env.get(name)]
        if agent_missing:
            raise ValueError(f"根目录 .env 缺少 Agent 配置：{', '.join(agent_missing)}")
    if config["mode"] == "run":
        return
    missing: list[str] = []
    for benchmark, settings in config["benchmarks"].items():
        if not settings.get("enabled", False):
            continue
        evaluation = settings.get("evaluation", {})
        default_dimensions = {
            "deep_research_bench": ["race", "fact"],
            "wiki_live_challenge": ["writing", "verifiability", "citation"],
            "deep_research_bench_ii": ["rubric"],
        }
        dimensions = set(evaluation.get("dimensions", default_dimensions[benchmark]))
        if benchmark == "deep_research_bench":
            backend = resolve_benchmark_config(benchmark, settings.get("runtime", {}), root_env)["backend"]
            key = "DRB_OPENROUTER_API_KEY" if backend == "openrouter" else "DRB_OPENAI_API_KEY"
            if not root_env.get(key) and not (backend == "openai" and root_env.get("OPENAI_API_KEY")):
                missing.append(key)
            if "fact" in dimensions and not (root_env.get("DRB_JINA_API_KEY") or root_env.get("JINA_API_KEY")):
                missing.append("DRB_JINA_API_KEY")
        elif benchmark == "wiki_live_challenge":
            steps = set(settings.get("preprocessing", {}).get("steps", ["extract", "fetch"]))
            required = []
            if "extract" in steps:
                required.extend(["WLC_EXTRACT_API_KEY", "WLC_EXTRACT_BASE_URL"])
            if "fetch" in steps:
                required.append("WLC_JINA_API_KEY")
            if dimensions & {"verifiability", "citation"}:
                required.extend(["WLC_VERIFIER_API_KEY", "WLC_VERIFIER_BASE_URL"])
            if "verifiability" in dimensions:
                required.append("WLC_EMBEDDING_API_KEY")
            if "writing" in dimensions:
                required.extend(["WLC_WRITING_API_KEY", "WLC_WRITING_BASE_URL"])
            missing.extend(name for name in required if not root_env.get(name))
        elif benchmark == "deep_research_bench_ii":
            if not (root_env.get("DRB2_OPENAI_API_KEY") or root_env.get("OPENAI_API_KEY")):
                missing.append("DRB2_OPENAI_API_KEY")
    if missing:
        names = ", ".join(sorted(set(missing)))
        raise ValueError(f"根目录 .env 缺少已启用评测器的配置：{names}")


def run_command(
    command: list[str],
    cwd: Path,
    env: dict[str, str],
    log_path: Path,
    timeout: float | None = None,
) -> tuple[float, str | None]:
    """执行子进程，返回墙钟时间和错误."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    try:
        with log_path.open("a", encoding="utf-8") as log_file:
            completed = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout,
                check=False,
            )
        duration = time.perf_counter() - started
        if completed.returncode != 0:
            return duration, f"命令退出码为 {completed.returncode}"
        return duration, None
    except subprocess.TimeoutExpired:
        return time.perf_counter() - started, f"超过 {timeout} 秒时限"
    except Exception as exc:  # noqa: BLE001 - 需要写入样本级错误而不中断批次
        return time.perf_counter() - started, str(exc)


def write_json(path: Path, value: Any) -> None:
    """以 UTF-8 和稳定缩进写入 JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    """读取 UTF-8 JSON."""
    return json.loads(path.read_text(encoding="utf-8"))
