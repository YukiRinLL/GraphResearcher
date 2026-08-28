"""确定性 LangGraph Reporter workflow 的独立回归检查。"""

import sys
from pathlib import Path

repo_dir = Path(__file__).parent.parent
sys.path.insert(0, str(repo_dir / "src"))

import workflow as root_workflow  # noqa: E402
from agents import reporter_workflow as workflow_module  # noqa: E402


def _outline_chapter(title="Finding", query_refs=None, section_type="body"):
    """构造满足 Reporter 大纲契约的测试章节."""
    return {
        "title": title,
        "goals": [f"Explain {title}"],
        "query_refs": list(query_refs or ["q1"]),
        "section_plan": f"Develop {title} from the bound Query evidence.",
        "section_type": section_type,
    }


def _install_fakes(
    model_outputs,
    *,
    commit_results=None,
    submit_results=None,
    research_state="REPORT_READY",
):
    """安装隔离运行时，并返回观测记录和恢复函数。"""
    observations = {
        "calls": [],
        "state_updates": [],
        "model_prompts": [],
        "committed_chapters": [],
    }
    outputs = iter(model_outputs)
    chapter_results = iter(commit_results or [{"status": "ok", "validated": True}])
    final_results = iter(
        submit_results
        or [
            {
                "delivered": True,
                "validated": True,
                "revision_requested": False,
                "review_status": "passed",
                "report": "# Report\n\nSupported fact.[1]",
            }
        ]
    )
    originals = {
        "get_goal": workflow_module.research_state.get_goal,
        "update_goal": workflow_module.research_state.update_goal,
        "export": workflow_module.graph_manager_tools.export_report_context,
        "outline": workflow_module.graph_manager_tools.commit_report_outline,
        "prepare": workflow_module.graph_manager_tools.prepare_report_chapter_batch,
        "commit": workflow_module.graph_manager_tools.commit_report_chapter_batch,
        "submit": workflow_module.graph_manager_tools.submit_final_report,
        "invoke": workflow_module._invoke_reporter_json,
    }
    from tools import graph_tools

    originals["validate_query_tree"] = graph_tools.validate_query_tree
    goal = {
        "id": "goal",
        "request": "Write a cited report.",
        "research_state": research_state,
    }

    workflow_module.research_state.get_goal = lambda: dict(goal)
    graph_tools.validate_query_tree = lambda: {"valid": True, "issues": []}

    def update_goal(attributes):
        observations["state_updates"].append(dict(attributes))
        goal.update(attributes)
        return dict(goal)

    workflow_module.research_state.update_goal = update_goal
    workflow_module.graph_manager_tools.export_report_context = lambda: {
        "user_request": goal["request"],
        "queries": [
            {"ref": "q1", "text": "Topic", "supported_topics": ["Supported fact"]}
        ],
        "disclosed_conflicts": [],
        "reference_registry": [
            {
                "n": 1,
                "title": "Source",
                "url": "https://example.com",
            }
        ],
    }

    def commit_outline(*, title, chapters):
        del title
        observations["calls"].append("commit_outline")
        return {"status": "ok", "chapters_count": len(chapters)}

    def prepare(*, chapters):
        observations["calls"].append("prepare")
        return {
            "status": "ok",
            "chapters": [
                {
                    "status": "ok",
                    "chapter_id": chapter["chapter_id"],
                    "bundle_token": f"b{chapter['chapter_id']}",
                    "chapter_title": "Finding",
                    "chapter_goals": ["Explain the evidence"],
                    "section_plan": "Use the evidence.",
                    "query_refs": ["q1"],
                    "evidence_items": [
                        {
                            "ref": "e1",
                            "text": "Supported fact",
                            "source_numbers": [1],
                        }
                    ],
                    "reference_registry_subset": [
                        {
                            "n": 1,
                            "url": "https://example.com",
                        }
                    ],
                    "disclosed_conflicts": [],
                }
                for chapter in chapters
            ],
        }

    def commit_chapters(*, chapters):
        observations["calls"].append("commit_chapters")
        observations["committed_chapters"].append(chapters)
        return next(chapter_results)

    def submit():
        observations["calls"].append("submit")
        return next(final_results)

    workflow_module.graph_manager_tools.commit_report_outline = commit_outline
    workflow_module.graph_manager_tools.prepare_report_chapter_batch = prepare
    workflow_module.graph_manager_tools.commit_report_chapter_batch = commit_chapters
    workflow_module.graph_manager_tools.submit_final_report = submit

    def invoke(prompt):
        observations["model_prompts"].append(prompt)
        return next(outputs)

    workflow_module._invoke_reporter_json = invoke

    def restore():
        workflow_module.research_state.get_goal = originals["get_goal"]
        workflow_module.research_state.update_goal = originals["update_goal"]
        graph_tools.validate_query_tree = originals["validate_query_tree"]
        workflow_module.graph_manager_tools.export_report_context = originals["export"]
        workflow_module.graph_manager_tools.commit_report_outline = originals["outline"]
        workflow_module.graph_manager_tools.prepare_report_chapter_batch = originals[
            "prepare"
        ]
        workflow_module.graph_manager_tools.commit_report_chapter_batch = originals[
            "commit"
        ]
        workflow_module.graph_manager_tools.submit_final_report = originals["submit"]
        workflow_module._invoke_reporter_json = originals["invoke"]

    return observations, restore


def test_workflow_commits_ordered_report_without_model_tool_calls():
    """状态图而不是模型掌控报告工具顺序。"""
    observations, restore = _install_fakes(
        [
            {
                "title": "Report",
                "chapters": [_outline_chapter()],
            },
            {
                "chapters": [
                    {
                        "chapter_id": 1,
                        "content": "Supported fact.[1]",
                        "evidence_refs": ["e1"],
                    }
                ]
            },
        ]
    )
    try:
        result = workflow_module.run_report_workflow()
    finally:
        restore()

    assert result["success"] and result["validated"], result
    assert observations["calls"] == [
        "commit_outline",
        "prepare",
        "commit_chapters",
        "submit",
    ]
    assert observations["state_updates"][0]["research_state"] == "REPORTING"
    assert observations["committed_chapters"][0][0]["bundle_token"] == "b1"


def test_outline_prompt_is_limited_to_outline_planning():
    """大纲 prompt 不继承章节写作或工具调度职责。"""
    context = {
        "user_request": "Write a cited report.",
        "queries": [
            {"ref": "q1", "text": "Topic", "supported_topics": ["Supported fact"]}
        ],
        "disclosed_conflicts": [],
        "reference_registry": [],
    }

    prompt = workflow_module._outline_prompt(context)
    retry_prompt = workflow_module._outline_prompt(
        context, "Unknown query reference: 'q2'"
    )

    assert "不调用工具" in prompt
    assert "不输出 `chapter_id`" in prompt
    assert "commit_report_outline" not in prompt
    assert "submit_final_report" not in prompt
    assert '"ref": "q1"' in prompt
    assert '"supported_topics": ["Supported fact"]' in prompt
    assert "`supported_topics`：" in prompt
    assert "只用于章节划分和 `query_refs` 选择" in prompt
    assert "正文事实和引用以后续章节 bundle 中的 Evidence 和 Claim 为准" in prompt
    assert "`q1.2.1` 是 `q1.2` 的子 Query" in prompt
    assert "同一层级的 Query 是并列研究分支" in prompt
    assert "实际列表可能不连续" in prompt
    assert "材料不会沿父子或兄弟关系自动合并" in prompt
    assert "必须在 `query_refs` 中逐一列出对应 handle" in prompt
    assert "识别报告的任务类型、目标读者和核心问题" in prompt
    assert "不按 Query 编号或树形顺序排列章节" in prompt
    assert "Query 数量不作为拆章或合章依据" in prompt
    assert "没有相关 Query 支持的维度不纳入章节范围" in prompt
    assert "研究对象本身的局限、风险或适用边界" in prompt
    assert '"conflict_type": "分歧类型"' in prompt
    assert '"n": 1' in prompt
    assert "Retry Feedback" not in prompt
    assert "# Retry Feedback" in retry_prompt
    assert "上一版大纲未通过校验" in retry_prompt


def test_workflow_retries_query_refs_outside_report_context():
    """大纲只能绑定本次 Report Context 公开的 Query handle."""
    observations, restore = _install_fakes(
        [
            {
                "title": "Report",
                "chapters": [_outline_chapter(query_refs=["q2"])],
            },
            {
                "title": "Report",
                "chapters": [_outline_chapter()],
            },
            {
                "chapters": [
                    {
                        "chapter_id": 1,
                        "content": "Supported fact.[1]",
                        "evidence_refs": ["e1"],
                    }
                ]
            },
        ]
    )
    try:
        result = workflow_module.run_report_workflow()
    finally:
        restore()

    assert result["success"], result
    assert observations["calls"].count("commit_outline") == 1
    assert len(observations["model_prompts"]) == 3
    assert "not available in Report Context" in observations["model_prompts"][1]


def test_empty_query_context_skips_outline_model_and_uses_fallback():
    """没有证据支持的 Query 时直接进入既有确定性降级路径."""
    observations, restore = _install_fakes(
        [],
        submit_results=[
            {
                "delivered": True,
                "validated": False,
                "revision_requested": False,
                "review_status": "soft_only_no_revise",
                "report": "# Evidence fallback",
            }
        ],
    )
    workflow_module.graph_manager_tools.export_report_context = lambda: {
        "user_request": "Write a cited report.",
        "queries": [],
        "disclosed_conflicts": [],
        "reference_registry": [],
    }
    try:
        result = workflow_module.run_report_workflow()
    finally:
        restore()

    assert result["success"] and result["delivered"], result
    assert result["fallback_reason"] == (
        "Reporter context has no evidence-backed Query handles"
    )
    assert observations["calls"] == ["submit"]
    assert observations["model_prompts"] == []


def test_chapter_prompt_receives_only_request_and_local_bundles():
    """章节写作阶段不继承大纲阶段的全局 Report Context."""
    prompt = workflow_module._chapter_prompt(
        "Write a cited report.",
        [
            {
                "chapter_id": 1,
                "chapter_title": "Finding",
                "query_refs": ["q1"],
                "evidence_items": [{"ref": "e1", "text": "Supported fact"}],
                "reference_registry_subset": [
                    {"n": 1, "title": "Local source", "url": "https://local.example"}
                ],
            }
        ],
        [],
        False,
    )

    assert "User Request:\nWrite a cited report." in prompt
    assert "Prepared chapter bundles:" in prompt
    assert "Report Context:" not in prompt
    assert "supported_topics" not in prompt
    assert "交付模式" not in prompt


def test_outline_contract_requires_complete_chapters_and_first_lead():
    """大纲字段完整性和 lead 位置由程序校验."""
    try:
        workflow_module.OutlineCandidate.model_validate(
            {
                "title": "Report",
                "chapters": [{"title": "Incomplete", "query_refs": ["q1"]}],
            }
        )
    except workflow_module.ValidationError:
        pass
    else:
        raise AssertionError("Incomplete outline chapter should be rejected")

    candidate = workflow_module.OutlineCandidate.model_validate(
        {
            "title": "Report",
            "chapters": [
                _outline_chapter(title="Body"),
                _outline_chapter(title="Late lead", section_type="lead"),
            ],
        }
    )
    try:
        workflow_module._validated_outline(
            candidate,
            {"queries": [{"ref": "q1"}]},
        )
    except ValueError as exc:
        assert "lead chapter must be the first" in str(exc)
    else:
        raise AssertionError("A lead chapter after chapter 1 should be rejected")


def test_workflow_retries_invalid_chapter_json_then_commits():
    """模型输出不合格时只重试当前证据包。"""
    observations, restore = _install_fakes(
        [
            {
                "title": "Report",
                "chapters": [_outline_chapter()],
            },
            {
                "chapters": [
                    {
                        "chapter_id": 2,
                        "content": "Wrong batch.[1]",
                        "evidence_refs": ["e1"],
                    }
                ]
            },
            {
                "chapters": [
                    {
                        "chapter_id": 1,
                        "content": "Supported fact.[1]",
                        "evidence_refs": ["e1"],
                    }
                ]
            },
        ]
    )
    try:
        result = workflow_module.run_report_workflow()
    finally:
        restore()

    assert result["success"], result
    assert observations["calls"].count("prepare") == 1
    assert observations["calls"].count("commit_chapters") == 1
    assert len(observations["model_prompts"]) == 3
    assert "Chapter IDs must exactly match" in observations["model_prompts"][-1]


def test_workflow_prepares_at_most_three_chapters_per_batch():
    """四章大纲被确定性地拆成三章和一章两个批次。"""
    outline_chapters = [
        _outline_chapter(title=f"Finding {chapter_id}")
        for chapter_id in range(1, 5)
    ]
    observations, restore = _install_fakes(
        [
            {"title": "Report", "chapters": outline_chapters},
            {
                "chapters": [
                    {
                        "chapter_id": chapter_id,
                        "content": f"Supported fact {chapter_id}.[1]",
                        "evidence_refs": ["e1"],
                    }
                    for chapter_id in range(1, 4)
                ],
            },
            {
                "chapters": [
                    {
                        "chapter_id": 4,
                        "content": "Supported fact 4.[1]",
                        "evidence_refs": ["e1"],
                    }
                ]
            },
        ],
        commit_results=[
            {"status": "ok", "validated": True},
            {"status": "ok", "validated": True},
        ],
    )
    try:
        result = workflow_module.run_report_workflow()
    finally:
        restore()

    assert result["success"], result
    assert observations["calls"] == [
        "commit_outline",
        "prepare",
        "commit_chapters",
        "prepare",
        "commit_chapters",
        "submit",
    ]
    assert [
        [chapter["chapter_id"] for chapter in batch]
        for batch in observations["committed_chapters"]
    ] == [[1, 2, 3], [4]]


def test_workflow_rewrites_chapters_once_after_review_feedback():
    """状态图掌控 Review 后唯一一轮章节修订。"""
    observations, restore = _install_fakes(
        [
            {
                "title": "Report",
                "chapters": [_outline_chapter()],
            },
            {
                "chapters": [
                    {
                        "chapter_id": 1,
                        "content": "Initial fact.[1]",
                        "evidence_refs": ["e1"],
                    }
                ]
            },
            {
                "chapters": [
                    {
                        "chapter_id": 1,
                        "content": "Revised fact.[1]",
                        "evidence_refs": ["e1"],
                    }
                ]
            },
        ],
        commit_results=[
            {"status": "ok", "validated": True},
            {"status": "ok", "validated": True},
        ],
        submit_results=[
            {
                "delivered": True,
                "validated": False,
                "revision_requested": True,
                "report": "# Report\n\nInitial fact.[1]",
                "issues": [
                    {
                        "section_title": "Finding",
                        "message": "Clarify attribution.",
                    }
                ],
            },
            {
                "delivered": True,
                "validated": True,
                "revision_requested": False,
                "review_status": "revised_once",
                "report": "# Report\n\nRevised fact.[1]",
            },
        ],
    )
    try:
        result = workflow_module.run_report_workflow()
    finally:
        restore()

    assert result["success"] and result["review_status"] == "revised_once", result
    assert observations["calls"] == [
        "commit_outline",
        "prepare",
        "commit_chapters",
        "submit",
        "prepare",
        "commit_chapters",
        "submit",
    ]
    assert "Clarify attribution." in observations["model_prompts"][-1]


def test_retry_exhaustion_uses_existing_fail_open_submission():
    """大纲重试耗尽后仍通过既有提交契约交付最佳报告。"""
    observations, restore = _install_fakes(
        [{}, {}, {}],
        submit_results=[
            {
                "delivered": True,
                "validated": False,
                "revision_requested": False,
                "review_status": "soft_only_no_revise",
                "report": "# Evidence fallback",
            }
        ],
    )
    try:
        result = workflow_module.run_report_workflow()
    finally:
        restore()

    assert result["success"] and result["delivered"], result
    assert not result["validated"]
    assert result["fallback_reason"].startswith("Outline attempt 3 failed")
    assert observations["calls"] == ["submit"]
    assert len(observations["model_prompts"]) == 3


def test_unauthorized_workflow_fails_without_report_tools():
    """未授权状态不会进入报告工具链。"""
    observations, restore = _install_fakes([], research_state="RESEARCHING")
    try:
        result = workflow_module.run_report_workflow()
    finally:
        restore()

    assert not result["success"], result
    assert observations["calls"] == []
    assert any(
        update.get("research_state") == "FAILED"
        for update in observations["state_updates"]
    )


def test_workflow_contains_only_runtime_nodes():
    """Reporter 状态图不保留旧的推进、组装或成功中转节点。"""
    nodes = set(workflow_module.reporter_workflow.get_graph().nodes)
    assert nodes == {
        "__start__",
        "authorize",
        "export_context",
        "plan_outline",
        "prepare_chapter_batch",
        "draft_chapter_batch",
        "submit",
        "finalize_best_effort",
        "fail",
        "__end__",
    }


def test_report_quality_checks_survive_middleware_removal():
    """旧 Reporter middleware 中仍有效的修订检查由报告模块保留。"""
    original_search = workflow_module.report_tools.graph_tools.search_nodes

    def search_nodes(node_type, _filters):
        if node_type == "user_request":
            return [{"request": "Write a Wikipedia article"}]
        if node_type == "evidence":
            return []
        return []

    workflow_module.report_tools.graph_tools.search_nodes = search_nodes
    try:
        issues = workflow_module.report_tools.check_report_quality(
            "# Topic\n\n| Key |\n| --- |\n| Value |\n\n## Body"
        )
    finally:
        workflow_module.report_tools.graph_tools.search_nodes = original_search

    assert any("Lead 散文必须在 Infobox 之前" in issue for issue in issues)
    assert any("章节数不足" in issue for issue in issues)


def test_top_level_report_node_calls_deterministic_workflow():
    """顶层 report 节点不再构建通用 Reporter Agent。"""
    original_run = root_workflow.run_report_workflow
    original_report = root_workflow.gmt.get_compiled_report
    original_get_config = root_workflow.get_config
    calls = []
    runnable_config = {"callbacks": ["trace"], "metadata": {"run": "test"}}
    root_workflow.run_report_workflow = lambda **kwargs: (
        calls.append(kwargs)
        or {
            "success": True,
            "delivered": True,
            "validated": False,
            "review_status": "soft_only_no_revise",
            "fallback_reason": "bounded retry exhausted",
        }
    )
    root_workflow.gmt.get_compiled_report = lambda: "# Report"
    root_workflow.get_config = lambda: runnable_config
    try:
        result = root_workflow.report_node({})
    finally:
        root_workflow.run_report_workflow = original_run
        root_workflow.gmt.get_compiled_report = original_report
        root_workflow.get_config = original_get_config

    assert calls == [{"runnable_config": runnable_config}]
    summary = result["messages"][0].content
    assert "workflow submitted" in summary
    assert "validated=False" in summary
    assert "fallback=bounded retry exhausted" in summary


def test_run_report_workflow_forwards_runnable_config():
    """Reporter 子图保留顶层 tracing config 和自己的递归上限。"""
    original_workflow = workflow_module.reporter_workflow
    observed = {}

    class _Workflow:
        def invoke(self, state, config):
            observed["state"] = state
            observed["config"] = config
            return {
                "final_result": {
                    "success": True,
                    "delivered": True,
                    "validated": True,
                    "review_status": "passed",
                }
            }

    workflow_module.reporter_workflow = _Workflow()
    runnable_config = {
        "callbacks": ["trace"],
        "metadata": {"run": "reporter-replay"},
        "recursion_limit": 999,
    }
    try:
        result = workflow_module.run_report_workflow(runnable_config=runnable_config)
    finally:
        workflow_module.reporter_workflow = original_workflow

    assert result["success"], result
    assert observed["state"] == {}
    assert observed["config"]["callbacks"] == ["trace"]
    assert observed["config"]["metadata"] == {"run": "reporter-replay"}
    assert observed["config"]["recursion_limit"] == 200


if __name__ == "__main__":
    test_workflow_commits_ordered_report_without_model_tool_calls()
    test_outline_prompt_is_limited_to_outline_planning()
    test_workflow_retries_query_refs_outside_report_context()
    test_empty_query_context_skips_outline_model_and_uses_fallback()
    test_chapter_prompt_receives_only_request_and_local_bundles()
    test_outline_contract_requires_complete_chapters_and_first_lead()
    test_workflow_retries_invalid_chapter_json_then_commits()
    test_workflow_prepares_at_most_three_chapters_per_batch()
    test_workflow_rewrites_chapters_once_after_review_feedback()
    test_retry_exhaustion_uses_existing_fail_open_submission()
    test_unauthorized_workflow_fails_without_report_tools()
    test_workflow_contains_only_runtime_nodes()
    test_report_quality_checks_survive_middleware_removal()
    test_top_level_report_node_calls_deterministic_workflow()
    test_run_report_workflow_forwards_runnable_config()
    print("ALL REPORTER WORKFLOW CHECKS PASSED")  # noqa: T201
