"""通过临时文件和替身生成器验证 Bench I 接入，无需外部服务。"""

# ruff: noqa: T201

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

repo_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_dir))

import test_deepresearch_bench as batch  # noqa: E402


def _items():
    return [
        {"id": 1, "prompt": "原始中文问题\n保留格式", "language": "zh", "topic": "测试"},
        {"id": 2, "prompt": "Original English question", "language": "en"},
        {"id": 3, "prompt": "Another question", "language": "en"},
    ]


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _bench_root(root):
    bench = root / "bench"
    files = [
        "deepresearch_bench_race.py", "data/criteria_data/criteria.jsonl",
        "data/test_data/cleaned_data/reference.jsonl",
        *(f"utils/{name}.py" for name in ("extract", "deduplicate", "scrape", "validate", "stat")),
    ]
    for name in files:
        path = bench / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    (bench / ".env").write_text(
        "LLM_BACKEND=openai\nOPENAI_API_KEY=bench-key\n"
        "OPENAI_BASE_URL=https://bench.example/v1\nJINA_API_KEY=jina-test\n",
        encoding="utf-8",
    )
    batch.write_jsonl(bench / "data/prompt_data/query.jsonl", _items())
    return bench


def _fake_run(prompt, run_dir, max_rounds, opts):
    assert prompt in {item["prompt"] for item in _items()}
    (run_dir / "report.md").write_text(f"# 报告\n{prompt}\n[来源](https://example.org)\n", encoding="utf-8")
    (run_dir / "run.log").write_text("test-log", encoding="utf-8")
    (run_dir / "research_graph.jsonl").write_text("{}\n", encoding="utf-8")


def _test_input_and_sampling():
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "query.jsonl"
        batch.write_jsonl(path, _items())
        items = batch.load_items(path)
        assert items == _items()
        assert batch.sample_items(items, 1, 42) == batch.sample_items(items, 1, 42)
        assert batch.sample_items(items, 0, None) == items
        for invalid in (
            [{**items[0], "id": True}], [{**items[0], "id": "../bad"}],
            [{**items[0], "prompt": " "}], [{**items[0], "language": "other"}],
            [items[0], items[0]], [],
        ):
            batch.write_jsonl(path, invalid)
            try:
                batch.load_items(path)
            except ValueError:
                pass
            else:
                raise AssertionError(f"Invalid input accepted: {invalid}")
        for value in ("../other", "", ".", "/tmp/model", "a/b", "a\\b"):
            try:
                batch.validate_model_name(value)
            except ValueError:
                pass
            else:
                raise AssertionError("Unsafe model name accepted")


def _test_generation_export_and_resume():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        items = _items()
        with patch.object(batch, "run", side_effect=_fake_run) as generator:
            first = batch.run_one(items[0], root, "GraphResearcher", 2, {})
            assert first == root / "report/GraphResearcher/id-1.md"
            batch.run_one(items[0], root, "GraphResearcher", 2, {})
            assert generator.call_count == 1
            run_dir = root / "_runs/GraphResearcher/id-1"
            assert json.loads((run_dir / "input.json").read_text()) == items[0]
            assert (run_dir / "run.log").is_file()
            assert (run_dir / "research_graph.jsonl").is_file()
            raw, query = batch.export_reports(items, root, "GraphResearcher")
            assert len(_read_jsonl(raw)) == 1
            batch.run_one(items[1], root, "GraphResearcher", 2, {})

        # 不发布缺失正文的任务；旧的未发布正文也不能被重试误用。
        stale_dir = root / "_runs/GraphResearcher/id-3"
        stale_dir.mkdir(parents=True)
        (stale_dir / "report.md").write_text("stale report", encoding="utf-8")
        with patch.object(batch, "run", return_value=None):
            assert batch.run_one(items[2], root, "GraphResearcher", 2, {}) is None
        raw, query = batch.export_reports(items, root, "GraphResearcher")
        reports = _read_jsonl(raw)
        assert [record["id"] for record in reports] == [1, 2]
        assert _read_jsonl(query) == items[:2]
        assert set(reports[0]) == {"id", "prompt", "article"}
        assert reports[0]["prompt"] == items[0]["prompt"]
        assert reports[0]["article"] == first.read_text(encoding="utf-8")
        assert not raw.with_suffix(".jsonl.tmp").exists()


def _test_environment_isolation():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        bench = _bench_root(root)
        with patch.dict(os.environ, {"OPENAI_API_KEY": "parent-key"}):
            env = batch.bench_subprocess_env(bench, "all")
            assert env["OPENAI_API_KEY"] == "bench-key"
            batch.run_command_tee([
                sys.executable, "-c",
                "import os; assert os.environ['OPENAI_API_KEY'] == 'bench-key'; print('env-ok')",
            ], bench, root / "env.log", env=env)
            assert os.environ["OPENAI_API_KEY"] == "parent-key"
        (bench / ".env").write_text("LLM_BACKEND=openai\nOPENAI_API_KEY=bench-key\n", encoding="utf-8")
        assert batch.bench_subprocess_env(bench, "race")["OPENAI_API_KEY"] == "bench-key"
        try:
            batch.bench_subprocess_env(bench, "fact")
        except ValueError as exc:
            assert "JINA_API_KEY" in str(exc)
        else:
            raise AssertionError("FACT must require a Jina key")
        (bench / ".env").write_text("OPENROUTER_API_KEY=router-test\n", encoding="utf-8")
        assert batch.bench_subprocess_env(bench, "race")["LLM_BACKEND"] == "openrouter"
        (bench / ".env").unlink()
        try:
            batch.bench_subprocess_env(bench, "race")
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("Missing benchmark .env must fail")


def _test_official_pipeline_commands():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        bench = _bench_root(root)
        output = root / "output"
        with patch.object(batch, "run", side_effect=_fake_run):
            batch.run_one(_items()[1], output, "GraphResearcher", 2, {})
        raw, query = batch.export_reports(_items(), output, "GraphResearcher")
        with patch.object(batch, "run_command_tee") as runner:
            batch.run_bench_evaluation(output, bench, "GraphResearcher", "all", sys.executable, 2)
        calls = runner.call_args_list
        assert len(calls) == 6
        for call in calls:
            assert call.args[0][0] == sys.executable
            assert call.args[1] == bench.resolve()
            assert call.kwargs["env"]["OPENAI_API_KEY"] == "bench-key"
        race = calls[0].args[0]
        assert race[1:3] == ["deepresearch_bench_race.py", "GraphResearcher"]
        race_query = query.resolve().with_name("race_query.jsonl")
        assert race[race.index("--query_file") + 1] == str(race_query)
        assert _read_jsonl(race_query) == [_items()[1]]
        assert race[race.index("--raw_data_dir") + 1] == str(raw.parent.resolve())
        assert race[race.index("--cleaned_data_dir") + 1] == str(output.resolve() / "cleaned_data")
        previous = raw.resolve()
        for call, module, filename in zip(calls[1:5],
            ("extract", "deduplicate", "scrape", "validate"),
            ("extracted", "deduplicated", "scraped", "validated"), strict=True,
        ):
            command = call.args[0]
            assert command[1:3] == ["-m", f"utils.{module}"]
            assert command[command.index("--raw_data_path") + 1] == str(previous)
            target = output.resolve() / "results/fact/GraphResearcher" / f"{filename}.jsonl"
            assert command[command.index("--output_path") + 1] == str(target)
            if module == "scrape":
                assert "--query_data_path" not in command
            else:
                assert command[command.index("--query_data_path") + 1] == str(query.resolve())
            previous = target
        assert calls[-1].args[0][1:3] == ["-m", "utils.stat"]
        assert str(previous) in calls[-1].args[0]
        for mode, count in (("race", 1), ("fact", 5)):
            with patch.object(batch, "run_command_tee") as runner:
                batch.run_bench_evaluation(output, bench, "GraphResearcher", mode)
                assert runner.call_count == count
        with patch.object(batch, "run_command_tee", side_effect=RuntimeError("failed")) as runner:
            try:
                batch.run_bench_evaluation(output, bench, "GraphResearcher")
            except RuntimeError:
                assert runner.call_count == 1
            else:
                raise AssertionError("Failed official subprocess must stop evaluation")


def _test_race_resume_filters_completed_queries():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        query = root / "query.jsonl"
        results = root / "raw_results.jsonl"
        pending = root / "race_query.jsonl"
        batch.write_jsonl(query, _items())
        batch.write_jsonl(results, [
            {"id": 1, "overall_score": 0.5}, {"id": 2, "error": "retry"},
        ])
        batch.stage_race_queries(query, results, pending)
        assert [item["id"] for item in _read_jsonl(pending)] == [2, 3]
        batch.write_jsonl(results, [{"id": item["id"], "overall_score": 0.5} for item in _items()])
        batch.stage_race_queries(query, results, pending)
        assert _read_jsonl(pending) == []


def _test_evaluate_only_and_batch_failures():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        bench = _bench_root(root)
        output = root / "output"
        argv = ["batch", "--bench-root", str(bench), "--output-path", str(output)]

        def fail_one(prompt, run_dir, max_rounds, opts):
            if prompt == _items()[1]["prompt"]:
                raise RuntimeError("Test generation failure")
            _fake_run(prompt, run_dir, max_rounds, opts)

        with (
            patch.object(sys, "argv", [*argv, "--sample-size", "0"]),
            patch.object(batch, "run", side_effect=fail_one),
        ):
            batch.main()
        assert [row["id"] for row in _read_jsonl(output / "raw_data/GraphResearcher.jsonl")] == [1, 3]
        with (
            patch.object(sys, "argv", [*argv, "--evaluate-only", "--sample-size", "1"]),
            patch.object(batch, "run", side_effect=AssertionError("Agent must not run")),
            patch.object(batch, "run_command_tee") as runner,
        ):
            batch.main()
        assert runner.call_count == 6
        assert [row["id"] for row in _read_jsonl(output / "_evaluation/GraphResearcher/query.jsonl")] == [1, 3]


def main():
    _test_input_and_sampling()
    _test_generation_export_and_resume()
    _test_environment_isolation()
    _test_official_pipeline_commands()
    _test_race_resume_filters_completed_queries()
    _test_evaluate_only_and_batch_failures()
    print("DeepResearch Bench batch regression checks passed.")


if __name__ == "__main__":
    main()
