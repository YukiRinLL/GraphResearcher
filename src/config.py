"""Central configuration for GraphResearcher agents.

Provides the model factory, prompt loader, and the `system_prompt` / model
constants that the workflow modules (`workflow.py`, `agents/searcher.py`,
`agents/reporter_workflow.py`) reference as `config.*`.

Follows the repo import convention: `src/` is on `sys.path`, so this module
imports sibling packages with bare names (`prompts.`, not `deep_research.`).
"""

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from langchain_openai import ChatOpenAI

PROMPTS_DIR = Path(__file__).parent / "prompts"

# Default model name; the project talks to an OpenAI-compatible proxy, so the
# endpoint is taken from OPENAI_BASE_URL when set. Override the model with
# the GR_MODEL environment variable.
DEFAULT_MODEL = os.environ.get("GR_MODEL", "gpt-5.1")


def _positive_int_from_env(name: str, default: int) -> int:
    """读取必须为正整数的环境变量配置."""
    raw_value = os.environ.get(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


REPORTER_CHAPTER_CONCURRENCY = _positive_int_from_env(
    "GR_REPORTER_CHAPTER_CONCURRENCY",
    3,
)

# 章节应用预算包含完整输入、输出预留和消息封装安全余量。
REPORTER_CONTEXT_TOKENS = _positive_int_from_env("GR_REPORTER_CONTEXT_TOKENS", 32_768)
REPORTER_OUTPUT_TOKENS = _positive_int_from_env("GR_REPORTER_OUTPUT_TOKENS", 8_192)
REPORTER_SAFETY_TOKENS = _positive_int_from_env("GR_REPORTER_SAFETY_TOKENS", 1_024)
REPORTER_SOURCE_TOKENS = _positive_int_from_env("GR_REPORTER_SOURCE_TOKENS", 2_000)
REPORTER_TOKENIZER = os.environ.get("GR_REPORTER_TOKENIZER", "").strip()


def _csv_env(name: str) -> list[str]:
    """读取逗号/换行分隔的字符串列表环境变量（去空、去重、保序）."""
    raw = os.environ.get(name, "")
    items = [part.strip() for part in re.split(r"[,\n]", raw) if part.strip()]
    return list(dict.fromkeys(items))


# 硬屏蔽来源：命中的种子文献在证据入图前被整源剔除（连同其文档/陈述/证据），
# 已在图中的同源节点会被标记 blocked 并从报告引用注册表排除。
# GR_BLOCKED_URLS：完整 URL 或 URL 片段；GR_BLOCKED_TITLES：标题子串（忽略大小写）。
BLOCKED_SOURCE_URLS = _csv_env("GR_BLOCKED_URLS")
BLOCKED_SOURCE_TITLES = _csv_env("GR_BLOCKED_TITLES")


# Max number of concurrent searcher dispatches per superstep. Each searcher
# call involves a Tavily search + analyzer LLM pass (10-30s of I/O); running
# multiple in parallel via ThreadPoolExecutor cuts wall-clock time for the
# dispatch phase proportionally. Graph writes are serialised by
# MemoryManager._state_lock, so this only parallelises the I/O-bound search
# and analysis work.
SEARCH_DISPATCH_CONCURRENCY = _positive_int_from_env(
    "GR_SEARCH_DISPATCH_CONCURRENCY",
    3,
)

# Max number of concurrent assess_query evaluations per superstep. Each
# assess_query call involves 1-2 LLM passes (normalize_claims + sufficiency
# evaluation) that read only the query's own evidence subgraph; they are
# independent across queries and can run in parallel. Graph writes are
# serialised by MemoryManager._state_lock and graph_tools._loop_lock, so
# only the LLM-bound evaluation work is parallelised.
ASSESS_QUERY_CONCURRENCY = _positive_int_from_env(
    "GR_ASSESS_QUERY_CONCURRENCY",
    3,
)

# Neo4j config
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.environ.get("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD")
NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")


def build_model(
    model_name: Optional[str] = None,
    temperature: float = 0.7,
    max_retries: int = 3,
    timeout: Optional[float] = None,
) -> ChatOpenAI:
    """Build a chat model bound to the configured OpenAI-compatible endpoint.

    Reads ``OPENAI_API_KEY`` and the optional ``OPENAI_BASE_URL`` from the
    environment so the project can run against an alternative proxy.

    Args:
        model_name: Model identifier; defaults to ``GR_MODEL`` / ``DEFAULT_MODEL``.
        temperature: Sampling temperature.
        max_retries: Number of automatic retries on transient API errors.
        timeout: Per-request timeout in seconds; defaults to ``GR_MODEL_TIMEOUT``
            or 180 seconds.

    Returns:
        A configured ``ChatOpenAI`` instance.
    """
    kwargs = {
        "model": model_name or DEFAULT_MODEL,
        "temperature": temperature,
        "max_retries": max_retries,
        "timeout": timeout if timeout is not None else float(os.environ.get("GR_MODEL_TIMEOUT", "180")),
    }
    base_url = os.environ.get("OPENAI_BASE_URL")
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)


def load_prompt(name: str) -> str:
    """Load a prompt file from ``src/prompts`` and inject the current date/time.

    Substitutes the ``<current_date>`` and ``<current_time>`` placeholders used
    by the prompt files.

    Args:
        name: Prompt file stem (without the ``.md`` extension).

    Returns:
        The prompt text with time placeholders resolved.
    """
    text = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    now = datetime.now()
    return text.replace("<current_date>", now.strftime("%Y-%m-%d")).replace(
        "<current_time>", now.strftime("%H:%M:%S")
    )


# System prompts (loaded lazily-at-import; cheap file reads).
reporter_system_prompt = load_prompt("reporter")
reporter_outline_prompt = load_prompt("reporter_outline")
reporter_polish_prompt = load_prompt("reporter_polish")
report_reviewer_system_prompt = load_prompt("report_reviewer")
analyzer_system_prompt = load_prompt("analyzer")

# Model handles. Built lazily so importing the module (e.g. for assembly checks
# or tests) does not require API credentials.
_model_cache: dict[str, ChatOpenAI] = {}


def _shared_model() -> ChatOpenAI:
    if "default" not in _model_cache:
        _model_cache["default"] = build_model()
    return _model_cache["default"]


def _reporter_model() -> ChatOpenAI:
    if "reporter" not in _model_cache:
        _model_cache["reporter"] = build_model(temperature=0.2)
    return _model_cache["reporter"]


def _reporter_polish_model() -> ChatOpenAI:
    if "reporter_polish" not in _model_cache:
        timeout = float(os.environ.get("GR_REPORTER_POLISH_TIMEOUT", "600"))
        if timeout <= 0:
            raise ValueError("GR_REPORTER_POLISH_TIMEOUT must be positive")
        _model_cache["reporter_polish"] = build_model(
            temperature=0.2,
            timeout=timeout,
        )
    return _model_cache["reporter_polish"]


def _report_reviewer_model() -> ChatOpenAI:
    if "report_reviewer" not in _model_cache:
        _model_cache["report_reviewer"] = build_model(temperature=0.0)
    return _model_cache["report_reviewer"]


def __getattr__(name: str) -> ChatOpenAI:
    """Lazily provide the configured workflow model handles.

    Building the model is deferred until first access so that importing
    ``config`` (for prompt loading or assembly checks) does not require API
    credentials to be present.
    """
    if name in ("default_model", "searcher_model"):
        return _shared_model()
    if name == "reporter_model":
        return _reporter_model()
    if name == "reporter_polish_model":
        return _reporter_polish_model()
    if name == "report_reviewer_model":
        return _report_reviewer_model()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
