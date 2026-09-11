"""证据封顶排序的回归检查：点名数据点优先、数字密度加权、预算有界."""

import sys
from pathlib import Path

repo_dir = Path(__file__).parent.parent
sys.path.insert(0, str(repo_dir / "src"))

import config  # noqa: E402
from tools import report_tools  # noqa: E402


def _item(item_id: str, text: str, *, source_ids=None) -> dict:
    return {
        "id": item_id,
        "ref": item_id,
        "type": "Evidence",
        "text": text,
        "source_ids": source_ids or ["s1"],
    }


def _patched_budget(monkeypatch_tokens: dict[str, int]):
    """临时替换预算常量的上下文管理器（模块属性直接覆写）."""

    class _Patch:
        def __enter__(self):
            self.originals = {
                name: getattr(config, name) for name in monkeypatch_tokens
            }
            for name, value in monkeypatch_tokens.items():
                setattr(config, name, value)
            return self

        def __exit__(self, *exc):
            for name, value in self.originals.items():
                setattr(config, name, value)

    return _Patch()


def test_named_data_point_evidence_survives_despite_low_overlap():
    """goal 点名的精确数字即使词面重合度低，也必须排在高重叠泛化证据之前."""
    chapter = {
        "chapter_id": 1,
        "title": "土地财政",
        "goals": ["说明 2021 年土地出让收入占地方财政比重 27.65%"],
    }
    # e_generic 与 goal 词面高度重合但无数字；e_number 只含精确数字，句子完全改写。
    e_generic = _item(
        "e_generic",
        "土地出让 收入 地方 财政 比重 土地出让 收入 地方 财政 比重 "
        "土地出让 收入 地方 财政 比重",
    )
    e_number = _item("e_number", "The observed ratio stood at 27.65% that year.")

    # 小预算触发截断；点名数字证据必须留下，即使它更短且无词面重合。
    with _patched_budget({
        "REPORTER_CONTEXT_TOKENS": 4_000,
        "REPORTER_OUTPUT_TOKENS": 1_024,
        "REPORTER_SAFETY_TOKENS": 256,
    }):
        kept = report_tools._cap_evidence_by_budget(
            [
                e_generic,
                e_number,
                *[
                    _item(f"e_filler_{i}", "土地出让 收入 地方 财政 比重 的泛化讨论")
                    for i in range(40)
                ],
            ],
            chapter,
        )
    kept_ids = {item["id"] for item in kept}
    assert "e_number" in kept_ids


def test_cap_respects_token_budget():
    """放大的预算下封顶结果仍严格不超过 60% 输入上限."""
    chapter = {"chapter_id": 1, "goals": ["讨论低代码平台的成本与采用情况"]}
    items = [
        _item(f"e{i}", "低代码平台成本采用效率讨论 " * 40)
        for i in range(200)
    ]
    with _patched_budget({
        "REPORTER_CONTEXT_TOKENS": 131_072,
        "REPORTER_OUTPUT_TOKENS": 16_384,
        "REPORTER_SAFETY_TOKENS": 1_024,
    }):
        kept = report_tools._cap_evidence_by_budget(items, chapter)
        budget = int((131_072 - 16_384 - 1_024) * 0.6)
        total = sum(
            report_tools._estimate_tokens(str(item["text"])) + 80
            for item in kept
        )
    assert len(kept) < len(items)
    assert total <= budget


def test_number_cores_normalization():
    """千分位与小数格式归一，同一数据点可跨文本匹配."""
    assert report_tools._number_cores("增长 27.65%，规模 87,051 亿元") == {
        "27.65", "87051",
    }
    assert report_tools._numeric_density("2020 年 12.5% 约 100 万人") == 3


if __name__ == "__main__":
    test_named_data_point_evidence_survives_despite_low_overlap()
    test_cap_respects_token_budget()
    test_number_cores_normalization()
    print("ALL EVIDENCE BUDGET CHECKS PASSED")  # noqa: T201
