"""回归检查 Reporter 静态大纲与章节动态元数据的持久化边界。"""

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

repo_dir = Path(__file__).parent.parent
sys.path.insert(0, str(repo_dir / "src"))

from tools import graph_manager_tools, report_tools  # noqa: E402


def _commit_outline(
    output_dir: str,
    chapters: list[dict] | None = None,
) -> Path:
    original_resolver = report_tools.graph_tools.resolve_query_reference
    report_tools.graph_tools.resolve_query_reference = lambda ref: ref
    try:
        result = report_tools.commit_report_outline(
            output_dir,
            "Static Report",
            chapters
            or [
                {
                    "chapter_id": 1,
                    "title": "First Chapter",
                    "goals": ["Explain the first topic"],
                    "query_refs": ["q1"],
                    "section_plan": "Present the evidence.",
                    "section_type": "body",
                }
            ],
        )
    finally:
        report_tools.graph_tools.resolve_query_reference = original_resolver
    assert result["status"] == "ok", result
    return Path(output_dir, ".report_outline.json")


def test_report_loading_uses_outline_order_after_out_of_order_commits():
    """并发完成顺序不改变最终章节顺序。"""
    with TemporaryDirectory() as output_dir:
        _commit_outline(
            output_dir,
            [
                {
                    "chapter_id": chapter_id,
                    "title": title,
                    "goals": [f"Explain chapter {chapter_id}"],
                    "query_refs": ["q1"],
                    "section_plan": "Present the evidence.",
                    "section_type": "body",
                }
                for chapter_id, title in ((1, "First Chapter"), (2, "Second Chapter"))
            ],
        )
        chapter_dir = Path(output_dir, ".report_chapters")
        chapter_dir.mkdir()
        for chapter_id in (1, 2):
            chapter_dir.joinpath(f"chapter_{chapter_id:02d}.meta.json").write_text(
                json.dumps(
                    {
                        "chapter_id": chapter_id,
                        "bundle_token": f"b{chapter_id}",
                        "evidence_ref_map": {"e1": f"evidence-{chapter_id}"},
                        "conflict_ref_map": {},
                    }
                ),
                encoding="utf-8",
            )

        original_validation = report_tools._chapter_candidate_validation
        report_tools._chapter_candidate_validation = lambda _output_dir, chapter: {
            "validated": True,
            "issues": [],
            "evidence_ids": [f"evidence-{chapter['chapter_id']}"],
            "source_ids": [f"source-{chapter['chapter_id']}"],
            "disclosed_conflict_ids": [],
            "unknown_evidence_refs": [],
            "unknown_conflict_refs": [],
        }
        try:
            committed = report_tools.commit_report_chapter_batch(
                output_dir,
                [
                    {
                        "chapter_id": chapter_id,
                        "bundle_token": f"b{chapter_id}",
                        "content": f"Chapter {chapter_id} content.[{chapter_id}]",
                        "evidence_refs": ["e1"],
                    }
                    for chapter_id in (2, 1)
                ],
            )
        finally:
            report_tools._chapter_candidate_validation = original_validation

        assert committed["status"] == "ok", committed
        _, sections, missing = report_tools._load_committed_report(output_dir)
        assert not missing
        assert [section["title"] for section in sections] == [
            "First Chapter",
            "Second Chapter",
        ]
        assert [section["content"] for section in sections] == [
            "Chapter 1 content.[1]",
            "Chapter 2 content.[2]",
        ]


def test_chapter_commit_keeps_outline_static_and_loads_meta():
    """章节提交只更新本章产物，报告加载从 meta 取得动态字段。"""
    with TemporaryDirectory() as output_dir:
        outline_path = _commit_outline(output_dir)
        original_outline = outline_path.read_text(encoding="utf-8")
        stored_chapter = json.loads(original_outline)["chapters"][0]
        assert "status" not in stored_chapter

        meta_path = Path(
            output_dir,
            ".report_chapters",
            "chapter_01.meta.json",
        )
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(
            json.dumps(
                {
                    "chapter_id": 1,
                    "bundle_token": "b1-test",
                    "evidence_ref_map": {"e1": "evidence-1"},
                    "conflict_ref_map": {},
                }
            ),
            encoding="utf-8",
        )

        original_validation = report_tools._chapter_candidate_validation
        report_tools._chapter_candidate_validation = lambda *_args: {
            "validated": True,
            "issues": [],
            "evidence_ids": ["evidence-1"],
            "source_ids": ["source-1"],
            "disclosed_conflict_ids": [],
            "unknown_evidence_refs": [],
            "unknown_conflict_refs": [],
        }
        try:
            committed = report_tools.commit_report_chapter_batch(
                output_dir,
                [
                    {
                        "chapter_id": 1,
                        "bundle_token": "b1-test",
                        "content": "Supported content.[1]",
                        "evidence_refs": ["e1"],
                    }
                ],
            )
        finally:
            report_tools._chapter_candidate_validation = original_validation

        assert committed["validated"] is True, committed
        assert outline_path.read_text(encoding="utf-8") == original_outline

        title, sections, missing = report_tools._load_committed_report(output_dir)
        assert title == "Static Report" and not missing
        assert sections == [
            {
                "chapter_id": 1,
                "title": "First Chapter",
                "content": "Supported content.[1]",
                "evidence_ref_map": {"e1": "evidence-1"},
                "source_ids": ["source-1"],
                "evidence_ids": ["evidence-1"],
                "disclosed_conflict_ids": [],
                "section_type": "body",
                "validated": True,
                "validation_issues": [],
            }
        ]

        original_compile = report_tools.compile_structured_report
        original_best_effort = report_tools._best_effort_report
        report_tools.compile_structured_report = lambda *_args, **_kwargs: {
            "report": "# Static Report\n\nSupported content.[1]",
            "issues": [],
        }
        report_tools._best_effort_report = lambda *_args: (
            "# Static Report\n\nSupported content.[1]",
            [],
        )
        try:
            submitted = report_tools.submit_committed_report(output_dir)
        finally:
            report_tools.compile_structured_report = original_compile
            report_tools._best_effort_report = original_best_effort

        assert submitted["validated"] is True, submitted
        assert submitted["issues"] == []


def test_fallback_chapter_keeps_outline_static():
    """确定性缺章补齐只写对应章节正文和 meta。"""
    with TemporaryDirectory() as output_dir:
        outline_path = _commit_outline(output_dir)
        original_outline = outline_path.read_text(encoding="utf-8")
        original_prepare = report_tools._prepare_report_chapter_bundle
        report_tools._prepare_report_chapter_bundle = lambda *_args: {
            "status": "ok",
            "chapter_id": 1,
            "evidence_items": [
                {
                    "id": "evidence-1",
                    "text": "Fallback evidence",
                    "source_numbers": [1],
                }
            ],
        }
        try:
            issues = report_tools._ensure_candidate_chapters(output_dir)
        finally:
            report_tools._prepare_report_chapter_bundle = original_prepare

        assert len(issues) == 1
        assert outline_path.read_text(encoding="utf-8") == original_outline
        assert (
            Path(
                output_dir,
                ".report_chapters",
                "chapter_01.md",
            ).read_text(encoding="utf-8")
            == "Fallback evidence.[1]\n"
        )
        meta = json.loads(
            Path(
                output_dir,
                ".report_chapters",
                "chapter_01.meta.json",
            ).read_text(encoding="utf-8")
        )
        assert meta["validated"] is False
        assert meta["validation_issues"] == issues


def test_legacy_outline_dynamic_fields_remain_readable():
    """没有 chapter meta 的旧产物继续从 outline 读取动态字段。"""
    with TemporaryDirectory() as output_dir:
        root = Path(output_dir)
        root.joinpath(".report_outline.json").write_text(
            json.dumps(
                {
                    "title": "Legacy Report",
                    "chapters": [
                        {
                            "chapter_id": 1,
                            "title": "Legacy Chapter",
                            "section_type": "body",
                            "validated": True,
                            "source_ids": ["legacy-source"],
                            "evidence_ids": ["legacy-evidence"],
                            "disclosed_conflict_ids": ["legacy-conflict"],
                            "validation_issues": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        chapter_dir = root / ".report_chapters"
        chapter_dir.mkdir()
        chapter_dir.joinpath("chapter_01.md").write_text(
            "Legacy content.[1]\n",
            encoding="utf-8",
        )

        title, sections, missing = report_tools._load_committed_report(output_dir)

        assert title == "Legacy Report" and not missing
        assert sections[0]["validated"] is True
        assert sections[0]["source_ids"] == ["legacy-source"]
        assert sections[0]["evidence_ids"] == ["legacy-evidence"]
        assert sections[0]["disclosed_conflict_ids"] == ["legacy-conflict"]


def test_polished_report_uses_existing_compiled_artifact_path():
    """润色结果继续通过现有最终报告缓存与文件路径交付。"""
    with TemporaryDirectory() as output_dir:
        original_state = {
            "cache_dir": graph_manager_tools._cache_dir,
            "compiled_report": graph_manager_tools._compiled_report,
            "salvaged_report": graph_manager_tools._salvaged_report,
            "best_report": graph_manager_tools._best_report,
            "last_report_attempt": graph_manager_tools._last_report_attempt,
            "report_submit_count": graph_manager_tools._report_submit_count,
        }
        graph_manager_tools._cache_dir = output_dir
        graph_manager_tools._compiled_report = ""
        graph_manager_tools._salvaged_report = ""
        graph_manager_tools._best_report = ""
        graph_manager_tools._last_report_attempt = {}
        graph_manager_tools._report_submit_count = 0
        try:
            result = graph_manager_tools.deliver_polished_report(
                "# Polished Report\n\nFinal prose.[1]",
                issues=[{"severity": "hard", "message": "fallback chapter"}],
            )

            expected = "# Polished Report\n\nFinal prose.[1]\n"
            assert result["delivered"] and not result["validated"]
            assert result["severity"] == "hard"
            assert graph_manager_tools.get_compiled_report() == expected
            assert (
                Path(output_dir, ".compiled_report.md").read_text(encoding="utf-8")
                == expected
            )
            assert graph_manager_tools.get_report_submit_count() == 1
        finally:
            graph_manager_tools._cache_dir = original_state["cache_dir"]
            graph_manager_tools._compiled_report = original_state["compiled_report"]
            graph_manager_tools._salvaged_report = original_state["salvaged_report"]
            graph_manager_tools._best_report = original_state["best_report"]
            graph_manager_tools._last_report_attempt = original_state[
                "last_report_attempt"
            ]
            graph_manager_tools._report_submit_count = original_state[
                "report_submit_count"
            ]


if __name__ == "__main__":
    test_report_loading_uses_outline_order_after_out_of_order_commits()
    test_chapter_commit_keeps_outline_static_and_loads_meta()
    test_fallback_chapter_keeps_outline_static()
    test_legacy_outline_dynamic_fields_remain_readable()
    test_polished_report_uses_existing_compiled_artifact_path()
    print("ALL REPORTER ARTIFACT PERSISTENCE CHECKS PASSED")  # noqa: T201
