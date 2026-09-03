"""Claim 规范化的回归测试。

这些用例由一次真实研究运行中的问题抽象而来，但夹具使用通用命题，
避免把特定研究主题固化进测试合同。
"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from agents.memory_manager import MemoryManager  # noqa: E402
from prompts import memory_manager_prompts as mm_prompts  # noqa: E402
from tools import graph_tools  # noqa: E402


def _type_name(value):
    """把枚举或字符串统一为图节点类型名称。"""
    return value.value if hasattr(value, "value") else str(value)


class StaticModel:
    """按顺序返回预设 JSON，隔离真实模型调用。"""

    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        payload = self.payloads.pop(0)

        class Result:
            content = json.dumps(payload, ensure_ascii=False)

        return Result()


class FakeGraph:
    """为 normalize_claims 提供最小的公开图工具边界。"""

    def __init__(self):
        self.nodes = {
            "q1": {
                "id": "q1",
                "type": "Query",
                "text": "项目进展",
                "objective_keys": ["progress"],
                "acceptance_criteria": [],
            },
            "objective": {
                "id": "objective",
                "type": "Analysis",
                "analysis_type": "objective",
                "objective_key": "progress",
                "requirement": "must",
                "weight": 1.0,
            },
            "s1": {
                "id": "s1",
                "type": "Source",
                "credibility_score": 0.8,
            },
            "st1": {
                "id": "st1",
                "type": "Statement",
                "text": "来源报告该项目在 2024 年启动试点。",
                "document_id": "d1",
                "source_id": "s1",
            },
            "e1": {
                "id": "e1",
                "type": "Evidence",
                "text": "该项目于 2024 年启动试点。",
                "document_id": "d1",
                "source_id": "s1",
                "statement_ref": "st1",
                "statement_refs": ["st1"],
            },
        }
        self.edges = []
        self._claim_sequence = 0

    def get_node(self, node_id):
        return dict(self.nodes.get(node_id, {}))

    def search_nodes(self, kind, filters=None):
        wanted = _type_name(kind).replace("_", "").lower()
        return [
            dict(node)
            for node in self.nodes.values()
            if str(node.get("type", "")).replace("_", "").lower() == wanted
            and all(node.get(key) == value for key, value in (filters or {}).items())
        ]

    def create_claim(
        self,
        statement,
        document_id=None,
        source_id=None,
        claim_key=None,
        canonical_text=None,
        **attributes,
    ):
        del document_id, source_id
        existing = next(
            (
                node
                for node in self.nodes.values()
                if node.get("type") == "Claim" and node.get("claim_key") == claim_key
            ),
            None,
        )
        properties = {
            "type": "Claim",
            "statement": statement,
            "canonical_text": canonical_text or statement,
            "claim_key": claim_key,
            **attributes,
        }
        if existing is not None:
            existing.update(properties)
            return existing["id"]
        self._claim_sequence += 1
        claim_id = f"claim{self._claim_sequence}"
        self.nodes[claim_id] = {"id": claim_id, **properties}
        return claim_id

    def add_edge(self, source, target, edge_type, attributes=None):
        edge = {
            "source": source,
            "target": target,
            "type": _type_name(edge_type),
            **(attributes or {}),
        }
        if edge not in self.edges:
            self.edges.append(edge)
        return f"{source}-{edge['type']}-{target}"

    def get_query_evaluation_subgraph(self, _query_id):
        return {
            "query": dict(self.nodes["q1"]),
            "nodes": [
                dict(self.nodes[node_id])
                for node_id in ("s1", "st1", "e1")
            ],
            "edges": [],
            "children": [],
        }

    def claims(self):
        return [
            node for node in self.nodes.values()
            if node.get("type") == "Claim"
        ]


def _claim_spec(
    *,
    canonical_text="该项目在 2024 年启动试点。",
    claim_key="project-pilot-2024",
    statement_refs=None,
    evidence_refs=None,
    confidence=0.8,
):
    """生成一个保持现有输出 shape 的 Claim spec。"""
    return {
        "canonical_text": canonical_text,
        "claim_key": claim_key,
        "statement_refs": ["st1"] if statement_refs is None else statement_refs,
        "evidence_refs": (
            [{"id": "e1", "stance": "supports"}]
            if evidence_refs is None
            else evidence_refs
        ),
        "objective_keys": ["progress"],
        "confidence": confidence,
        "qualifiers": [],
        "limitations": [],
    }


class ClaimNormalizationRegressionTests(unittest.TestCase):
    """通过 normalize_claims 的公开行为检查 Claim 合同。"""

    def setUp(self):
        self.graph = FakeGraph()
        replacements = {
            "get_node": self.graph.get_node,
            "search_nodes": self.graph.search_nodes,
            "create_claim": self.graph.create_claim,
            "add_edge": self.graph.add_edge,
            "get_query_evaluation_subgraph": self.graph.get_query_evaluation_subgraph,
        }
        for name, replacement in replacements.items():
            patcher = patch.object(graph_tools, name, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)

    def normalize(self, *payloads):
        manager = MemoryManager(model=StaticModel(*payloads))
        return manager.normalize_claims("q1")

    def test_valid_claim_persists_with_complete_provenance(self):
        result = self.normalize({"claims": [_claim_spec()]})

        self.assertEqual(result["claim_count"], 1)
        self.assertEqual(self.graph.nodes["claim1"]["canonical_text"], "该项目在 2024 年启动试点。")
        self.assertIn(
            {"source": "st1", "target": "claim1", "type": "NORMALIZED_TO"},
            self.graph.edges,
        )
        self.assertIn(
            {"source": "e1", "target": "claim1", "type": "SUPPORTED_BY"},
            self.graph.edges,
        )
        self.assertIn(
            {"source": "claim1", "target": "objective", "type": "COVERS_OBJECTIVE"},
            self.graph.edges,
        )

    def test_valid_empty_claim_list_does_not_trigger_fallback(self):
        result = self.normalize({"claims": []})

        self.assertEqual(result, {"created_or_updated_claim_ids": [], "claim_count": 0})
        self.assertEqual(self.graph.claims(), [])

    def test_statement_bound_evidence_is_added_when_model_omits_evidence_refs(self):
        result = self.normalize({
            "claims": [_claim_spec(evidence_refs=[])]
        })

        self.assertEqual(result["claim_count"], 1)
        self.assertIn(
            {"source": "e1", "target": "claim1", "type": "SUPPORTED_BY"},
            self.graph.edges,
        )

    def test_claim_with_only_invalid_refs_is_not_persisted(self):
        result = self.normalize({
            "claims": [
                _claim_spec(
                    statement_refs=["missing-statement"],
                    evidence_refs=[{"id": "missing-evidence", "stance": "supports"}],
                    confidence=0.99,
                )
            ]
        })

        self.assertEqual(result, {"created_or_updated_claim_ids": [], "claim_count": 0})
        self.assertEqual(self.graph.claims(), [])

    def test_claim_key_collision_does_not_overwrite_existing_meaning(self):
        model = StaticModel(
            {"claims": [_claim_spec(canonical_text="该项目在 2024 年启动试点。")]},
            {"claims": [_claim_spec(canonical_text="该项目在 2025 年完成部署。")]},
        )
        manager = MemoryManager(model=model)

        manager.normalize_claims("q1")
        manager.normalize_claims("q1")

        self.assertEqual(
            self.graph.nodes["claim1"]["canonical_text"],
            "该项目在 2024 年启动试点。",
        )

    def test_prompt_is_generic_chinese_and_preserves_output_contract(self):
        prompt = mm_prompts.normalize_claims
        required_fragments = {
            "你是 GraphResearcher 的 Claim 规范化器",
            "# 命题粒度",
            "# 内容蕴含",
            "# 输出前自检",
            "{query}",
            "{evidence_subgraph}",
            '"claims"',
            '"canonical_text"',
            '"claim_key"',
            '"statement_refs"',
            '"evidence_refs"',
            '"objective_keys"',
            '"confidence"',
            '"qualifiers"',
            '"limitations"',
            "supports|contradicts|qualifies",
        }
        forbidden_task_terms = {
            "Archaeology",
            "Manwoldae",
            "Goguryeo",
            "考古",
            "遗址",
            "发掘",
        }

        self.assertEqual(
            [item for item in required_fragments if item not in prompt],
            [],
        )
        self.assertEqual(
            [item for item in forbidden_task_terms if item in prompt],
            [],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
