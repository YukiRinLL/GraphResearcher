"""验证三套评测器的 YAML 环境映射和凭据隔离，不执行评测请求。"""

import json
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from benchmarking import adapters  # noqa: E402
from benchmarking.orchestrator import _evaluator_snapshot  # noqa: E402
from benchmarking.runtime import (  # noqa: E402
    benchmark_environment,
    validate_evaluator_environment,
)
from benchmarking.tasks import BenchmarkTask  # noqa: E402
from run_config import BENCHMARK_SETTINGS, resolve_benchmark_config  # noqa: E402


def main():
    root_env = {"OPENAI_API_KEY": "agent-secret", "OPENAI_BASE_URL": "https://agent.invalid/v1",
                "DRB_OPENROUTER_API_KEY": "router-secret", "WLC_EMBEDDING_API_KEY": "embedding-secret"}
    cases = {
        "deep_research_bench": ({"backend": "openrouter", "race_model": "race-yaml", "fact_model": "fact-yaml",
                                 "model_timeout_seconds": 43, "max_output_tokens": 321},
                                {"LLM_BACKEND": "openrouter", "RACE_MODEL": "race-yaml", "FACT_MODEL": "fact-yaml",
                                 "LLM_HTTP_TIMEOUT": "43", "MAX_OUTPUT_TOKENS": "321"}),
        "wiki_live_challenge": ({"extract_model": "extract-yaml", "verifier_model": "verify-yaml",
                                 "writing_model": "write-yaml", "embedding_model": "embed-yaml",
                                 "model_timeout_seconds": 32.5, "max_retries": 0, "concurrency": 2},
                                {"EXTRACT_MODEL": "extract-yaml", "VERIFIER_MODEL": "verify-yaml",
                                 "WRITING_MODEL": "write-yaml", "EMBEDDING_MODEL": "embed-yaml",
                                 "API_TIMEOUT": "32.5", "MAX_RETRIES": "0", "CONCURRENCY": "2"}),
        "deep_research_bench_ii": ({"model": "rubric-yaml", "reasoning_effort": "high",
                                    "max_output_tokens": 456, "model_timeout_seconds": 54},
                                   {"OPENAI_MODEL": "rubric-yaml", "OPENAI_REASONING_EFFORT": "high",
                                    "OPENAI_MAX_OUTPUT_TOKENS": "456", "OPENAI_TIMEOUT": "54"}),
    }
    config = {"mode": "evaluate", "benchmarks": {}}
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        report = root / "report.md"
        report.write_text("离线测试报告", encoding="utf-8")
        for name, (runtime, expected) in cases.items():
            original = deepcopy(runtime)
            env = dict(root_env)
            for key, (env_name, default) in BENCHMARK_SETTINGS[name].items():
                env[env_name] = "openai" if key == "backend" else ("env-model" if isinstance(default, str) else "99")
            before = dict(env)
            actual = benchmark_environment(env, name, runtime)
            assert {key: actual[key] for key in expected} == expected
            assert env == before and runtime == original
            assert actual["OPENAI_API_KEY"] == ("embedding-secret" if name == "wiki_live_challenge" else "agent-secret")
            fallback = resolve_benchmark_config(name, {}, env)
            partial = resolve_benchmark_config(name, {next(iter(runtime)): next(iter(runtime.values()))}, env)
            for key in runtime:
                if key != next(iter(runtime)):
                    assert partial[key] == fallback[key]
            settings = {"runtime": runtime, "enabled": True, "evaluation": {"dimensions": ["race"]}}
            config["benchmarks"][name] = settings

            class Captured(Exception):
                pass

            def capture(_command, _cwd, environment, *_args):
                assert {key: environment[key] for key in expected} == expected
                raise Captured

            task = BenchmarkTask(name, "1", "1", "offline", {"id": 1})
            with patch.object(adapters, "_run", side_effect=capture):
                try:
                    adapters.evaluate_sample(root, task, report, root / name, settings, env)
                except Captured:
                    pass
                else:
                    raise AssertionError("应通过适配层传入评测器环境")

    # 凭据校验也必须使用 YAML 选择的后端，不能被旧的环境配置误导。
    drb_only = {"mode": "evaluate", "benchmarks": {"deep_research_bench": config["benchmarks"]["deep_research_bench"]}}
    validate_evaluator_environment(drb_only, {"DRB_OPENROUTER_API_KEY": "router-secret", "DRB_LLM_BACKEND": "openai"})
    snapshot = _evaluator_snapshot(config, root_env)
    assert snapshot["models"]["deep_research_bench.race"] == "race-yaml"
    assert snapshot["models"]["deep_research_bench_ii"] == "rubric-yaml"
    assert "secret" not in json.dumps(snapshot)
    for name, (runtime, _) in cases.items():
        assert snapshot["benchmarks"][name]["runtime"] == runtime


if __name__ == "__main__":
    main()
