"""验证 Query 派发和来源抽取的 YAML 校验与真实子进程传递，不调用外部服务。"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import yaml

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

import config as runtime_config  # noqa: E402
from benchmarking.config import load_config  # noqa: E402
from benchmarking.orchestrator import _run_agent  # noqa: E402
from benchmarking.tasks import BenchmarkTask  # noqa: E402

BASE_YAML = "mode: run\nbenchmarks:\n  deep_research_bench:\n    enabled: true\n"
ENV_NAMES = {
    "search_dispatch_concurrency": "GR_SEARCH_DISPATCH_CONCURRENCY",
    "source_extraction_concurrency": "GR_SOURCE_EXTRACTION_CONCURRENCY",
}


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        path = root / "config.yaml"
        for field in ENV_NAMES:
            for raw in ("0", "-1", "0.5", "true", "false", "null", '"3"'):
                path.write_text(f"{BASE_YAML}agent:\n  {field}: {raw}\n")
                try:
                    load_config(path)
                except ValueError as exc:
                    assert f"agent.{field}" in str(exc)
                else:
                    raise AssertionError(f"应拒绝无效并发配置 {field}：{raw}")

        (root / "main.py").write_text(
            f"""import json
import sys
from pathlib import Path
sys.path.insert(0, {str(SRC_DIR)!r})
import config
from agents import searcher
output = Path(sys.argv[sys.argv.index('--output-dir') + 1])
(output / 'report.md').write_text(json.dumps({{
    'search_dispatch_concurrency': config.SEARCH_DISPATCH_CONCURRENCY,
    'source_extraction_concurrency': config.SOURCE_EXTRACTION_CONCURRENCY,
}}))
""",
            encoding="utf-8",
        )
        task = BenchmarkTask("deep_research_bench", "1", "1", "离线配置测试", {})
        cases = (
            ({}, {}, (3, 3)),
            ({}, {"search_dispatch_concurrency": 7, "source_extraction_concurrency": 5}, (7, 5)),
            ({"search_dispatch_concurrency": 2},
             {"search_dispatch_concurrency": 7, "source_extraction_concurrency": 5}, (2, 5)),
            ({"source_extraction_concurrency": 2},
             {"search_dispatch_concurrency": 7, "source_extraction_concurrency": 5}, (7, 2)),
            ({"search_dispatch_concurrency": 1, "source_extraction_concurrency": 5},
             {"search_dispatch_concurrency": 7, "source_extraction_concurrency": 9}, (1, 5)),
            ({"source_extraction_concurrency": 1},
             {"search_dispatch_concurrency": 7, "source_extraction_concurrency": 9}, (7, 1)),
        )
        for index, (yaml_values, env_values, expected_values) in enumerate(cases):
            extra = yaml.safe_dump({"agent": yaml_values}) if yaml_values else ""
            path.write_text(BASE_YAML + extra, encoding="utf-8")
            config = load_config(path)
            for field in ENV_NAMES:
                if field not in yaml_values:
                    assert field not in config["agent"]
            env = {ENV_NAMES[field]: str(value) for field, value in env_values.items()}
            before = dict(env)
            run_dir = root / f"run-{index}"
            result = _run_agent(root, run_dir, task, config, env)
            assert result["run"]["status"] == "completed", result
            actual = json.loads((run_dir / result["run"]["report_path"]).read_text())
            expected = dict(zip(ENV_NAMES, expected_values))
            assert actual == expected, (actual, expected)
            assert env == before

    for env_name in ENV_NAMES.values():
        for raw in ("0", "-1", "0.5", "true", "invalid"):
            with patch.dict("os.environ", {env_name: raw}):
                try:
                    runtime_config._positive_int_from_env(env_name, 3)
                except ValueError as exc:
                    assert env_name in str(exc)
                else:
                    raise AssertionError(f"应拒绝无效并发环境配置 {env_name}：{raw}")


if __name__ == "__main__":
    main()
