"""构造有界原文阅读视图，并校验 Evidence 的块引用与精确位置."""

from __future__ import annotations

import re
from typing import Any

SNAPSHOT_FIELDS = ("snapshot_id", "chunker_version", "capture_id")
LOCATION_FIELDS = ("block_refs", "location_status")
ANALYZER_BODY_CHARS = 20_000
_TARGET_SHARE = 0.75


def snapshot_fields(item: dict[str, Any]) -> dict[str, Any]:
    """提取显式出现的快照关联字段，保留旧调用没有这些字段的语义."""
    return {key: item[key] for key in SNAPSHOT_FIELDS if key in item}


def _terms(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+|[\u3400-\u9fff]+", text.casefold())
    return {
        term
        for word in words
        for term in (
            [word] if word.isascii() or len(word) == 1
            else [word[index:index + 2] for index in range(len(word) - 1)]
        )
    }


def _overlap(terms: set[str], wanted: set[str]) -> float:
    return len(terms & wanted) / len(wanted) if wanted else 0.0


def _exact_ranges(body: str, text: str) -> list[tuple[int, int]]:
    ranges = []
    start = 0
    while text:
        start = body.find(text, start)
        if start < 0:
            break
        ranges.append((start, start + len(text)))
        start += 1
    return ranges


def select_source_blocks(
    body: str,
    index: dict[str, Any],
    query: dict[str, Any],
    research_context: dict[str, Any],
    content: str,
    *,
    max_chars: int = ANALYZER_BODY_CHARS,
) -> dict[str, Any]:
    """按相关性和标题分区选择原文，所有正文及结构依赖共享字符预算."""
    blocks = index["blocks"]
    by_ref = {block["block_id"]: block for block in blocks}
    texts = {ref: body[block["start_char"]:block["end_char"]] for ref, block in by_ref.items()}
    terms = {ref: _terms(text) for ref, text in texts.items()}
    target_terms = _terms(" ".join([
        str(query.get("text") or ""),
        *[str(value) for value in query.get("acceptance_criteria") or []],
        content,
    ]))
    goal_terms = _terms(str(research_context.get("research_goal") or ""))
    # 整段摘要无法匹配时，仍可识别其中逐行返回的精确片段。
    snippets = {content.strip()} | {line.strip() for line in content.splitlines() if len(line.strip()) >= 20}
    matches = [span for snippet in snippets if snippet for span in _exact_ranges(body, snippet)]
    exact_refs = {
        block["block_id"] for block in blocks
        if any(start < block["end_char"] and end > block["start_char"] for start, end in matches)
    }
    candidates = [block["block_id"] for block in blocks if block["kind"] != "heading"]
    target_scores = {ref: _overlap(terms[ref], target_terms) for ref in candidates}
    goal_scores = {ref: _overlap(terms[ref], goal_terms) for ref in candidates}
    targeted = sorted(
        (ref for ref in candidates if ref in exact_refs or target_scores[ref] or goal_scores[ref]),
        key=lambda ref: (-int(ref in exact_refs), -target_scores[ref], -goal_scores[ref], by_ref[ref]["start_char"]),
    )
    groups: dict[str, list[str]] = {}
    for ref in candidates:
        section = (by_ref[ref]["dependency_refs"] or [""])[-1]
        groups.setdefault(section, []).append(ref)
    ordered_groups = sorted(
        (sorted(refs, key=lambda ref: (-goal_scores[ref], by_ref[ref]["start_char"])) for refs in groups.values()),
        key=lambda refs: (-max(goal_scores[ref] for ref in refs), min(by_ref[ref]["start_char"] for ref in refs)),
    )
    coverage_order = [
        refs[position]
        for position in range(max((len(refs) for refs in ordered_groups), default=0))
        for refs in ordered_groups if position < len(refs)
    ]
    selected: set[str] = set()
    used = 0

    def take(refs: list[str], limit: int) -> None:
        nonlocal used
        for ref in refs:
            unit = {ref, *by_ref[ref]["dependency_refs"]} - selected
            cost = sum(len(texts[part]) for part in unit)
            if used + cost <= limit:
                selected.update(unit)
                used += cost

    target_limit = int(max_chars * _TARGET_SHARE)
    take(targeted, target_limit)
    take(coverage_order, used + max_chars - target_limit)
    take(targeted, max_chars)
    take(coverage_order, max_chars)
    return {
        "blocks": [
            {"block_id": block["block_id"], "text": texts[block["block_id"]]}
            for block in blocks if block["block_id"] in selected
        ],
        "reading_coverage": {
            "mode": "blocks",
            "selection": "matched" if targeted else "coverage_fallback",
            "selected_chars": used,
            "snapshot_chars": len(body),
            "selected_blocks": len(selected),
            "total_blocks": len(blocks),
            "unloaded_blocks": len(blocks) - len(selected),
        },
    }


def validate_block_refs(refs: object, allowed_refs: set[str]) -> dict[str, Any]:
    """只接受已展示的非空块标识，任一非法引用使整条定位失效."""
    if refs is None or refs == []:
        return {"block_refs": [], "location_status": "missing"}
    if not isinstance(refs, list) or any(not isinstance(ref, str) or ref not in allowed_refs for ref in refs):
        return {"block_refs": [], "location_status": "invalid"}
    return {"block_refs": list(dict.fromkeys(refs)), "location_status": "valid"}


def quote_locations(text: str, refs: list[str], body: str, index: dict[str, Any]) -> list[dict[str, int]]:
    """返回实际引用范围内的精确原句位置，跨块时只允许未展示的空白间隔."""
    selected = sorted(
        (block for block in index["blocks"] if block["block_id"] in refs),
        key=lambda block: block["start_char"],
    )
    if not selected or not text.strip():
        return []
    ranges: list[tuple[int, int]] = []
    for block in selected:
        start, end = block["start_char"], block["end_char"]
        if ranges and not body[ranges[-1][1]:start].strip():
            ranges[-1] = (ranges[-1][0], end)
        else:
            ranges.append((start, end))
    return [
        {"start_char": start + left, "end_char": start + right}
        for start, end in ranges
        for left, right in _exact_ranges(body[start:end], text)
    ]
