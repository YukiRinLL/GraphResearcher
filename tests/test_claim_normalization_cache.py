"""离线验证规范化缓存、失效边界和并行评估。"""

import json
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from test_claim_normalization_regressions import FakeGraph, _claim_spec  # noqa: E402

from agents.memory_manager import MemoryManager  # noqa: E402
from prompts import memory_manager_prompts as mm_prompts  # noqa: E402
from tools import graph_tools, research_state  # noqa: E402


class CountingModel:
    """记录真实调用边界，并可注入确定性的失败或线程同步。"""

    def __init__(self, payload=None, hook=None):
        self.payload = {"claims": [_claim_spec()]} if payload is None else payload
        self.hook = hook
        self.prompts = []
        self.lock = threading.Lock()

    def invoke(self, prompt):
        with self.lock:
            self.prompts.append(prompt)
        if self.hook:
            self.hook()
        if isinstance(self.payload, Exception):
            raise self.payload
        content = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        return SimpleNamespace(content=content)


class CacheTests(unittest.TestCase):
    """通过公开规范化方法验证模型调用和图写入。"""

    def setUp(self):
        self.graph = FakeGraph()
        self.context = "run-a"
        self.reverse = False
        self.model = CountingModel()
        self.manager = MemoryManager(model=self.model)
        replacements = {
            "get_node": self.graph.get_node,
            "search_nodes": self.graph.search_nodes,
            "create_claim": self.graph.create_claim,
            "add_edge": self.graph.add_edge,
            "get_query_evaluation_subgraph": self.evaluation,
            "get_all_edges": lambda: deepcopy(self.graph.edges),
            "get_current_context": lambda: self.context,
        }
        self.mocks = {}
        for name, replacement in replacements.items():
            patcher = patch.object(graph_tools, name, side_effect=replacement)
            self.mocks[name] = patcher.start()
            self.addCleanup(patcher.stop)

    def evaluation(self, query_id):
        nodes = list(self.graph.nodes.values())
        if self.reverse:
            nodes.reverse()
            nodes = [dict(reversed(list(node.items()))) for node in nodes]
        return {
            "query": deepcopy(self.graph.nodes[query_id]),
            "nodes": deepcopy(nodes),
            "edges": deepcopy(self.graph.edges),
            "children": [{"id": "child", "status": "blocked"}],
        }

    def test_same_input_skips_model_and_writes_and_returns_copy(self):
        first = self.manager.normalize_claims("q1")
        writes = (self.mocks["create_claim"].call_count, self.mocks["add_edge"].call_count)
        first["created_or_updated_claim_ids"].clear()
        second = self.manager.normalize_claims("q1")
        self.assertEqual(second, {"created_or_updated_claim_ids": ["claim1"], "claim_count": 1})
        self.assertEqual(len(self.model.prompts), 1)
        self.assertEqual(writes, (self.mocks["create_claim"].call_count, self.mocks["add_edge"].call_count))

    def test_order_and_derived_state_do_not_invalidate(self):
        self.graph.nodes["st2"] = {**self.graph.nodes["st1"], "id": "st2"}
        self.graph.nodes["e2"] = {**self.graph.nodes["e1"], "id": "e2"}
        self.manager.normalize_claims("q1")
        self.reverse = True
        self.graph.nodes["q1"].update(status="waiting_children", sufficiency_score=0.8)
        self.graph.nodes["objective"]["coverage"] = 0.9
        self.manager.normalize_claims("q1")
        self.assertEqual(len(self.model.prompts), 1)

    def test_material_and_query_fields_invalidate(self):
        changes = [
            ("st1", "text", "来源修正了试点年份。"),
            ("e1", "text", "试点年份存在不确定性。"),
            ("e1", "stance", "qualifies"),
            ("e1", "statement_refs", []),
            ("st1", "qualifiers", ["某地区"]),
            ("e1", "limitations", ["仅限试点"]),
            ("e1", "confidence", 0.3),
            ("s1", "credibility_score", 0.4),
            ("q1", "text", "项目部署进展"),
            ("q1", "acceptance_criteria", ["确认部署时间"]),
            ("q1", "objective_keys", []),
        ]
        self.manager.normalize_claims("q1")
        for index, (node_id, field, value) in enumerate(changes, start=2):
            with self.subTest(field=field):
                self.graph.nodes[node_id][field] = value
                self.manager.normalize_claims("q1")
                self.assertEqual(len(self.model.prompts), index)

    def test_addition_and_removal_invalidate(self):
        self.manager.normalize_claims("q1")
        self.graph.nodes["st2"] = {**self.graph.nodes["st1"], "id": "st2"}
        self.manager.normalize_claims("q1")
        del self.graph.nodes["st2"]
        self.manager.normalize_claims("q1")
        self.assertEqual(len(self.model.prompts), 3)

    def test_context_manager_model_and_prompt_are_isolated(self):
        self.manager.normalize_claims("q1")
        self.context = "run-b"
        self.manager.normalize_claims("q1")
        MemoryManager(model=self.model).normalize_claims("q1")
        replacement = CountingModel()
        self.manager.model = replacement
        self.manager.normalize_claims("q1")
        with patch.object(mm_prompts, "normalize_claims", mm_prompts.normalize_claims + "\n修订版本。"):
            self.manager.normalize_claims("q1")
        self.assertEqual(len(self.model.prompts), 3)
        self.assertEqual(len(replacement.prompts), 2)

    def test_deleted_claim_or_removed_binding_invalidates(self):
        for kind in ("node", "provenance", "objective"):
            with self.subTest(kind=kind):
                manager = MemoryManager(model=self.model)
                result = manager.normalize_claims("q1")
                before = len(self.model.prompts)
                claim_id = result["created_or_updated_claim_ids"][0]
                if kind == "node":
                    del self.graph.nodes[claim_id]
                else:
                    target_type = "NORMALIZED_TO" if kind == "provenance" else "COVERS_OBJECTIVE"
                    self.graph.edges[:] = [e for e in self.graph.edges if e["type"] != target_type]
                manager.normalize_claims("q1")
                self.assertEqual(len(self.model.prompts), before + 1)

    def test_empty_materials_clear_previous_result(self):
        self.manager.normalize_claims("q1")
        statement = self.graph.nodes.pop("st1")
        evidence = self.graph.nodes.pop("e1")
        self.assertEqual(self.manager.normalize_claims("q1"), {
            "created_or_updated_claim_ids": [], "claim_count": 0,
        })
        self.graph.nodes.update(st1=statement, e1=evidence)
        self.manager.normalize_claims("q1")
        self.assertEqual(len(self.model.prompts), 2)

    def test_failed_or_degraded_output_is_retried(self):
        for payload in (RuntimeError("模型失败"), "invalid json", {"claims": []}, {"claims": [{"canonical_text": ""}]}):
            with self.subTest(payload=payload):
                model = CountingModel(payload=payload)
                manager = MemoryManager(model=model)
                if isinstance(payload, Exception):
                    with self.assertRaises(RuntimeError):
                        manager.normalize_claims("q1")
                else:
                    manager.normalize_claims("q1")
                model.payload = {"claims": [_claim_spec()]}
                manager.normalize_claims("q1")
                self.assertEqual(len(model.prompts), 2)

    def test_partial_write_failure_does_not_publish_cache(self):
        original = self.graph.add_edge
        self.mocks["add_edge"].side_effect = RuntimeError("写入失败")
        with self.assertRaises(RuntimeError):
            self.manager.normalize_claims("q1")
        self.mocks["add_edge"].side_effect = original
        self.manager.normalize_claims("q1")
        self.assertEqual(len(self.model.prompts), 2)

    def test_unacknowledged_binding_write_is_not_cached(self):
        self.mocks["add_edge"].side_effect = lambda *_args: ""
        self.manager.normalize_claims("q1")
        # 后续修复了边，也不能把之前未完整写入的调用当作可复用结果。
        self.graph.add_edge("st1", "claim1", "NORMALIZED_TO")
        self.graph.add_edge("e1", "claim1", "SUPPORTED_BY")
        self.graph.add_edge("claim1", "objective", "COVERS_OBJECTIVE")
        self.mocks["add_edge"].side_effect = self.graph.add_edge
        self.manager.normalize_claims("q1")
        self.assertEqual(len(self.model.prompts), 2)

    def test_evidence_only_fallback_is_reused(self):
        del self.graph.nodes["st1"]
        first = self.manager.normalize_claims("q1")
        writes = self.mocks["create_claim"].call_count
        self.assertEqual(self.manager.normalize_claims("q1"), first)
        self.assertEqual(self.model.prompts, [])
        self.assertEqual(self.mocks["create_claim"].call_count, writes)

    def test_same_query_concurrency_calls_model_once(self):
        started = threading.Event()
        release = threading.Event()

        def hook():
            started.set()
            if not release.wait(2):
                raise AssertionError("模型等待超时")

        self.model.hook = hook
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.manager.normalize_claims, "q1")
            self.assertTrue(started.wait(2))
            second = pool.submit(self.manager.normalize_claims, "q1")
            release.set()
            self.assertEqual(first.result(timeout=3), second.result(timeout=3))
        self.assertEqual(len(self.model.prompts), 1)

    def test_different_queries_remain_parallel(self):
        self.graph.nodes["q2"] = {**self.graph.nodes["q1"], "id": "q2"}
        barrier = threading.Barrier(2)
        self.model.hook = lambda: barrier.wait(timeout=2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.manager.normalize_claims, qid) for qid in ("q1", "q2")]
            for future in futures:
                self.assertEqual(future.result(timeout=3)["claim_count"], 1)
        self.assertEqual(len(self.model.prompts), 2)

    def test_parent_reassessment_still_calls_assessor(self):
        query = self.graph.nodes["q1"]
        query.update(handle="q1", status="assessing")
        original = self.model.invoke
        assessments = []

        def invoke(prompt):
            if "Claim 规范化器" in prompt:
                return original(prompt)
            assessments.append(prompt)
            return SimpleNamespace(content=json.dumps({
                "sufficiency_score": 0.9, "recommendation": "sufficient", "gaps": [],
            }))

        with (
            patch.object(self.model, "invoke", side_effect=invoke),
            patch.object(self.manager, "_resolve_query_id", return_value="q1"),
            patch.object(self.manager, "_query_gap_ids", return_value=[]),
            patch.object(self.manager, "_propagate_child_completion"),
            patch.object(self.manager, "_bump_portfolio_revision", return_value=1),
            patch.object(graph_tools, "get_query_children", return_value=[]),
            patch.object(graph_tools, "transition_query"),
            patch.object(graph_tools, "upsert_node"),
            patch.object(research_state, "get_status", return_value={"research_state": research_state.RESEARCHING}),
            patch.object(research_state, "get_goal", return_value={"id": "goal"}),
        ):
            self.manager.assess_query("q1")
            query["status"] = "waiting_children"
            self.manager.assess_query("q1")
        self.assertEqual(len(self.model.prompts), 1)
        self.assertEqual(len(assessments), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
