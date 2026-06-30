import sys
import types
from pathlib import Path

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))
sys.modules.setdefault("config", types.SimpleNamespace(build_model=lambda: None))
sys.modules.setdefault("tools.middleware", types.SimpleNamespace(get_max_search_rounds=lambda: 0))

from agents.memory_manager import MemoryManager  # noqa: E402
from tools import graph_tools, research_state  # noqa: E402


def _manager():
    mm = object.__new__(MemoryManager)
    mm.cache_dir = None
    mm.model = None
    mm._state_lock = __import__("threading").RLock()
    return mm


def test_init_research_persists_structured_task_contract(monkeypatch):
    mm = _manager()
    sys.modules["tools.middleware"] = types.SimpleNamespace(get_max_search_rounds=lambda: 9)
    monkeypatch.setattr(mm, "_plan_task_contract", lambda user_request: {
        "research_goal": "compare deployment paths",
        "language": "zh",
        "scope_mode": "bounded",
        "task_contract": {
            "deliverable_type": "research_report",
            "target_shape": "multi-section report with comparison table",
            "coverage_axes": ["technology_route", "commercialization"],
            "required_sections": [
                {"section_key": "overview", "title": "概览", "purpose": "summarize routes"},
                {"section_key": "comparison", "title": "对比", "purpose": "compare routes"},
            ],
            "required_tables": [
                {"table_key": "route-matrix", "title": "路线对比", "columns": ["route", "status"]},
            ],
            "time_scope": "2024-2026",
            "source_constraints": ["fresh sources"],
            "completeness_mode": "bounded",
            "freshness_requirement": "high",
        },
        "coverage_slots": [
            {"slot_key": "overview-core", "section": "overview", "unit_type": "paragraph", "priority": "core", "description": "overview"},
            {"slot_key": "comparison-table", "section": "comparison", "unit_type": "table_row", "priority": "core", "description": "table row"},
        ],
    })
    monkeypatch.setattr(mm, "_plan_seed_queries", lambda task_contract: {
        "seed_queries": [
            {
                "text": "route A 2024 2026 commercialization",
                "importance": "core",
                "query_role": "seed",
                "granularity_level": "section_axis",
                "scope_signature": "route-a",
                "target_slot_keys": ["overview-core"],
                "acceptance_criteria": ["route A basics"],
            }
        ]
    })
    nodes = {}
    slot_nodes = {}
    edges = []
    counter = {"query": 0}
    monkeypatch.setattr(graph_tools, "search_nodes", lambda kind, _filter=None: [])
    monkeypatch.setattr(graph_tools, "create_user_request", lambda **attrs: nodes.setdefault("goal", {"id": "goal", "type": "UserRequest", **attrs})["id"])
    monkeypatch.setattr(graph_tools, "create_task_contract", lambda goal_id, deliverable_type, target_shape, **attrs: nodes.setdefault("contract", {"id": "contract", "type": "TaskContract", "deliverable_type": deliverable_type, "target_shape": target_shape, **attrs})["id"])
    monkeypatch.setattr(graph_tools, "create_coverage_slot", lambda goal_id, task_contract_id, slot_key, section, unit_type="paragraph", status="open", **attrs: slot_nodes.setdefault(slot_key, {"id": slot_key, "type": "CoverageSlot", "slot_key": slot_key, "section": section, "unit_type": unit_type, "status": status, **attrs})["id"])
    monkeypatch.setattr(graph_tools, "get_node", lambda node_id: dict(nodes.get(node_id) or slot_nodes.get(node_id) or nodes.get("query")))
    monkeypatch.setattr(graph_tools, "create_query_child", lambda parent_id, text, importance, acceptance_criteria=None, **attrs: nodes.setdefault("query", {"id": "q1", "type": "Query", "handle": "q1", "text": text, "priority_tier": "high", **attrs})["id"])
    monkeypatch.setattr(graph_tools, "add_edge", lambda source, target, edge_type, attributes=None: edges.append((source, target, str(getattr(edge_type, "value", edge_type)))))
    monkeypatch.setattr(research_state, "RESEARCHING", "RESEARCHING")
    monkeypatch.setattr(research_state, "update_goal", lambda attrs, goal_id=None: attrs)

    result = mm.init_research("test request")

    assert result["task_contract"]["deliverable_type"] == "research_report"
    assert result["coverage_slots"][0]["slot_key"] == "overview-core"
    assert result["queries"][0]["query_role"] == "seed"
    assert any(edge[2] == "TARGETS_SLOT" for edge in edges)


def test_create_coverage_slots_falls_back_to_article_sections(monkeypatch):
    mm = _manager()
    monkeypatch.setattr(graph_tools, "create_coverage_slot", lambda goal_id, task_contract_id, slot_key, section, unit_type="paragraph", status="open", **attrs: slot_key)
    monkeypatch.setattr(graph_tools, "get_node", lambda node_id: {"id": node_id, "type": "CoverageSlot", "slot_key": node_id, "section": node_id.replace("-core", "")})

    slots = mm._create_coverage_slots(
        "goal",
        "contract",
        {
            "deliverable_type": "wikipedia_article",
            "required_sections": [
                {"section_key": "lead", "title": "Lead", "purpose": "summary"},
                {"section_key": "history", "title": "History", "purpose": "history"},
            ],
        },
        [],
    )

    assert [slot["slot_key"] for slot in slots] == ["lead-core", "history-core"]
