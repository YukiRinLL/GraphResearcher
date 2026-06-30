import sys
import types
from pathlib import Path

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))
sys.modules.setdefault("config", types.SimpleNamespace(build_model=lambda: None))

from agents.memory_manager import MemoryManager  # noqa: E402
from tools import graph_tools  # noqa: E402


def _manager():
    mm = object.__new__(MemoryManager)
    mm.cache_dir = None
    mm.model = None
    return mm


def _install_fake_graph(monkeypatch):
    nodes = {
        "goal": {"id": "goal", "type": "UserRequest"},
        "slot-a": {"id": "slot-a", "type": "CoverageSlot", "slot_key": "lead"},
        "slot-b": {"id": "slot-b", "type": "CoverageSlot", "slot_key": "history"},
        "parent": {"id": "parent", "type": "Query", "handle": "q1", "text": "root cluster"},
        "existing": {
            "id": "existing",
            "type": "Query",
            "handle": "q1.1",
            "text": "existing sibling",
            "scope_signature": "dup-scope",
        },
        "child-existing": {
            "id": "child-existing",
            "type": "Query",
            "handle": "q1.2",
            "text": "existing child",
            "scope_signature": "dup-child",
        },
        "fh1": {
            "id": "fh1",
            "type": "ResearchFrontier",
            "frontier_type": "horizontal",
            "status": "selected",
            "scope_signature": "new-a",
            "description": "new sibling a",
            "target_slot_keys": ["lead"],
        },
        "fh2": {
            "id": "fh2",
            "type": "ResearchFrontier",
            "frontier_type": "horizontal",
            "status": "selected",
            "scope_signature": "new-b",
            "description": "new sibling b",
            "target_slot_keys": ["history"],
        },
        "fh3": {
            "id": "fh3",
            "type": "ResearchFrontier",
            "frontier_type": "horizontal",
            "status": "selected",
            "scope_signature": "new-c",
            "description": "new sibling c",
            "target_slot_keys": ["lead"],
        },
        "fh4": {
            "id": "fh4",
            "type": "ResearchFrontier",
            "frontier_type": "horizontal",
            "status": "selected",
            "scope_signature": "dup-scope",
            "description": "duplicate sibling",
            "target_slot_keys": ["lead"],
        },
        "fv1": {
            "id": "fv1",
            "type": "ResearchFrontier",
            "frontier_type": "vertical",
            "status": "selected",
            "scope_signature": "deep-a",
            "description": "verify launch date",
            "target_slot_keys": ["history"],
            "anchor_claim_ids": ["claim-1"],
            "anchor_conflict_ids": [],
            "anchor_evidence_ids": [],
        },
    }
    children = {"parent": ["existing"], "owner": ["child-existing"]}
    edges = []
    counter = {"value": 0}

    def get_node(node_id):
        return dict(nodes.get(node_id, {}))

    def get_query_children(parent_id):
        return list(children.get(parent_id, []))

    def get_coverage_slots(_goal_id):
        return [dict(nodes["slot-a"]), dict(nodes["slot-b"])]

    def create_query_child(parent_id, text, importance, acceptance_criteria=None, **attributes):
        counter["value"] += 1
        query_id = f"q-new-{counter['value']}"
        children.setdefault(parent_id, []).append(query_id)
        nodes[query_id] = {
            "id": query_id,
            "type": "Query",
            "handle": f"{parent_id}.{counter['value']}",
            "text": text,
            "status": "pending",
            "importance": importance,
            "acceptance_criteria": acceptance_criteria or [],
            **attributes,
        }
        return query_id

    def add_edge(source, target, edge_type, attributes=None):
        edge_name = edge_type.value if hasattr(edge_type, "value") else str(edge_type)
        edges.append((source, target, edge_name, attributes or {}))
        return edge_name

    def upsert_node(node_type, attributes, dedupe_key=None):
        nodes[dedupe_key].update(attributes)
        return dedupe_key

    monkeypatch.setattr(graph_tools, "get_node", get_node)
    monkeypatch.setattr(graph_tools, "get_query_children", get_query_children)
    monkeypatch.setattr(graph_tools, "get_coverage_slots", get_coverage_slots)
    monkeypatch.setattr(graph_tools, "create_query_child", create_query_child)
    monkeypatch.setattr(graph_tools, "add_edge", add_edge)
    monkeypatch.setattr(graph_tools, "upsert_node", upsert_node)
    return nodes, children, edges


def test_horizontal_expansion_creates_siblings_and_caps_batch(monkeypatch):
    mm = _manager()
    monkeypatch.setattr(mm, "_goal_node", lambda goal_id=None: {"id": "goal", "breadth_budget_used": 0})
    nodes, children, edges = _install_fake_graph(monkeypatch)

    created = mm._materialize_horizontal_queries(
        "parent",
        [nodes["fh1"], nodes["fh2"], nodes["fh3"], nodes["fh4"]],
        [
            {"text": "new sibling a query", "scope_signature": "new-a", "target_slot_keys": ["lead"]},
            {"text": "new sibling b query", "scope_signature": "new-b", "target_slot_keys": ["history"]},
            {"text": "new sibling c query", "scope_signature": "new-c", "target_slot_keys": ["lead"]},
            {"text": "duplicate sibling query", "scope_signature": "dup-scope", "target_slot_keys": ["lead"]},
        ],
    )

    assert len(created) == 3
    assert children["parent"][:1] == ["existing"]
    assert all(item["id"] in children["parent"] for item in created)
    assert nodes["fh1"]["status"] == "expanded"
    assert nodes["fh2"]["status"] == "expanded"
    assert nodes["fh3"]["status"] == "expanded"
    assert nodes["fh4"]["status"] == "selected"
    assert sum(1 for edge in edges if edge[2] == "TARGETS_SLOT") == 3


def test_vertical_expansion_creates_children_under_current_query(monkeypatch):
    mm = _manager()
    monkeypatch.setattr(
        mm,
        "_goal_node",
        lambda goal_id=None: {"id": "goal", "depth_budget_used": 0, "verification_budget_used": 0},
    )
    nodes, children, edges = _install_fake_graph(monkeypatch)

    created = mm._materialize_vertical_queries(
        "owner",
        [nodes["fv1"]],
        [
            {
                "text": "verify launch date child query",
                "scope_signature": "deep-a",
                "target_slot_keys": ["history"],
                "anchor_claim_ids": ["claim-1"],
            }
        ],
    )

    assert len(created) == 1
    child = nodes[created[0]["id"]]
    assert created[0]["id"] in children["owner"]
    assert child["query_role"] == "vertical"
    assert child["anchor_claim_ids"] == ["claim-1"]
    assert nodes["fv1"]["status"] == "expanded"
    assert any(edge[0] == created[0]["id"] and edge[2] == "TARGETS_SLOT" for edge in edges)
