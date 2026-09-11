"""为 Reporter 构造有预算的章节原文视图，读取范围固定在本章关联快照内."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import tiktoken

import config
from memory import source_snapshots
from memory.evidence_locations import _overlap, _terms, validate_block_refs

logger = logging.getLogger(__name__)
_replay_root: Path | None = None


@contextmanager
def replay_source_scope(source_run: Path) -> Iterator[None]:
    """绑定回放的来源根，不配置或清理图谱，也不写入来源运行."""
    global _replay_root
    previous = _replay_root
    _replay_root = source_run.resolve() / "source_snapshots"
    try:
        yield
    finally:
        _replay_root = previous


def capture_binding() -> dict[str, Any]:
    """在准备章节时固定只读根，供并行章节使用而不向模型公开."""
    scope = source_snapshots.current_capture_context()
    return {
        "root": str(_replay_root or scope.root) if _replay_root or scope.root else None,
        "context": scope.context,
        "replay": _replay_root is not None,
    }


def _load(location: dict, binding: dict) -> tuple[str, dict, dict]:
    if not binding.get("root"):
        raise ValueError("Snapshot root unavailable")
    root = Path(binding["root"])
    if binding.get("replay"):
        return source_snapshots.load_replay_snapshot(root, location, location["url"])
    return source_snapshots.load_captured_snapshot(
        location, location["url"], context=binding.get("context"),
        scope=source_snapshots.CaptureContext(root, binding.get("context")),
    )


class PromptBudgetError(ValueError):
    """无法容纳基础材料或必要阅读元数据，不应再次调用模型."""


def _resolve_reporter_encoding() -> "tiktoken.Encoding":
    """Resolve a tiktoken encoding for token counting.

    Priority:
    1. ``GR_REPORTER_TOKENIZER`` if set and valid.
    2. ``tiktoken.encoding_for_model(DEFAULT_MODEL)`` if the model is known.
    3. ``o200k_base`` as a universal fallback with a warning.
    """
    if config.REPORTER_TOKENIZER:
        try:
            return tiktoken.get_encoding(config.REPORTER_TOKENIZER)
        except (KeyError, ValueError):
            logger.warning(
                "GR_REPORTER_TOKENIZER=%r is not a known encoding; "
                "falling back to o200k_base.",
                config.REPORTER_TOKENIZER,
            )
    try:
        return tiktoken.encoding_for_model(config.DEFAULT_MODEL)
    except (KeyError, ValueError):
        logger.warning(
            "Model %r has no known tiktoken mapping; "
            "using o200k_base for Reporter token counting. "
            "Set GR_REPORTER_TOKENIZER to silence this warning.",
            config.DEFAULT_MODEL,
        )
        return tiktoken.get_encoding("o200k_base")


def write_audit(bundle: dict, record: dict) -> None:
    """将诊断写入独立目录，失败不改变报告交付结果."""
    output_dir = bundle.get("_source_audit_dir")
    if not output_dir:
        return
    try:
        path = Path(output_dir) / "report_source_context" / f"chapter-{int(bundle['chapter_id'])}"
        path.mkdir(parents=True, exist_ok=True)
        (path / "audit.json").write_text(json.dumps({
            "bundle_token": bundle.get("bundle_token"), "chapter_id": bundle["chapter_id"], **record,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except (OSError, ValueError):
        logger.exception("Could not write chapter source audit")


class SourceContext:
    """保存单章读取与审计状态，所有模型输入都重新序列化并计数."""

    def __init__(self, bundle: dict[str, Any]):
        """加载章节可定位材料；旧图或损坏快照只产生不可用状态."""
        self.bundle = bundle
        try:
            self.encoding = (
                tiktoken.get_encoding(config.REPORTER_TOKENIZER)
                if config.REPORTER_TOKENIZER else (
                    tiktoken.get_encoding("o200k_base") if config.DEFAULT_MODEL == "gpt-5.1"
                    else tiktoken.encoding_for_model(config.DEFAULT_MODEL)
                )
            )
        except (KeyError, ValueError) as exc:
            raise PromptBudgetError("unknown_reporter_tokenizer: set GR_REPORTER_TOKENIZER") from exc
        self.input_limit = (
            config.REPORTER_CONTEXT_TOKENS - config.REPORTER_OUTPUT_TOKENS - config.REPORTER_SAFETY_TOKENS
        )
        self.binding = bundle.get("_snapshot_binding") or {}
        self.items = {
            item["ref"]: item for item in bundle.get("evidence_items") or []
            if item.get("type") == "Evidence"
        }
        self.locations: dict[str, dict] = {}
        self.blocks: dict[str, dict] = {}
        self.automatic: set[str] = set()
        self.advertised: dict[str, set[str]] = {}
        self.requests: list[dict] = []
        self.results: list[dict] = []
        self.requested: list[str] = []
        self.views: list[dict] = []
        for ref, item in self.items.items():
            location = item.get("_source_location") or {}
            try:
                body, index, _ = _load(location, self.binding)
                by_ref = {block["block_id"]: block for block in index["blocks"]}
                validated = validate_block_refs(location.get("block_refs"), set(by_ref))
                direct = validated["block_refs"]
                if validated["location_status"] != "valid" or location.get("location_status") != "valid":
                    raise ValueError("Evidence location unavailable")
            except (OSError, ValueError, KeyError, TypeError):
                self.locations[ref] = {"status": "unavailable", "block_refs": [], "readable_block_refs": []}
                continue
            ordered = list(by_ref)
            readable = set(direct)
            for block_ref in direct:
                position = ordered.index(block_ref)
                readable.update(by_ref[block_ref]["dependency_refs"])
                readable.update(ordered[max(0, position - 1):position + 2])
            self.locations[ref] = {
                "status": "available", "block_refs": direct,
                "readable_block_refs": [key for key in ordered if key in readable],
            }
            self.automatic.update(direct)
            for key in readable:
                block = by_ref[key]
                shared = self.blocks.setdefault(key, {
                    "block_ref": key, "text": body[block["start_char"]:block["end_char"]],
                    "evidence_refs": [], "sources": [],
                })
                if ref not in shared["evidence_refs"]:
                    shared["evidence_refs"].append(ref)
                source = {"title": location.get("title") or "", "citation": location.get("citation") or ""}
                if source not in shared["sources"]:
                    shared["sources"].append(source)
        self.block_terms = {key: _terms(block["text"]) for key, block in self.blocks.items()}

    def count(self, text: str) -> int:
        """对完整文本计数，网页中的特殊标记按普通文本处理."""
        return len(self.encoding.encode(text, disallowed_special=()))

    def accept_requests(self, requests: list[dict]) -> None:
        """唯一回读事件内复核文件；失败逐项返回，不在后续重试中重新读取."""
        self.requests = requests
        self.results = []
        self.requested = []
        for request in requests:
            ref = request["evidence_ref"]
            location = self.locations.get(ref, {})
            explicit = request.get("block_refs") or []
            refs = explicit or location.get("block_refs") or [None]
            results = []
            loaded = False
            fresh_blocks: dict[str, str] = {}
            if ref in self.items and location.get("status") == "available":
                try:
                    body, index, _ = _load(self.items[ref]["_source_location"], self.binding)
                    fresh_blocks = {
                        block["block_id"]: body[block["start_char"]:block["end_char"]]
                        for block in index["blocks"]
                    }
                    loaded = True
                except (OSError, ValueError, KeyError, TypeError):
                    self.automatic.difference_update(location.get("block_refs") or [])
            for block_ref in dict.fromkeys(refs):
                if ref not in self.items or (explicit and block_ref not in self.advertised.get(ref, set())):
                    status = "invalid_ref"
                elif not loaded or block_ref not in fresh_blocks:
                    status = "unavailable"
                else:
                    status = "loaded"
                    self.blocks[block_ref]["text"] = fresh_blocks[block_ref]
                    if block_ref not in self.requested:
                        self.requested.append(block_ref)
                results.append({"block_ref": block_ref, "status": status})
            self.results.append({"evidence_ref": ref, "purpose": request["purpose"], "results": results})

    def prompt(self, render: Callable[[dict], str], *, readback_used: bool) -> str:
        """在完整输入和原文增量双重上限内，先放请求块再按目标轮流选块."""
        base_tokens = self.count(render(self.bundle))
        if base_tokens > self.input_limit:
            raise PromptBudgetError("base_prompt_over_budget")
        view: dict[str, Any] = {
            "readback_available": not readback_used, "evidence_locations": {},
            "context_blocks": [], "read_results": json.loads(json.dumps(self.results)),
        }
        # 先按最坏的未加载状态计入结果开销，再尝试放入完整块。
        for request in view["read_results"]:
            for result in request["results"]:
                if result["status"] == "loaded":
                    result["status"] = "budget_exceeded"

        def serialized() -> str:
            return render({**self.bundle, "_source_context": view})

        def fits() -> bool:
            count = self.count(serialized())
            return count <= self.input_limit and count - base_tokens <= config.REPORTER_SOURCE_TOKENS

        if not fits():
            raise PromptBudgetError("source_context_metadata_over_budget")
        selected: set[str] = set()
        reasons: list[dict] = []

        def add_block(key: str, reason: str, goal: str = "") -> bool:
            if key in selected:
                return True
            view["context_blocks"].append(self.blocks[key])
            affected = [
                result for request in view["read_results"] for result in request["results"]
                if result["block_ref"] == key and result["status"] == "budget_exceeded"
            ]
            for result in affected:
                result["status"] = "loaded"
            if fits():
                selected.add(key)
                reasons.append({"block_ref": key, "reason": reason, "goal": goal, "status": "loaded"})
                return True
            view["context_blocks"].pop()
            for result in affected:
                result["status"] = "budget_exceeded"
            reasons.append({"block_ref": key, "reason": reason, "goal": goal, "status": "budget_exceeded"})
            return False

        for key in self.requested:
            add_block(key, "requested")
        goals = [str(goal) for goal in self.bundle.get("chapter_goals") or []] or [str(self.bundle.get("section_plan") or "")]
        goal_terms = [_terms(goal) for goal in goals]
        seen_terms = set().union(*(self.block_terms[key] for key in selected)) if selected else set()
        remaining = self.automatic - selected - set(self.requested)
        turn = 0
        while remaining:
            goal_index = turn % len(goals)
            wanted = goal_terms[goal_index]

            def rank(key: str) -> tuple:
                terms = self.block_terms[key]
                has_boundary = any(
                    relation.get("stance") in {"qualifies", "contradicts"}
                    for ref in self.blocks[key]["evidence_refs"]
                    for relation in self.items[ref].get("claim_relations") or []
                )
                return (-_overlap(terms, wanted), -len(terms - seen_terms), -int(has_boundary), key)

            key = min(remaining, key=rank)
            remaining.remove(key)
            if add_block(key, "goal_round_robin", goals[goal_index]):
                seen_terms.update(self.block_terms[key])
            turn += 1
        # 正文优先；只公开预算还能容纳的直接定位与一跳索引。
        if not readback_used:
            self.advertised = {}
            for ref, location in self.locations.items():
                public = {"block_refs": [], "readable_block_refs": []}
                view["evidence_locations"][ref] = public
                if not fits():
                    del view["evidence_locations"][ref]
                    continue
                for key in location["readable_block_refs"]:
                    public["readable_block_refs"].append(key)
                    if key in location["block_refs"]:
                        public["block_refs"].append(key)
                    if not fits():
                        public["readable_block_refs"].remove(key)
                        if key in public["block_refs"]:
                            public["block_refs"].remove(key)
                self.advertised[ref] = set(public["readable_block_refs"])
            for block in view["context_blocks"]:
                for ref in block["evidence_refs"]:
                    self.advertised.setdefault(ref, set()).add(block["block_ref"])
        prompt = serialized()
        total = self.count(prompt)
        self.views.append({
            "view": json.loads(json.dumps(view)), "selection": reasons,
            "input_tokens": total, "base_tokens": base_tokens,
            "source_tokens": max(0, total - base_tokens), "tokenizer": self.encoding.name,
            "input_limit": self.input_limit, "source_limit": config.REPORTER_SOURCE_TOKENS,
        })
        return prompt

    def audit(self, *, model_invocations: int, failed_attempts: int, readback_used: bool, error: str) -> None:
        """写入独立章节审计目录；诊断写入失败不改变已有报告交付结果."""
        write_audit(self.bundle, {
            "requests": self.requests, "views": self.views,
            "resolved_requests": self.results,
            "model_invocations": model_invocations, "failed_attempts": failed_attempts,
            "readback_used": readback_used, "error": error,
            "tokenizer": self.encoding.name, "model": config.DEFAULT_MODEL,
            "context_tokens": config.REPORTER_CONTEXT_TOKENS,
            "output_tokens": config.REPORTER_OUTPUT_TOKENS,
            "safety_tokens": config.REPORTER_SAFETY_TOKENS,
            "source_tokens": config.REPORTER_SOURCE_TOKENS,
        })
