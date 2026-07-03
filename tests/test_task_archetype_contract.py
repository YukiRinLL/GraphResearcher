"""Standalone checks for task archetype + staged portfolio initialization."""

import sys
from pathlib import Path

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from agents.memory_manager import MemoryManager  # noqa: E402
from tools import graph_tools, middleware, research_state  # noqa: E402

NODES: dict[str, dict] = {}
EDGES: list[dict] = []
SEQ = 0


def _install_fakes():
    def search_nodes(kind, filt=None):
        wanted = kind.replace("_", "").lower()
        return [
            dict(node) for node in NODES.values()
            if str(node.get("type", "")).replace("_", "").lower() == wanted
            and all(node.get(key) == value for key, value in (filt or {}).items())
        ]

    def get_node(node_id):
        return dict(NODES.get(node_id, {}))

    def create_user_request(request, research_goal=None, language=None, **attrs):
        node_id = "goal"
        NODES[node_id] = {
            "id": node_id,
            "type": "UserRequest",
            "request": request,
            "research_goal": research_goal,
            "language": language,
            **attrs,
        }
        return node_id

    def create_analysis(text, query_id=None, analysis_type="insight", **attrs):
        global SEQ
        SEQ += 1
        node_id = f"a{SEQ}"
        NODES[node_id] = {
            "id": node_id,
            "type": "Analysis",
            "text": text,
            "analysis_type": analysis_type,
            **attrs,
        }
        if query_id:
            EDGES.append({
                "source": query_id,
                "target": node_id,
                "type": "HAS_OBJECTIVE" if analysis_type == "objective" else "HAS_ANALYSIS",
            })
        return node_id

    def create_query_child(parent_id, text, importance, acceptance_criteria=None, gap_ids=None, **attrs):
        global SEQ
        SEQ += 1
        node_id = f"q{SEQ}"
        NODES[node_id] = {
            "id": node_id,
            "type": "Query",
            "handle": f"q{SEQ}",
            "text": text,
            "status": "pending",
            "importance": importance,
            "priority": 1.0,
            "priority_tier": "high",
            "sem": 1.0,
            "acceptance_criteria": acceptance_criteria or [],
            **attrs,
        }
        EDGES.append({"source": parent_id, "target": node_id, "type": "HAS_QUERY"})
        return node_id

    def add_edge(source, target, edge_type, attributes=None):
        EDGES.append({
            "source": source,
            "target": target,
            "type": edge_type.value if hasattr(edge_type, "value") else str(edge_type),
            **(attributes or {}),
        })
        return EDGES[-1]

    def upsert_node(_node_type, attrs, dedupe_key=None):
        if dedupe_key not in NODES:
            NODES[dedupe_key] = {"id": dedupe_key}
        NODES[dedupe_key].update(attrs)
        return dedupe_key

    graph_tools.search_nodes = search_nodes
    graph_tools.get_node = get_node
    graph_tools.create_user_request = create_user_request
    graph_tools.create_analysis = create_analysis
    graph_tools.create_query_child = create_query_child
    graph_tools.add_edge = add_edge
    graph_tools.upsert_node = upsert_node
    middleware.get_max_search_rounds = lambda: 6
    research_state.update_goal = lambda attrs, goal_id=None: (NODES["goal"].update(attrs) or dict(NODES["goal"]))
    research_state.get_goal = lambda goal_id=None: dict(NODES.get(goal_id or "goal", {}))


def main():
    _install_fakes()
    mm = MemoryManager(model=object())
    mm._plan_initial_queries = lambda _request: {
        "research_goal": "比较机器人公司",
        "language": "zh",
        "time_window": "2024-2026",
        "scope_mode": "bounded",
        "task_archetype": "comparative_matrix",
        "delivery_contract": {
            "report_mode": "comparative_matrix",
            "required_section_types": ["lead", "body", "comparison", "limitations"],
            "required_slot_labels": ["对比矩阵", "融资状态"],
            "comparison_required": True,
            "entity_focus": False,
            "strict_time_window": True,
            "prefer_compression_over_expansion": True,
        },
        "objectives": [
            {
                "objective_key": "capital",
                "description": "比较资本与商业化",
                "requirement": "must",
                "weight": 1.0,
                "acceptance_criteria": ["给出资本与商业化比较"],
            }
        ],
        "query_portfolio_plan": [
            {
                "plan_id": "disc-1",
                "portfolio_stage": "discovery",
                "text": "机器人公司 融资与商业化 2024 2026",
                "importance": "core",
                "objective_keys": ["capital"],
                "acceptance_criteria": ["找到可比较的资本与商业化公开事实"],
                "slot_targets": ["融资状态"],
                "section_targets": ["body", "comparison"],
                "search_subject_key": "robotics-companies",
            },
            {
                "plan_id": "slot-1",
                "portfolio_stage": "slot_completion",
                "text": "机器人公司 对比矩阵 资本与部署 缺口 2024 2026",
                "importance": "supporting",
                "objective_keys": ["capital"],
                "acceptance_criteria": ["补齐比较槽位"],
                "slot_targets": ["跨公司对比矩阵"],
                "section_targets": ["comparison"],
                "search_subject_key": "robotics-companies",
            },
            {
                "plan_id": "deep-1",
                "portfolio_stage": "deep_dive",
                "text": "机器人公司 商业化 真实性 验证 2024 2026",
                "importance": "supporting",
                "objective_keys": ["capital"],
                "acceptance_criteria": ["验证核心商业化说法"],
                "slot_targets": [],
                "section_targets": ["body"],
                "search_subject_key": "robotics-companies",
            },
        ],
        "initial_queries": [],
    }

    result = mm.init_research("比较机器人公司")
    assert result["task_archetype"] == "comparative_matrix", result
    assert result["delivery_contract"]["comparison_required"] is True, result
    assert result["delivery_contract"]["required_slot_labels"] == ["comparison", "financing_status"], result
    assert len(result["query_portfolio_plan"]) == 3, result
    assert len(result["queries"]) == 1, result
    assert result["queries"][0]["portfolio_stage"] == "discovery", result
    assert NODES["goal"]["task_archetype"] == "comparative_matrix", NODES["goal"]
    assert NODES["goal"]["delivery_contract"]["strict_time_window"] is True, NODES["goal"]
    assert NODES["goal"]["query_portfolio_plan"][0]["slot_targets"] == ["financing_status"], NODES["goal"]
    assert NODES["goal"]["query_portfolio_plan"][1]["slot_targets"] == ["comparison"], NODES["goal"]
    assert {item["portfolio_stage"] for item in NODES["goal"]["query_portfolio_plan"]} == {
        "discovery", "slot_completion", "deep_dive"
    }, NODES["goal"]["query_portfolio_plan"]
    query_nodes = [node for node in NODES.values() if node.get("type") == "Query"]
    assert len(query_nodes) == 1, query_nodes
    assert query_nodes[0]["slot_targets"] == ["financing_status"], query_nodes[0]


if __name__ == "__main__":
    main()
