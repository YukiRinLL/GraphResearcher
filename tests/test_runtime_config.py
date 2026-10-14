"""离线验证共享配置解析和两个启动入口的实际生效参数。"""

import json
import os
import subprocess
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from benchmarking.config import load_config  # noqa: E402
from benchmarking.orchestrator import _run_agent  # noqa: E402
from benchmarking.tasks import BenchmarkTask  # noqa: E402
from run_config import (  # noqa: E402
    AGENT_SETTINGS,
    BENCHMARK_SETTINGS,
    agent_environment,
    read_config_file,
    resolve_agent_config,
    resolve_benchmark_config,
    write_agent_snapshot,
)


def raises(function, *args):
    try:
        function(*args)
    except ValueError:
        return
    raise AssertionError("应拒绝无效配置")


def test_resolution():
    env = {"GR_MODEL": "legacy-model", "GR_MODEL_MAX_RETRIES": "7", "GR_MODEL_TIMEOUT": "42"}
    raw = {"model": "yaml-model", "max_rounds": 8, "reporter": {"output_tokens": 2000}}
    original = deepcopy(raw)
    resolved = resolve_agent_config(raw, env, {"max_rounds": 0})
    assert resolved["model"] == "yaml-model" and resolved["max_rounds"] == 0
    assert resolved["max_retries"] == 7 and resolved["model_timeout_seconds"] == 42
    assert resolved["reporter"]["model"] == "yaml-model"
    assert resolved["reporter"]["output_tokens"] == 2000
    assert resolved["reporter"]["packet_tokens"] == 48000 and raw == original
    assert resolve_agent_config({"max_retries": 0}, env)["max_retries"] == 0
    assert resolve_agent_config({}, {})["max_retries"] == 3

    for field, (env_name, default) in AGENT_SETTINGS.items():
        if field == "merge_normalize_assess":
            value = 1  # 0/1 开关字段只能取 0 或 1。
        else:
            value = "test-model" if isinstance(default, str) else 11
        section, _, child = field.partition(".")
        supplied = {section: {child: value}} if child else {field: value}
        resolved = resolve_agent_config(supplied, {env_name: "ignored-invalid-value"})
        assert agent_environment(resolved)[env_name] == str(value)
        supplied_null = {section: {child: None}} if child else {field: None}
        raises(resolve_agent_config, supplied_null, {})
    for invalid in (True, 0, -1, 1.5, "3", float("inf")):
        raises(resolve_agent_config, {"search_dispatch_concurrency": invalid}, {})
    for invalid in (False, 0, -2, float("nan"), "180"):
        raises(resolve_agent_config, {"model_timeout_seconds": invalid}, {})
    for invalid in ({"reporter": []}, {"api_key": "secret"}, {"source_extration_concurrency": 3}):
        raises(resolve_agent_config, invalid, {})
    for name in BENCHMARK_SETTINGS:
        assert resolve_benchmark_config(name, {}, {})
        raises(resolve_benchmark_config, name, {"api_key": "secret"}, {})


def test_snapshots(root):
    agent = resolve_agent_config({}, {"GR_MODEL": "resolved-model", "OPENAI_API_KEY": "secret-marker"})
    path = root / "agent.effective.yaml"
    write_agent_snapshot(path, agent)
    assert "secret-marker" not in path.read_text()
    assert read_config_file(path)["agent"] == agent
    assert resolve_agent_config(read_config_file(path)["agent"], {"GR_MODEL": "other"}) == agent


def test_purpose_model_routing():
    import config

    for source_model in ("", "source-model"):
        env = {name: "" for name in config.PURPOSE_MODEL_ENV.values()}
        env["GR_SOURCE_ANALYZER_MODEL"] = source_model
        with (
            patch.dict(os.environ, env),
            patch.dict(config._model_cache, {}, clear=True),
            patch.object(config, "DEFAULT_MODEL", "default-model"),
            patch.object(config, "build_model", side_effect=lambda **kwargs: SimpleNamespace(**kwargs)) as build,
        ):
            models = {purpose: config.get_purpose_model(purpose) for purpose in config.PURPOSE_MODEL_ENV}
            for purpose, model in models.items():
                expected = source_model if purpose == "source_analyzer" and source_model else "default-model"
                assert model.model_name == expected
                assert config.get_purpose_model(purpose) is model
            assert config.source_analyzer_model is models["source_analyzer"]
            assert config.searcher_model is models["source_analyzer"]
            assert len({id(model) for model in models.values()}) == len(models)
            assert build.call_count == len(models)


def entry_script():
    # 只替换研究循环；真实入口仍负责解析、应用配置和写入快照。
    return f'''import importlib.util
import json
import sys
import dotenv
from pathlib import Path
dotenv.load_dotenv = lambda *args, **kwargs: False
spec = importlib.util.spec_from_file_location("research_entry", {str(ROOT / "main.py")!r})
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)
entry.DEFAULT_CONFIG_PATH = Path(__file__).parent / "evaluate.yaml"
def fake_run(request, output_dir, max_rounds, opts):
    assert "config" not in sys.modules
    import config
    from agents import searcher
    from tools import search_tools
    model = config.build_model()
    reporter = config.reporter_global_model
    observed = {{
        "model": model.model_name, "model_timeout": model.request_timeout,
        "retries": model.max_retries, "rounds": max_rounds,
        "dispatch": config.SEARCH_DISPATCH_CONCURRENCY,
        "sources": config.SOURCE_EXTRACTION_CONCURRENCY,
        "slots": searcher._source_analyzer_slots._value,
        "assess": config.ASSESS_QUERY_CONCURRENCY,
        "search_timeout": search_tools.SEARCH_TIMEOUT,
        "reporter_model": reporter.model_name, "reporter_timeout": reporter.request_timeout,
        "packet_tokens": config.GR_GLOBAL_PACKET_TOKENS,
        "output_tokens": config.GR_GLOBAL_WRITER_OUTPUT_TOKENS,
        "stream": opts["stream"],
    }}
    (output_dir / "report.md").write_text(json.dumps(observed))
entry.run = fake_run
entry.main()
'''


def test_entrypoints(root):
    script = root / "main.py"
    script.write_text(entry_script(), encoding="utf-8")
    path = root / "evaluate.yaml"
    raw = {
        "model": "yaml-model", "model_timeout_seconds": 41.5, "max_retries": 2,
        "max_rounds": 6, "verbosity": "debug", "search_timeout_seconds": 12.5,
        "search_dispatch_concurrency": 2,
        "source_extraction_concurrency": 4, "assess_query_concurrency": 6,
        "reporter": {"model": "writer-model", "model_timeout_seconds": 83,
                     "packet_tokens": 8000, "output_tokens": 3000},
    }
    # 直接运行只需要 Agent 区块，不要求启用 Benchmark。
    path.write_text(yaml.safe_dump({"agent": raw}), encoding="utf-8")
    env = {"OPENAI_API_KEY": "test-key", "GR_MODEL": "legacy-model", "GR_MODEL_TIMEOUT": "99",
           "GR_MODEL_MAX_RETRIES": "9", "GR_SEARCH_DISPATCH_CONCURRENCY": "9"}
    direct = root / "direct"
    subprocess.run(
        [sys.executable, str(script), "offline", "--config", str(path), "--output-dir", str(direct)],
        env=env, check=True, capture_output=True, text=True,
    )
    actual = json.loads((direct / "report.md").read_text())
    assert actual == {
        "model": "yaml-model", "model_timeout": 41.5, "retries": 2, "rounds": 6,
        "dispatch": 2, "sources": 4, "slots": 4, "assess": 6,
        "search_timeout": 12.5,
        "reporter_model": "writer-model", "reporter_timeout": 83,
        "packet_tokens": 8000, "output_tokens": 3000, "stream": True,
    }, actual

    path.write_text(yaml.safe_dump({"mode": "run", "agent": raw,
                                   "benchmarks": {"deep_research_bench": {"enabled": True}}}))
    config = load_config(path)
    task = BenchmarkTask("deep_research_bench", "1", "1", "offline", {})
    run_dir = root / "batch"
    result = _run_agent(root, run_dir, task, config, env)
    assert result["run"]["status"] == "completed", result
    report = run_dir / result["run"]["report_path"]
    assert json.loads(report.read_text()) == actual
    assert read_config_file(report.parent / "agent.effective.yaml") == read_config_file(direct / "agent.effective.yaml")

    override = root / "override"
    subprocess.run(
        [sys.executable, str(script), "offline", "--config", str(path), "--output-dir", str(override),
         "--max-rounds", "0", "--verbose", "quiet"], env=env, check=True, capture_output=True,
    )
    overridden = json.loads((override / "report.md").read_text())
    assert overridden == {**actual, "rounds": 0, "stream": False}
    snapshot = read_config_file(override / "agent.effective.yaml")["agent"]
    assert snapshot["max_rounds"] == 0 and snapshot["verbosity"] == "quiet"
    assert "test-key" not in (override / "agent.effective.yaml").read_text()

    automatic = root / "automatic"
    subprocess.run([sys.executable, str(script), "offline", "--output-dir", str(automatic)],
                   env=env, check=True, capture_output=True)
    assert json.loads((automatic / "report.md").read_text()) == actual

    path.unlink()
    legacy = root / "legacy"
    subprocess.run([sys.executable, str(script), "offline", "--output-dir", str(legacy)],
                   env=env, check=True, capture_output=True)
    old = json.loads((legacy / "report.md").read_text())
    assert old["model"] == "legacy-model" and old["retries"] == 9 and old["rounds"] == 30


def main():
    test_resolution()
    test_purpose_model_routing()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        test_snapshots(root)
        test_entrypoints(root)


if __name__ == "__main__":
    main()
