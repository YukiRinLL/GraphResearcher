"""章节原文、预算与一次回读的离线回归，不调用模型、数据库或外部搜索。

运行方式：uv run python tests/test_report_source_context.py。
"""

import json
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import config  # noqa: E402
from agents import reporter_workflow as workflow  # noqa: E402
from memory import source_snapshots as snapshots  # noqa: E402
from tools import report_source_context as sources  # noqa: E402
from tools import report_tools  # noqa: E402


def writer_view(prompt):
    return json.JSONDecoder().raw_decode(prompt.split("# Current Chapter Bundle\n\n", 1)[1])[0]


class SourceContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.previous = snapshots._run_context
        self.addCleanup(setattr, snapshots, "_run_context", self.previous)
        snapshots.configure(str(self.root), "source-run")
        self.binding = sources.capture_binding()
        self.bundle = {
            "status": "ok", "chapter_id": 1, "bundle_token": "bound-token",
            "chapter_title": "Measurements", "chapter_goals": ["temperature", "pressure"],
            "section_plan": "Explain conditions", "section_type": "body",
            "evidence_items": [], "disclosed_conflicts": [],
            "_snapshot_binding": self.binding, "_source_audit_dir": str(self.root / "report"),
        }
        self.addCleanup(patch.stopall)
        patch.object(config, "REPORTER_TOKENIZER", "o200k_base").start()
        patch.object(config, "REPORTER_SOURCE_TOKENS", 2000).start()
        patch.object(config, "REPORTER_CONTEXT_TOKENS", 32768).start()
        patch.object(config, "REPORTER_OUTPUT_TOKENS", 8192).start()
        patch.object(config, "REPORTER_SAFETY_TOKENS", 1024).start()

    def add_source(self, body, *, ref="e1", direct=None, url=None):
        url = url or f"https://example.com/{ref}"
        captured = snapshots.capture_source(
            {"url": url, "title": "Measured source", "raw_content": body}, query="conditions",
            stage="single", search_parameters={}, response={}, result_index=0, raw_content_limit=20000,
        )
        self.assertEqual(captured["status"], "stored")
        _, index = snapshots.read_snapshot(Path(self.binding["root"]), captured["snapshot_id"])
        refs = [block["block_id"] for block in index["blocks"]]
        location = {
            **captured, "block_refs": [refs[position] for position in (direct if direct is not None else [0])],
            "location_status": "valid", "url": url, "title": "Measured source", "citation": "[1]",
        }
        self.bundle["evidence_items"].append({
            "ref": ref, "type": "Evidence", "text": f"Measured fact {ref}",
            "source_numbers": [1], "_source_location": location,
        })
        return refs

    def render(self, bundle):
        return workflow._chapter_prompt("Explain conditions", {}, bundle, language="English")

    def run_chapter(self, responses, *, commit=None):
        calls = []
        payloads = []
        responses = iter(responses)

        def invoke(prompt, **kwargs):
            calls.append(prompt)
            response = next(responses)
            if callable(response):
                response = response(prompt)
            if isinstance(response, Exception):
                raise response
            return response

        def save(*, chapters):
            payloads.append(chapters)
            return commit(chapters) if commit else {"status": "ok", "chapters": [{"chapter_id": self.bundle["chapter_id"], "candidate_saved": True}]}

        with patch.object(workflow, "_invoke_reporter_json", invoke), patch.object(workflow.graph_manager_tools, "commit_report_chapter_batch", save):
            result = workflow.draft_chapter_node({
                "chapter_bundle": self.bundle, "outline": {},
                "report_context": {"user_request": "Explain conditions", "language": "English"},
            })["chapter_results"][0]
        return result, calls, payloads

    def final(self):
        return {"chapters": [{"chapter_id": self.bundle["chapter_id"], "content": "Fact.[1]", "evidence_refs": ["e1"]}]}

    def request(self, ref="e1", block_refs=None):
        return {"read_requests": [{"evidence_ref": ref, "block_refs": block_refs or [], "purpose": "核对条件"}]}

    def audit(self):
        return json.loads((self.root / "report/report_source_context/chapter-1/audit.json").read_text())

    def test_direct_blocks_only_and_shared_deduplication(self):
        refs = self.add_source("# Heading\n\nTemperature measured under pressure.\n\nNeighbour context.", direct=[1])
        duplicate = deepcopy(self.bundle["evidence_items"][0])
        duplicate["ref"] = "e2"
        self.bundle["evidence_items"].append(duplicate)
        context = sources.SourceContext(self.bundle)
        view = writer_view(context.prompt(self.render, readback_used=False))
        self.assertEqual([block["block_ref"] for block in view["context_blocks"]], [refs[1]])
        self.assertEqual(view["context_blocks"][0]["evidence_refs"], ["e1", "e2"])
        self.assertIn(refs[2], view["evidence"][0]["readable_block_refs"])
        self.assertNotIn("_snapshot_binding", self.render(self.bundle))
        self.assertNotIn(str(self.root), self.render(self.bundle))
        self.assertEqual(view["evidence"][0]["citation"], "[1]")

    def test_default_final_has_one_call_and_original_commit_shape(self):
        self.add_source("temperature measured")
        result, calls, payloads = self.run_chapter([self.final()])
        self.assertTrue(result["success"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(set(payloads[0][0]), {"chapter_id", "bundle_token", "content", "evidence_refs", "disclosed_conflict_refs"})
        self.assertEqual(payloads[0][0]["bundle_token"], "bound-token")
        self.assertEqual(self.audit()["model_invocations"], 1)

    def test_readback_has_two_calls_and_same_binding(self):
        refs = self.add_source("# Heading\n\nTemperature measured.\n\nAdjacent measurement.", direct=[1])
        result, calls, payloads = self.run_chapter([self.request(block_refs=[refs[2]]), self.final()])
        self.assertTrue(result["success"])
        self.assertEqual(len(calls), 2)
        second = writer_view(calls[1])
        self.assertFalse(second["readback_available"])
        self.assertEqual(second["read_results"][0]["results"][0]["status"], "loaded")
        self.assertEqual(second["context_blocks"][0]["block_ref"], refs[2])
        self.assertEqual(payloads[0][0]["bundle_token"], "bound-token")

    def test_malformed_then_read_then_failure_then_final_has_four_calls(self):
        self.add_source("temperature measured")
        result, calls, _ = self.run_chapter([ValueError("invalid JSON"), self.request(), TimeoutError("provider timeout"), self.final()])
        self.assertTrue(result["success"])
        self.assertEqual(len(calls), 4)
        audit = self.audit()
        self.assertEqual(audit["failed_attempts"], 2)
        self.assertTrue(audit["readback_used"])
        self.assertEqual(writer_view(calls[2])["context_blocks"], writer_view(calls[3])["context_blocks"])

    def test_bad_requests_consume_once_and_repeated_requests_exhaust(self):
        self.add_source("temperature measured")
        result, calls, payloads = self.run_chapter([self.request("c1")] * 4)
        self.assertFalse(result["success"])
        self.assertEqual(len(calls), 4)
        self.assertEqual(payloads, [])
        self.assertEqual(writer_view(calls[1])["read_results"][0]["results"][0]["status"], "invalid_ref")
        self.assertEqual(self.audit()["failed_attempts"], 3)

    def test_structural_failures_do_not_consume_readback(self):
        self.add_source("temperature measured")
        malformed = [
            {"read_requests": [], "chapters": self.final()["chapters"]},
            {"read_requests": [{"evidence_ref": "e1", "block_refs": "wrong", "purpose": "check"}]},
            self.request(), self.final(),
        ]
        result, calls, _ = self.run_chapter(malformed)
        self.assertTrue(result["success"])
        self.assertEqual(len(calls), 4)
        self.assertTrue(writer_view(calls[2])["readback_available"])
        with self.assertRaises(workflow.ValidationError):
            workflow.ChapterReadCandidate.model_validate({"read_requests": []})

    def test_partial_results_and_unadvertised_reference(self):
        refs = self.add_source("first\n\nsecond\n\nthird\n\nfourth", direct=[0])
        result, calls, _ = self.run_chapter([self.request(block_refs=[refs[0], refs[3], "../../body.txt"]), self.final()])
        self.assertTrue(result["success"])
        statuses = [item["status"] for item in writer_view(calls[1])["read_results"][0]["results"]]
        self.assertEqual(statuses, ["loaded", "invalid_ref", "invalid_ref"])

    def test_deleted_snapshot_returns_unavailable_without_cached_automatic_text(self):
        self.add_source("Unique captured context")

        def delete_and_request(prompt):
            location = self.bundle["evidence_items"][0]["_source_location"]
            (Path(self.binding["root"]) / "snapshots" / location["snapshot_id"] / "body.txt").unlink()
            return self.request()

        result, calls, _ = self.run_chapter([delete_and_request, self.final()])
        self.assertTrue(result["success"])
        view = writer_view(calls[1])
        self.assertEqual(view["read_results"][0]["results"][0]["status"], "unavailable")
        self.assertEqual(view["context_blocks"], [])
        self.assertNotIn("Unique captured context", calls[1])

    def test_commit_failure_does_not_reopen_readback(self):
        self.add_source("temperature measured")
        count = 0

        def commit(chapters):
            nonlocal count
            count += 1
            return {"status": "error", "message": "try again"} if count == 1 else {"status": "ok", "chapters": [{"chapter_id": 1, "candidate_saved": True}]}

        result, calls, _ = self.run_chapter([self.request(), self.final(), self.request(), self.final()], commit=commit)
        self.assertTrue(result["success"])
        self.assertEqual(len(calls), 4)
        self.assertFalse(writer_view(calls[-1])["readback_available"])

    def test_oversized_base_stops_without_invocation(self):
        self.add_source("temperature measured")
        with patch.object(config, "REPORTER_CONTEXT_TOKENS", 9300):
            result, calls, _ = self.run_chapter([self.final()])
        self.assertEqual(result["error"], "base_prompt_over_budget")
        self.assertEqual(calls, [])
        self.assertEqual(self.audit()["model_invocations"], 0)

    def test_unknown_tokenizer_stops_and_explicit_encoding_works(self):
        with patch.object(config, "REPORTER_TOKENIZER", ""), patch.object(config, "DEFAULT_MODEL", "custom-proxy-model"):
            result, calls, _ = self.run_chapter([self.final()])
        self.assertIn("unknown_reporter_tokenizer", result["error"])
        self.assertEqual(calls, [])
        with patch.object(config, "DEFAULT_MODEL", "custom-proxy-model"):
            result, _, _ = self.run_chapter([self.final()])
        self.assertTrue(result["success"])

    def test_request_priority_replaces_automatic_text_under_same_budget(self):
        self.add_source("AUTO_ONLY " + "temperature " * 230)
        self.add_source("READ_ONLY " + "pressure " * 230, ref="e2")
        with patch.object(config, "REPORTER_SOURCE_TOKENS", 500):
            result, calls, _ = self.run_chapter([self.request("e2"), self.final()])
        self.assertTrue(result["success"])
        self.assertIn("AUTO_ONLY", calls[0])
        self.assertNotIn("READ_ONLY", calls[0])
        self.assertNotIn("AUTO_ONLY", calls[1])
        self.assertIn("READ_ONLY", calls[1])
        for view in self.audit()["views"]:
            self.assertLessEqual(view["source_tokens"], 500)
            self.assertLessEqual(view["input_tokens"], view["input_limit"])

    def test_request_has_partial_budget_results(self):
        self.add_source("Small direct fact.\n\n" + "Large " * 4000, direct=[0, 1])
        result, calls, _ = self.run_chapter([self.request(), self.final()])
        self.assertTrue(result["success"])
        statuses = [item["status"] for item in writer_view(calls[1])["read_results"][0]["results"]]
        self.assertEqual(statuses, ["loaded", "budget_exceeded"])

    def test_necessary_metadata_overflow_stops_after_readback(self):
        requests = [{"evidence_ref": "invalid" + str(i), "block_refs": ["z" * 100] * 4, "purpose": "说明" * 100} for i in range(4)]
        with patch.object(config, "REPORTER_SOURCE_TOKENS", 100):
            result, calls, _ = self.run_chapter([{"read_requests": requests}, self.final()])
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["error"], "source_context_metadata_over_budget")
        self.assertTrue(self.audit()["readback_used"])
        self.assertEqual(len(self.audit()["resolved_requests"]), 4)

    def test_raw_text_placeholders_remain_literal(self):
        text = "Raw <user_request> and <report_outline> and <retry_feedback>."
        self.add_source(text)
        context = sources.SourceContext(self.bundle)
        view = writer_view(context.prompt(self.render, readback_used=False))
        self.assertEqual(view["context_blocks"][0]["text"], text)

    def test_legacy_evidence_readback_remains_unavailable(self):
        self.bundle["evidence_items"] = [{"ref": "e1", "type": "Evidence", "text": "Old fact", "source_numbers": [1]}]
        result, calls, _ = self.run_chapter([self.request(), self.final()])
        self.assertTrue(result["success"])
        self.assertEqual(writer_view(calls[1])["read_results"][0]["results"], [{"block_ref": None, "status": "unavailable"}])

    def test_full_prompt_headroom_limits_source_budget(self):
        self.add_source("temperature " * 250)
        context = sources.SourceContext(self.bundle)
        base = context.count(self.render(self.bundle))
        with patch.object(config, "REPORTER_CONTEXT_TOKENS", base + 8192 + 1024 + 120):
            context = sources.SourceContext(self.bundle)
            context.prompt(self.render, readback_used=False)
        self.assertLessEqual(context.views[0]["source_tokens"], 120)
        self.assertLessEqual(context.views[0]["input_tokens"], context.input_limit)

    def test_audit_failure_does_not_break_delivery(self):
        self.add_source("temperature measured")
        with patch.object(Path, "write_text", side_effect=OSError("audit disk unavailable")), self.assertLogs(sources.logger, level="ERROR"):
            result, calls, payloads = self.run_chapter([self.final()])
        self.assertTrue(result["success"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(payloads), 1)

    def test_replay_entry_reads_source_and_writes_audit_to_new_run(self):
        import replay_reporter_workflow as replay

        self.add_source("Source-run-only raw context")
        (self.root / "input.json").write_text(json.dumps({"question": "Explain conditions"}))
        graph = {"kind": "node", "id": "goal", "type": "UserRequest", "request": "Explain conditions", "research_state": "COMPLETED", "reporting_from_state": "REPORT_READY"}
        (self.root / "research_graph.jsonl").write_text(json.dumps(graph) + "\n")
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        output = self.root / "new-replay"
        snapshots.configure(str(self.root / "unrelated"), "unrelated-run")

        def run_report_workflow(**kwargs):
            bundle = {**self.bundle, "_snapshot_binding": sources.capture_binding(), "_source_audit_dir": str(output)}
            context = sources.SourceContext(bundle)
            prompt = context.prompt(self.render, readback_used=False)
            self.assertIn("Source-run-only raw context", prompt)
            context.audit(model_invocations=1, failed_attempts=0, readback_used=False, error="")
            return {"success": True, "delivered": True, "validated": True}

        with patch.object(replay, "run_report_workflow", run_report_workflow), patch.object(replay.graph_manager_tools, "get_compiled_report", return_value="# Report\n\nFact.[1]"):
            result = replay.run_replay(self.root, output, enable_langfuse=False)
        self.assertTrue(result["success"])
        self.assertTrue((output / "report_source_context/chapter-1/audit.json").is_file())
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        self.assertFalse(sources.capture_binding()["replay"])

    def test_goal_round_robin_skips_large_blocks_and_preserves_source_identity(self):
        self.add_source("| temperature | condition |\n|---|---|\n" + "| temperature big | varied extensive physical conditions |\n" * 1500)
        self.add_source("pressure measured", ref="e2")
        self.add_source("temperature measured", ref="e3")
        self.add_source("temperature measured", ref="e4")
        context = sources.SourceContext(self.bundle)
        view = writer_view(context.prompt(self.render, readback_used=False))
        refs = [block["evidence_refs"] for block in view["context_blocks"]]
        self.assertNotIn(["e1"], refs)
        self.assertEqual(refs[0], ["e2"])
        self.assertIn(["e3"], refs)
        self.assertIn(["e4"], refs)
        self.assertEqual(len(view["context_blocks"]), 3)

    def test_run_isolation_and_explicit_replay_root(self):
        self.add_source("Original run context")
        snapshots.configure(str(self.root / "other"), "other-run")
        self.bundle["_snapshot_binding"] = sources.capture_binding()
        context = sources.SourceContext(self.bundle)
        self.assertEqual(context.automatic, set())
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with sources.replay_source_scope(self.root):
            self.bundle["_snapshot_binding"] = sources.capture_binding()
        context = sources.SourceContext(self.bundle)
        self.assertTrue(context.automatic)
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        self.assertEqual(sources.capture_binding()["context"], "other-run")

    def test_parallel_chapters_keep_local_readback_states(self):
        self.add_source("temperature measured")
        bundles = [deepcopy(self.bundle) for _ in range(2)]
        bundles[1]["chapter_id"] = 2

        def run(bundle):
            context = sources.SourceContext(bundle)
            context.prompt(self.render, readback_used=False)
            if bundle["chapter_id"] == 1:
                context.accept_requests(self.request()["read_requests"])
            return writer_view(context.prompt(self.render, readback_used=bundle["chapter_id"] == 1))

        with ThreadPoolExecutor(max_workers=2) as executor:
            first, second = executor.map(run, bundles)
        self.assertFalse(first["readback_available"])
        self.assertTrue(second["readback_available"])
        self.assertEqual(second["read_results"], [])

    def test_graph_projection_carries_only_matching_document_location(self):
        self.add_source("temperature measured")
        location = self.bundle["evidence_items"][0]["_source_location"]
        evidence = {"id": "ev", "type": "Evidence", "text": "Fact", "document_id": "doc", "source_id": "src", "block_refs": location["block_refs"], "location_status": "valid"}
        document = {"id": "doc", "type": "Document", "source_id": "src", **{key: location[key] for key in ("snapshot_id", "chunker_version", "capture_id")}}
        with (
            patch.object(report_tools.graph_tools, "resolve_query_reference", return_value="query"),
            patch.object(report_tools.graph_tools, "get_all_nodes", return_value=[evidence, document]),
            patch.object(report_tools.graph_tools, "get_all_edges", return_value=[]),
            patch.object(report_tools.graph_tools, "get_query_evaluation_subgraph", return_value={"nodes": [evidence]}),
            patch.object(report_tools, "build_reference_registry", return_value=[{"source_id": "src", "n": 1, "title": "Measured source", "url": location["url"]}]),
            patch.object(report_tools, "_source_ids_for_item", return_value=["src"]),
        ):
            items = report_tools.get_report_evidence("q1")["items"]
            self.assertEqual(items[0]["_source_location"]["snapshot_id"], location["snapshot_id"])
            public, refs = report_tools._public_evidence_items(items)
            self.assertEqual(public[0]["ref"], "e1")
            self.assertEqual(refs, {"e1": "ev"})
            evidence["source_id"] = "other"
            self.assertNotIn("_source_location", report_tools.get_report_evidence("q1")["items"][0])

    def test_chapter_model_enforces_output_reserve(self):
        class FakeModel:
            def bind(self, **kwargs):
                self.kwargs = kwargs
                return self

            def invoke(self, prompt):
                return '{"chapters": []}'

        fake = FakeModel()
        with patch.dict(config._model_cache, {"reporter": fake}), patch.object(workflow.graph_manager_tools, "increment_reporter_model_call_count"):
            workflow._invoke_reporter_json("prompt", phase="chapter")
        self.assertEqual(fake.kwargs, {"max_tokens": 8192})


if __name__ == "__main__":
    unittest.main()
