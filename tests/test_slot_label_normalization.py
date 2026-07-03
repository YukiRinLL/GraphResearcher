"""Standalone checks for canonical slot labels and artifact-backed coverage."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

repo_dir = Path(__file__).parent.parent
sys.path.insert(0, str(repo_dir))
sys.path.insert(0, str(repo_dir / "src"))

from agents.memory_manager import MemoryManager  # noqa: E402
from tools import graph_tools, report_tools, research_state  # noqa: E402

NODES: dict[str, dict] = {}


def _install_fakes():
    def search_nodes(kind, filt=None):
        wanted = kind.replace("_", "").lower()
        return [
            dict(node) for node in NODES.values()
            if str(node.get("type", "")).replace("_", "").lower() == wanted
            and all(node.get(key) == value for key, value in (filt or {}).items())
        ]

    graph_tools.search_nodes = search_nodes
    graph_tools.get_node = lambda node_id: dict(NODES.get(node_id, {}))
    graph_tools.get_query_evaluation_subgraph = lambda query_id: {
        "query": dict(NODES.get(query_id, {})),
        "nodes": [],
        "edges": [],
        "children": [],
    }
    research_state.get_goal = lambda goal_id=None: dict(NODES.get(goal_id or "goal", {}))


def test_slot_alias_canonicalization():
    labels = report_tools.canonicalize_slot_labels([
        "对比矩阵",
        "融资状态",
        "Team Profile",
        "Lead",
        "Capital Insight",
    ])
    assert labels == [
        "comparison",
        "financing_status",
        "team_profile",
        "lead",
        "capital_insight",
    ], labels


def test_delivery_readiness_bridges_chapter_semantics():
    _install_fakes()
    NODES.clear()
    NODES["goal"] = {
        "id": "goal",
        "type": "UserRequest",
        "task_archetype": "comparative_matrix",
        "delivery_contract": {
            "report_mode": "comparative_matrix",
            "required_section_types": ["body", "comparison", "limitations"],
            "required_slot_labels": ["跨公司对比矩阵", "团队画像"],
            "comparison_required": True,
            "entity_focus": False,
            "strict_time_window": False,
            "prefer_compression_over_expansion": True,
        },
    }
    NODES["q1"] = {
        "id": "q1",
        "type": "Query",
        "status": "sufficient",
        "text": "机器人公司团队",
        "slot_targets": ["团队画像"],
    }

    with TemporaryDirectory() as temp_dir:
        report_tools.commit_report_outline(temp_dir, "机器人公司比较", [{
            "chapter_id": 1,
            "title": "跨公司对比矩阵",
            "goals": ["做公司间核心差异对比"],
            "query_ids": ["q1"],
            "section_plan": "围绕融资状态与团队画像展开",
            "section_type": "comparison",
        }])
        original_build_assets = report_tools.build_report_planning_assets
        try:
            report_tools.build_report_planning_assets = lambda query_ids=None: {
                "query_evidence_digests": [],
                "lead_candidates": [],
                "comparison_slots": [],
                "entity_profiles": [],
            }
            mm = MemoryManager(model=object(), cache_dir=temp_dir)
            readiness = mm._compute_delivery_readiness(
                "goal",
                goal=dict(NODES["goal"]),
                queries=[dict(NODES["q1"])],
                gaps=[],
            )
        finally:
            report_tools.build_report_planning_assets = original_build_assets
    assert readiness["ready"] is True, readiness
    assert readiness["missing_contract_slots"] == [], readiness
    assert {"comparison", "team_profile"}.issubset(set(readiness["slot_coverage"])), readiness


def main():
    test_slot_alias_canonicalization()
    test_delivery_readiness_bridges_chapter_semantics()


if __name__ == "__main__":
    main()
