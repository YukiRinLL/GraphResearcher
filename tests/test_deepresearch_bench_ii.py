"""Regression checks for the DeepResearch Bench II batch runner."""

# ruff: noqa: T201

import json
import sys
import tempfile
from pathlib import Path

repo_dir = Path(__file__).parent.parent
sys.path.insert(0, str(repo_dir))

import test_deepresearch_bench_ii as batch  # noqa: E402


def _write_jsonl(path, records):
    path.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n", encoding="utf-8")


def _test_load_and_sample_items():
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "tasks.jsonl"
        path.write_text(
            "\n".join([
                json.dumps({"id": "one", "idx": "1", "prompt": "Prompt one"}),
                "not json",
                json.dumps(["not", "an", "object"]),
                json.dumps({"id": "bad-idx", "idx": "x", "prompt": "Prompt"}),
                json.dumps({"id": "no-prompt", "idx": 2, "prompt": " "}),
                json.dumps({"id": "three", "idx": 3, "prompt": "Prompt three"}),
            ]) + "\n",
            encoding="utf-8",
        )

        items = batch.load_items(path)
        assert [(item["idx"], item["prompt"]) for item in items] == [(1, "Prompt one"), (3, "Prompt three")]
        assert batch.sample_items(items, 1, 42) == batch.sample_items(items, 1, 42)
        assert batch.sample_items(items, 0, None) is items


def _test_run_one_and_skip_existing():
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        calls = []
        original_run = batch.run

        def fake_run(prompt, run_dir, max_rounds, opts):
            calls.append((prompt, run_dir, max_rounds, opts))
            (run_dir / "report.md").write_text("# Generated report\n", encoding="utf-8")
            (run_dir / "run.log").write_text("log", encoding="utf-8")
            (run_dir / "research_graph.jsonl").write_text("{}\n", encoding="utf-8")

        try:
            batch.run = fake_run
            item = {
                "id": "task/7",
                "idx": 7,
                "language": "en",
                "theme": "Test",
                "description": "Description",
                "prompt": "Full prompt with blocked-source instructions",
                "content": {"task": "Evaluator-only task"},
            }
            report_path = batch.run_one(item, output_dir, "GraphResearcher", 12, {"subgraphs": True})
            assert report_path == output_dir / "report" / "GraphResearcher" / "idx-7.md"
            assert report_path.read_text(encoding="utf-8") == "# Generated report\n"
            assert calls[0][0] == item["prompt"]
            assert calls[0][2] == 12

            run_dir = output_dir / "_runs" / "idx-7-task-7"
            snapshot = json.loads((run_dir / "input.json").read_text(encoding="utf-8"))
            assert snapshot["prompt"] == item["prompt"]
            assert "content" not in snapshot

            second_path = batch.run_one(item, output_dir, "GraphResearcher", 1, {})
            assert second_path == report_path
            assert len(calls) == 1
        finally:
            batch.run = original_run


def _test_successful_evaluations_and_staging():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        result_path = root / "result.jsonl"
        result_path.write_text(
            "\n".join([
                json.dumps({"model": "GraphResearcher", "idx": 1, "result": {"scores": {}}}),
                json.dumps({"model": "GraphResearcher", "idx": 2, "result": {"error": "retry"}}),
                json.dumps({"model": "Other", "idx": "3", "result": json.dumps({"scores": {}})}),
                "malformed",
            ]) + "\n",
            encoding="utf-8",
        )
        completed = batch.load_successful_evaluations(result_path)
        assert completed == {("GraphResearcher", 1), ("Other", 3)}

        model_dir = root / "report" / "GraphResearcher"
        model_dir.mkdir(parents=True)
        for idx in (1, 2, 10):
            (model_dir / f"idx-{idx}.md").write_text(f"report {idx}", encoding="utf-8")
        (model_dir / "notes.md").write_text("ignore", encoding="utf-8")

        reports = batch.discover_reports(model_dir)
        assert [idx for idx, _ in reports] == [1, 2, 10]
        staging = root / "staging" / "report"
        staged = batch.stage_pending_reports(reports, completed, "GraphResearcher", staging)
        assert [path.name for path in staged] == ["idx-2.md", "idx-10.md"]
        assert sorted(path.name for path in (staging / "GraphResearcher").iterdir()) == ["idx-10.md", "idx-2.md"]


def _make_bench_root(root):
    bench_root = root / "bench"
    bench_root.mkdir()
    (bench_root / "tasks_and_rubrics.jsonl").write_text("{}\n", encoding="utf-8")
    (bench_root / "run_evaluation.py").write_text("", encoding="utf-8")
    (bench_root / "aggregate_scores.py").write_text("", encoding="utf-8")
    return bench_root


def _test_evaluation_commands_and_resume():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        bench_root = _make_bench_root(root)
        output_dir = root / "output"
        model_dir = output_dir / "report" / "GraphResearcher"
        model_dir.mkdir(parents=True)
        for idx in (1, 2):
            (model_dir / f"idx-{idx}.md").write_text(f"report {idx}", encoding="utf-8")
        _write_jsonl(
            output_dir / "result.jsonl",
            [
                {"model": "GraphResearcher", "idx": 1, "result": {"scores": {}}},
                {"model": "GraphResearcher", "idx": 2, "result": {"error": "retry"}},
            ],
        )

        calls = []
        original_runner = batch.run_command_tee
        try:
            batch.run_command_tee = lambda command, cwd, log_path: calls.append((command, cwd, log_path))
            batch.run_bench_evaluation(output_dir, bench_root, "GraphResearcher")
        finally:
            batch.run_command_tee = original_runner

        assert len(calls) == 2
        evaluation_command, cwd, log_path = calls[0]
        assert evaluation_command[:6] == ["uv", "run", "--project", str(bench_root.resolve()), "--isolated", "python"]
        assert str(bench_root.resolve() / "run_evaluation.py") in evaluation_command
        assert evaluation_command[evaluation_command.index("--log_file") + 1] == ""
        assert cwd == bench_root.resolve()
        assert log_path == output_dir.resolve() / "_evaluation" / "run_evaluation.log"
        staged_model_dir = output_dir / "_evaluation" / "staging" / "report" / "GraphResearcher"
        assert [path.name for path in staged_model_dir.iterdir()] == ["idx-2.md"]

        aggregate_command = calls[1][0]
        assert str(bench_root.resolve() / "aggregate_scores.py") in aggregate_command
        assert aggregate_command[aggregate_command.index("--output-prefix") + 1] == str(output_dir.resolve() / "agg_scores")


def _test_all_scored_skips_judge_but_aggregates():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        bench_root = _make_bench_root(root)
        output_dir = root / "output"
        model_dir = output_dir / "report" / "GraphResearcher"
        model_dir.mkdir(parents=True)
        (model_dir / "idx-1.md").write_text("report", encoding="utf-8")
        _write_jsonl(
            output_dir / "result.jsonl",
            [{"model": "GraphResearcher", "idx": 1, "result": {"scores": {}}}],
        )

        calls = []
        original_runner = batch.run_command_tee
        try:
            batch.run_command_tee = lambda command, cwd, log_path: calls.append(command)
            batch.run_bench_evaluation(output_dir, bench_root, "GraphResearcher")
        finally:
            batch.run_command_tee = original_runner

        assert len(calls) == 1
        assert str(bench_root.resolve() / "aggregate_scores.py") in calls[0]
        assert str(bench_root.resolve() / "run_evaluation.py") not in calls[0]


def main():
    _test_load_and_sample_items()
    _test_run_one_and_skip_existing()
    _test_successful_evaluations_and_staging()
    _test_evaluation_commands_and_resume()
    _test_all_scored_skips_judge_but_aggregates()
    print("DeepResearch Bench II batch regression checks passed.")


if __name__ == "__main__":
    main()
