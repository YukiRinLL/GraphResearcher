"""B4：章级引用作用域——bundle 内漏报为 soft，bundle 外为 hard，组装时剥离。"""

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

repo_dir = Path(__file__).parent.parent
sys.path.insert(0, str(repo_dir / "src"))

from tools import graph_tools, report_tools  # noqa: E402


S1 = "s1"
S2 = "s2"
S3 = "s3"
E1 = "e1-node"
E2 = "e2-node"
E3 = "e3-node"

REGISTRY = [
    {"source_id": S1, "n": 1, "title": "One", "url": "https://example.com/1"},
    {"source_id": S2, "n": 2, "title": "Two", "url": "https://example.com/2"},
    {"source_id": S3, "n": 3, "title": "Three", "url": "https://example.com/3"},
]

NODES = {
    S1: {"id": S1, "type": "Source", "url": "https://example.com/1"},
    S2: {"id": S2, "type": "Source", "url": "https://example.com/2"},
    S3: {"id": S3, "type": "Source", "url": "https://example.com/3"},
    E1: {"id": E1, "type": "Evidence", "text": "第一条材料。"},
    E2: {"id": E2, "type": "Evidence", "text": "第二条材料。"},
    E3: {"id": E3, "type": "Evidence", "text": "第三章才有的材料。"},
}

EDGES = [
    {"source": S1, "target": E1, "type": "SUPPORTED_BY"},
    {"source": S2, "target": E2, "type": "SUPPORTED_BY"},
    {"source": S3, "target": E3, "type": "SUPPORTED_BY"},
]


@pytest.fixture
def patched_graph(monkeypatch):
    monkeypatch.setattr(graph_tools, "get_all_nodes", lambda: list(NODES.values()))
    monkeypatch.setattr(graph_tools, "get_all_edges", lambda: list(EDGES))
    monkeypatch.setattr(
        graph_tools,
        "search_nodes",
        lambda kind, _filters=None: [{"id": "req", "type": "UserRequest", "request": "分析低代码平台"}],
    )
    monkeypatch.setattr(report_tools, "build_reference_registry", lambda: REGISTRY)


def _chapter_dir(tmp: str, bundle_refs: dict[str, str]) -> Path:
    root = Path(tmp) / ".report_chapters"
    root.mkdir(parents=True, exist_ok=True)
    meta = {
        "chapter_id": 1,
        "bundle_token": "tok-1",
        "evidence_ref_map": bundle_refs,
        "conflict_ref_map": {},
    }
    (root / "chapter_01.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8"
    )
    return root


def _validate(tmp: str, content: str, refs: list[str]) -> dict:
    return report_tools._chapter_candidate_validation(
        tmp,
        {
            "chapter_id": 1,
            "bundle_token": "tok-1",
            "content": content,
            "evidence_refs": refs,
            "disclosed_conflict_refs": [],
        },
    )


def test_bundle_backed_but_undeclared_citation_is_soft(patched_graph, tmp_path):
    _chapter_dir(str(tmp_path), {"e1": E1, "e2": E2})
    result = _validate(str(tmp_path), "正文中的论断。[2]", ["e1"])
    codes = {issue["code"]: issue["severity"] for issue in result["issues"]}
    assert codes.get("undeclared_bundle_citations") == "soft"
    assert "unsupported_inline_citations" not in codes
    assert result["validated"] is True


def test_citation_absent_from_bundle_is_hard(patched_graph, tmp_path):
    _chapter_dir(str(tmp_path), {"e1": E1, "e2": E2})
    result = _validate(str(tmp_path), "正文中的论断。[3]", ["e1"])
    codes = {issue["code"]: issue["severity"] for issue in result["issues"]}
    assert codes.get("unsupported_inline_citations") == "hard"
    assert result["validated"] is False


def test_declared_citation_is_clean(patched_graph, tmp_path):
    _chapter_dir(str(tmp_path), {"e1": E1, "e2": E2})
    result = _validate(str(tmp_path), "正文中的论断。[1]", ["e1"])
    assert result["issues"] == []
    assert result["validated"] is True


def test_assembly_strips_citations_absent_from_bundle(patched_graph, tmp_path):
    root = _chapter_dir(str(tmp_path), {"e1": E1, "e2": E2})
    (root / "chapter_01.md").write_text(
        "本章论断一。[1] 越界论断。[3] 另一条。[2]\n", encoding="utf-8"
    )
    (Path(tmp_path) / ".report_outline.json").write_text(json.dumps({
        "title": "测试报告",
        "chapters": [{
            "chapter_id": 1, "title": "第一章", "section_type": "lead",
            "query_refs": ["q1"],
        }],
    }, ensure_ascii=False), encoding="utf-8")

    result = report_tools.assemble_committed_report(str(tmp_path))
    report = result["report"]
    assert "[3]" not in report
    assert "[1]" in report and "[2]" in report
    codes = {issue["code"] for issue in result["issues"]}
    assert "unsupported_inline_citations_removed" in codes


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
