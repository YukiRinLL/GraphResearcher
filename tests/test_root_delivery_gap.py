"""根属 delivery-requirement 恢复 Gap 不得被分支冷却逻辑永久搁置。

复现 deepseek-v4-pro 评测样本 53 / 第 37 题的故障链：
``_recover_unactionable_research`` 把恢复 Gap 挂在 goal UserRequest 上，
``_build_branch_summary`` 不列 root owner，portfolio LLM 合规地省略该
owner 的 branch_decision，旧逻辑默认 cool_down → hard skip → Gap 永远
无法 selected，未满足的 must Objective 被静默收敛。
"""

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_tree_state_machine as tsm  # noqa: E402

from agents.memory_manager import MemoryManager  # noqa: E402
from memory.graph import EdgeType  # noqa: E402
from tools import graph_tools  # noqa: E402

INITIAL_NODES = copy.deepcopy(tsm.NODES)
INITIAL_EDGES = copy.deepcopy(tsm.EDGES)


@pytest.fixture(autouse=True)
def reset_graph():
    # install_fakes 会全局重绑 graph_tools；保存原函数并在用例后还原，
    # 避免污染同一会话中的其他测试文件。
    bound_names = (
        "get_node", "search_nodes", "upsert_node", "add_edge", "get_node_edges",
        "get_query_children", "get_query_parent", "get_all_nodes", "get_all_edges",
        "create_analysis", "create_claim", "create_query_child",
    )
    originals = {name: getattr(graph_tools, name, None) for name in bound_names}
    tsm.NODES.clear()
    tsm.NODES.update(copy.deepcopy(INITIAL_NODES))
    tsm.EDGES.clear()
    tsm.EDGES.extend(copy.deepcopy(INITIAL_EDGES))
    tsm.SEQ = 0
    tsm.install_fakes()
    yield
    for name, fn in originals.items():
        setattr(graph_tools, name, fn)


def _verdict(objective_coverage=0.1):
    # 真实模型的行为：branch_summary 里没有 root owner，因此裁决中也
    # 不含 goal 的 branch_decision。
    return {
        "objectives": [
            {"objective_key": "core-answer", "coverage": 0.4, "confidence": 0.4},
            {
                "objective_key": "recover-answer",
                "coverage": objective_coverage,
                "confidence": 0.1,
            },
        ],
        "branch_decisions": [],
        "fatal_unresolved_conflicts": [],
        "gap_query_drafts": [],
    }


def _add_root_recovery_objective(objective_status="open"):
    tsm.NODES["orecover"] = {
        "id": "orecover",
        "type": "Analysis",
        "analysis_type": "objective",
        "objective_key": "recover-answer",
        "description": "recover missing answer",
        "acceptance_criteria": ["recover"],
        "requirement": "must",
        "weight": 1.0,
        "coverage": 0.1,
        "confidence": 0.1,
        "status": objective_status,
    }
    tsm.EDGES.append({"source": "goal", "target": "orecover", "type": "HAS_OBJECTIVE"})
    return "orecover"


def _add_root_recovery_gap(objective_status="open"):
    if "orecover" not in tsm.NODES:
        _add_root_recovery_objective(objective_status)
    gap_id = graph_tools.create_analysis(
        "Missing report evidence for Objective recover-answer",
        query_id="goal",
        analysis_type="gap",
        description="Missing report evidence for Objective recover-answer",
        gap_key="objective-recover-answer",
        importance="core",
        required_for_parent=False,
        status="candidate",
        gap_category="missing_core_evidence",
        objective_keys=["recover-answer"],
        search_subject_key="objective-recover-answer",
        decision_impact=1.0,
        confidence_gain=1.0,
        estimated_search_rounds=1,
        acceptance_criteria=["recover"],
        expansion_mode="horizontal",
        expansion_parent_id="goal",
        trigger_type="delivery_requirement",
        trigger_refs=["orecover"],
        recovery_objective_key="recover-answer",
    )
    graph_tools.add_edge(gap_id, "orecover", EdgeType.IMPACTS_OBJECTIVE)
    return gap_id


def test_root_delivery_gap_selected_when_llm_omits_root_owner(tmp_path):
    gap_id = _add_root_recovery_gap()
    mm = MemoryManager(model=tsm.FakeModel([_verdict()]), cache_dir=str(tmp_path))

    result = mm.evaluate_research_portfolio("goal")

    assert gap_id in result["selected_gap_ids"], result
    assert tsm.NODES[gap_id]["status"] == "selected"
    assert tsm.NODES[gap_id]["expansion_parent_id"] == "goal"


def test_root_delivery_gap_still_selected_under_cached_empty_verdict(tmp_path):
    """reopen 后 material signature 不变、空 branch_decisions 被缓存重放时，
    选择不能依赖 LLM 补回 root owner 决策。"""
    _add_root_recovery_objective()
    mm = MemoryManager(
        model=tsm.FakeModel([_verdict(), _verdict()]), cache_dir=str(tmp_path)
    )

    # 稳态 prime：objective 的 streak/unmet 等字段由先前轮次写入，
    # 与生产中"delivery gap 创建前 objective 已被评估多次"一致。
    mm.evaluate_research_portfolio("goal")

    # recovery 循环创建 root gap，裁决中省略 root owner。
    gap_id = _add_root_recovery_gap()
    first = mm.evaluate_research_portfolio("goal")
    assert gap_id in first["selected_gap_ids"], first

    # 模拟 reopen：Gap 回到 candidate，revision bump 触发重评。
    tsm.NODES[gap_id]["status"] = "candidate"
    tsm.NODES[gap_id]["reopen_count"] = 1
    tsm.NODES["goal"]["portfolio_revision"] += 1
    # FakeModel 已无 payload：命中缓存则不触达模型；未命中会抛 IndexError。
    replayed = mm.evaluate_research_portfolio("goal")
    assert gap_id in replayed["selected_gap_ids"], replayed
    assert tsm.NODES[gap_id]["status"] == "selected"


def test_root_delivery_gap_defers_when_objective_blocked(tmp_path):
    """Objective 已 blocked 时，残留 root Gap 不得借豁免重新扩张。"""
    gap_id = _add_root_recovery_gap(objective_status="blocked")
    mm = MemoryManager(model=tsm.FakeModel([_verdict()]), cache_dir=str(tmp_path))

    result = mm.evaluate_research_portfolio("goal")

    assert gap_id not in result["selected_gap_ids"], result
    assert gap_id in result["deferred_gap_ids"], result
    assert tsm.NODES[gap_id]["status"] == "deferred_branch_cool_down"
