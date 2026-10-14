"""Central configuration for GraphResearcher agents.

Provides the model factory, prompt loader, and the `system_prompt` / model
constants that the workflow modules (`workflow.py`, `agents/searcher.py`,
`agents/reporter_global_workflow.py`) reference as `config.*`.

Follows the repo import convention: `src/` is on `sys.path`, so this module
imports sibling packages with bare names (`prompts.`, not `deep_research.`).
"""

import os
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


REPORTER_GLOBAL_MODEL = os.environ.get("GR_REPORTER_GLOBAL_MODEL", "").strip() or DEFAULT_MODEL
GR_GLOBAL_WRITER_OUTPUT_TOKENS = _positive_int_from_env(
    "GR_GLOBAL_WRITER_OUTPUT_TOKENS", 40_000
)
GR_GLOBAL_PACKET_TOKENS = _positive_int_from_env("GR_GLOBAL_PACKET_TOKENS", 48_000)
# 初稿（draft_report）按全图证据无上限拼接，曾出现 37 万字符的草稿
# 挤占 writer 上下文。封顶后被截断的材料仍完整保留在预算化 findings 中。
GR_REPORTER_DRAFT_MAX_CHARS = _positive_int_from_env(
    "GR_REPORTER_DRAFT_MAX_CHARS", 120_000
)
# research_notes 是每查询的证据清单/分析模式元数据，体量小但 ID 列表
# 可能很长，这里设置打包进 writer prompt 的总字符安全上限。
GR_REPORTER_NOTES_MAX_CHARS = _positive_int_from_env(
    "GR_REPORTER_NOTES_MAX_CHARS", 16_000
)
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

# 所有 Query 共用来源 analyzer 的进程内并发上限；值为 1 时模型调用串行。
SOURCE_EXTRACTION_CONCURRENCY = _positive_int_from_env(
    "GR_SOURCE_EXTRACTION_CONCURRENCY", 3
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
    max_retries: Optional[int] = None,
    timeout: Optional[float] = None,
) -> ChatOpenAI:
    """Build a chat model bound to the configured OpenAI-compatible endpoint.

    Reads ``OPENAI_API_KEY`` and the optional ``OPENAI_BASE_URL`` from the
    environment so the project can run against an alternative proxy.

    Args:
        model_name: Model identifier; defaults to ``GR_MODEL`` / ``DEFAULT_MODEL``.
        temperature: Sampling temperature.
        max_retries: 每次模型调用遇到暂时性错误时的自动重试次数；未指定时
            读取 ``GR_MODEL_MAX_RETRIES``，默认是 3。
        timeout: Per-request timeout in seconds; defaults to ``GR_MODEL_TIMEOUT``
            or 180 seconds.

    Returns:
        A configured ``ChatOpenAI`` instance.
    """
    if max_retries is None:
        try:
            max_retries = int(os.environ.get("GR_MODEL_MAX_RETRIES", "3"))
        except ValueError as exc:
            raise ValueError("GR_MODEL_MAX_RETRIES 必须是非负整数。") from exc
        if max_retries < 0:
            raise ValueError("GR_MODEL_MAX_RETRIES 必须是非负整数。")
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
reporter_global_system_prompt = load_prompt("reporter_global")
report_reviewer_system_prompt = load_prompt("report_reviewer")
analyzer_system_prompt = load_prompt("analyzer")

# 每一类 LLM 调用使用的模型名环境变量。未设置或留空时回退到 DEFAULT_MODEL
# （即 GR_MODEL / agent.model），与 evaluate.yaml 的 agent.models.* 一一对应。
PURPOSE_MODEL_ENV: dict[str, str] = {
    "planner": "GR_PLANNER_MODEL",
    "source_analyzer": "GR_SOURCE_ANALYZER_MODEL",
    "query_reformulator": "GR_QUERY_REFORMULATOR_MODEL",
    "claim_normalizer": "GR_CLAIM_NORMALIZER_MODEL",
    "query_assessor": "GR_QUERY_ASSESSOR_MODEL",
    "portfolio": "GR_PORTFOLIO_MODEL",
    "gap_expander": "GR_GAP_EXPANDER_MODEL",
    "convergence": "GR_CONVERGENCE_MODEL",
}

# Model handles. Built lazily so importing the module (e.g. for assembly checks
# or tests) does not require API credentials.
_model_cache: dict[str, ChatOpenAI] = {}


def _shared_model() -> ChatOpenAI:
    if "default" not in _model_cache:
        _model_cache["default"] = build_model()
    return _model_cache["default"]


def _purpose_model(purpose: str) -> ChatOpenAI:
    """返回某类调用专用的模型句柄，未单独配置时回退到默认模型."""
    if purpose not in PURPOSE_MODEL_ENV:
        raise ValueError(f"Unknown model purpose: {purpose!r}")
    cache_key = f"purpose.{purpose}"
    if cache_key not in _model_cache:
        model_name = os.environ.get(PURPOSE_MODEL_ENV[purpose], "").strip() or DEFAULT_MODEL
        _model_cache[cache_key] = build_model(model_name=model_name)
    return _model_cache[cache_key]


def get_purpose_model(purpose: str) -> ChatOpenAI:
    """供 MemoryManager 等调用方按调用类型取模型句柄."""
    return _purpose_model(purpose)


def _reporter_global_model() -> ChatOpenAI:
    if "reporter_global" not in _model_cache:
        timeout = float(os.environ.get("GR_REPORTER_GLOBAL_TIMEOUT", "600"))
        if timeout <= 0:
            raise ValueError("GR_REPORTER_GLOBAL_TIMEOUT must be positive")
        _model_cache["reporter_global"] = build_model(
            model_name=REPORTER_GLOBAL_MODEL,
            temperature=0.2,
            timeout=timeout,
        )
    return _model_cache["reporter_global"]


def _report_reviewer_model() -> ChatOpenAI:
    if "report_reviewer" not in _model_cache:
        # 留空时回退到 DEFAULT_MODEL；evaluate.yaml 的
        # agent.reporter.reviewer_model 映射到这个环境变量。
        model_name = os.environ.get("GR_REPORT_REVIEWER_MODEL", "").strip() or DEFAULT_MODEL
        _model_cache["report_reviewer"] = build_model(
            model_name=model_name,
            temperature=0.0,
        )
    return _model_cache["report_reviewer"]


def __getattr__(name: str) -> ChatOpenAI:
    """Lazily provide the configured workflow model handles.

    Building the model is deferred until first access so importing
    ``config`` (for prompt loading or assembly checks) does not require API
    credentials.
    """
    if name == "default_model":
        return _shared_model()
    # searcher_model 作为 source_analyzer 的旧名保留，避免外部引用失效。
    if name in ("searcher_model", "source_analyzer_model"):
        return _purpose_model("source_analyzer")
    if name == "reporter_global_model":
        return _reporter_global_model()
    if name == "report_reviewer_model":
        return _report_reviewer_model()
    for purpose_name in PURPOSE_MODEL_ENV:
        if name == f"{purpose_name}_model":
            return _purpose_model(purpose_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
