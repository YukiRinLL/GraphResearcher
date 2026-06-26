"""Standalone checks for Statement/Evidence -> Claim normalization."""

import json
import sys
from pathlib import Path

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from agents.memory_manager import MemoryManager  # noqa: E402
from tools import graph_tools  # noqa: E402


NODES = {
    "q1": {
        "id": "q1",
        "type": "Query",
        "text": "company pilot progress",
        "objective_keys": ["progress"],
        "acceptance_criteria": [],
    },
    "objective": {
        "id": "objective",
        "type": "Analysis",
        "analysis_type": "objective",
        "objective_key": "progress",
        "requirement": "must",
    },
    "st1": {
        "id": "st1",
        "type": "Statement",
        "text": "Figure AI ran a BMW factory pilot in 2024.",
        "document_id": "d1",
        "source_id": "s1",
    },
    "e1": {
        "id": "e1",
        "type": "Evidence",
        "text": "BMW and Figure announced a factory pilot.",
        "document_id": "d1",
        "source_id": "s1",
    },
}
EDGES = []


def _type_name(value):
    return value.value if hasattr(value, "value") else str(value)


class FakeModel:
    def invoke(self, _prompt):
        class Result:
            content = json.dumps({
                "claims": [{
                    "canonical_text": "Figure AI had a BMW factory pilot in 2024.",
                    "claim_key": "figure-bmw-pilot-2024",
                    "statement_refs": ["st1"],
                    "evidence_refs": [{"id": "e1", "stance": "supports"}],
                    "objective_keys": ["progress"],
                    "confidence": 0.8,
                    "qualifiers": ["factory pilot"],
                    "limitations": [],
                }]
            })

        return Result()


def install_fakes():
    def search_nodes(kind, filt=None):
        wanted = _type_name(kind).replace("_", "").lower()
        return [
            dict(node) for node in NODES.values()
            if str(node.get("type", "")).replace("_", "").lower() == wanted
            and all(node.get(key) == value for key, value in (filt or {}).items())
        ]

    def add_edge(source, target, edge_type, attributes=None):
        edge = {
            "source": source,
            "target": target,
            "type": _type_name(edge_type),
            **(attributes or {}),
        }
        if edge not in EDGES:
            EDGES.append(edge)
        return f"{source}-{edge['type']}-{target}"

    def create_claim(statement, document_id=None, source_id=None, claim_key=None, canonical_text=None, **attrs):
        claim_id = "claim1"
        NODES[claim_id] = {
            "id": claim_id,
            "type": "Claim",
            "statement": statement,
            "canonical_text": canonical_text or statement,
            "claim_key": claim_key,
            **attrs,
        }
        return claim_id

    graph_tools.get_node = lambda node_id: dict(NODES.get(node_id, {}))
    graph_tools.search_nodes = search_nodes
    graph_tools.create_claim = create_claim
    graph_tools.add_edge = add_edge
    graph_tools.get_query_evaluation_subgraph = lambda _query_id: {
        "query": dict(NODES["q1"]),
        "nodes": [dict(NODES["st1"]), dict(NODES["e1"])],
        "edges": [],
        "children": [],
    }


def main():
    install_fakes()
    result = MemoryManager(model=FakeModel()).normalize_claims("q1")
    assert result["claim_count"] == 1, result
    assert NODES["claim1"]["claim_key"] == "figure-bmw-pilot-2024"
    assert {"source": "st1", "target": "claim1", "type": "NORMALIZED_TO"} in EDGES
    assert {"source": "e1", "target": "claim1", "type": "SUPPORTED_BY"} in EDGES
    assert {"source": "claim1", "target": "objective", "type": "COVERS_OBJECTIVE"} in EDGES
    print("ALL CLAIM NORMALIZATION CHECKS PASSED")


if __name__ == "__main__":
    main()
