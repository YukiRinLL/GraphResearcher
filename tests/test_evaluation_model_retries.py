"""验证 YAML 重试配置传入真实模型客户端，不发送 API 请求。"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

SRC_DIR = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

import config as model_config  # noqa: E402
from benchmarking.config import load_config  # noqa: E402
from benchmarking.orchestrator import _run_agent  # noqa: E402
from benchmarking.tasks import BenchmarkTask  # noqa: E402


def main() -> None:
    with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=True):
        assert model_config.build_model().max_retries == 3
        for raw_value in ("-1", "0.5", "invalid"):
            with patch.dict("os.environ", {"GR_MODEL_MAX_RETRIES": raw_value}):
                try:
                    model_config.build_model()
                except ValueError as exc:
                    assert "GR_MODEL_MAX_RETRIES" in str(exc)
                else:
                    raise AssertionError(f"应拒绝无效重试环境变量：{raw_value}")
                assert model_config.build_model(max_retries=0).max_retries == 0

    with tempfile.TemporaryDirectory() as directory:
        repo_root = Path(directory)
        (repo_root / "main.py").write_text(
            f"""import json
import sys
from pathlib import Path

sys.path.insert(0, {str(SRC_DIR)!r})
import config

models = {{
    "default": config.build_model(),
    "searcher": config.searcher_model,
    "reporter": config.reporter_global_model,
    "reviewer": config.report_reviewer_model,
    "explicit": config.build_model(max_retries=2),
}}
retries = {{
    name: [model.max_retries, model.root_client.max_retries, model.root_async_client.max_retries]
    for name, model in models.items()
}}
output_dir = Path(sys.argv[sys.argv.index("--output-dir") + 1])
(output_dir / "report.md").write_text(json.dumps(retries), encoding="utf-8")
""",
            encoding="utf-8",
        )
        task = BenchmarkTask("deep_research_bench", "1", "1", "本地测试", {})
        env = {"OPENAI_API_KEY": "test-key", "GR_MODEL_MAX_RETRIES": "9"}
        config_path = repo_root / "evaluate.yaml"
        for index, max_retries in enumerate((None, 0, 1)):
            retry_yaml = "" if max_retries is None else f"agent:\n  max_retries: {max_retries}\n"
            config_path.write_text(
                f"mode: run\nbenchmarks:\n  deep_research_bench:\n    enabled: true\n{retry_yaml}",
                encoding="utf-8",
            )
            config = load_config(config_path)
            run_dir = repo_root / f"run-{index}"
            result = _run_agent(repo_root, run_dir, task, config, env)
            assert result["run"]["status"] == "completed", result
            report_path = run_dir / result["run"]["report_path"]
            actual = json.loads(report_path.read_text(encoding="utf-8"))
            expected = 3 if max_retries is None else max_retries
            for name in ("default", "searcher", "reporter", "reviewer"):
                assert actual[name] == [expected] * 3, actual
            assert actual["explicit"] == [2] * 3
            assert env["GR_MODEL_MAX_RETRIES"] == "9"


if __name__ == "__main__":
    main()
