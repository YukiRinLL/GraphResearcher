"""二期：LLM 失败熔断、指纹缓存落盘、portfolio 草稿落图/消费的离线测试。"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from agents import memory_manager  # noqa: E402
from agents.memory_manager import (  # noqa: E402
    LLMResponseCircuitOpenError,
    MemoryManager,
)
from tools import graph_tools  # noqa: E402


class FlakyModel:
    """前 ``fail_times`` 次调用抛错，之后返回固定 JSON。"""

    def __init__(self, fail_times=2, payload=None):
        self.fail_times = fail_times
        self.calls = 0
        self.payload = payload or {"ok": True}

    def invoke(self, prompt):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("provider unavailable")
        return SimpleNamespace(content=json.dumps(self.payload))


def test_circuit_opens_after_threshold_and_recovers(monkeypatch):
    monkeypatch.setattr(memory_manager, "_LLM_CIRCUIT_FAILURE_THRESHOLD", 2)
    monkeypatch.setattr(memory_manager, "_LLM_CIRCUIT_COOLDOWN_SECONDS", 600)
    model = FlakyModel()
    manager = MemoryManager(model=model)

    for _ in range(2):
        try:
            manager._invoke_json("same prompt", purpose="query_assessor")
        except RuntimeError:
            pass
        else:  # pragma: no cover - 前两次必须失败
            raise AssertionError("expected provider failure")

    # 熔断窗口内：立即快速失败，不再触达模型。
    try:
        manager._invoke_json("same prompt", purpose="query_assessor")
    except LLMResponseCircuitOpenError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected circuit-open error")
    assert model.calls == 2

    # 冷却结束后允许重试；成功即清除失败记录。
    record = next(iter(manager._llm_failure_tracker.values()))
    record["open_until"] = 0.0
    result = manager._invoke_json("same prompt", purpose="query_assessor")
    assert result == {"ok": True}
    assert model.calls == 3
    assert manager._llm_failure_tracker == {}

    # 记录已清零：再次失败只算第 1 次，不会立即熔断。
    model.fail_times = 4
    try:
        manager._invoke_json("same prompt", purpose="query_assessor")
    except RuntimeError:
        pass
    assert model.calls == 4
    record = next(iter(manager._llm_failure_tracker.values()))
    assert int(record["failures"]) == 1
    assert float(record["open_until"]) == 0.0


def test_disk_cache_roundtrip_and_purpose_isolation(tmp_path):
    manager = MemoryManager(model=FlakyModel(fail_times=0), cache_dir=str(tmp_path))
    manager._llm_cache_write("portfolio", {"signature": "s1", "verdict": {"a": 1}})
    loaded = manager._llm_cache_read("portfolio")
    assert loaded == {"signature": "s1", "verdict": {"a": 1}}

    # 白名单外的 purpose 不落盘、不读取。
    manager._llm_cache_write("gap_expander", {"x": 1})
    assert manager._llm_cache_read("gap_expander") is None

    # 规范化缓存按 (purpose, query_id) 隔离，互不覆盖。
    name_a = MemoryManager._normalization_disk_name("q1", "claim_normalizer")
    name_b = MemoryManager._normalization_disk_name("q1", "query_assessor")
    assert name_a != name_b
    manager._llm_cache_write("claim_normalizer", {"purpose": "claim_normalizer", "v": 1}, name=name_a)
    manager._llm_cache_write("claim_normalizer", {"purpose": "query_assessor", "v": 2}, name=name_b)
    assert manager._llm_cache_read("claim_normalizer", name_a)["v"] == 1
    assert manager._llm_cache_read("claim_normalizer", name_b)["v"] == 2


def test_spec_from_portfolio_draft_coverage_rules():
    manager = MemoryManager(model=FlakyModel(fail_times=0))
    base_gap = {
        "id": "g1",
        "drafted_query_text": "Japan digital strategy policy timeline 1960 2022",
        "drafted_query_gap_ids": ["g1"],
        "drafted_acceptance_criteria": ["c1"],
        "drafted_search_mode": "news",
    }
    spec = manager._spec_from_portfolio_draft([dict(base_gap)], set())
    assert spec is not None
    assert spec["text"] == base_gap["drafted_query_text"]
    assert spec["acceptance_criteria"] == ["c1"]
    assert spec["search_mode"] == "news"
    assert spec["analysis_mode"] == "none"

    # 草稿声明覆盖范围与实际组不一致（部分覆盖）→ 拒绝，走 planner 兜底。
    partial = dict(base_gap, drafted_query_gap_ids=["g1", "g2"])
    assert manager._spec_from_portfolio_draft([partial], set()) is None

    # 与既有 Query 去重冲突 → 拒绝。
    from agents.memory_manager import _normalize_query_text

    used = {_normalize_query_text(base_gap["drafted_query_text"])}
    assert manager._spec_from_portfolio_draft([dict(base_gap)], used) is None

    # 组内草稿文本不一致 → 拒绝。
    g2 = dict(base_gap, id="g2", drafted_query_text="different phrase entirely xyz")
    assert manager._spec_from_portfolio_draft([dict(base_gap), g2], set()) is None

    # 非法 search_mode 回落 general。
    bad_mode = dict(base_gap, drafted_search_mode="bogus")
    spec = manager._spec_from_portfolio_draft([bad_mode], set())
    assert spec is not None and spec["search_mode"] == "general"


def test_store_portfolio_gap_drafts_persists_only_selected_groups():
    manager = MemoryManager(model=FlakyModel(fail_times=0))
    gaps = {
        "g1": {"id": "g1", "status": "selected"},
        "g2": {"id": "g2", "status": "selected"},
        "g3": {"id": "g3", "status": "deferred_low_value"},
    }
    stored: dict[str, dict] = {}

    def fake_upsert(node_type, properties, node_id):
        assert node_type == graph_tools.NodeType.ANALYSIS
        stored.setdefault(node_id, {}).update(properties)

    verdict = {
        "gap_query_drafts": [
            {
                "gap_ids": ["g1", "g2"],
                "text": "Japan digital strategy policy timeline 1960 2022",
                "acceptance_criteria": ["确认政策年份"],
                "search_mode": "news",
            },
            # 未 selected 的 gap：整条草稿拒绝。
            {
                "gap_ids": ["g3"],
                "text": "unrelated topic phrasing abcdef",
                "acceptance_criteria": [],
                "search_mode": "general",
            },
            # 编造的 gap id：拒绝。
            {
                "gap_ids": ["g999"],
                "text": "phantom gap phrasing zzzzz",
                "acceptance_criteria": [],
                "search_mode": "general",
            },
        ]
    }
    with patch.object(graph_tools, "upsert_node", side_effect=fake_upsert):
        manager._store_portfolio_gap_drafts(
            verdict,
            list(gaps.values()),
            [gaps["g1"], gaps["g2"]],
            existing_query_texts=[],
        )

    assert stored["g1"]["drafted_query_text"].startswith("Japan digital strategy")
    assert stored["g2"]["drafted_query_text"] == stored["g1"]["drafted_query_text"]
    assert stored["g1"]["drafted_query_gap_ids"] == ["g1", "g2"]
    assert stored["g1"]["drafted_search_mode"] == "news"
    # g3 只经历清空，不得有草稿文本。
    assert not stored["g3"].get("drafted_query_text")


def test_store_portfolio_gap_drafts_clears_stale_drafts():
    manager = MemoryManager(model=FlakyModel(fail_times=0))
    gap = {"id": "g1", "status": "selected"}
    stored: dict[str, dict] = {}

    def fake_upsert(node_type, properties, node_id):
        stored.setdefault(node_id, {}).update(properties)

    with patch.object(graph_tools, "upsert_node", side_effect=fake_upsert):
        # verdict 不含草稿：上一轮残留必须被清空。
        manager._store_portfolio_gap_drafts({}, [gap], [gap], [])
    assert stored["g1"]["drafted_query_text"] is None
    assert stored["g1"]["drafted_query_gap_ids"] == []
