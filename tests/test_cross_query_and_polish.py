"""B4 回归：跨章证据共享与润色稿验收闸。"""

import sys
from pathlib import Path

repo_dir = Path(__file__).parent.parent
sys.path.insert(0, str(repo_dir / "src"))

import config  # noqa: E402
from tools import report_tools  # noqa: E402


# ---------------------------------------------------------------------------
# 跨章证据补充
# ---------------------------------------------------------------------------

def _registry():
    return [
        {"source_id": "s1", "n": 1, "title": "Source One", "url": "https://example.com/1"},
        {"source_id": "s2", "n": 2, "title": "Source Two", "url": "https://example.com/2"},
    ]


def _evidence_node(node_id: str, text: str, source_id: str) -> dict:
    return {"id": node_id, "type": "Evidence", "text": text, "source_id": source_id}


def _install_graph(monkeypatch, nodes, edges):
    monkeypatch.setattr(
        report_tools.graph_tools, "get_all_nodes", lambda: list(nodes.values())
    )
    monkeypatch.setattr(report_tools.graph_tools, "get_all_edges", lambda: edges)
    monkeypatch.setattr(report_tools, "build_reference_registry", _registry)


def test_cross_query_supplements_on_goal_evidence_from_sibling_query(monkeypatch):
    """绑定 query 外的强相关证据应补入章证据包，且不挤占绑定证据。"""
    chapter = {"chapter_id": 2, "goals": ["界定低代码与无代码的定义和连续光谱定位"]}
    bound = [{
        "id": "e-bound", "type": "Evidence",
        "text": "低代码使用可视化建模环境并允许少量自定义代码。",
        "source_ids": ["s1"], "citations": [1],
    }]
    nodes = {
        "e-bound": _evidence_node("e-bound", bound[0]["text"], "s1"),
        "e-cross": _evidence_node(
            "e-cross",
            "分析机构将低代码、无代码与传统编码放在同一连续光谱上定位，"
            "并讨论公民开发者的定义与分类框架。",
            "s2",
        ),
        "e-irrelevant": _evidence_node(
            "e-irrelevant", "某厂商发布会上的客户成功故事与促销信息。", "s2"
        ),
        "s1": {"id": "s1", "type": "Source", "url": "https://example.com/1"},
        "s2": {"id": "s2", "type": "Source", "url": "https://example.com/2"},
    }
    edges = [
        {"source": "s1", "target": "e-bound", "type": "SUPPORTED_BY"},
        {"source": "s2", "target": "e-cross", "type": "SUPPORTED_BY"},
        {"source": "s2", "target": "e-irrelevant", "type": "SUPPORTED_BY"},
    ]
    _install_graph(monkeypatch, nodes, edges)

    result = report_tools._supplement_cross_query_evidence(bound, chapter)
    ids = {item["id"] for item in result}
    assert "e-bound" in ids
    assert "e-cross" in ids
    assert "e-irrelevant" not in ids


def test_cross_query_disabled_returns_bound_only(monkeypatch):
    chapter = {"chapter_id": 2, "goals": ["界定低代码与无代码的定义和连续光谱定位"]}
    bound = [{
        "id": "e-bound", "type": "Evidence",
        "text": "低代码使用可视化建模环境。", "source_ids": ["s1"],
    }]
    _install_graph(monkeypatch, {}, [])
    original = config.REPORTER_CROSS_QUERY_EVIDENCE
    try:
        config.REPORTER_CROSS_QUERY_EVIDENCE = False
        result = report_tools._supplement_cross_query_evidence(bound, chapter)
    finally:
        config.REPORTER_CROSS_QUERY_EVIDENCE = original
    assert [item["id"] for item in result] == ["e-bound"]


def test_cross_query_respects_item_cap_and_budget(monkeypatch):
    chapter = {"chapter_id": 1, "goals": ["低代码平台的定义、分类、光谱、公民开发"]}
    bound = [{
        "id": "e-bound", "type": "Evidence",
        "text": "低代码定义简述。", "source_ids": ["s1"],
    }]
    nodes = {f"e{i}": _evidence_node(
        f"e{i}",
        "低代码与无代码的定义分类连续光谱与公民开发定位讨论 " * 6,
        "s2",
    ) for i in range(20)}
    nodes["e-bound"] = _evidence_node("e-bound", bound[0]["text"], "s1")
    nodes["s1"] = {"id": "s1", "type": "Source", "url": "https://example.com/1"}
    nodes["s2"] = {"id": "s2", "type": "Source", "url": "https://example.com/2"}
    edges = [{"source": "s1", "target": "e-bound", "type": "SUPPORTED_BY"}]
    edges += [
        {"source": "s2", "target": f"e{i}", "type": "SUPPORTED_BY"} for i in range(20)
    ]
    _install_graph(monkeypatch, nodes, edges)
    original_cap = config.REPORTER_CROSS_QUERY_MAX_ITEMS
    try:
        config.REPORTER_CROSS_QUERY_MAX_ITEMS = 5
        result = report_tools._supplement_cross_query_evidence(bound, chapter)
        added = [item for item in result if item["id"] != "e-bound"]
        assert len(added) <= 5
        assert len(result) <= 6
    finally:
        config.REPORTER_CROSS_QUERY_MAX_ITEMS = original_cap


# ---------------------------------------------------------------------------
# 润色稿验收闸
# ---------------------------------------------------------------------------

_COMPILED = """# 低代码与无代码平台分析

## 定义

低代码与无代码是两种不同抽象层级的开发方式。[1]它们位于传统编码与纯配置之间。[2]

## 比较

| 维度 | 低代码 | 无代码 |
|---|---|---|
| 定制 | 可写代码[1] | 纯配置[2] |

## 参考文献

[1] Source One https://example.com/1
[2] Source Two https://example.com/2
"""


def test_polish_gate_accepts_style_only_edit():
    polished = """# 低代码与无代码平台分析

## 定义

低代码与无代码代表两种抽象层级。[1]

二者处在传统编码与纯配置之间。[2]

## 比较

| 维度 | 低代码 | 无代码 |
|---|---|---|
| 定制 | 可写代码[1] | 纯配置[2] |

## 参考文献

[1] Source One https://example.com/1
[2] Source Two https://example.com/2
"""
    ok, reasons = report_tools.evaluate_polished_report(polished, _COMPILED)
    assert ok, reasons


def test_polish_gate_rejects_dropped_reference():
    polished = _COMPILED.replace(
        "[2] Source Two https://example.com/2\n", ""
    ).replace("[2]", "[1]")
    ok, reasons = report_tools.evaluate_polished_report(polished, _COMPILED)
    assert not ok
    assert any("reference list altered" in r for r in reasons)


def test_polish_gate_rejects_invented_citation():
    polished = _COMPILED.replace(
        "可写代码[1]", "可写代码[1][9]"
    )
    ok, reasons = report_tools.evaluate_polished_report(polished, _COMPILED)
    assert not ok
    assert any("absent from draft" in r for r in reasons)


def test_polish_gate_rejects_dropped_table_row():
    polished = _COMPILED.replace("| 定制 | 可写代码[1] | 纯配置[2] |\n", "")
    ok, reasons = report_tools.evaluate_polished_report(polished, _COMPILED)
    assert not ok
    assert any("table row count changed" in r for r in reasons)


def test_polish_gate_rejects_severe_shrink():
    polished = """# 低代码与无代码平台分析

## 定义

低代码是一种开发方式。[1]

## 参考文献

[1] Source One https://example.com/1
[2] Source Two https://example.com/2
"""
    ok, reasons = report_tools.evaluate_polished_report(polished, _COMPILED)
    assert not ok
    assert any("shrunk below" in r for r in reasons)


def test_reference_entries_tolerate_embedded_whitespace():
    """URL 中的杂散空白（? id= / ?hl= zh-CN）归一后仍能被识别。"""
    entries = report_tools._reference_entries(
        "[14] ACM Queue https://queue.acm.org/detail.cfm? id=3631183\n"
        "[24] Google Cloud https://cloud.google.com/discover/low-code? hl=zh-CN"
    )
    assert entries == {
        14: "https://queue.acm.org/detail.cfm?id=3631183",
        24: "https://cloud.google.com/discover/low-code?hl=zh-CN",
    }


def test_polish_gate_accepts_same_url_with_whitespace_variant():
    """草稿与润色稿仅在 URL 空白形态上不同，归一后参考文献应判为一致。"""
    polished = _COMPILED.replace(
        "[1] Source One https://example.com/1",
        "[1] Source One https://example.com/ ?id=1",
    )
    compiled = _COMPILED.replace(
        "[1] Source One https://example.com/1",
        "[1] Source One https://example.com/?id=1",
    )
    ok, reasons = report_tools.evaluate_polished_report(polished, compiled)
    assert ok, reasons


def test_compile_drops_dangling_reference_when_meta_sentence_sanitized():
    """清洗掉承载某引用的唯一句子后，参考文献不得保留悬空条目或编号空洞。"""
    registry = [
        {"source_id": "s1", "n": 1, "title": "Source One", "url": "https://example.com/1"},
        {"source_id": "s2", "n": 2, "title": "Source Two", "url": "https://example.com/2"},
    ]
    sections = [{
        "title": "概述",
        "section_type": "body",
        "content": (
            "这是有证据支持的客观事实判断[1]。 "
            "下面这句是过程性元叙述，按规则应当在清洗时删除：研究图谱[2]显示该来源仅供内部参考。"
        ),
    }]
    out = report_tools._compile_section_report(
        "测试报告", sections, registry, {"s1", "s2"}
    )
    assert "[1]" in out
    assert "[2]" not in out
    assert "example.com/2" not in out
    # 保留的唯一引用必须连续编号为 [1]，参考文献只有一条。
    assert out.count("## 参考文献") == 1


def test_compile_declared_but_unused_source_has_no_dangling_reference():
    """章节声明了来源但正文从未引用时，参考文献不得渲染该来源。"""
    registry = [
        {"source_id": "s1", "n": 1, "title": "Source One", "url": "https://example.com/1"},
        {"source_id": "s2", "n": 2, "title": "Source Two", "url": "https://example.com/2"},
        {"source_id": "s3", "n": 3, "title": "Source Three", "url": "https://example.com/3"},
    ]
    sections = [{
        "title": "概述",
        "section_type": "body",
        # s2/s3 在章节声明集合内（cited_source_ids），但正文只引用了 [1]。
        "content": "这是有证据支持的客观事实判断[1]。",
    }]
    out = report_tools._compile_section_report(
        "测试报告", sections, registry, {"s1", "s2", "s3"}
    )
    assert "[1]" in out
    assert "[2]" not in out and "[3]" not in out
    assert "example.com/2" not in out and "example.com/3" not in out
    body, _, refs_section = out.partition("## 参考文献")
    assert refs_section.count("https://") == 1


def test_prune_dangling_references_removes_entry_and_renumbers():
    report = (
        "# T\n\n事实甲[1]。事实乙[3]。\n\n"
        "## 参考文献\n\n"
        "[1] A https://a.example/\n\n"
        "[2] B https://b.example/\n\n"
        "[3] C https://c.example/\n"
    )
    out = report_tools.prune_dangling_references(report)
    assert "b.example" not in out
    assert "[2] C" in out
    assert "事实乙[2]" in out
    # [1] 保持不变。
    assert "事实甲[1]" in out
    assert out.count("https://") == 2


def test_prune_dangling_references_passthrough_when_canonical():
    report = (
        "# T\n\n事实甲[1]。事实乙[2]。\n\n"
        "## 参考文献\n\n[1] A https://a.example/\n\n[2] B https://b.example/\n"
    )
    assert report_tools.prune_dangling_references(report) == report


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
