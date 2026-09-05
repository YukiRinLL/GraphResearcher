"""确定性 LangGraph Reporter workflow 的独立回归检查。"""

import os
import sys
import threading
import time
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
    delivery_results=None,
    polish_output=None,
    polish_error=None,
    research_state="REPORT_READY",
    model_delay=0.0,
    prepare_fail_ids=None,
):
    """安装隔离运行时，并返回观测记录和恢复函数。"""
    observations = {
        "calls": [],
        "state_updates": [],
        "model_prompts": [],
        "model_phases": [],
        "committed_chapters": [],
        "prepared_chapters": [],
        "polished_reports": [],
        "peak_model_concurrency": 0,
    }
    outputs = iter(model_outputs)
    chapter_results = iter(commit_results or [{"status": "ok", "validated": True}])
    output_lock = threading.Lock()
    chapter_result_lock = threading.Lock()
    observation_lock = threading.Lock()
    active_model_calls = 0
    failed_preparations = set(prepare_fail_ids or [])
    final_results = iter(
        delivery_results
        or [
            {
                "delivered": True,
                "validated": False,
                "revision_requested": False,
                "review_status": "skipped",
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
        "assemble": workflow_module.graph_manager_tools.assemble_report_draft,
        "deliver": workflow_module.graph_manager_tools.deliver_final_report,
        "deliver_polished": workflow_module.graph_manager_tools.deliver_polished_report,
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
    }

    def commit_outline(*, title, chapters):
        del title
        observations["calls"].append("commit_outline")
        return {"status": "ok", "chapters_count": len(chapters)}

    def prepare(*, chapters):
        observations["calls"].append("prepare")
        observations["prepared_chapters"].append(chapters)
        prepared_chapters = [
            (
                {
                    "status": "error",
                    "chapter_id": chapter["chapter_id"],
                    "message": "Prepared chapter failed",
                }
                if chapter["chapter_id"] in failed_preparations
                else {
                    "status": "ok",
                    "chapter_id": chapter["chapter_id"],
                    "bundle_token": f"b{chapter['chapter_id']}",
                    "chapter_title": "Finding",
                    "chapter_goals": ["Explain the evidence"],
                    "section_plan": "Use the evidence.",
                    "section_type": "body",
                    "query_refs": ["q1"],
                    "evidence_items": [
                        {
                            "ref": "e1",
                            "type": "Evidence",
                            "text": f"Supported fact {chapter['chapter_id']}",
                            "source_numbers": [1],
                        }
                    ],
                    "disclosed_conflicts": [],
                }
            )
            for chapter in chapters
        ]
        return {
            "status": (
                "error"
                if any(item["status"] != "ok" for item in prepared_chapters)
                else "ok"
            ),
            "chapters": prepared_chapters,
        }

    def commit_chapters(*, chapters):
        with observation_lock:
            observations["calls"].append("commit_chapters")
            observations["committed_chapters"].append(chapters)
        with chapter_result_lock:
            result = dict(next(chapter_results))
        result.setdefault(
            "chapters",
            [
                {
                    "chapter_id": chapter["chapter_id"],
                    "candidate_saved": True,
                    "validated": bool(result.get("validated")),
                }
                for chapter in chapters
            ],
        )
        return result

    def deliver():
        observations["calls"].append("deliver")
        return next(final_results)

    def assemble():
        observations["calls"].append("assemble")
        return next(final_results)

    def deliver_polished(report, *, issues):
        observations["calls"].append("deliver_polished")
        observations["polished_reports"].append(report)
        return {
            "delivered": bool(report.strip()),
            "validated": False,
            "revision_requested": False,
            "review_status": "skipped",
            "report": report,
            "issues": issues,
        }

    workflow_module.graph_manager_tools.commit_report_outline = commit_outline
    workflow_module.graph_manager_tools.prepare_report_chapter_batch = prepare
    workflow_module.graph_manager_tools.commit_report_chapter_batch = commit_chapters
    workflow_module.graph_manager_tools.assemble_report_draft = assemble
    workflow_module.graph_manager_tools.deliver_final_report = deliver
    workflow_module.graph_manager_tools.deliver_polished_report = deliver_polished

    def invoke(prompt, *, phase="draft"):
        nonlocal active_model_calls
        is_polish = "# Complete Draft" in prompt
        if is_polish:
            output = (
                polish_output
                if polish_output is not None
                else {"report": "# Polished Report\n\nSupported fact.[1]"}
            )
        else:
            with output_lock:
                output = next(outputs)
        with observation_lock:
            observations["model_prompts"].append(prompt)
            observations["model_phases"].append(phase)
            active_model_calls += 1
            observations["peak_model_concurrency"] = max(
                observations["peak_model_concurrency"],
                active_model_calls,
            )
        try:
            if model_delay:
                time.sleep(model_delay)
            if is_polish and polish_error is not None:
                raise polish_error
            return output
        finally:
            with observation_lock:
                active_model_calls -= 1

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
        workflow_module.graph_manager_tools.assemble_report_draft = originals["assemble"]
        workflow_module.graph_manager_tools.deliver_final_report = originals["deliver"]
        workflow_module.graph_manager_tools.deliver_polished_report = originals[
            "deliver_polished"
        ]
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

    assert result["success"] and not result["validated"], result
    assert result["review_status"] == "skipped", result
    assert observations["calls"] == [
        "commit_outline",
        "prepare",
        "commit_chapters",
        "assemble",
        "deliver_polished",
    ]
    assert observations["state_updates"][0]["research_state"] == "REPORTING"
    assert observations["committed_chapters"][0][0]["bundle_token"] == "b1"
    assert observations["polished_reports"] == [
        "# Polished Report\n\nSupported fact.[1]"
    ]
    assert observations["model_phases"][-1] == "polish"


def test_outline_prompt_is_limited_to_outline_planning():
    """大纲 prompt 不继承章节写作或工具调度职责。"""
    context = {
        "user_request": "Write a cited report.",
        "queries": [
            {"ref": "q1", "text": "Topic", "supported_topics": ["Supported fact"]}
        ],
        "disclosed_conflicts": [],
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
    assert '"reference_registry"' not in prompt
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
    assert len(observations["model_prompts"]) == 4
    assert "not available in Report Context" in observations["model_prompts"][1]


def test_empty_query_context_skips_outline_model_and_uses_fallback():
    """没有证据支持的 Query 时直接进入既有确定性降级路径."""
    observations, restore = _install_fakes(
        [],
        delivery_results=[
            {
                "delivered": True,
                "validated": False,
                "revision_requested": False,
                "review_status": "skipped",
                "report": "# Evidence fallback",
            }
        ],
    )
    workflow_module.graph_manager_tools.export_report_context = lambda: {
        "user_request": "Write a cited report.",
        "queries": [],
        "disclosed_conflicts": [],
    }
    try:
        result = workflow_module.run_report_workflow()
    finally:
        restore()

    assert result["success"] and result["delivered"], result
    assert result["fallback_reason"] == (
        "Reporter context has no evidence-backed Query handles"
    )
    assert observations["calls"] == ["deliver"]
    assert observations["model_prompts"] == []


def test_chapter_prompt_receives_full_outline_and_one_local_bundle():
    """章节写作阶段接收完整写作大纲和一个章节局部证据包."""
    outline = {
        "title": "Complete Report",
        "chapters": [
            {
                "chapter_id": 1,
                "title": "Finding",
                "goals": ["Explain the evidence"],
                "query_refs": ["q1"],
                "section_plan": "Use the claim and its supporting evidence.",
                "section_type": "body",
                "status": "pending",
            },
            {
                "chapter_id": 2,
                "title": "Later Analysis",
                "goals": ["Interpret the implications"],
                "query_refs": ["q2"],
                "section_plan": "Develop the implications after the finding.",
                "section_type": "body",
                "status": "pending",
            },
        ],
    }
    bundle = {
        "status": "ok",
        "chapter_id": 1,
        "bundle_token": "b1-internal",
        "chapter_title": "Finding",
        "chapter_goals": ["Explain the evidence"],
        "section_plan": "Use the claim and its supporting evidence.",
        "section_type": "body",
        "query_refs": ["q1"],
        "evidence_items": [
            {
                "ref": "e1",
                "type": "Evidence",
                "text": "Specific supporting evidence",
                "confidence": 0.9,
                "qualifiers": ["internal evidence qualifier"],
                "limitations": ["internal evidence limitation"],
                "locator": "paragraph 2",
                "claim_relations": [
                    {"target_ref": "c1", "stance": "supports"}
                ],
                "evidence_relations": [],
                "source_numbers": [1],
            },
            {
                "ref": "c1",
                "type": "Claim",
                "text": "Normalized claim",
                "confidence": 0.8,
                "qualifiers": ["for this case"],
                "limitations": ["single source"],
                "claim_relations": [],
                "evidence_relations": [
                    {"target_ref": "e1", "stance": "supports"}
                ],
                "source_numbers": [1],
            },
        ],
        "disclosed_conflicts": [
            {
                "ref": "x1",
                "description": "A disclosed disagreement",
                "conflict_type": "factual",
                "evidence_refs": ["e1"],
            }
        ],
    }
    prompt = workflow_module._chapter_prompt(
        "Write a cited report.",
        outline,
        bundle,
    )

    assert "# User Request\n\nWrite a cited report." in prompt
    assert "# Report Outline" in prompt
    assert '"title": "Complete Report"' in prompt
    assert '"title": "Finding"' in prompt
    assert '"title": "Later Analysis"' in prompt
    assert "# Current Chapter Bundle" in prompt
    assert "本次调用的唯一写作目标由 `Current Chapter Bundle` 直接给出" in prompt
    assert '"chapter_title": "Finding"' in prompt
    assert '"chapter_goals": ["Explain the evidence"]' in prompt
    assert '"section_plan": "Use the claim and its supporting evidence."' in prompt
    assert '"section_type": "body"' in prompt
    assert '"text": "Specific supporting evidence"' in prompt
    assert '"text": "Normalized claim"' in prompt
    assert '"evidence_refs": [{"ref": "e1", "stance": "supports"}]' in prompt
    assert '"description": "A disclosed disagreement"' in prompt
    assert '"evidence_items"' not in prompt
    assert '"bundle_token"' not in prompt
    assert '"query_refs"' not in prompt
    assert '"status": "pending"' not in prompt
    assert "internal evidence qualifier" not in prompt
    assert "internal evidence limitation" not in prompt
    assert "paragraph 2" not in prompt
    assert "reference_registry_subset" not in prompt
    assert '"sources"' not in prompt
    assert "Report Context" not in prompt
    assert "supported_topics" not in prompt
    assert "交付模式" not in prompt
    assert "Retry Feedback" not in prompt
    assert "<retry_feedback>" not in prompt
    assert "<report_outline>" not in prompt
    assert "<current_chapter_bundle>" not in prompt

    retry_prompt = workflow_module._chapter_prompt(
        "Write a cited report.",
        outline,
        bundle,
        "Chapter IDs do not match.",
    )
    assert retry_prompt.count("# Retry Feedback") == 1
    assert "Chapter IDs do not match." in retry_prompt
    assert "仍输出当前章节的完整候选正文" in retry_prompt
    assert "<retry_feedback>" not in retry_prompt
    assert "<report_outline>" not in retry_prompt
    assert "<current_chapter_bundle>" not in retry_prompt


def test_polish_prompt_receives_complete_draft_and_preserves_contract():
    """全文润色接收完整草稿，并在保留结构和引用的前提下允许语言转换。"""
    draft = "# Report\n\n## Finding\n\nFact 42.[1]\n\n## References\n\n1. Source"

    prompt = workflow_module._polish_prompt("Write a cited report.", draft)

    assert "Write a cited report." in prompt
    assert draft in prompt
    assert "保留章节主题、数量、顺序和标题层级" in prompt
    assert "不新增、删除、拆分或合并章节" in prompt
    assert "标题翻译不得改变章节主题" in prompt
    assert "事实、数值、单位、日期、名称、归因、限定条件" in prompt
    assert "不新增、删除、替换或重新编号引用" in prompt
    assert '"report": "完整的 Markdown 报告"' in prompt
    assert "<user_request>" not in prompt
    assert "<complete_draft>" not in prompt


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


def test_chapter_contract_accepts_exactly_one_chapter():
    """章节写作响应不能同时提交多个章节."""
    chapter = {
        "chapter_id": 1,
        "content": "Supported fact.[1]",
        "evidence_refs": ["e1"],
    }
    workflow_module.ChapterDraftCandidate.model_validate({"chapters": [chapter]})
    try:
        workflow_module.ChapterDraftCandidate.model_validate(
            {"chapters": [chapter, {**chapter, "chapter_id": 2}]}
        )
    except workflow_module.ValidationError:
        pass
    else:
        raise AssertionError("A chapter response must contain exactly one chapter")


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
                        "content": "Wrong chapter.[1]",
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
    assert len(observations["model_prompts"]) == 4
    assert "Chapter ID must match the current chapter" in observations["model_prompts"][-2]


def test_workflow_writes_one_chapter_per_parallel_model_call():
    """四章分别生成和提交，并在每次写作时提供完整大纲."""
    outline_chapters = [
        _outline_chapter(title=f"Finding {chapter_id}")
        for chapter_id in range(1, 5)
    ]
    observations, restore = _install_fakes(
        [
            {"title": "Report", "chapters": outline_chapters},
            *[
                {
                    "chapters": [
                        {
                            "chapter_id": chapter_id,
                            "content": f"Supported fact {chapter_id}.[1]",
                            "evidence_refs": ["e1"],
                        }
                    ]
                }
                for chapter_id in range(1, 5)
            ],
        ],
        commit_results=[{"status": "ok", "validated": True}] * 4,
        model_delay=0.05,
    )
    original_concurrency = workflow_module.config.REPORTER_CHAPTER_CONCURRENCY
    try:
        workflow_module.config.REPORTER_CHAPTER_CONCURRENCY = 2
        result = workflow_module.run_report_workflow()
    finally:
        workflow_module.config.REPORTER_CHAPTER_CONCURRENCY = original_concurrency
        restore()

    assert result["success"], result
    assert observations["calls"][0] == "commit_outline"
    assert observations["calls"].count("prepare") == 2
    assert observations["calls"].count("commit_chapters") == 4
    assert observations["calls"][-2:] == ["assemble", "deliver_polished"]
    assert sorted(
        chapter["chapter_id"]
        for batch in observations["committed_chapters"]
        for chapter in batch
    ) == [1, 2, 3, 4]
    assert [
        [chapter["chapter_id"] for chapter in batch]
        for batch in observations["prepared_chapters"]
    ] == [[1, 2, 3], [4]]
    assert observations["peak_model_concurrency"] == 2
    chapter_prompts = observations["model_prompts"][1:-1]
    assert len(chapter_prompts) == 4
    assert all(
        all(f'"title": "Finding {chapter_id}"' in prompt for chapter_id in range(1, 5))
        for prompt in chapter_prompts
    )
    assert all(prompt.count("# Current Chapter Bundle") == 1 for prompt in chapter_prompts)
    for current_id in range(1, 5):
        prompt = next(
            prompt
            for prompt in chapter_prompts
            if f'"text": "Supported fact {current_id}"' in prompt
        )
        assert f'"text": "Supported fact {current_id}"' in prompt
        assert all(
            f'"text": "Supported fact {other_id}"' not in prompt
            for other_id in range(1, 5)
            if other_id != current_id
        )


def test_workflow_ignores_chapter_validation_and_skips_review():
    """章节语义校验失败不阻断后续章节，完成后直接交付。"""
    outline_chapters = [
        _outline_chapter(title=f"Finding {chapter_id}")
        for chapter_id in range(1, 5)
    ]
    observations, restore = _install_fakes(
        [
            {
                "title": "Report",
                "chapters": outline_chapters,
            },
            *[
                {
                    "chapters": [
                        {
                            "chapter_id": chapter_id,
                            "content": f"Initial fact {chapter_id}.[1]",
                            "evidence_refs": ["e1"],
                        }
                    ]
                }
                for chapter_id in range(1, 5)
            ],
        ],
        commit_results=[{"status": "ok", "validated": False}] * 4,
        delivery_results=[
            {
                "delivered": True,
                "validated": False,
                "revision_requested": False,
                "review_status": "skipped",
                "report": "# Report\n\nInitial facts.[1]",
            },
        ],
    )
    try:
        result = workflow_module.run_report_workflow()
    finally:
        restore()

    assert result["success"] and result["review_status"] == "skipped", result
    assert not result["validated"], result
    assert observations["calls"][0] == "commit_outline"
    assert observations["calls"].count("prepare") == 2
    assert observations["calls"].count("commit_chapters") == 4
    assert observations["calls"][-2:] == ["assemble", "deliver_polished"]
    assert len(observations["model_prompts"]) == 6


def test_failed_chapter_does_not_block_parallel_siblings():
    """单章准备失败时，其他章节仍写作并进入统一交付。"""
    outline_chapters = [
        _outline_chapter(title=f"Finding {chapter_id}")
        for chapter_id in range(1, 4)
    ]
    observations, restore = _install_fakes(
        [
            {"title": "Report", "chapters": outline_chapters},
            {
                "chapters": [
                    {
                        "chapter_id": 2,
                        "content": "Supported fact 2.[1]",
                        "evidence_refs": ["e1"],
                    }
                ]
            },
            {
                "chapters": [
                    {
                        "chapter_id": 3,
                        "content": "Supported fact 3.[1]",
                        "evidence_refs": ["e1"],
                    }
                ]
            },
        ],
        commit_results=[{"status": "ok", "validated": True}] * 2,
        prepare_fail_ids={1},
    )
    try:
        result = workflow_module.run_report_workflow()
    finally:
        restore()

    assert result["success"], result
    assert result["fallback_reason"] == (
        "Reporter failed to draft chapters 1; deterministic fallbacks were used"
    )
    assert observations["calls"].count("commit_chapters") == 2
    assert observations["calls"][-2:] == ["assemble", "deliver_polished"]
    assert len(observations["model_prompts"]) == 4
    assert observations["model_prompts"][-1].count("# Complete Draft") == 1


def test_exhausted_chapter_still_enters_polish():
    """单章写作重试耗尽后先确定性补齐，再进入一次全文润色。"""
    invalid_chapter = {
        "chapters": [
            {
                "chapter_id": 2,
                "content": "Wrong chapter.[1]",
                "evidence_refs": ["e1"],
            }
        ]
    }
    observations, restore = _install_fakes(
        [
            {"title": "Report", "chapters": [_outline_chapter()]},
            invalid_chapter,
            invalid_chapter,
            invalid_chapter,
        ]
    )
    try:
        result = workflow_module.run_report_workflow()
    finally:
        restore()

    assert result["success"], result
    assert result["fallback_reason"] == (
        "Reporter failed to draft chapters 1; deterministic fallbacks were used"
    )
    assert observations["calls"] == [
        "commit_outline",
        "prepare",
        "assemble",
        "deliver_polished",
    ]
    polish_prompts = [
        prompt
        for prompt in observations["model_prompts"]
        if "# Complete Draft" in prompt
    ]
    assert len(polish_prompts) == 1


def test_polish_timeout_delivers_assembled_draft():
    """润色请求超时时交付按大纲组装完成的章节草稿。"""
    assembled = {
        "delivered": True,
        "validated": False,
        "revision_requested": False,
        "review_status": "skipped",
        "report": "# Report\n\nSupported fact.[1]",
    }
    observations, restore = _install_fakes(
        [
            {"title": "Report", "chapters": [_outline_chapter()]},
            {
                "chapters": [
                    {
                        "chapter_id": 1,
                        "content": "Supported fact.[1]",
                        "evidence_refs": ["e1"],
                    }
                ]
            },
        ],
        delivery_results=[assembled, assembled],
        polish_error=TimeoutError("Request timed out."),
    )
    try:
        result = workflow_module.run_report_workflow()
    finally:
        restore()

    assert result["success"] and result["delivered"], result
    assert result["fallback_reason"] == (
        "Report polishing failed: Request timed out."
    )
    assert observations["calls"][-2:] == ["assemble", "deliver"]
    assert "deliver_polished" not in observations["calls"]
    polish_prompts = [
        prompt
        for prompt in observations["model_prompts"]
        if "# Complete Draft" in prompt
    ]
    assert len(polish_prompts) == 1


def test_reporter_polish_timeout_defaults_to_600_seconds():
    """全文润色使用独立的 600 秒请求超时。"""
    config = workflow_module.config
    name = "GR_REPORTER_POLISH_TIMEOUT"
    original_value = os.environ.get(name)
    original_build_model = config.build_model
    original_cache = dict(config._model_cache)
    observed = {}
    sentinel = object()
    try:
        os.environ.pop(name, None)
        config._model_cache.pop("reporter_polish", None)

        def build_model(**kwargs):
            observed.update(kwargs)
            return sentinel

        config.build_model = build_model
        assert config._reporter_polish_model() is sentinel
    finally:
        config.build_model = original_build_model
        config._model_cache.clear()
        config._model_cache.update(original_cache)
        if original_value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = original_value

    assert observed["timeout"] == 600.0


def test_direct_report_assembly_skips_validation():
    """直接组装不进入严格校验或图谱持久化路径。"""
    from tools import report_tools

    originals = {
        "ensure": report_tools._ensure_candidate_chapters,
        "load": report_tools._load_committed_report,
        "best_effort": report_tools._best_effort_report,
        "compile": report_tools.compile_structured_report,
    }
    calls = []
    try:
        report_tools._ensure_candidate_chapters = lambda _output_dir: []
        report_tools._load_committed_report = lambda _output_dir: (
            "Report",
            [{"title": "Finding", "content": "Draft"}],
            [],
        )
        report_tools._best_effort_report = lambda title, sections: (
            calls.append((title, sections)) or ("# Report\n\n## Finding\n\nDraft", [])
        )
        report_tools.compile_structured_report = lambda *_args, **_kwargs: (
            _ for _ in ()
        ).throw(AssertionError("Strict validation must not be called"))

        result = report_tools.deliver_committed_report(None)
    finally:
        report_tools._ensure_candidate_chapters = originals["ensure"]
        report_tools._load_committed_report = originals["load"]
        report_tools._best_effort_report = originals["best_effort"]
        report_tools.compile_structured_report = originals["compile"]

    assert len(calls) == 1
    assert result["delivered"] and not result["validated"]
    assert not result["accepted"] and not result["graph_persisted"]
    assert result["review_status"] == "skipped"


def test_retry_exhaustion_uses_direct_delivery():
    """大纲重试耗尽后仍直接交付当前最佳报告。"""
    observations, restore = _install_fakes(
        [{}, {}, {}],
        delivery_results=[
            {
                "delivered": True,
                "validated": False,
                "revision_requested": False,
                "review_status": "skipped",
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
    assert observations["calls"] == ["deliver"]
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
        "prepare_chapters",
        "draft_chapter",
        "assemble_draft",
        "polish_report",
        "submit",
        "finalize_best_effort",
        "fail",
        "__end__",
    }


def test_report_quality_checks_survive_middleware_removal():
    """旧 Reporter middleware 中仍有效的修订检查由报告模块保留。"""
    from tools import report_tools

    original_search = report_tools.graph_tools.search_nodes

    def search_nodes(node_type, _filters):
        if node_type == "user_request":
            return [{"request": "Write a Wikipedia article"}]
        if node_type == "evidence":
            return []
        return []

    report_tools.graph_tools.search_nodes = search_nodes
    try:
        issues = report_tools.check_report_quality(
            "# Topic\n\n| Key |\n| --- |\n| Value |\n\n## Body"
        )
    finally:
        report_tools.graph_tools.search_nodes = original_search

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
    assert observed["config"]["max_concurrency"] == 3


def test_reporter_chapter_concurrency_config_requires_positive_integer():
    """并发配置接受正整数，并尽早拒绝无效值。"""
    name = "GR_REPORTER_CHAPTER_CONCURRENCY"
    original_value = os.environ.get(name)
    try:
        os.environ[name] = "5"
        assert workflow_module.config._positive_int_from_env(name, 3) == 5
        for invalid_value in ("0", "-1", "not-an-integer"):
            os.environ[name] = invalid_value
            try:
                workflow_module.config._positive_int_from_env(name, 3)
            except ValueError:
                pass
            else:
                raise AssertionError(f"Invalid concurrency was accepted: {invalid_value}")
    finally:
        if original_value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = original_value


if __name__ == "__main__":
    test_workflow_commits_ordered_report_without_model_tool_calls()
    test_outline_prompt_is_limited_to_outline_planning()
    test_workflow_retries_query_refs_outside_report_context()
    test_empty_query_context_skips_outline_model_and_uses_fallback()
    test_chapter_prompt_receives_full_outline_and_one_local_bundle()
    test_polish_prompt_receives_complete_draft_and_preserves_contract()
    test_outline_contract_requires_complete_chapters_and_first_lead()
    test_chapter_contract_accepts_exactly_one_chapter()
    test_workflow_retries_invalid_chapter_json_then_commits()
    test_workflow_writes_one_chapter_per_parallel_model_call()
    test_workflow_ignores_chapter_validation_and_skips_review()
    test_failed_chapter_does_not_block_parallel_siblings()
    test_exhausted_chapter_still_enters_polish()
    test_polish_timeout_delivers_assembled_draft()
    test_reporter_polish_timeout_defaults_to_600_seconds()
    test_direct_report_assembly_skips_validation()
    test_retry_exhaustion_uses_direct_delivery()
    test_unauthorized_workflow_fails_without_report_tools()
    test_workflow_contains_only_runtime_nodes()
    test_report_quality_checks_survive_middleware_removal()
    test_top_level_report_node_calls_deterministic_workflow()
    test_run_report_workflow_forwards_runnable_config()
    test_reporter_chapter_concurrency_config_requires_positive_integer()
    print("ALL REPORTER WORKFLOW CHECKS PASSED")  # noqa: T201
