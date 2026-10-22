"""合并关卡 B：登录墙/短页判定必须基于最长可用正文。

复现线上误杀：搜索后端 ``content`` 短摘要仅 ~120 字符，而抓取得到的
``raw_content`` 是数千字有效正文且 analyzer 已成功抽取；旧逻辑优先用
短摘要做 len<400 判定，整份来源连同证据被丢弃。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from agents import searcher  # noqa: E402


VALID_BODY = (
    "The finance ministry published its annual investment review. " * 120
)  # ~6.6k chars, no login-wall hints


def _valid_packet():
    return {
        "document": {"document_summary": "An official investment review with concrete figures."},
        "source": {"source_type": "official"},
        "statements": [
            {"local_ref": "st1", "text": "The fund increased its infrastructure allocation."},
        ],
        "evidence": [
            {"local_ref": "e1", "text": "Infrastructure rose to 38 percent of the portfolio.",
             "statement_refs": ["st1"]},
        ],
        "conflicts": [],
        "_location_log": [],
    }


def _merge(source):
    return searcher._merge_source_packets(
        {"results": [source]},
        [_valid_packet()],
    )


def test_long_raw_content_survives_short_snippet():
    package = _merge({
        "url": "https://example.gov/review",
        "title": "Annual investment review",
        "content": "Official review of the fund's annual allocation.",  # 58 chars
        "raw_content": VALID_BODY,
    })
    assert len(package["sources"]) == 1, package["extraction_log"]
    assert len(package["documents"]) == 1
    assert len(package["statements"]) == 1
    assert len(package["evidence"]) == 1
    assert package["extraction_log"][-1]["stage"] == "binding_ok"


def test_short_body_without_raw_content_still_rejected():
    package = _merge({
        "url": "https://example.com/stub",
        "title": "Stub",
        "content": "Just a stub.",
        "raw_content": "",
    })
    assert package["sources"] == []
    assert package["statements"] == []
    assert package["evidence"] == []
    assert package["extraction_log"][-1]["stage"] == "B_login_wall"


def test_long_body_with_mild_login_hint_survives():
    # 单个弱提示词 + 长正文不应被短页规则误杀（真正的登录墙由 analyzer
    # 关卡 C 处理）。
    package = _merge({
        "url": "https://example.org/article",
        "title": "Markets article",
        "content": "short snippet",
        "raw_content": "Subscribe for more. " + VALID_BODY,
    })
    assert len(package["sources"]) == 1, package["extraction_log"]
    assert len(package["evidence"]) == 1
