"""保存本次运行捕获的原文，并提供不改变正文的稳定位置索引."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

logger = logging.getLogger(__name__)
CHUNKER_VERSION = "v1"
_PARAGRAPH_CHARS = 2_000
_SNAPSHOT_ID = re.compile(r"s_[0-9a-f]{64}")
_CAPTURE_ID = re.compile(r"cap_[0-9a-f]{32}")
_HEADING = re.compile(r"^ {0,3}(#{1,6})\s+")
_LIST = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")
_FOOTNOTE = re.compile(r"^\s*\[\^[^\]]+\]:")


def canonicalize_source_url(value: object) -> str | None:
    """按 Searcher 既有规则规范化 URL，移除 fragment 和常见跟踪参数."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parts = urlsplit(value.strip())
        hostname = parts.hostname
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"} or not hostname:
        return None
    netloc = parts.netloc.lower()
    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    query_items = sorted(
        (key, item_value)
        for key, item_value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in {"gclid", "fbclid"}
    )
    return urlunsplit((scheme, netloc, path, urlencode(query_items, doseq=True), ""))


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _snapshot_id(source_key: str, body_sha256: str) -> str:
    return "s_" + hashlib.sha256(_json_bytes([source_key, body_sha256])).hexdigest()


def _paragraph_spans(body: str, start: int, end: int) -> Iterator[tuple[int, int]]:
    """在句界按软上限分段，无法分开的长句保持原样."""
    cursor = start
    previous = start
    for match in re.finditer(r"[。！？]|[.!?](?=\s|$)", body[start:end]):
        boundary = start + match.end()
        if boundary - cursor > _PARAGRAPH_CHARS and previous > cursor:
            yield cursor, previous
            cursor = previous
        previous = boundary
    if not body[previous:end].strip():
        previous = end
    if end - cursor > _PARAGRAPH_CHARS and previous > cursor and previous < end:
        yield cursor, previous
        cursor = previous
    if cursor < end:
        yield cursor, end


def _block_spans(body: str) -> Iterator[tuple[str, int, int]]:
    """识别常见 Markdown 单元，保留表格、脚注和围栏代码的完整位置."""
    lines = body.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))

    def table_at(position: int) -> bool:
        return (
            position + 1 < len(lines)
            and "|" in lines[position]
            and bool(_TABLE_SEPARATOR.match(lines[position + 1]))
        )

    index = 0
    while index < len(lines):
        if not lines[index].strip():
            index += 1
            continue
        start = index
        fence = _FENCE.match(lines[index])
        if fence:
            kind = "code"
            marker = fence.group(1)
            index += 1
            while index < len(lines):
                closing = lines[index].strip()
                index += 1
                if len(closing) >= len(marker) and set(closing) == {marker[0]}:
                    break
        elif _HEADING.match(lines[index]):
            kind = "heading"
            index += 1
        elif table_at(index):
            kind = "table"
            index += 2
            while index < len(lines) and lines[index].strip() and "|" in lines[index]:
                index += 1
            # 显式脚注可以紧随表格，也可以由空行分隔；其他段落仍独立保存。
            while index < len(lines):
                note = index
                while note < len(lines) and not lines[note].strip():
                    note += 1
                if note == len(lines) or not _FOOTNOTE.match(lines[note]):
                    break
                index = note + 1
                while index < len(lines) and lines[index].strip() and lines[index].startswith(("    ", "\t")):
                    index += 1
        else:
            kind = "list" if _LIST.match(lines[index]) else "paragraph"
            index += 1
            while index < len(lines) and lines[index].strip():
                if _HEADING.match(lines[index]) or _FENCE.match(lines[index]) or table_at(index):
                    break
                if kind == "paragraph" and _LIST.match(lines[index]):
                    break
                if kind == "list" and not (_LIST.match(lines[index]) or lines[index].startswith((" ", "\t"))):
                    break
                index += 1
        begin, end = offsets[start], offsets[index]
        if kind == "paragraph":
            yield from ((kind, left, right) for left, right in _paragraph_spans(body, begin, end))
        else:
            yield kind, begin, end


def build_snapshot_index(source_key: str, body: str) -> dict[str, Any]:
    """从精确正文生成身份与索引，所有偏移均为 Python 字符串区间."""
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    snapshot_id = _snapshot_id(source_key, digest)
    blocks = []
    headings: list[tuple[int, str]] = []
    for number, (kind, start, end) in enumerate(_block_spans(body), start=1):
        block_id = f"{snapshot_id}:{CHUNKER_VERSION}:b{number:06d}"
        if kind == "heading":
            level = len(_HEADING.match(body[start:end]).group(1))
            headings = [(depth, ref) for depth, ref in headings if depth < level]
        blocks.append({
            "block_id": block_id,
            "kind": kind,
            "start_char": start,
            "end_char": end,
            "dependency_refs": [ref for _, ref in headings],
        })
        if kind == "heading":
            headings.append((level, block_id))
    return {
        "schema_version": 1,
        "snapshot_id": snapshot_id,
        "source_key": source_key,
        "body_sha256": digest,
        "chunker_version": CHUNKER_VERSION,
        "blocks": blocks,
    }


def _contained_path(root: Path, *parts: str) -> Path:
    root = root.resolve()
    path = root.joinpath(*parts).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Snapshot path leaves the configured root")
    return path


def _publish_file(path: Path, data: bytes) -> None:
    """原子发布不可变文件；并发发布时校验已有内容，不覆盖已有文件."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=".snapshot-")
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != data:
                raise ValueError("Existing snapshot file failed integrity validation") from None
    finally:
        temporary.unlink(missing_ok=True)


def save_snapshot(root: Path, source_key: str, body: str) -> dict[str, Any]:
    """先发布完整正文，再发布可读取索引，返回生成的索引."""
    index = build_snapshot_index(source_key, body)
    _publish_file(_contained_path(root, "snapshots", index["snapshot_id"], "body.txt"), body.encode("utf-8"))
    _publish_file(_contained_path(root, "snapshots", index["snapshot_id"], f"index-{CHUNKER_VERSION}.json"), _json_bytes(index))
    return index


def read_snapshot(root: Path, snapshot_id: str, chunker_version: str = CHUNKER_VERSION) -> tuple[str, dict[str, Any]]:
    """只读取指定根内的有效快照，并验证正文哈希、身份和全部位置."""
    if not _SNAPSHOT_ID.fullmatch(snapshot_id) or chunker_version != CHUNKER_VERSION:
        raise ValueError("Invalid snapshot identity or unsupported chunker version")
    index = json.loads(_contained_path(root, "snapshots", snapshot_id, f"index-{chunker_version}.json").read_bytes())
    body = _contained_path(root, "snapshots", snapshot_id, "body.txt").read_bytes().decode("utf-8")
    if not isinstance(index, dict) or not isinstance(index.get("source_key"), str):
        raise ValueError("Invalid snapshot index")
    expected = build_snapshot_index(index["source_key"], body)
    if index != expected or index["snapshot_id"] != snapshot_id:
        raise ValueError("Snapshot body or index failed integrity validation")
    return body, index


@dataclass(frozen=True)
class CaptureContext:
    """固定一次搜索使用的运行根与归属，不向模型公开文件路径."""

    root: Path | None = None
    context: str | None = None
    query_id: str | None = None
    search_run_id: str | None = None


_run_context = CaptureContext()
_search_context: ContextVar[CaptureContext | None] = ContextVar("source_capture_context", default=None)


def configure(output_dir: str | None, context: str | None) -> None:
    """绑定本轮捕获根；缺少输出目录时禁用捕获，不创建或删除文件."""
    global _run_context
    root = Path(output_dir).resolve() / "source_snapshots" if output_dir else None
    _run_context = CaptureContext(root=root, context=context)


@contextmanager
def search_capture_scope(query_id: str | None, search_run_id: str | None) -> Iterator[None]:
    """在当前调用内固定运行配置与搜索归属，退出时恢复原绑定."""
    run = _run_context
    token = _search_context.set(CaptureContext(run.root, run.context, query_id, search_run_id))
    try:
        yield
    finally:
        _search_context.reset(token)


def current_capture_context() -> CaptureContext:
    """返回当前调用固定的捕获配置，供读取边界核对运行归属."""
    return _search_context.get() or _run_context


def load_captured_snapshot(
    reference: dict[str, Any],
    source_url: str,
    *,
    context: str | None,
    query_id: str | None = None,
    search_run_id: str | None = None,
    scope: CaptureContext | None = None,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """核对运行、搜索和来源归属后读取捕获关联的原文，失败不寻找其他目录."""
    scope = scope or current_capture_context()
    if scope.root is None or scope.context != context:
        raise ValueError("Snapshot root is unavailable for this context")
    capture_id = reference.get("capture_id")
    if not isinstance(capture_id, str) or not _CAPTURE_ID.fullmatch(capture_id):
        raise ValueError("Invalid capture identity")
    record = json.loads(_contained_path(scope.root, "captures", f"{capture_id}.json").read_bytes())
    if not isinstance(record, dict) or record.get("status") != "stored" or record.get("schema_version") != 1:
        raise ValueError("Capture is not available")
    if record.get("capture_id") != capture_id or record.get("context") != context:
        raise ValueError("Capture does not belong to this context")
    if any(reference.get(key) != record.get(key) for key in ("snapshot_id", "chunker_version")):
        raise ValueError("Capture and snapshot references do not match")
    if query_id is not None and record.get("query_id") != query_id:
        raise ValueError("Capture does not belong to this Query")
    if search_run_id is not None and record.get("search_run_id") != search_run_id:
        raise ValueError("Capture does not belong to this SearchRun")
    source_key = canonicalize_source_url(source_url)
    if source_key is None or canonicalize_source_url(record.get("url")) != source_key:
        raise ValueError("Capture does not belong to this Source")
    body, index = read_snapshot(scope.root, record["snapshot_id"], record["chunker_version"])
    if index["source_key"] != source_key:
        raise ValueError("Snapshot does not belong to this Source")
    return body, index, record


def load_replay_snapshot(
    root: Path, reference: dict[str, Any], source_url: str,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """从显式来源运行根只读回放，兼容导出图没有 context 属性的情况."""
    capture_id = reference.get("capture_id")
    if not isinstance(capture_id, str) or not _CAPTURE_ID.fullmatch(capture_id):
        raise ValueError("Invalid capture identity")
    record = json.loads(_contained_path(root, "captures", f"{capture_id}.json").read_bytes())
    if not isinstance(record, dict):
        raise ValueError("Invalid capture record")
    context = record.get("context")
    return load_captured_snapshot(
        reference, source_url, context=context, scope=CaptureContext(root, context),
    )


def capture_source(
    item: dict[str, Any],
    *,
    query: str,
    stage: str,
    search_parameters: dict[str, Any],
    response: dict[str, Any],
    result_index: int | None,
    raw_content_limit: int,
) -> dict[str, Any]:
    """在裁剪前捕获一条结果，文件失败只返回捕获错误，不中断搜索."""
    scope = current_capture_context()
    if scope.root is None:
        return {"status": "disabled", "reason": "no_output_dir"}
    capture_id = "cap_" + uuid4().hex
    body = item.get("raw_content")
    record = {
        "schema_version": 1,
        "capture_id": capture_id,
        "context": scope.context,
        "query_id": scope.query_id,
        "search_run_id": scope.search_run_id,
        "query": query,
        "result_index": result_index,
        "url": item.get("url"),
        "title": item.get("title"),
        "published_at": item.get("published_at") or item.get("published_date") or item.get("date"),
        "content": item.get("content"),
        "captured_at": datetime.now(UTC).isoformat(),
        "provider": "tavily",
        "request_id": response.get("request_id"),
        "response_time": response.get("response_time"),
        "stage": stage,
        "search_parameters": search_parameters,
        "requested_depth": search_parameters.get("search_depth") or "provider_default",
        "provider_completeness": "unknown",
        "provider_raw_content_truncated": item.get("raw_content_truncated"),
        "raw_content_chars": len(body) if isinstance(body, str) else None,
        "application_truncated": isinstance(body, str) and len(body) > raw_content_limit,
        "application_raw_content_limit": raw_content_limit,
    }
    result: dict[str, Any] = {"status": "unavailable", "reason": "no_raw_content"}
    try:
        if isinstance(body, str) and body:
            source_key = canonicalize_source_url(item.get("url")) or str(item.get("url") or "")
            index = save_snapshot(scope.root, source_key, body)
            result = {"status": "stored", "snapshot_id": index["snapshot_id"], "chunker_version": CHUNKER_VERSION}
    except Exception as exc:  # noqa: BLE001 - 捕获副作用失败不改变搜索结果。
        result = {"status": "error", "reason": type(exc).__name__}
        logger.warning("Source snapshot capture failed: capture_id=%s error=%s", capture_id, type(exc).__name__)
    try:
        _publish_file(_contained_path(scope.root, "captures", f"{capture_id}.json"), _json_bytes({**record, **result}))
    except Exception as exc:  # noqa: BLE001 - 审计文件失败仍必须保留搜索正文。
        logger.warning("Source capture record failed: capture_id=%s error=%s", capture_id, type(exc).__name__)
        return {"status": "error", "reason": "capture_record_write_failed"}
    return {**result, "capture_id": capture_id}
