"""硬屏蔽来源（B3.3）：入图前整源剔除 + 引用注册表排除。

直接运行：``.venv\\Scripts\\python.exe tests/test_blocked_sources.py``。
"""

import sys
from pathlib import Path
from unittest.mock import patch

src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

import config  # noqa: E402
from agents.memory_manager import (  # noqa: E402
    MemoryManager,
    _source_matches_blocklist,
)
from tools import graph_tools, report_tools  # noqa: E402


def test_url_and_title_matching():
    urls = ["https://seed.example.com/paper.html", "blocked.org/dataset"]
    titles = ["Forbidden Compendium 2024"]
    assert _source_matches_blocklist(
        "https://seed.example.com/paper.html#footnote-1", None, urls, []
    )
    assert _source_matches_blocklist(
        "https://SEED.example.com/paper.html/", None, urls, []
    )
    # URL 片段命中（协议/尾斜杠归一化后包含匹配）
    assert _source_matches_blocklist("https://www.blocked.org/dataset?v=2", None, urls, [])
    # 标题忽略大小写的子串匹配
    assert _source_matches_blocklist(
        "https://news.example.com/a", "the forbidden compendium 2024 edition", [], titles
    )
    # 干净来源不命中
    assert not _source_matches_blocklist(
        "https://other.example.org/article", "Clean Analysis", urls, titles
    )
    assert not _source_matches_blocklist(None, None, urls, titles)


def _sample_package():
    return {
        "sources": [
            {"local_ref": "s-good", "url": "https://good.example.com/a", "title": "Good"},
            {"local_ref": "s-bad", "url": "https://seed.example.com/paper.html", "title": "Seed"},
        ],
        "documents": [
            {"local_ref": "d-good", "source_ref": "s-good", "document_summary": "good doc"},
            {"local_ref": "d-bad", "source_ref": "s-bad", "document_summary": "blocked doc"},
        ],
        "statements": [
            {"local_ref": "st-good", "source_ref": "s-good", "document_ref": "d-good",
             "statement": "clean fact"},
            {"local_ref": "st-bad", "source_ref": "s-bad", "document_ref": "d-bad",
             "statement": "seed fact"},
        ],
        "evidence": [
            {"local_ref": "ev-good", "source_ref": "s-good", "document_ref": "d-good",
             "statement_refs": ["st-good"], "evidence_text": "clean evidence"},
            {"local_ref": "ev-bad", "source_ref": "s-bad", "document_ref": "d-bad",
             "statement_refs": ["st-bad"], "evidence_text": "blocked evidence"},
            {"local_ref": "ev-cross", "source_ref": "s-good", "document_ref": "d-good",
             "statement_refs": ["st-good", "st-bad"], "evidence_text": "cross evidence"},
        ],
        "claims": [
            {"canonical_text": "clean claim", "source_ref": "s-good", "document_ref": "d-good",
             "statement_refs": ["st-good"],
             "evidence_refs": ["ev-good"]},
            {"canonical_text": "cross claim", "source_ref": "s-good", "document_ref": "d-good",
             "statement_refs": ["st-good"],
             "evidence_refs": [{"id": "ev-bad", "stance": "supports"}]},
        ],
        "conflicts": [
            {"description": "bad-only conflict", "evidence_refs": ["ev-bad"]},
            {"description": "good conflict", "evidence_refs": ["ev-good"]},
        ],
    }


def test_filter_blocked_sources_cascades_whole_chain():
    package = _sample_package()
    filtered, hits = MemoryManager._filter_blocked_sources(
        package, ["https://seed.example.com/paper.html"], []
    )
    assert hits == ["https://seed.example.com/paper.html"], hits
    assert [s["local_ref"] for s in filtered["sources"]] == ["s-good"]
    assert [d["local_ref"] for d in filtered["documents"]] == ["d-good"]
    assert [s["local_ref"] for s in filtered["statements"]] == ["st-good"]
    # 直接挂在 blocked 链上的证据与跨链引用 blocked 陈述的证据都剔除
    assert [e["local_ref"] for e in filtered["evidence"]] == ["ev-good"]
    # cross claim 保留但被清洗掉指向已删证据的 provenance
    cross = next(c for c in filtered["claims"] if c["canonical_text"] == "cross claim")
    assert cross["evidence_refs"] == [], cross
    assert [c["description"] for c in filtered["conflicts"]] == ["good conflict"]
    # 原 package 不被原地修改
    assert len(package["sources"]) == 2
    # 过滤后的包引用仍然自洽（不返回校验错误）
    refs_error = MemoryManager(model=object())._validate_evidence_package_refs(filtered)
    assert refs_error is None, refs_error


def test_filter_blocked_sources_noop_without_blocklist():
    package = _sample_package()
    filtered, hits = MemoryManager._filter_blocked_sources(package, [], [])
    assert filtered is package and hits == []


def test_reference_registry_excludes_blocked_sources():
    nodes = {
        "s1": {"id": "s1", "type": "Source", "url": "https://good.example.com/a",
               "title": "Good"},
        "s2": {"id": "s2", "type": "Source", "url": "https://seed.example.com/paper.html",
               "title": "Seed", "blocked": True},
        "st1": {"id": "st1", "type": "Statement"},
        "st2": {"id": "st2", "type": "Statement"},
    }
    edges = [
        {"source": "s1", "target": "st1", "type": "SUPPORTED_BY"},
        {"source": "s2", "target": "st2", "type": "SUPPORTED_BY"},
    ]

    def search_nodes(kind, _filters=None):
        wanted = kind.lower()
        return [dict(n) for n in nodes.values() if str(n.get("type", "")).lower() == wanted]

    def get_node(node_id):
        return dict(nodes.get(node_id, {}))

    def get_node_edges(node_id, direction="both"):
        return [dict(e) for e in edges if e["target"] == node_id]

    with patch.multiple(
        graph_tools,
        search_nodes=search_nodes,
        get_node=get_node,
        get_node_edges=get_node_edges,
    ):
        registry = report_tools.build_reference_registry()
    assert [item["source_id"] for item in registry] == ["s1"], registry
    assert registry[0]["url"] == "https://good.example.com/a"


def test_csv_env_parsing():
    original = config.os.environ.get("GR_BLOCKED_URLS")
    try:
        config.os.environ["GR_BLOCKED_URLS"] = (
            "https://a.example.com/1, https://b.example.com/2\nhttps://c.example.com/3"
            ",https://a.example.com/1"
        )
        values = config._csv_env("GR_BLOCKED_URLS")
        assert values == [
            "https://a.example.com/1",
            "https://b.example.com/2",
            "https://c.example.com/3",
        ], values
        assert config._csv_env("GR_BLOCKED_URLS_DEFINITELY_UNSET") == []
    finally:
        if original is None:
            config.os.environ.pop("GR_BLOCKED_URLS", None)
        else:
            config.os.environ["GR_BLOCKED_URLS"] = original


def main():
    test_url_and_title_matching()
    test_filter_blocked_sources_cascades_whole_chain()
    test_filter_blocked_sources_noop_without_blocklist()
    test_reference_registry_excludes_blocked_sources()
    test_csv_env_parsing()
    print("ALL BLOCKED-SOURCE CHECKS PASSED")


if __name__ == "__main__":
    main()
