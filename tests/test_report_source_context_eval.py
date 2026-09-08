"""验证离线参数评估的统计口径、复现性与只读边界。

运行方式：uv run python tests/test_report_source_context_eval.py。
"""

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

import eval_report_source_context as evaluation  # noqa: E402


class EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        with patch.object(evaluation.config, "build_model", side_effect=AssertionError("Real model forbidden")):
            cls.summary = evaluation.run_evaluation(cls.root / "evaluation")
        cls.rows = {(row["case"], row["source_budget"]): row for row in cls.summary["cases"]}

    def test_matrix_counts_actual_prompts_and_calls(self):
        self.assertTrue(self.summary["checks_passed"])
        self.assertEqual(len(self.rows), 24)
        self.assertEqual(self.summary["history"]["summary"], {"chapters": 0})
        for row in self.rows.values():
            self.assertTrue(all(row["checks"].values()), row)
            self.assertEqual(len(row["views"]), row["model_invocations"])

    def test_duplicate_evidence_does_not_multiply_blocks(self):
        for budget in evaluation.BUDGET_DEFAULTS:
            regular = self.rows[("two_goals", budget)]["views"][0]
            duplicate = self.rows[("duplicate_evidence", budget)]["views"][0]
            self.assertEqual(regular["selected_blocks"], duplicate["selected_blocks"])
            self.assertTrue(duplicate["unique_blocks"])

    def test_annotations_measure_goal_coverage(self):
        small = self.rows[("three_goals", 1000)]["views"][0]
        large = self.rows[("three_goals", 4000)]["views"][0]
        self.assertEqual(small["covered_goals"], [2])
        self.assertEqual(large["covered_goals"], [0, 1, 2])
        self.assertEqual(large["annotated_goals"], 3)

    def test_table_and_footnote_are_loaded_as_one_unit(self):
        row = self.rows[("table_dependency", 1000)]
        audit = evaluation.read_json(self.root / "evaluation" / row["audit"])
        self.assertEqual(row["views"][0]["selected_blocks"], ["table:b2"])
        self.assertEqual(row["views"][1]["selected_blocks"], ["table:b1", "table:b2"])
        table = audit["views"][0]["view"]["context_blocks"][0]["text"]
        self.assertIn("| 项目 | 数值 | 条件 |", table)
        self.assertIn("| 样品 34 | 54 | 恒温 |", table)
        self.assertIn("[^1]:", table)

    def test_replacement_uses_one_read_and_preserves_input_budget(self):
        row = self.rows[("replacement", 2000)]
        self.assertEqual([view["selected_blocks"] for view in row["views"]], [["temperature:b1"], ["pressure:b1"]])
        self.assertEqual(row["model_invocations"], 2)
        self.assertEqual(row["failed_attempts"], 0)
        self.assertTrue(row["readback_used"])
        self.assertEqual(row["views"][1]["read_results"], {"loaded": 1})

    def test_missing_and_oversized_materials_remain_explicit(self):
        self.assertEqual(self.rows[("missing_snapshot", 2000)]["views"][1]["read_results"], {"unavailable": 1})
        self.assertEqual(self.rows[("replacement", 1000)]["views"][1]["read_results"], {"budget_exceeded": 1})
        row = self.rows[("base_overflow", 2000)]
        self.assertEqual(row["chapter_result"]["error"], "base_prompt_over_budget")
        self.assertEqual(row["model_invocations"], 0)
        self.assertGreater(row["base_prompt_tokens"], 23552)

    def test_retry_metrics_are_not_reported_as_additional_readbacks(self):
        row = self.rows[("retry_readback", 2000)]
        self.assertEqual(row["model_invocations"], 4)
        self.assertEqual(row["failed_attempts"], 2)
        self.assertTrue(row["readback_used"])
        self.assertEqual(row["views"][2]["selected_blocks"], row["views"][3]["selected_blocks"])

    def test_runs_are_reproducible_and_configuration_is_restored(self):
        with patch.object(evaluation.config, "REPORTER_CONTEXT_TOKENS", 17000), patch.object(evaluation.config, "REPORTER_SOURCE_TOKENS", 123):
            again = evaluation.run_evaluation(self.root / "again")
            self.assertEqual(evaluation.config.REPORTER_CONTEXT_TOKENS, 17000)
            self.assertEqual(evaluation.config.REPORTER_SOURCE_TOKENS, 123)
        self.assertEqual(again, self.summary)

    def test_history_statistics_use_evidence_and_candidate_denominators(self):
        run = self.root / "history"
        run.mkdir()
        (run / ".report_chapters").mkdir()
        nodes = [
            {"kind": "node", "id": "ev1", "type": "Evidence", "text": "alpha"},
            {"kind": "node", "id": "ev2", "type": "Evidence", "text": "alpha"},
            {"kind": "node", "id": "claim", "type": "Claim", "statement": "gamma"},
            {"kind": "edge", "source": "ev1", "target": "claim", "type": "SUPPORTED_BY"},
        ]
        (run / "research_graph.jsonl").write_text("\n".join(json.dumps(node) for node in nodes))
        (run / ".report_outline.json").write_text(json.dumps({"chapters": [{"chapter_id": 1, "title": "Title", "goals": ["Goal"]}]}))
        (run / ".report_chapters/chapter_01.meta.json").write_text(json.dumps({"chapter_id": 1, "evidence_ref_map": {"e1": "ev1", "e2": "ev2", "c1": "claim", "e3": "missing"}}))
        before = {p: p.read_bytes() for p in run.rglob("*") if p.is_file()}
        encoding = evaluation.sources.tiktoken.get_encoding("o200k_base")
        history, cases = evaluation.read_history([run, self.root / "absent"], encoding)
        self.assertEqual(history["runs"][1]["status"], "missing_inputs")
        chapter = history["chapters"][0]
        self.assertEqual(chapter["evidence_count"], 2)
        self.assertEqual(chapter["candidate_count"], 3)
        self.assertEqual(chapter["candidate_text_tokens"], 3)
        self.assertEqual(chapter["unique_evidence_texts"], 1)
        self.assertEqual(chapter["max_text_multiplicity"], 2)
        self.assertEqual(chapter["missing_node_ids"], ["missing"])
        self.assertEqual(len(cases), 1)
        claim = next(item for item in cases[0]["bundle"]["evidence_items"] if item["ref"] == "c1")
        self.assertEqual(claim["evidence_relations"], [{"target_ref": "e1", "stance": "supports"}])
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        self.assertEqual(len(history["runs"][0]["files_sha256"]), 3)

    def test_existing_output_and_source_overlap_are_rejected(self):
        with self.assertRaises(FileExistsError):
            evaluation.run_evaluation(self.root / "evaluation")
        with self.assertRaises(ValueError):
            evaluation.run_evaluation(self.root / "source/child", run_paths=[self.root / "source"])
        self.assertFalse((self.root / "source").exists())


if __name__ == "__main__":
    unittest.main()
