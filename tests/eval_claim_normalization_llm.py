"""使用真实模型回放 Claim 规范化案例。

该脚本读取指定历史运行中的 Statement/Evidence，但把图写入限制在内存替身中。
它会消耗 API 配额，不参与常规单元测试。
"""

import json
import logging
import sys
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from dotenv import load_dotenv

repo_root = Path(__file__).parent.parent
load_dotenv(dotenv_path=repo_root / ".env")
sys.path.insert(0, str(repo_root / "src"))
sys.path.insert(0, str(repo_root / "tests"))

from test_claim_normalization_regressions import FakeGraph  # noqa: E402

import config  # noqa: E402
from agents.memory_manager import MemoryManager  # noqa: E402
from tools import graph_tools  # noqa: E402

run_dir = (
    repo_root
    / "outputs"
    / "wlc_tavily_baseline_16"
    / "_runs"
    / "52-Archaeology_of_North_Korea"
)
graph_path = run_dir / "research_graph.jsonl"
result_path = run_dir / "claim_normalization_llm_eval.json"
logger = logging.getLogger(__name__)


case_specs = [
    {
        "name": "wudong_grounding_and_atomicity",
        "query_handle": "q2",
        "statement_ids": [
            "20260827160522814408_e62b19ba",
            "20260827160522862153_bd875ab9",
            "20260827160522895469_15395005",
            "20260827160522928678_a4486a88",
        ],
    },
    {
        "name": "manwoldae_atomicity_and_numbers",
        "query_handle": "q3",
        "statement_ids": [
            "20260827160857690922_6083e218",
            "20260827160857725314_1a08c5eb",
            "20260827160857839410_be8ae9e6",
            "20260827160857875733_776ca8f3",
        ],
    },
    {
        "name": "query_scope_does_not_become_evidence",
        "query_handle": "q6",
        "statement_ids": [
            "20260827161816910638_0b7bf89d",
            "20260827161817193818_055f50b2",
        ],
    },
    {
        "name": "interpretation_keeps_attribution",
        "query_handle": "q2.2",
        "statement_ids": [
            "20260827162550511690_c2552523",
            "20260827162550549536_0b99f08e",
        ],
    },
    {
        "name": "uncertainty_survives_normalization",
        "query_handle": "q2.4",
        "statement_ids": [
            "20260827163241395805_b70fe73b",
        ],
    },
]


class RecordingModel:
    """记录真实模型的原始响应和用量信息。"""

    def __init__(self, model):
        self.model = model
        self.raw_responses = []
        self.usage = []

    def invoke(self, prompt):
        response = self.model.invoke(prompt)
        content = getattr(response, "content", response)
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        self.raw_responses.append(str(content))
        self.usage.append(getattr(response, "usage_metadata", None))
        return response


class ReplayGraph(FakeGraph):
    """承载单个历史案例的内存图。"""

    def __init__(self, query, nodes):
        super().__init__()
        self.query_id = query["id"]
        self.nodes = {
            query["id"]: dict(query),
            **{node["id"]: dict(node) for node in nodes},
        }
        self.edges = []
        self._claim_sequence = 0

    def get_query_evaluation_subgraph(self, query_id):
        assert query_id == self.query_id
        return {
            "query": dict(self.nodes[self.query_id]),
            "nodes": [
                dict(node)
                for node in self.nodes.values()
                if node.get("type") in {"Source", "Statement", "Evidence"}
            ],
            "edges": [],
            "children": [],
        }


def load_run():
    """读取历史运行并建立节点索引。"""
    items = [
        json.loads(line)
        for line in graph_path.read_text(encoding="utf-8").splitlines()
    ]
    nodes = {
        item["id"]: item
        for item in items
        if item.get("kind") == "node" and item.get("id")
    }
    return nodes


def materialize_case(nodes, spec):
    """从历史图中投影一个 Query-local 回放案例。"""
    query = next(
        node
        for node in nodes.values()
        if node.get("type") == "Query" and node.get("handle") == spec["query_handle"]
    )
    statements = [nodes[node_id] for node_id in spec["statement_ids"]]
    statement_ids = set(spec["statement_ids"])
    evidence = [
        node
        for node in nodes.values()
        if node.get("type") == "Evidence"
        and statement_ids.intersection(
            node.get("statement_refs")
            or ([node.get("statement_ref")] if node.get("statement_ref") else [])
        )
    ]
    source_ids = {
        node.get("source_id")
        for node in statements + evidence
        if node.get("source_id")
    }
    sources = [nodes[source_id] for source_id in source_ids]
    return query, sources + statements + evidence


def graph_patches(graph):
    """返回 ReplayGraph 对 graph_tools 的边界替换。"""
    replacements = {
        "get_node": graph.get_node,
        "search_nodes": graph.search_nodes,
        "create_claim": graph.create_claim,
        "add_edge": graph.add_edge,
        "get_query_evaluation_subgraph": graph.get_query_evaluation_subgraph,
    }
    stack = ExitStack()
    for name, replacement in replacements.items():
        stack.enter_context(patch.object(graph_tools, name, replacement))
    return stack


def claim_refs(graph, claim_id, edge_type):
    """返回指定类型关系指向 Claim 的来源节点。"""
    return {
        edge["source"]
        for edge in graph.edges
        if edge.get("target") == claim_id and edge.get("type") == edge_type
    }


def common_checks(graph, claims, raw_response):
    """检查所有案例共享的输出和 provenance 合同。"""
    parsed_claims = None
    try:
        parsed = json.loads(raw_response)
        strict_json = isinstance(parsed, dict) and isinstance(parsed.get("claims"), list)
        if strict_json:
            parsed_claims = parsed["claims"]
    except json.JSONDecodeError:
        strict_json = False

    evidence_nodes = {
        node["id"]: node
        for node in graph.nodes.values()
        if node.get("type") == "Evidence"
    }
    statement_nodes = {
        node["id"]: node
        for node in graph.nodes.values()
        if node.get("type") == "Statement"
    }
    grounded = True
    evidence_complete = True
    for claim in claims:
        statement_refs = claim_refs(graph, claim["id"], "NORMALIZED_TO")
        evidence_refs = claim_refs(graph, claim["id"], "SUPPORTED_BY")
        if not statement_refs and not evidence_refs:
            grounded = False
        if not statement_refs.issubset(statement_nodes):
            grounded = False
        expected_evidence = {
            evidence_id
            for evidence_id, evidence in evidence_nodes.items()
            if statement_refs.intersection(
                evidence.get("statement_refs")
                or (
                    [evidence.get("statement_ref")]
                    if evidence.get("statement_ref")
                    else []
                )
            )
        }
        if not expected_evidence.issubset(evidence_refs):
            evidence_complete = False

    return {
        "strict_json": strict_json,
        "honors_valid_empty_claim_list": (
            parsed_claims != [] or not claims
        ),
        "all_claims_grounded": grounded,
        "statement_bound_evidence_complete": evidence_complete,
    }


def normalized_text(claims):
    """返回便于数值检查的合并文本。"""
    return " ".join(claim.get("canonical_text", "") for claim in claims).replace(",", "")


def case_checks(name, graph, claims):
    """执行与案例目标对应的确定性检查。"""
    texts = [claim.get("canonical_text", "") for claim in claims]
    refs = {
        claim["id"]: claim_refs(graph, claim["id"], "NORMALIZED_TO")
        for claim in claims
    }
    combined = normalized_text(claims)

    if name == "wudong_grounding_and_atomicity":
        return {
            "does_not_introduce_unstated_liutingdong": not any(
                "Liutingdong" in text or "柳庭洞" in text
                for text in texts
            ),
            "preserves_input_proper_name": any("Wudong" in text for text in texts),
            "does_not_add_unstated_vessel_morphology": not any(
                "敞口鼓腹" in text for text in texts
            ),
            "keeps_independent_statements_atomic": (
                len(claims) >= 4
                and all(len(statement_refs) <= 1 for statement_refs in refs.values())
            ),
            "does_not_bundle_excavation_date_with_house_count": not any(
                "1954" in text
                and "1955" in text
                and any(
                    marker in text.lower()
                    for marker in ("8座", "八座", "8处", "八处", "eight house")
                )
                for text in texts
            ),
        }
    if name == "manwoldae_atomicity_and_numbers":
        return {
            "preserves_decisive_numbers": all(
                token in combined for token in ("7500", "40", "1400", "114")
            ),
            "preserves_other_celadon_artifacts": any(
                "青瓷" in text and "其他" in text
                or "celadon" in text.lower() and "other" in text.lower()
                for text in texts
            ),
            "keeps_independent_statements_atomic": (
                len(claims) >= 4
                and all(len(statement_refs) <= 1 for statement_refs in refs.values())
            ),
            "keeps_interpretation_attributed": any(
                ("archaeologist" in text.lower() or "考古学家" in text)
                and any(marker in text.lower() for marker in ("suggest", "推测", "认为"))
                for text in texts
            ),
            "does_not_bundle_independent_find_details": not any(
                (
                    "7500" in text.replace(",", "")
                    and any(
                        marker in text.lower()
                        for marker in (
                            "七至八",
                            "七或八",
                            "7至8",
                            "7或8",
                            "seven or eight",
                        )
                    )
                )
                or (
                    "1400" in text.replace(",", "")
                    and any(
                        marker in text.lower()
                        for marker in (
                            "两英尺",
                            "two-foot",
                            "功能仍不确定",
                            "function remains uncertain",
                        )
                    )
                )
                for text in texts
            ),
        }
    if name == "query_scope_does_not_become_evidence":
        return {
            "does_not_import_query_subject": not any(
                "Manwoldae" in text or "满月台" in text
                for text in texts
            ),
            "does_not_merge_independent_statements": all(
                len(statement_refs) <= 1 for statement_refs in refs.values()
            ),
            "does_not_emit_workflow_gap_claim": not any(
                marker in text
                for text in texts
                for marker in ("当前输入", "所给材料", "本次搜索", "provided material")
            ),
        }
    if name == "interpretation_keeps_attribution":
        return {
            "keeps_periods_as_separate_propositions": (
                len(claims) >= 2
                and all(len(statement_refs) <= 1 for statement_refs in refs.values())
            ),
            "keeps_source_attribution_in_claim_text": all(
                any(
                    marker in text.lower()
                    for marker in ("ho-tae", "jeon", "该研究", "研究介绍")
                )
                for text in texts
            ),
        }
    if name == "uncertainty_survives_normalization":
        return {
            "keeps_date_and_taxonomy_atomic": len(claims) >= 2,
            "preserves_date_range": "46" in combined and "48" in combined,
            "preserves_dating_method": any(
                "u-series" in text.lower() or "铀系" in text
                for text in texts
            ),
            "preserves_taxonomic_uncertainty": any(
                marker in combined.lower()
                for marker in (
                    "?",
                    "可能",
                    "暂定",
                    "不确定",
                    "provisional",
                    "tentative",
                    "tentatively",
                    "uncertain",
                    "uncertainty",
                )
            ),
        }
    raise ValueError(f"Unknown case: {name}")


def run_case(model, nodes, spec):
    """调用真实模型并返回单个案例的完整结果。"""
    query, replay_nodes = materialize_case(nodes, spec)
    graph = ReplayGraph(query, replay_nodes)
    recorder = RecordingModel(model)
    with graph_patches(graph):
        result = MemoryManager(model=recorder).normalize_claims(query["id"])
    claims = graph.claims()
    checks = {
        **common_checks(graph, claims, recorder.raw_responses[0]),
        **case_checks(spec["name"], graph, claims),
    }
    return {
        "name": spec["name"],
        "query": {
            "id": query["id"],
            "handle": query.get("handle"),
            "text": query.get("text"),
        },
        "input_statement_ids": spec["statement_ids"],
        "input_evidence_ids": sorted(
            node["id"] for node in replay_nodes if node.get("type") == "Evidence"
        ),
        "normalization_result": result,
        "claims": claims,
        "edges": graph.edges,
        "checks": checks,
        "passed": all(checks.values()),
        "raw_response": recorder.raw_responses[0],
        "usage": recorder.usage[0],
    }


def main():
    """运行全部真实模型回放案例并保存结果。"""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    nodes = load_run()
    model = config.build_model(temperature=0.0)
    cases = []
    for index, spec in enumerate(case_specs, start=1):
        logger.info("[%d/%d] %s", index, len(case_specs), spec["name"])
        case = run_case(model, nodes, spec)
        cases.append(case)
        passed = sum(case["checks"].values())
        total = len(case["checks"])
        logger.info(
            "  checks=%d/%d claims=%d",
            passed,
            total,
            len(case["claims"]),
        )

    output = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "model": config.DEFAULT_MODEL,
        "temperature": 0.0,
        "source_graph": str(graph_path.relative_to(repo_root)),
        "summary": {
            "case_count": len(cases),
            "passed_cases": sum(case["passed"] for case in cases),
            "failed_cases": sum(not case["passed"] for case in cases),
            "passed_checks": sum(
                sum(case["checks"].values()) for case in cases
            ),
            "check_count": sum(len(case["checks"]) for case in cases),
        },
        "cases": cases,
    }
    result_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(json.dumps(output["summary"], ensure_ascii=False))
    logger.info("saved=%s", result_path)
    return 0 if not output["summary"]["failed_cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
