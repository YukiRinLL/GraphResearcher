"""Deterministic report evidence, chapter, citation, and delivery helpers.

The v4 delivery path compiles the latest Reporter chapter candidates. Reporter-authored
inline citations are validated against Sources derived from the selected Report
Evidence and are preserved in place; the compiler generates the single final
references section and persists ReportSection bindings only for the accepted
delivery artifact.

``finalize_report`` remains a conservative utility for callers outside the v4
committed-chapter path. The main delivery flow does not call it because that
would renumber citations and write a second set of ReportSection nodes.
"""

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

from memory.graph import EdgeType
from tools import graph_tools

logger = logging.getLogger(__name__)

# In-text citation token, e.g. ``[12]``; adjacency ``[1][3]`` is two matches.
_CITE_TOKEN_RE = re.compile(r"\[(\d{1,4})\]")
# Local reference token (bundle-internal refs), e.g. ``[e17]``, ``[c4]``, ``[d5]``.
_LOCAL_REF_RE = re.compile(r"\[([ecd])\d+\]")
# The references-section heading line (any ATX level, zh/en, case-insensitive).
_REF_HEADING_RE = re.compile(r"(?mi)^#{1,6}\s*(参考文献|References)\s*$")
# Any ATX heading line (chapters/sections/sub-sections mix ``#`` / ``##`` / ``###``).
_ANY_HEADING_RE = re.compile(r"(?m)^#{1,6}\s+(.*\S)\s*$")
_INTERNAL_TERMS = (
    "Research Graph",
    "`blocked`",
    "`pending`",
    "本轮证据",
    "检索轮次",
    "证据受限版",
    "摘要线索",
    "snippet",
    "未读取正文",
    "标题层",
    "sufficiency",
    "source 节点",
    "evidence 节点",
    "claim 节点",
    "supplied material",
    "supplied evidence",
    "provided material",
    "provided evidence",
    "available material",
    "available evidence",
    "研究图谱",
)
_FORBIDDEN_META_RE = re.compile(
    r"research graph|研究图谱|本次图谱|图谱覆盖范围|导出片段|"
    r"由于引用系统限制|引用系统限制|无法.{0,20}引用|正文不逐条打|"
    r"\b(?:report_ready|limited_report_ready|budget_exhausted)\b|"
    r"report-level objectives reached marginal-utility convergence|"
    r"bounded research reached best-effort convergence|"
    r"exhaustive objective remained open after targeted recovery|"
    r"(?:search|research)\s+budget\s+(?:was\s+|is\s+|has\s+been\s+)?exhausted|"
    r"targeted\s+recovery(?:\s+query)?\s+(?:was\s+|has\s+)?failed|"
    r"(?:搜索|检索|研究)预算(?:已经|已)?(?:耗尽|用尽)|"
    r"定向(?:恢复|检索)(?:查询)?(?:已经|已)?失败|"
    r"如果你(?:后续|接下来|希望|需要|想)|可以指定维度|可直接进\s*ppt|"
    r"帮你补全|如需.{0,40}可|"
    r"supplied\s+(?:material|evidence|data|information)|"
    r"the\s+supplied|provided\s+(?:material|evidence|data)|"
    r"available\s+(?:material|evidence|data)|"
    r"本研究|本次检索|本轮|本次|检索轮次|摘要线索|未读取正文|标题层|"
    r"source\s+节点|evidence\s+节点|claim\s+节点|"
    r"sufficiency|snippet|"
    # Fix 1 (auto-strip safety net): reader-directive / methodological-caveat
    # meta-narratives — sentences that instruct the reader on how to use
    # sources or pronounce on the reliability/nature of the record. These
    # describe "how to use the material" rather than the subject itself.
    r"should\s+not\s+be\s+(?:treated|taken|regarded|considered|used)\s+as\s+(?:interchangeable|equivalent|synonymous|definitive|secure|reliable)|"
    r"should\s+not\s+be\s+used\s+to\s+(?:collapse|treat|conflate|conclude|infer)|"
    r"do\s+not\s+amount\s+to\s+a\s+\w+\s+(?:determination|account|assessment|conclusion|verdict)|"
    r"rather\s+than\s+a\s+(?:definitive|secure|reliable|forensic)\s+(?:laboratory\s+)?(?:account|determination|assessment|record)|"
    r"not\s+a\s+(?:securely|reliably)\s+documented\s+\w+(?:\s+chain\s+of\s+custody)?|"
    r"reported\s+reconstructions\s+rather\s+than|"
    r"concern\s+reported\s+(?:discovery|reconstructions|judgments|findings)|"
    r"further\s+(?:catalogue|catalog)\s+verification|"
    # Fix C: residual meta-analytical / evidence-state commentary (auto-strip —
    # pure commentary on what the evidence can/cannot establish, no facts lost).
    r"are\s+best\s+presented\s+as\s+\w+\s+rather\s+than|"
    r"rather\s+than\s+as\s+an?\s+uncontested|"
    r"do\s+not,?\s+(?:by\s+themselves|alone|on\s+their\s+own),?\s+(?:establish|demonstrate|prove)|"
    r"do\s+not\s+(?:establish|demonstrate|prove)\s+that|"
    r"the\s+evidence\s+does\s+not\s+(?:reconcile|establish|support|demonstrate)|"
    r"remains\s+(?:contested|unresolved|undetermined)\s+rather\s+than|"
    r"parts\s+of\s+the\s+recorded\s+history\s+of\s+the\s+object\s+rather\s+than",
    re.IGNORECASE,
)
_REFERENCE_VARIANT_RE = re.compile(
    r"(?mi)^#{1,6}\s*(?:参考资料|参考文献（合并版）|References\s*\(Merged\))\s*$"
)
_REFERENCE_ONLY_RE = re.compile(r"^(?:详见|参考|see|reference)\s*\[\d{1,4}\]\s*[。.]?$", re.IGNORECASE)
_PLACEHOLDER_RE = re.compile(
    r"此处省略|篇幅所限|内容已截断|以下类似|同之前，略|omitted for brevity|"
    r"content truncated|for brevity|remaining content follows the same pattern",
    re.IGNORECASE,
)
_EXTERNAL_FILE_RE = re.compile(
    r"详见附件|保存在.+文件|see full.+file|stored in.+file|详见.+chapter_\d+|详见.+draft\.md",
    re.IGNORECASE,
)
_NO_FINDINGS_TEXT = {"暂无可核实结论。", "No verifiable findings are available."}
_MIN_RETENTION_RATIO = 0.6
_RESERVED_SECTION_TITLES = {
    "references",
    "reference",
    "bibliography",
    "notes",
    "参考文献",
    "参考资料",
}
_OUTLINE_FILE = ".report_outline.json"
_OUTLINE_MARKDOWN_FILE = ".report_outline.md"
_CHAPTER_DIR = ".report_chapters"
_CHAPTER_META_SUFFIX = ".meta.json"


def _artifact_root(output_dir: Optional[str]) -> Path:
    """Return the report-workflow artifact root."""
    root = Path(output_dir) if output_dir else Path(".")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _outline_path(output_dir: Optional[str]) -> Path:
    return _artifact_root(output_dir) / _OUTLINE_FILE


def _outline_markdown_path(output_dir: Optional[str]) -> Path:
    return _artifact_root(output_dir) / _OUTLINE_MARKDOWN_FILE


def _chapter_dir(output_dir: Optional[str]) -> Path:
    path = _artifact_root(output_dir) / _CHAPTER_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _chapter_path(output_dir: Optional[str], chapter_id: int) -> Path:
    return _chapter_dir(output_dir) / f"chapter_{int(chapter_id):02d}.md"


def _chapter_meta_path(output_dir: Optional[str], chapter_id: int) -> Path:
    return _chapter_dir(output_dir) / f"chapter_{int(chapter_id):02d}{_CHAPTER_META_SUFFIX}"


def _read_json_file(path: Path) -> dict[str, Any]:
    """Read one JSON artifact; missing files return an empty dict."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _render_outline_markdown(title: str, chapters: list[dict[str, Any]]) -> str:
    """Render a concise markdown view of the current report outline."""
    lines = [f"# {title}", ""]
    for chapter in chapters:
        lines.append(f"## {chapter['chapter_id']}. {chapter['title']}")
        goals = [str(goal).strip() for goal in chapter.get("goals") or [] if str(goal).strip()]
        if goals:
            lines.append("")
            lines.extend(f"- {goal}" for goal in goals)
        plan = str(chapter.get("section_plan") or "").strip()
        if plan:
            lines.extend(["", plan])
        query_refs = [str(query_ref).strip() for query_ref in chapter.get("query_refs") or [] if str(query_ref).strip()]
        if query_refs:
            lines.extend(["", f"Queries: {', '.join(query_refs)}"])
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def build_reference_registry() -> list[dict]:
    """Return the canonical, URL-deduped, stably-numbered reference registry.

    Reads every ``Source`` node for the current run context, drops entries
    without a URL or that are not transitively referenced by any Statement
    (ghost sources from login-wall/catalog pages are excluded), deduplicates by
    URL (first node in id order wins), and sorts by node id.  Assigns 1-based
    numbers.

    Chapter bundles, review contexts, and final report compilation build the
    registry through this one function, so the ``n``→source mapping remains
    identical throughout citation validation and rendering.

    Returns:
        A list of ``{"n", "source_id", "title", "url"}`` dicts.
    """
    all_sources = [s for s in graph_tools.search_nodes("source", {}) if s.get("url")]
    referenced_source_ids: set[str] = set()
    # direction="in" returns edges where target == stmt_id; edge["source"] is the
    # upstream node (Document or Source). Walk Statement -> Document -> Source.
    for stmt in graph_tools.search_nodes("statement", {}):
        stmt_id = stmt.get("id")
        if not stmt_id:
            continue
        for edge in graph_tools.get_node_edges(stmt_id, direction="in") or []:
            src_node_id = edge.get("source")
            if not src_node_id:
                continue
            src_node = graph_tools.get_node(src_node_id)
            if not src_node:
                continue
            node_type = str(src_node.get("type") or "").lower()
            if node_type == "document":
                for doc_edge in graph_tools.get_node_edges(src_node_id, direction="in") or []:
                    doc_src_id = doc_edge.get("source")
                    if not doc_src_id:
                        continue
                    doc_src_node = graph_tools.get_node(doc_src_id)
                    if doc_src_node and str(doc_src_node.get("type") or "").lower() == "source":
                        referenced_source_ids.add(doc_src_node.get("id"))
            elif node_type == "source":
                referenced_source_ids.add(src_node_id)
    sources = [s for s in all_sources if s.get("id") in referenced_source_ids]
    sources.sort(key=lambda s: s.get("id") or "")
    registry: list[dict] = []
    seen: set[str] = set()
    for source in sources:
        url = source["url"]
        if url in seen:
            continue
        seen.add(url)
        registry.append({
            "n": len(registry) + 1,
            "source_id": source.get("id"),
            "title": source.get("title") or url,
            "url": url,
        })
    return registry


def get_reference_registry() -> list[dict]:
    """Return the canonical reference registry for Reporter-facing tools."""
    return build_reference_registry()


def _source_ids_for_item(item_id: str, nodes: dict[str, dict], edges: list[dict]) -> list[str]:
    """Return URL-bearing Source IDs that support one Claim or Evidence node."""
    def is_type(node_id: str, expected: str) -> bool:
        return str(nodes.get(node_id, {}).get("type") or "").lower() == expected.lower()

    source_ids: set[str] = set()
    document_ids: set[str] = set()
    statement_ids: set[str] = set()
    evidence_ids: set[str] = set()
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if target == item_id and is_type(source, "Source"):
            source_ids.add(source)
        if target == item_id and is_type(source, "Document"):
            document_ids.add(source)
        if target == item_id and is_type(source, "Statement"):
            statement_ids.add(source)
        if target == item_id and is_type(source, "Evidence"):
            evidence_ids.add(source)
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if target in statement_ids and is_type(source, "Source"):
            source_ids.add(source)
        if target in statement_ids and is_type(source, "Document"):
            document_ids.add(source)
        if target in document_ids and is_type(source, "Source"):
            source_ids.add(source)
        if target in evidence_ids and is_type(source, "Source"):
            source_ids.add(source)
        if target in evidence_ids and is_type(source, "Document"):
            document_ids.add(source)
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if target in document_ids and is_type(source, "Source"):
            source_ids.add(source)
    return sorted(
        source_id for source_id in source_ids
        if nodes.get(source_id, {}).get("url")
    )


def get_report_evidence(query_id: str, offset: int = 0, limit: int = 20) -> dict:
    """Return one compact, citation-ready page of a Query's evidence."""
    try:
        resolved_query_id = graph_tools.resolve_query_reference(query_id)
    except graph_tools.AmbiguousQueryReference as exc:
        return {"error": str(exc)}
    if resolved_query_id is None:
        return {"error": f"Unknown query reference: {query_id!r}"}
    offset = max(0, int(offset or 0))
    limit = min(100, max(1, int(limit or 20)))
    nodes = {node["id"]: node for node in graph_tools.get_all_nodes()}
    edges = graph_tools.get_all_edges()
    registry = build_reference_registry()
    registry_by_source = {entry["source_id"]: entry for entry in registry}
    evaluation = graph_tools.get_query_evaluation_subgraph(resolved_query_id)
    items: list[dict] = []
    for node in evaluation.get("nodes", []):
        if str(node.get("type") or "").lower() not in {"claim", "evidence"}:
            continue
        source_ids = [
            source_id for source_id in _source_ids_for_item(node["id"], nodes, edges)
            if source_id in registry_by_source
        ]
        if not source_ids:
            continue
        text = node.get("statement") or node.get("claim") or node.get("text")
        if not str(text or "").strip():
            continue
        stance_by_edge = {
            "supported_by": "supports",
            "contradicted_by": "contradicts",
            "qualified_by": "qualifies",
        }
        claim_relations = [
            {
                "claim_id": edge.get("target"),
                "stance": stance_by_edge[str(edge.get("type") or "").lower()],
            }
            for edge in edges
            if edge.get("source") == node["id"]
            and nodes.get(edge.get("target"), {}).get("type") == "Claim"
            and str(edge.get("type") or "").lower() in {
                "supported_by", "contradicted_by", "qualified_by",
            }
        ]
        evidence_relations = [
            {
                "evidence_id": edge.get("source"),
                "stance": stance_by_edge[str(edge.get("type") or "").lower()],
            }
            for edge in edges
            if edge.get("target") == node["id"]
            and nodes.get(edge.get("source"), {}).get("type") == "Evidence"
            and str(edge.get("type") or "").lower() in {
                "supported_by", "contradicted_by", "qualified_by",
            }
        ]
        items.append({
            "id": node["id"],
            "type": node["type"],
            "text": str(text).strip(),
            "confidence": node.get("confidence"),
            "qualifiers": node.get("qualifiers") or [],
            "limitations": node.get("limitations") or [],
            "locator": node.get("locator"),
            "claim_relations": claim_relations,
            "evidence_relations": evidence_relations,
            "source_ids": source_ids,
            "citations": [registry_by_source[source_id]["n"] for source_id in source_ids],
            "sources": [
                {
                    "source_id": source_id,
                    "title": registry_by_source[source_id]["title"],
                    "url": registry_by_source[source_id]["url"],
                    "source_type": nodes.get(source_id, {}).get("source_type"),
                    "published_at": (
                        nodes.get(source_id, {}).get("published_at")
                        or nodes.get(source_id, {}).get("publication_date")
                    ),
                }
                for source_id in source_ids
            ],
        })
    items.sort(key=lambda item: item["id"])
    page = items[offset : offset + limit]
    next_offset = offset + len(page)
    return {
        "query": {
            key: evaluation.get("query", {}).get(key)
            for key in ("id", "handle", "text", "importance")
        },
        "items": page,
        "offset": offset,
        "limit": limit,
        "total": len(items),
        "next_offset": next_offset if next_offset < len(items) else None,
    }


def commit_report_outline(output_dir: Optional[str], title: str, chapters: list[dict]) -> dict[str, Any]:
    """Persist the chapter-level report outline for the current run."""
    normalized: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for index, chapter in enumerate(chapters or [], start=1):
        chapter_id = int(chapter.get("chapter_id") or index)
        if chapter_id in seen_ids:
            chapter_id = max(seen_ids) + 1 if seen_ids else chapter_id
        seen_ids.add(chapter_id)
        query_refs = [
            str(query_id).strip()
            for query_id in chapter.get("query_refs") or []
            if str(query_id).strip()
        ]
        for query_ref in query_refs:
            try:
                resolved = graph_tools.resolve_query_reference(query_ref)
            except graph_tools.AmbiguousQueryReference:
                return {
                    "status": "error",
                    "message": f"Ambiguous query reference: {query_ref!r}",
                }
            if resolved is None:
                return {"status": "error", "message": f"Unknown query reference: {query_ref!r}"}
        normalized.append({
            "chapter_id": chapter_id,
            "title": str(chapter.get("title") or "").strip() or f"Section {chapter_id}",
            "goals": [str(goal).strip() for goal in chapter.get("goals") or [] if str(goal).strip()],
            "query_refs": list(dict.fromkeys(query_refs)),
            "section_plan": str(chapter.get("section_plan") or "").strip(),
            "section_type": chapter.get("section_type"),
            "status": str(chapter.get("status") or "pending"),
        })
    outline = {"title": str(title).strip() or "Research Report", "chapters": normalized}
    _write_json_file(_outline_path(output_dir), outline)
    _outline_markdown_path(output_dir).write_text(
        _render_outline_markdown(outline["title"], normalized),
        encoding="utf-8",
    )
    return {
        "status": "ok",
        "outline_path": str(_outline_path(output_dir)),
        "outline_markdown_path": str(_outline_markdown_path(output_dir)),
        "chapters_count": len(normalized),
    }


def _public_evidence_items(
    evidence_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Project graph evidence into chapter-local references."""
    counters = {"Claim": 0, "Evidence": 0}
    id_to_ref: dict[str, str] = {}
    for item in evidence_items:
        item_type = str(item.get("type") or "Evidence")
        counters[item_type] = counters.get(item_type, 0) + 1
        prefix = "c" if item_type == "Claim" else "e"
        id_to_ref[str(item["id"])] = f"{prefix}{counters[item_type]}"

    projected = []
    for item in evidence_items:
        projected.append({
            "ref": id_to_ref[str(item["id"])],
            "type": item.get("type"),
            "text": item.get("text"),
            "confidence": item.get("confidence"),
            "qualifiers": item.get("qualifiers") or [],
            "limitations": item.get("limitations") or [],
            "locator": item.get("locator"),
            "claim_relations": [
                {
                    "target_ref": id_to_ref.get(str(relation.get("claim_id"))),
                    "stance": relation.get("stance"),
                }
                for relation in item.get("claim_relations") or []
                if id_to_ref.get(str(relation.get("claim_id")))
            ],
            "evidence_relations": [
                {
                    "target_ref": id_to_ref.get(str(relation.get("evidence_id"))),
                    "stance": relation.get("stance"),
                }
                for relation in item.get("evidence_relations") or []
                if id_to_ref.get(str(relation.get("evidence_id")))
            ],
            "source_numbers": item.get("citations") or [],
        })
    return projected, {ref: item_id for item_id, ref in id_to_ref.items()}


def _bundle_token(chapter_id: int, resolved_query_ids: list[str], evidence_ids: list[str]) -> str:
    payload = "|".join([str(chapter_id), *resolved_query_ids, *evidence_ids])
    return f"b{chapter_id}-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:8]}"


def _prepare_report_chapter_bundle(
    output_dir: Optional[str],
    chapter_id: int,
    extra_query_refs: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Load one chapter plan together with the evidence needed to write it."""
    outline = _read_json_file(_outline_path(output_dir))
    chapters = outline.get("chapters") or []
    chapter = next((item for item in chapters if int(item.get("chapter_id") or 0) == int(chapter_id)), None)
    if chapter is None:
        return {"status": "error", "message": f"Unknown chapter_id: {chapter_id}"}

    query_refs = list(dict.fromkeys([
        *[str(query_ref).strip() for query_ref in chapter.get("query_refs") or [] if str(query_ref).strip()],
        *[str(query_ref).strip() for query_ref in extra_query_refs or [] if str(query_ref).strip()],
    ]))
    evidence_items: list[dict[str, Any]] = []
    seen_items: set[str] = set()
    resolved_query_ids: list[str] = []
    for query_ref in query_refs:
        try:
            resolved_query_id = graph_tools.resolve_query_reference(query_ref)
        except graph_tools.AmbiguousQueryReference:
            return {
                "status": "error",
                "message": f"Ambiguous query reference: {query_ref!r}",
                "chapter_id": int(chapter_id),
            }
        if resolved_query_id is None:
            return {
                "status": "error",
                "message": f"Unknown query reference: {query_ref!r}",
                "chapter_id": int(chapter_id),
            }
        resolved_query_ids.append(resolved_query_id)
        offset = 0
        while True:
            page = get_report_evidence(resolved_query_id, offset=offset, limit=100)
            if page.get("error"):
                return {"status": "error", "message": page["error"], "chapter_id": int(chapter_id)}
            for item in page.get("items", []):
                if item["id"] in seen_items:
                    continue
                evidence_items.append(item)
                seen_items.add(item["id"])
            if page.get("next_offset") is None:
                break
            offset = int(page["next_offset"])

    if not evidence_items:
        return {
            "status": "error",
            "message": "Chapter bundle contains no URL-backed Report Evidence.",
            "chapter_id": int(chapter_id),
        }

    source_ids = sorted({
        source_id
        for item in evidence_items
        for source_id in item.get("source_ids") or []
    })
    public_items, evidence_ref_map = _public_evidence_items(evidence_items)
    conflicts = [
        conflict
        for conflict in get_disclosed_conflicts()
        if set(conflict.get("source_ids") or []).intersection(source_ids)
    ]
    conflict_ref_map = {f"x{index}": str(conflict["id"]) for index, conflict in enumerate(conflicts, start=1)}
    token = _bundle_token(int(chapter_id), resolved_query_ids, [item["id"] for item in evidence_items])
    bundle = {
        "status": "ok",
        "chapter_id": int(chapter_id),
        "bundle_token": token,
        "chapter_title": chapter.get("title"),
        "chapter_goals": chapter.get("goals") or [],
        "section_plan": chapter.get("section_plan") or "",
        "query_refs": query_refs,
        "evidence_items": public_items,
        "disclosed_conflicts": [
            {
                "ref": ref,
                "description": next(
                    conflict.get("description")
                    for conflict in conflicts
                    if str(conflict.get("id")) == conflict_id
                ),
                "conflict_type": next(
                    conflict.get("conflict_type")
                    for conflict in conflicts
                    if str(conflict.get("id")) == conflict_id
                ),
            }
            for ref, conflict_id in conflict_ref_map.items()
        ],
    }
    meta = {
        "chapter_id": int(chapter_id),
        "title": chapter.get("title"),
        "bundle_token": token,
        "query_refs": query_refs,
        "resolved_query_ids": resolved_query_ids,
        "evidence_ref_map": evidence_ref_map,
        "conflict_ref_map": conflict_ref_map,
    }
    _write_json_file(_chapter_meta_path(output_dir, int(chapter_id)), meta)
    return bundle


def _resolve_chapter_id_from_outline(
    output_dir: Optional[str],
    chapter: dict[str, Any],
) -> int:
    """Resolve chapter_id from outline when not explicitly provided."""
    provided_id = int(chapter.get("chapter_id") or 0)
    if provided_id > 0:
        return provided_id

    outline = _read_json_file(_outline_path(output_dir))
    outline_chapters = outline.get("chapters") or []
    if not outline_chapters:
        return 0

    key = str(chapter.get("key") or "").strip().lower()
    title = str(chapter.get("title") or "").strip().lower()

    for i, oc in enumerate(outline_chapters, start=1):
        oc_id = int(oc.get("chapter_id") or i)
        oc_title = str(oc.get("title") or "").strip().lower()
        oc_section_type = str(oc.get("section_type") or "").strip().lower()

        # Match by key or title
        if key and (key == oc_title or key == oc_section_type):
            return oc_id
        if title and title == oc_title:
            return oc_id

        # Match by section_type (e.g. "lead" matches "lead" section)
        if key and oc_section_type and key == oc_section_type:
            return oc_id

    # Fallback: use sequential index
    return 0


def prepare_report_chapter_batch(
    output_dir: Optional[str],
    chapters: list[dict[str, Any]],
) -> dict[str, Any]:
    """Prepare up to three chapter-scoped evidence bundles."""
    if not chapters or len(chapters) > 3:
        return {"status": "error", "message": "Prepare between one and three chapters per batch."}
    prepared = []
    for chapter in chapters:
        chapter_id = _resolve_chapter_id_from_outline(output_dir, chapter)
        if chapter_id <= 0:
            prepared.append({
                "status": "error",
                "message": f"Cannot resolve chapter_id from outline. Provide chapter_id explicitly.",
            })
        else:
            prepared.append(
                _prepare_report_chapter_bundle(
                    output_dir,
                    chapter_id,
                    chapter.get("extra_query_refs") or [],
                )
            )
    errors = [item for item in prepared if item.get("status") != "ok"]
    return {
        "status": "error" if errors else "ok",
        "chapters": prepared,
        "errors": errors,
    }


def _chapter_candidate_validation(
    output_dir: Optional[str],
    chapter: dict[str, Any],
) -> dict[str, Any]:
    chapter_id = int(chapter.get("chapter_id") or 0)
    prepared_meta = _read_json_file(_chapter_meta_path(output_dir, chapter_id))
    issues: list[dict[str, Any]] = []
    token_matches = bool(prepared_meta) and chapter.get("bundle_token") == prepared_meta.get("bundle_token")
    if not token_matches:
        issues.append(_issue(
            "stale_bundle_token",
            "hard",
            f"chapter {chapter_id} used an unknown or stale bundle token",
            "Reload this chapter bundle and use its local references.",
        ))

    evidence_ref_map = prepared_meta.get("evidence_ref_map") or {}
    conflict_ref_map = prepared_meta.get("conflict_ref_map") or {}
    evidence_refs = list(dict.fromkeys(chapter.get("evidence_refs") or []))
    conflict_refs = list(dict.fromkeys(chapter.get("disclosed_conflict_refs") or []))
    unknown_evidence_refs = [ref for ref in evidence_refs if ref not in evidence_ref_map]
    unknown_conflict_refs = [ref for ref in conflict_refs if ref not in conflict_ref_map]
    if unknown_evidence_refs:
        issues.append(_issue(
            "unknown_evidence_refs",
            "hard",
            f"chapter {chapter_id} used unknown local evidence refs: {unknown_evidence_refs}",
            "Use only refs returned by this chapter bundle.",
        ))
    if unknown_conflict_refs:
        issues.append(_issue(
            "unknown_conflict_refs",
            "hard",
            f"chapter {chapter_id} used unknown local conflict refs: {unknown_conflict_refs}",
            "Use only conflict refs returned by this chapter bundle.",
        ))
    if not evidence_refs:
        issues.append(_issue(
            "missing_evidence_refs",
            "hard",
            f"chapter {chapter_id} selected no local evidence refs",
            "Select the local refs actually used by this chapter.",
        ))

    evidence_ids = [evidence_ref_map[ref] for ref in evidence_refs if ref in evidence_ref_map] if token_matches else []
    conflict_ids = [conflict_ref_map[ref] for ref in conflict_refs if ref in conflict_ref_map] if token_matches else []
    nodes = {node["id"]: node for node in graph_tools.get_all_nodes()}
    edges = graph_tools.get_all_edges()
    registry = build_reference_registry()
    registry_by_url = {entry["url"]: entry for entry in registry}
    source_ids = sorted({
        registry_by_url[nodes[source_id]["url"]]["source_id"]
        for item_id in evidence_ids
        for source_id in _source_ids_for_item(item_id, nodes, edges)
        if nodes.get(source_id, {}).get("url") in registry_by_url
    })
    registry_by_number = {entry["n"]: entry for entry in registry}
    cited_numbers = {int(value) for value in _CITE_TOKEN_RE.findall(str(chapter.get("content") or ""))}
    invalid_citations = sorted(
        number for number in cited_numbers
        if registry_by_number.get(number, {}).get("source_id") not in source_ids
    )
    if invalid_citations:
        issues.append(_issue(
            "unsupported_inline_citations",
            "hard",
            f"chapter {chapter_id} cites sources not supported by its local evidence refs: {invalid_citations}",
            "Use citation numbers attached to the selected local evidence refs.",
        ))
    return {
        "validated": not issues,
        "issues": issues,
        "evidence_ids": evidence_ids,
        "source_ids": source_ids,
        "disclosed_conflict_ids": conflict_ids,
        "unknown_evidence_refs": unknown_evidence_refs,
        "unknown_conflict_refs": unknown_conflict_refs,
    }


def commit_report_chapter_batch(
    output_dir: Optional[str],
    chapters: list[dict[str, Any]],
) -> dict[str, Any]:
    """Save and validate up to three chapter candidates."""
    if not chapters or len(chapters) > 3:
        return {"status": "error", "message": "Commit between one and three chapters per batch."}
    outline_path = _outline_path(output_dir)
    outline = _read_json_file(outline_path)
    outline_by_id = {
        int(item.get("chapter_id") or 0): item
        for item in outline.get("chapters") or []
    }
    results = []
    for candidate in chapters:
        chapter_id = int(candidate.get("chapter_id") or 0)
        outline_chapter = outline_by_id.get(chapter_id)
        if outline_chapter is None:
            results.append({
                "chapter_id": chapter_id,
                "candidate_saved": False,
                "validated": False,
                "issues": [_issue(
                    "unknown_chapter",
                    "hard",
                    f"unknown chapter_id: {chapter_id}",
                    "Use a chapter from the committed outline.",
                )],
            })
            continue

        content = str(candidate.get("content") or "").strip()
        _chapter_path(output_dir, chapter_id).write_text(content + "\n", encoding="utf-8")
        validation = _chapter_candidate_validation(output_dir, candidate)
        outline_chapter.update({
            "title": str(candidate.get("title") or outline_chapter.get("title") or f"Section {chapter_id}"),
            "status": "completed",
            "section_type": candidate.get("section_type") or outline_chapter.get("section_type"),
            "validated": validation["validated"],
            "source_ids": validation["source_ids"],
            "evidence_ids": validation["evidence_ids"],
            "disclosed_conflict_ids": validation["disclosed_conflict_ids"],
            "validation_issues": validation["issues"],
        })
        meta = _read_json_file(_chapter_meta_path(output_dir, chapter_id))
        meta.update({
            "title": outline_chapter["title"],
            "section_type": outline_chapter["section_type"],
            "validated": validation["validated"],
            "source_ids": validation["source_ids"],
            "evidence_ids": validation["evidence_ids"],
            "disclosed_conflict_ids": validation["disclosed_conflict_ids"],
            "validation_issues": validation["issues"],
        })
        _write_json_file(_chapter_meta_path(output_dir, chapter_id), meta)
        results.append({
            "chapter_id": chapter_id,
            "candidate_saved": True,
            "validated": validation["validated"],
            "issues": validation["issues"],
            "unknown_evidence_refs": validation["unknown_evidence_refs"],
            "unknown_conflict_refs": validation["unknown_conflict_refs"],
        })

    _write_json_file(outline_path, outline)
    _outline_markdown_path(output_dir).write_text(
        _render_outline_markdown(outline.get("title") or "Research Report", outline.get("chapters") or []),
        encoding="utf-8",
    )
    return {
        "status": "ok",
        "chapters": results,
        "validated": all(item.get("validated") for item in results),
    }


def _load_committed_report(output_dir: Optional[str]) -> tuple[str, list[dict], list[int]]:
    """Load the outline title and every committed chapter in outline order."""
    outline = _read_json_file(_outline_path(output_dir))
    chapters = outline.get("chapters") or []
    sections: list[dict[str, Any]] = []
    missing: list[int] = []
    for chapter in sorted(chapters, key=lambda item: int(item.get("chapter_id") or 0)):
        chapter_id = int(chapter.get("chapter_id") or 0)
        content_path = _chapter_path(output_dir, chapter_id)
        if not content_path.exists():
            missing.append(chapter_id)
            continue
        content = content_path.read_text(encoding="utf-8").strip()
        sections.append({
            "title": str(chapter.get("title") or "").strip() or f"Section {chapter_id}",
            "content": content,
            "source_ids": list(dict.fromkeys(chapter.get("source_ids") or [])),
            "evidence_ids": list(dict.fromkeys(chapter.get("evidence_ids") or [])),
            "disclosed_conflict_ids": list(dict.fromkeys(chapter.get("disclosed_conflict_ids") or [])),
            "section_type": chapter.get("section_type"),
        })
    return str(outline.get("title") or "Research Report"), sections, missing


def _fallback_chapter_content(bundle: dict[str, Any], *, lead: bool) -> str:
    """Render a deterministic, citation-ready chapter when the Reporter omitted one."""
    items = [
        item for item in bundle.get("evidence_items") or []
        if str(item.get("text") or "").strip()
    ]
    limit = 4 if lead else 8
    paragraphs = []
    seen_text: set[str] = set()
    for item in items:
        text = str(item.get("text") or "").strip().rstrip("。.")
        normalized = re.sub(r"\s+", " ", text).casefold()
        if not text or normalized in seen_text:
            continue
        seen_text.add(normalized)
        citations = "".join(f"[{number}]" for number in item.get("source_numbers") or [])
        paragraphs.append(f"{text}。{citations}" if re.search(r"[\u4e00-\u9fff]", text) else f"{text}.{citations}")
        if len(paragraphs) >= limit:
            break
    if paragraphs:
        return "\n\n".join(paragraphs)
    return "暂无可核实结论。" if lead else "暂无可核实的补充资料。"


def _ensure_candidate_chapters(output_dir: Optional[str]) -> list[dict[str, Any]]:
    """Create deterministic candidate files for any outlined chapter the Reporter omitted."""
    outline_path = _outline_path(output_dir)
    outline = _read_json_file(outline_path)
    generated_issues = []
    for chapter in sorted(outline.get("chapters") or [], key=lambda item: int(item.get("chapter_id") or 0)):
        chapter_id = int(chapter.get("chapter_id") or 0)
        if _chapter_path(output_dir, chapter_id).exists():
            continue
        bundle = _prepare_report_chapter_bundle(output_dir, chapter_id)
        content = _fallback_chapter_content(
            bundle,
            lead=chapter.get("section_type") == "lead" or chapter_id == 1,
        )
        _chapter_path(output_dir, chapter_id).write_text(content + "\n", encoding="utf-8")
        issue = _issue(
            "deterministic_fallback_chapter",
            "hard",
            f"chapter {chapter_id} was generated from its evidence bundle because no Reporter candidate existed",
            "Provide a Reporter-authored chapter in a future run.",
            section_title=str(chapter.get("title") or ""),
        )
        chapter.update({
            "status": "completed",
            "section_type": chapter.get("section_type") or ("lead" if chapter_id == 1 else "body"),
            "validated": False,
            "source_ids": [],
            "evidence_ids": [],
            "disclosed_conflict_ids": [],
            "validation_issues": [issue],
        })
        meta = _read_json_file(_chapter_meta_path(output_dir, chapter_id))
        meta.update({
            "chapter_id": chapter_id,
            "title": chapter.get("title"),
            "section_type": chapter.get("section_type"),
            "validated": False,
            "source_ids": [],
            "evidence_ids": [],
            "disclosed_conflict_ids": [],
            "validation_issues": [issue],
        })
        _write_json_file(_chapter_meta_path(output_dir, chapter_id), meta)
        generated_issues.append(issue)
    if outline:
        _write_json_file(outline_path, outline)
    return generated_issues


def _best_effort_report(title: str, sections: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Compile every candidate section without discarding prose on validation failure."""
    registry = build_reference_registry()
    registry_by_number = {entry["n"]: entry for entry in registry}
    compiled_sections = []
    cited_source_ids: set[str] = set()
    issues: list[dict[str, Any]] = []
    for section in sections:
        content = str(section.get("content") or "").strip()
        invalid_numbers = sorted({
            int(value)
            for value in _CITE_TOKEN_RE.findall(content)
            if int(value) not in registry_by_number
        })
        if invalid_numbers:
            invalid_set = set(invalid_numbers)
            content = _CITE_TOKEN_RE.sub(
                lambda match: "" if int(match.group(1)) in invalid_set else match.group(0),
                content,
            )
            issues.append(_issue(
                "unknown_inline_citations_removed",
                "hard",
                f"section {section.get('title')!r} contained unknown citation numbers: {invalid_numbers}",
                "Use citation numbers from the chapter bundle.",
                section_title=str(section.get("title") or ""),
            ))
        cited_numbers = {int(value) for value in _CITE_TOKEN_RE.findall(content)}
        source_ids = sorted({
            registry_by_number[number]["source_id"]
            for number in cited_numbers
            if number in registry_by_number
        })
        cited_source_ids.update(source_ids)
        compiled_sections.append({
            "title": str(section.get("title") or "").strip() or "Section",
            "content": _compile_section_content(content, source_ids, {}),
            "source_ids": source_ids,
            "evidence_ids": list(section.get("evidence_ids") or []),
            "section_type": section.get("section_type"),
            "disclosed_conflict_ids": list(section.get("disclosed_conflict_ids") or []),
        })
    request_text = " ".join(
        str(goal.get("request") or goal.get("research_goal") or "")
        for goal in graph_tools.search_nodes("user_request", {})
    )
    report = _compile_section_report(
        title,
        compiled_sections,
        registry,
        cited_source_ids,
        wikipedia_task=is_wikipedia_task(request_text),
    )
    return report, issues


def submit_committed_report(output_dir: Optional[str], *, persist: bool = False) -> dict[str, Any]:
    """Compile and always deliver the latest chapter candidates."""
    generated_issues = _ensure_candidate_chapters(output_dir)
    title, sections, missing = _load_committed_report(output_dir)
    if not sections and not missing:
        request_text = " ".join(
            str(goal.get("request") or goal.get("research_goal") or "")
            for goal in graph_tools.search_nodes("user_request", {})
        )
        fallback = build_cited_evidence_report(request_text)
        issue = _issue(
            "missing_report_outline",
            "hard",
            "Reporter created no outline; delivered the deterministic evidence report",
            "Create an outline and chapter candidates in a future run.",
        )
        return {
            "delivered": bool(fallback.strip()),
            "validated": False,
            "accepted": False,
            "revision_requested": False,
            "severity": "hard",
            "report": fallback,
            "salvaged_report": fallback,
            "graph_persisted": False,
            "issues": [issue],
        }
    chapter_issues = [
        issue
        for chapter in _read_json_file(_outline_path(output_dir)).get("chapters") or []
        for issue in chapter.get("validation_issues") or []
    ]
    chapters_validated = bool(sections) and not missing and all(
        bool(chapter.get("validated"))
        for chapter in _read_json_file(_outline_path(output_dir)).get("chapters") or []
    )
    strict = compile_structured_report(
        title,
        sections,
        persist=False,
    )
    validated = bool(
        chapters_validated
        and strict.get("report")
        and not strict.get("issues")
    )
    graph_persisted = False
    if persist and validated:
        persisted = compile_structured_report(title, sections, persist=True)
        graph_persisted = bool(
            persisted.get("report")
            and not persisted.get("issues")
        )
    best_effort, best_effort_issues = _best_effort_report(title, sections)
    report = str(strict.get("report") or best_effort)
    issues = [*generated_issues, *chapter_issues, *strict.get("issues", []), *best_effort_issues]
    severity = "hard" if any(item.get("severity") == "hard" for item in issues) else ("soft" if issues else "clean")
    return {
        **{key: value for key, value in strict.items() if key not in {
            "accepted", "revision_requested", "severity", "report", "salvaged_report", "issues",
            "auto_appended_conflict_ids",
        }},
        "delivered": bool(report.strip()),
        "validated": validated,
        "accepted": validated,
        "revision_requested": False,
        "severity": severity,
        "report": report,
        "salvaged_report": "" if validated else report,
        "graph_persisted": graph_persisted,
        "issues": issues,
    }


def get_committed_review_context(output_dir: Optional[str]) -> dict[str, Any]:
    """Return only the evidence and references used by committed chapters."""
    _, sections, missing = _load_committed_report(output_dir)
    selected_ids = {
        item_id
        for section in sections
        for item_id in section.get("evidence_ids") or []
    }
    source_ids = {
        source_id
        for section in sections
        for source_id in section.get("source_ids") or []
    }
    selected_items: dict[str, dict] = {}
    for query in graph_tools.search_nodes("query", {}):
        offset = 0
        while True:
            page = get_report_evidence(query["id"], offset=offset, limit=100)
            if page.get("error"):
                break
            for item in page.get("items", []):
                if item.get("id") in selected_ids:
                    selected_items[item["id"]] = item
            if page.get("next_offset") is None:
                break
            offset = int(page["next_offset"])
    return {
        "missing_chapter_ids": missing,
        "report_evidence": [
            {
                "type": item.get("type"),
                "text": item.get("text"),
                "confidence": item.get("confidence"),
                "qualifiers": item.get("qualifiers") or [],
                "limitations": item.get("limitations") or [],
                "locator": item.get("locator"),
                "citation_numbers": item.get("citations") or [],
                "sources": [
                    {key: source.get(key) for key in ("title", "url", "source_type", "published_at")}
                    for source in item.get("sources") or []
                ],
            }
            for item_id in sorted(selected_items)
            for item in [selected_items[item_id]]
        ],
        "reference_registry": [
            {key: item.get(key) for key in ("n", "title", "url", "source_type", "published_at")}
            for item in build_reference_registry()
            if item.get("source_id") in source_ids
        ],
    }


def _render_references(registry: list[dict], cited_source_ids: set[str], label: str) -> str:
    """Render canonical URL-backed references for the selected Source IDs."""
    lines = [f"## {label}", ""]
    for entry in registry:
        if entry["source_id"] not in cited_source_ids:
            continue
        if entry["title"] == entry["url"]:
            lines.append(f"[{entry['n']}] {entry['url']}")
        else:
            lines.append(f"[{entry['n']}] {entry['title']} {entry['url']}")
        lines.append("")
    return "\n".join(lines).rstrip()


def sanitize_report(report_text: str) -> str:
    """Remove internal-process explanations and service-offer paragraphs."""
    text = report_text or ""
    text = _LOCAL_REF_RE.sub("", text)
    kept: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        stripped = block.strip()
        if not stripped or _FORBIDDEN_META_RE.search(stripped):
            continue
        kept.append(stripped)
    return "\n\n".join(kept).strip() + ("\n" if kept else "")


def _reference_entries(report_text: str) -> dict[int, str]:
    """Return numbered URL-bearing reference entries from report Markdown."""
    result: dict[int, str] = {}
    for line in (report_text or "").splitlines():
        match = re.match(r"^\[(\d{1,4})\]\s+.*?(https?://\S+)\s*$", line.strip())
        if match:
            result[int(match.group(1))] = match.group(2).rstrip(".,，。);）]")
    return result


def _body_units(report_text: str) -> list[str]:
    """Return prose paragraphs and individual list items before references."""
    ref_match = _REF_HEADING_RE.search(report_text or "")
    body = report_text[: ref_match.start()] if ref_match else report_text
    units: list[str] = []
    for block in re.split(r"\n\s*\n", body):
        lines = [
            line.strip() for line in block.splitlines()
            if line.strip() and not line.lstrip().startswith("#") and line.strip() != "---"
        ]
        paragraph: list[str] = []
        for line in lines:
            if re.match(r"^(?:[-*+]|\d+[.)])\s+", line):
                if paragraph:
                    units.append(" ".join(paragraph))
                    paragraph = []
                units.append(line)
            else:
                paragraph.append(line)
        if paragraph:
            units.append(" ".join(paragraph))
    return units


def validate_delivery_invariants(report_text: str) -> list[str]:
    """Return hard delivery violations for citations and forbidden prose."""
    text = report_text or ""
    issues: list[str] = []
    if _FORBIDDEN_META_RE.search(text):
        issues.append("forbidden internal-process or service-offer prose")
    references = _reference_entries(text)
    for unit in _body_units(text):
        if unit in _NO_FINDINGS_TEXT:
            continue
        citations = [int(match.group(1)) for match in _CITE_TOKEN_RE.finditer(unit)]
        if not citations:
            issues.append(f"uncited factual paragraph or list item: {unit[:80]}")
            continue
        for citation in citations:
            if citation not in references:
                issues.append(f"citation has no URL-backed reference: [{citation}]")
    return list(dict.fromkeys(issues))


def validate_report_quality(report_text: str) -> list[str]:
    """Return narrow quality-gate violations only."""
    text = report_text or ""
    issues: list[str] = []
    if _PLACEHOLDER_RE.search(text):
        issues.append("report body contains placeholder or brevity markers")
    if _EXTERNAL_FILE_RE.search(text):
        issues.append("report body redirects the reader to an external file")
    if any(_REFERENCE_ONLY_RE.match(unit.strip()) for unit in _body_units(text)):
        issues.append("report body contains reference-only placeholder prose")
    headings = _REF_HEADING_RE.findall(text)
    if len(headings) > 1 or _REFERENCE_VARIANT_RE.search(text):
        issues.append("report contains multiple or variant references sections")
    return list(dict.fromkeys(issues))


_INFOBOX_RE = re.compile(r"^\s*\|.*\|\s*\n\s*\|[\s-]+\|\s*\n", re.MULTILINE)
_REPORTER_META_NARRATIVE_TERMS = (
    r"supplied\s+(?:material|evidence|data)", r"the\s+supplied",
    r"provided\s+(?:material|evidence)", r"available\s+(?:material|evidence)",
    r"本研究", r"本次检索", r"本轮", r"研究图谱", r"摘要线索", r"未读取正文",
    r"source\s+节点", r"evidence\s+节点",
    r"should\s+not\s+be\s+(?:treated|taken|regarded|considered|used)\s+as",
    r"should\s+not\s+be\s+used\s+to", r"do\s+not\s+amount\s+to\s+a\s+\w+",
    r"rather\s+than\s+a\s+(?:definitive|secure|reliable|forensic)\s+\w+",
    r"not\s+a\s+(?:securely|reliably)\s+documented", r"concern\s+reported\s+\w+",
    r"reported\s+reconstructions", r"further\s+(?:catalogue|catalog)\s+verification",
    r"so-called\s+", r"(?:purported|alleged)\s+(?:Ring|Nestor|the\s+\w+\s+ring)",
    r"some\s+(?:interpretations?|scholars?|researchers?|experts?)\s+(?:regard|argue|believe|suggest|state|note|consider|claim)",
    r"a\s+(?:discussion|study|paper)\s+(?:reports|states|notes|suggests|claims)",
    r"a\s+\d{4}\s+discussion\s+(?:reports|states|notes|suggests)",
    r"it\s+has\s+been\s+(?:argued|suggested|noted|proposed)",
    r"scholars\s+have\s+(?:discussed|noted|argued|suggested)",
    r"many\s+scholars\s+(?:believe|argue|consider|regard)",
    r"one\s+(?:position|view)\s+(?:treats|holds|regards|considers)",
    r"the\s+other\s+position\s+(?:treats|holds|regards|considers)",
    r"arguments\s+(?:advanced|have\s+been\s+advanced)\s+in\s+the\s+debate",
    r"some\s+(?:argue|contend)\s+that", r"the\s+debate\s+involves",
    r"are\s+best\s+presented\s+as\s+\w+\s+rather\s+than",
    r"rather\s+than\s+as\s+an?\s+uncontested",
    r"do\s+not,?\s+(?:by\s+themselves|alone|on\s+their\s+own),?\s+(?:establish|demonstrate|prove)",
    r"do\s+not\s+(?:establish|demonstrate|prove)\s+that",
    r"the\s+evidence\s+does\s+not\s+(?:reconcile|establish|support|demonstrate)",
    r"remains\s+(?:contested|unresolved|undetermined)\s+rather\s+than",
    r"parts\s+of\s+the\s+recorded\s+history\s+of\s+the\s+object\s+rather\s+than",
    r"reportedly\s+(?:discovered|found|excavated|dated|uncovered)",
    r"reports\s+that\s+(?:the\s+(?:ring|object)\s+(?:was|is)\s+(?:discovered|found))",
)


def check_report_quality(report_text: str) -> list[str]:
    """Return the Reporter prose checks used during the single revision round."""
    text = report_text or ""
    if not text.strip():
        return ["报告为空"]

    request_text = ""
    evidence_count = 0
    try:
        requests = graph_tools.search_nodes("user_request", {})
        if requests:
            request_text = str(requests[0].get("request") or "").casefold()
        evidence_count = len(graph_tools.search_nodes("evidence", {}))
    except Exception:  # noqa: BLE001 - quality checks remain fail-open
        pass

    issues: list[str] = []
    is_wikipedia = "wikipedia" in request_text or "维基百科" in request_text
    has_infobox = bool(_INFOBOX_RE.search(text))
    if is_wikipedia and not has_infobox:
        issues.append("Wikipedia 风格报告缺少 Infobox（Markdown pipe table），必须在 Lead 之后插入")
    if is_wikipedia and has_infobox:
        lines = text.splitlines()
        title_idx = next((i for i, line in enumerate(lines) if line.strip().startswith("#")), -1)
        first_line = next((line.strip() for line in lines[title_idx + 1 if title_idx >= 0 else 0:] if line.strip()), "")
        if first_line.startswith("|"):
            issues.append(
                "Lead 散文必须在 Infobox 之前：当前标题后第一行是表格，应先写概括主题的散文导言，"
                "Infobox 放在 Lead 段落之后"
            )

    meta_found = []
    for term_re in _REPORTER_META_NARRATIVE_TERMS:
        matches = re.findall(term_re, text, re.IGNORECASE)
        if matches:
            meta_found.append(f"'{matches[0]}'")
    if meta_found:
        issues.append(f"报告中包含元叙述/模糊归因短语：{', '.join(meta_found[:5])}")

    heading_count = len(re.findall(r"^##\s+", text, re.MULTILINE))
    min_headings = 5 if evidence_count >= 30 else 3
    if is_wikipedia and heading_count < min_headings:
        issues.append(
            f"Wikipedia 风格报告章节数不足（当前 {heading_count} 个 ## 标题，"
            f"证据 {evidence_count} 条，建议至少 {min_headings} 个主体章节，按维度独立分节）"
        )
    return issues


def _conflict_evidence_ids(conflict_id: str, edges: list[dict]) -> list[str]:
    """返回与一个披露冲突关联的 Evidence ID."""
    return list(dict.fromkeys(
        edge.get("target")
        for edge in edges
        if edge.get("source") == conflict_id and str(edge.get("type") or "").lower() == "has_conflict"
    ))


def _conflict_source_ids(conflict_id: str, nodes: dict[str, dict], edges: list[dict]) -> list[str]:
    """返回支撑一个披露冲突且包含 URL 的 Source ID."""
    source_ids: list[str] = []
    for evidence_id in _conflict_evidence_ids(conflict_id, edges):
        source_ids.extend(_source_ids_for_item(evidence_id, nodes, edges))
    return list(dict.fromkeys(source_id for source_id in source_ids if source_id in nodes))


def get_disclosed_conflicts() -> list[dict[str, Any]]:
    """Return disclosed conflicts with stable IDs and citation-ready source bindings."""
    nodes = {node["id"]: node for node in graph_tools.get_all_nodes()}
    edges = graph_tools.get_all_edges()
    conflicts = []
    for item in graph_tools.search_nodes("conflict", {}):
        if item.get("resolution_status") != "disclosed":
            continue
        conflicts.append({
            "id": item.get("id"),
            "description": str(item.get("description") or "").strip(),
            "conflict_type": item.get("conflict_type"),
            "evidence_ids": _conflict_evidence_ids(str(item.get("id") or ""), edges),
            "source_ids": _conflict_source_ids(str(item.get("id") or ""), nodes, edges),
        })
    conflicts.sort(key=lambda item: item.get("id") or "")
    return conflicts


def _conflict_section_title(is_chinese: bool) -> str:
    """Return the localized conflict-disclosure section title."""
    return "冲突披露" if is_chinese else "Disclosed Conflicts"


def is_wikipedia_task(request_text: str) -> bool:
    """判断用户是否要求 Wikipedia 风格的条目."""
    normalized = str(request_text or "").casefold()
    return "wikipedia" in normalized or "维基百科" in normalized


def _conflict_section_paragraph(conflict: dict[str, Any], registry_by_source: dict[str, dict], is_chinese: bool) -> tuple[str, set[str]]:
    """Render one standardized conflict-disclosure paragraph."""
    source_ids = [
        source_id for source_id in dict.fromkeys(conflict.get("source_ids") or [])
        if source_id in registry_by_source
    ]
    citations = "".join(f"[{registry_by_source[source_id]['n']}]" for source_id in source_ids)
    description = str(conflict.get("description") or "").strip().rstrip("。.")
    paragraph = (
        f"公开资料对以下问题仍存在未消解分歧：{description}。{citations}"
        if is_chinese else
        f"Public sources still contain unresolved disagreement on the following point: {description}. {citations}"
    )
    return paragraph.strip(), set(source_ids)


def _append_missing_conflicts(
    compiled_sections: list[dict[str, Any]],
    registry_by_source: dict[str, dict],
    is_chinese: bool,
    auto_append: bool = True,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Ensure every disclosed conflict is structurally covered in the compiled report."""
    disclosed_conflicts = [
        item
        for item in get_disclosed_conflicts()
        if item.get("id")
        and item.get("description")
        and item.get("evidence_ids")
        and item.get("source_ids")
    ]
    if not disclosed_conflicts:
        return compiled_sections, [], []

    covered_ids: set[str] = set()
    conflict_section_index: Optional[int] = None
    for index, section in enumerate(compiled_sections):
        section_ids = section.get("disclosed_conflict_ids") or []
        covered_ids.update(str(conflict_id) for conflict_id in section_ids if conflict_id)
        if (
            section.get("section_type") == "conflict_disclosure"
            or section.get("title") == _conflict_section_title(is_chinese)
        ):
            conflict_section_index = index

    missing = [item for item in disclosed_conflicts if item["id"] not in covered_ids]
    if not missing:
        return compiled_sections, [], []
    if not auto_append:
        return compiled_sections, [], [str(item["id"]) for item in missing]

    added_ids: list[str] = []
    paragraphs: list[str] = []
    evidence_ids: set[str] = set()
    source_ids: set[str] = set()
    for conflict in missing:
        paragraph, conflict_sources = _conflict_section_paragraph(conflict, registry_by_source, is_chinese)
        if not paragraph or not conflict_sources:
            continue
        paragraphs.append(paragraph)
        evidence_ids.update(str(item_id) for item_id in conflict.get("evidence_ids") or [] if item_id)
        source_ids.update(conflict_sources)
        added_ids.append(str(conflict["id"]))

    if not paragraphs:
        return compiled_sections, [], [str(item["id"]) for item in missing]

    if conflict_section_index is None:
        compiled_sections.append({
            "title": _conflict_section_title(is_chinese),
            "content": "\n\n".join(paragraphs),
            "source_ids": sorted(source_ids),
            "evidence_ids": sorted(evidence_ids),
            "section_type": "conflict_disclosure",
            "disclosed_conflict_ids": added_ids,
        })
    else:
        section = compiled_sections[conflict_section_index]
        section["content"] = "\n\n".join([section["content"], *paragraphs]).strip()
        section["source_ids"] = sorted(set(section.get("source_ids") or []) | source_ids)
        section["evidence_ids"] = sorted(set(section.get("evidence_ids") or []) | evidence_ids)
        existing_ids = [str(conflict_id) for conflict_id in section.get("disclosed_conflict_ids") or [] if conflict_id]
        section["disclosed_conflict_ids"] = list(dict.fromkeys(existing_ids + added_ids))
        section["section_type"] = "conflict_disclosure"

    return compiled_sections, added_ids, []


def _issue(
    code: str,
    severity: str,
    message: str,
    repair_hint: str,
    section_title: str = "",
    block_index: Optional[int] = None,
) -> dict[str, Any]:
    """Build one structured report-validation issue."""
    return {
        "code": code,
        "severity": severity,
        "section_title": section_title,
        "block_index": block_index,
        "message": message,
        "repair_hint": repair_hint,
    }


def _is_reserved_section_title(title: str) -> bool:
    """Return True when a section title collides with the references area."""
    normalized = re.sub(r"\s+", " ", str(title or "").strip()).lower()
    return normalized in _RESERVED_SECTION_TITLES


def _unmet_objective_fragments() -> list[str]:
    """返回不得复制到正文的标准化内部契约文本."""
    objectives = graph_tools.search_nodes("analysis", {"analysis_type": "objective"})
    raw_fragments = [
        value
        for objective in objectives
        if objective.get("requirement") == "must" and objective.get("status") != "satisfied"
        for value in [
            objective.get("description") or objective.get("text"),
            *(
                objective.get("unmet_acceptance_criteria")
                if isinstance(objective.get("unmet_acceptance_criteria"), list)
                else objective.get("acceptance_criteria") or []
            ),
        ]
        if isinstance(value, str)
    ]
    normalized = {
        re.sub(r"\s+", " ", value).strip().casefold()
        for value in raw_fragments
        if len(re.sub(r"\s+", " ", value).strip()) >= 12
    }
    return sorted(normalized, key=len, reverse=True)


def _normalize_disclosure_text(value: Any) -> str:
    """标准化读者可见的不确定性文本，供精确内容校验."""
    return re.sub(r"\s+", " ", str(value or "")).strip().rstrip("。.").casefold()


def _strip_embedded_references(content: str) -> tuple[str, bool]:
    """Drop any embedded references block from one section body."""
    match = _REF_HEADING_RE.search(content or "")
    if match is None:
        return str(content or "").strip(), False
    return str(content or "")[: match.start()].rstrip(), True


def _sanitize_section_blocks(content: str) -> tuple[list[str], list[int], bool]:
    """Remove forbidden meta prose from a section while preserving normal blocks."""
    cleaned, had_embedded_refs = _strip_embedded_references(content)
    blocks: list[str] = []
    removed_indexes: list[int] = []
    for index, block in enumerate(re.split(r"\n\s*\n", cleaned), start=1):
        stripped = block.strip()
        if not stripped:
            continue
        if _FORBIDDEN_META_RE.search(stripped):
            removed_indexes.append(index)
            continue
        blocks.append(stripped)
    return blocks, removed_indexes, had_embedded_refs


def _compile_section_content(content: str, source_ids: list[str], registry_by_source: dict[str, dict]) -> str:
    """Sanitize one chapter body while preserving Reporter-authored citations."""
    del source_ids, registry_by_source
    blocks, _, _ = _sanitize_section_blocks(content)
    return "\n\n".join(item.strip() for item in blocks if item.strip()).strip()


def _strip_leading_heading(content: str) -> str:
    """Remove a leading ATX markdown heading (## Title) if present in the content.

    Prevents duplicate headings when the LLM includes a section heading in the content
    and the system also adds one.
    """
    lines = content.strip().split("\n")
    if not lines:
        return content
    # Check if first non-empty line is an ATX heading
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^#{1,6}\s+", stripped):
            # Skip this heading line and any immediately following blank lines
            remaining = lines[i + 1:]
            while remaining and not remaining[0].strip():
                remaining = remaining[1:]
            return "\n".join(remaining).strip()
        break
    return content


def _compile_section_report(
    title: str,
    compiled_sections: list[dict[str, Any]],
    registry: list[dict],
    cited_source_ids: set[str],
    wikipedia_task: bool = False,
) -> str:
    """Render a structured report from already-validated sections.

    Renumbers in-text citations contiguously by first-appearance order so that
    the references section has no gaps (e.g. [1][2][3] instead of [1][3][5]).
    """
    is_chinese = bool(re.search(r"[\u4e00-\u9fff]", title or ""))
    report_title = str(title or ("调研报告" if is_chinese else "Research Report")).strip()
    parts = [f"# {report_title}"]
    for section in compiled_sections:
        content = _strip_leading_heading(section["content"])
        if wikipedia_task and section.get("section_type") == "lead":
            parts.append(content)
        else:
            parts.extend([f"## {section['title']}", content])

    raw_body = "\n\n".join(parts)

    registry_by_number = {entry["n"]: entry for entry in registry}
    cited_source_ids = {sid for sid in cited_source_ids if sid}

    first_seen_numbers: list[int] = []
    seen_numbers: set[int] = set()
    for token in _CITE_TOKEN_RE.finditer(raw_body):
        old_num = int(token.group(1))
        if old_num in seen_numbers:
            continue
        entry = registry_by_number.get(old_num)
        if entry is None or entry["source_id"] not in cited_source_ids:
            continue
        seen_numbers.add(old_num)
        first_seen_numbers.append(old_num)

    old_to_new: dict[int, int] = {old: i + 1 for i, old in enumerate(first_seen_numbers)}

    def _renumber(match: re.Match) -> str:
        old = int(match.group(1))
        new = old_to_new.get(old)
        return f"[{new}]" if new is not None else ""

    renumbered_body = _CITE_TOKEN_RE.sub(_renumber, raw_body)

    cited_registry_entries = [
        registry_by_number[old_num]
        for old_num in first_seen_numbers
        if old_num in registry_by_number
    ]

    references_text = _render_references(
        _renumber_registry(cited_registry_entries, old_to_new),
        {entry["source_id"] for entry in cited_registry_entries},
        "参考文献" if is_chinese else "References",
    )

    return sanitize_report(f"{renumbered_body}\n\n{references_text}")


def _renumber_registry(
    entries: list[dict],
    old_to_new: dict[int, int],
) -> list[dict]:
    """Renumber a subset of registry entries using the old→new mapping."""
    renumbered: list[dict] = []
    for entry in entries:
        new_n = old_to_new.get(entry["n"], entry["n"])
        renumbered.append({**entry, "n": new_n})
    return renumbered


def _validate_compiled_report_content(report_text: str) -> list[str]:
    """Validate report content before section bindings are persisted."""
    text = report_text or ""
    issues = [
        f"internal process term leaked into report: {term}"
        for term in _INTERNAL_TERMS
        if term.lower() in text.lower()
    ]
    ref_match = _REF_HEADING_RE.search(text)
    body = text[: ref_match.start()] if ref_match else text
    for section in _parse_sections(body):
        if len(section["content"]) >= 80 and not section["cites"]:
            issues.append(f"factual report section has no citation: {section['title']}")
    return list(dict.fromkeys(issues))


def _persist_compiled_sections(compiled_sections: list[dict[str, Any]]) -> None:
    """Persist section-to-source bindings for an accepted structured report."""
    for section in compiled_sections:
        section_id = graph_tools.create_report_section(
            section["title"], section["content"], section["section_type"]
        )
        evidence_ids: list[str] = []
        claim_ids: list[str] = []
        for item_id in section.get("evidence_ids") or []:
            node_type = str(graph_tools.get_node(item_id).get("type") or "").lower()
            if node_type == "evidence":
                evidence_ids.append(item_id)
            elif node_type == "claim":
                claim_ids.append(item_id)
        if (evidence_ids or claim_ids) and hasattr(graph_tools, "bind_evidence_to_section"):
            try:
                graph_tools.bind_evidence_to_section(
                    section_id,
                    evidence_ids=evidence_ids,
                    claim_ids=claim_ids,
                )
            except Exception:  # noqa: BLE001 - traceability repair must not break report delivery
                logger.warning("section evidence binding failed for %s", section_id)
        for source_id in section["source_ids"]:
            graph_tools.add_edge(section_id, source_id, EdgeType.USES)


def compile_structured_report(title: str, sections: list[dict], *, persist: bool = False) -> dict:
    """Validate and deterministically compile a chapter-level cited report."""
    registry = build_reference_registry()
    registry_by_source = {entry["source_id"]: entry for entry in registry}
    issues: list[dict[str, Any]] = []
    compiled_sections: list[dict[str, Any]] = []
    cited_source_ids: set[str] = set()
    submitted_sections = len(sections or [])
    submitted_paragraphs = 0
    kept_paragraphs = 0
    dropped_paragraphs = 0
    submitted_chars = 0
    kept_chars = 0
    auto_appended_conflict_ids: list[str] = []
    is_chinese = bool(re.search(r"[\u4e00-\u9fff]", title or ""))
    goals = graph_tools.search_nodes("user_request", {})
    request_text = " ".join(
        str(goal.get("request") or goal.get("research_goal") or "")
        for goal in goals
    ).casefold()
    wikipedia_task = is_wikipedia_task(request_text)
    unmet_fragments = _unmet_objective_fragments()
    disclosed_conflicts = {
        str(conflict["id"]): conflict
        for conflict in get_disclosed_conflicts()
        if conflict.get("id")
        and conflict.get("description")
        and conflict.get("evidence_ids")
        and conflict.get("source_ids")
    }

    for section_index, section in enumerate(sections or []):
        section_title = str(section.get("title") or "").strip()
        content = str(section.get("content") or "").strip()
        source_ids = list(dict.fromkeys(section.get("source_ids") or []))
        evidence_ids = list(dict.fromkeys(section.get("evidence_ids") or []))
        disclosed_conflict_ids = [
            str(conflict_id)
            for conflict_id in dict.fromkeys(section.get("disclosed_conflict_ids") or [])
            if conflict_id
        ]
        normalized_content = re.sub(r"\s+", " ", content).strip().casefold()
        if any(fragment in normalized_content for fragment in unmet_fragments):
            issues.append(_issue(
                "internal_unmet_objective_prose",
                "hard",
                f"section {section_title!r} copies an internal unmet Objective",
                "Rewrite from cited evidence and disclose only evidence-bound substantive uncertainty.",
                section_title=section_title,
            ))
            continue
        if "blocks" in section:
            issues.append(_issue(
                "legacy_block_schema",
                "hard",
                f"section {section_index + 1} still uses the removed blocks schema",
                "Submit chapter-level prose through the content/source_ids schema only.",
                section_title=section_title,
            ))
            continue
        if not section_title:
            issues.append(_issue(
                "missing_section_title",
                "soft",
                f"section {section_index + 1} has no title",
                "Add a concise section title and resubmit only this section.",
            ))
            continue
        if _is_reserved_section_title(section_title):
            issues.append(_issue(
                "reserved_section_title",
                "soft",
                f"section {section_title!r} collides with the generated references section",
                "Use a reader-facing analytical heading; references are generated automatically at the end.",
                section_title=section_title,
            ))
            continue
        invalid = [source_id for source_id in source_ids if source_id not in registry_by_source]
        if not source_ids or invalid:
            issues.append(_issue(
                "invalid_source_ids",
                "soft",
                f"section {section_title!r} requires valid URL-backed source_ids",
                "Replace missing or invalid source_ids with valid URL-backed sources for this section.",
                section_title=section_title,
            ))
            continue
        cited_numbers = {int(value) for value in _CITE_TOKEN_RE.findall(content)}
        registry_by_number = {entry["n"]: entry for entry in registry}
        invalid_citations = sorted(
            number for number in cited_numbers
            if registry_by_number.get(number, {}).get("source_id") not in source_ids
        )
        if invalid_citations:
            # Strip only the invalid [n] tokens, keep the prose. This preserves
            # valuable content (e.g. scholar discussions) while flagging the
            # citation hygiene issue for soft review. Then append a fallback
            # citation to paragraphs that lost all citations.
            invalid_pattern = re.compile(
                r"\[(?:%s)\]" % "|".join(str(n) for n in invalid_citations)
            )
            content = invalid_pattern.sub("", content)
            content = re.sub(r"\s{2,}", " ", content).strip()
            if source_ids:
                first_valid_number = next(
                    (entry["n"] for entry in registry
                     if entry.get("source_id") in source_ids),
                    None,
                )
                if first_valid_number is not None:
                    paragraphs = re.split(r"(\n\s*\n)", content)
                    for i, para in enumerate(paragraphs):
                        if not para.strip() or para.strip().startswith("#"):
                            continue
                        if not _CITE_TOKEN_RE.search(para):
                            paragraphs[i] = para.rstrip(".。") + f". [{first_valid_number}]"
                    content = "".join(paragraphs)
            issues.append(_issue(
                "invalid_inline_citations_stripped",
                "soft",
                f"section {section_title!r} had {len(invalid_citations)} invalid citation(s) stripped; prose retained",
                "Re-add valid citation numbers from the section's Report Evidence to support the affected claims.",
                section_title=section_title,
            ))
        if evidence_ids:
            valid_evidence_ids = []
            for evidence_id in evidence_ids:
                try:
                    node_type = graph_tools.get_node(evidence_id).get("type")
                except Exception:  # noqa: BLE001 - validation must not block compilation
                    node_type = None
                if str(node_type or "").lower() in {"evidence", "claim"}:
                    valid_evidence_ids.append(evidence_id)
            evidence_ids = valid_evidence_ids
        invalid_conflict_ids = []
        for conflict_id in disclosed_conflict_ids:
            conflict = disclosed_conflicts.get(conflict_id)
            if (
                not conflict
                or not set(evidence_ids) & set(conflict.get("evidence_ids") or [])
                or not set(source_ids) & set(conflict.get("source_ids") or [])
                or _normalize_disclosure_text(conflict.get("description"))
                not in _normalize_disclosure_text(content)
            ):
                invalid_conflict_ids.append(conflict_id)
        if invalid_conflict_ids:
            issues.append(_issue(
                "invalid_conflict_disclosure_binding",
                "hard",
                f"section {section_title!r} has {len(invalid_conflict_ids)} invalid conflict disclosure binding(s)",
                "Use the chapter bundle's local conflict ref and include its neutral description in the section prose.",
                section_title=section_title,
            ))
            continue
        submitted_chars += len(content)
        blocks, removed_indexes, had_embedded_refs = _sanitize_section_blocks(content)
        submitted_paragraphs += len(blocks) + len(removed_indexes)
        if had_embedded_refs:
            issues.append(_issue(
                "embedded_references_section",
                "soft",
                f"section {section_title!r} embedded its own references section",
                "Keep source discussion in prose; let the compiler generate the final references section.",
                section_title=section_title,
            ))
        for paragraph_index in removed_indexes:
            dropped_paragraphs += 1
            issues.append(_issue(
                "forbidden_meta_prose",
                "soft",
                f"section {section_title!r} paragraph {paragraph_index} contains forbidden meta prose",
                "Delete the internal-process sentence and keep the evidence-backed substantive content.",
                section_title=section_title,
                block_index=paragraph_index,
            ))
        if not blocks:
            issues.append(_issue(
                "empty_section_content",
                "soft",
                f"section {section_title!r} has no usable prose content",
                "Provide substantive chapter prose for this section.",
                section_title=section_title,
            ))
            continue
        compiled_content = _compile_section_content(content, source_ids, registry_by_source)
        if not compiled_content:
            issues.append(_issue(
                "empty_section_content",
                "soft",
                f"section {section_title!r} has no usable prose content",
                "Provide substantive chapter prose for this section.",
                section_title=section_title,
            ))
            continue
        kept_paragraphs += len(blocks)
        kept_chars += len(compiled_content)
        cited_source_ids.update(source_ids)
        compiled_sections.append({
            "title": section_title,
            "content": compiled_content,
            "source_ids": sorted(source_ids),
            "evidence_ids": evidence_ids,
            "section_type": section.get("section_type"),
            "disclosed_conflict_ids": disclosed_conflict_ids,
        })

    retention_ratio = (kept_chars / submitted_chars) if submitted_chars > 0 else 0.0
    report = ""
    salvaged_report = ""

    if not compiled_sections:
        issues.append(_issue(
            "no_valid_sections",
            "hard",
            "structured report contains no valid cited sections",
            "Rewrite the report with valid section titles and URL-backed citations.",
        ))
    else:
        compiled_sections, auto_appended_conflict_ids, missing_conflict_ids = _append_missing_conflicts(
            compiled_sections,
            registry_by_source,
            is_chinese,
            auto_append=not wikipedia_task,
        )
        if missing_conflict_ids:
            issues.append(_issue(
                "missing_substantive_uncertainty",
                "hard",
                f"Wikipedia report omitted {len(missing_conflict_ids)} evidence-bound substantive uncertainty item(s)",
                "Integrate each uncertainty into its relevant topic section and select its local conflict ref.",
            ))
        cited_source_ids = {
            source_id
            for section in compiled_sections
            for source_id in section.get("source_ids") or []
        }
        if wikipedia_task:
            lead_count = sum(
                section.get("section_type") == "lead" for section in compiled_sections
            )
            lead_is_first = compiled_sections[0].get("section_type") == "lead"
            if lead_count != 1 or not lead_is_first:
                issues.append(_issue(
                    "invalid_wikipedia_lead",
                    "hard",
                    f"Wikipedia reports require exactly one opening lead chapter; found {lead_count}",
                    "Mark exactly the first chapter as section_type='lead'.",
                ))
        candidate = _compile_section_report(
            title,
            compiled_sections,
            registry,
            cited_source_ids,
            wikipedia_task=wikipedia_task,
        )
        for item in validate_delivery_invariants(candidate):
            issues.append(_issue(
                "delivery_invariant_failed",
                "hard",
                item,
                "Fix missing citations, broken references, or forbidden process prose before resubmitting.",
            ))
        for item in _validate_compiled_report_content(candidate):
            issues.append(_issue(
                "content_consistency_failed",
                "hard",
                item,
                "Ensure disclosed conflicts are covered and every factual section keeps citations.",
            ))
        for item in validate_report_quality(candidate):
            issues.append(_issue(
                "quality_gate_failed",
                "soft",
                item,
                "Replace placeholder or reference-only prose with substantive, evidence-backed writing.",
            ))
        if kept_paragraphs and retention_ratio < _MIN_RETENTION_RATIO:
            issues.append(_issue(
                "low_retention_ratio",
                "soft",
                f"kept content retention ratio {retention_ratio:.2f} is below {_MIN_RETENTION_RATIO:.2f}",
                "Keep the accepted sections, then restore the dropped evidence-backed prose instead of rewriting the whole report.",
            ))
        if any(issue["severity"] == "hard" for issue in issues):
            report = ""
            salvaged_report = ""
        elif issues:
            salvaged_report = candidate
        else:
            report = candidate

    accepted = bool(report or salvaged_report)
    revision_requested = accepted and bool(issues)
    severity = "hard" if any(item["severity"] == "hard" for item in issues) else ("soft" if issues else "clean")

    if accepted and persist:
        _persist_compiled_sections(compiled_sections)

    return {
        "accepted": accepted,
        "revision_requested": revision_requested,
        "severity": severity,
        "report": report,
        "salvaged_report": salvaged_report,
        "issues": issues,
        "retention_ratio": round(retention_ratio, 4),
        "submitted_sections": submitted_sections,
        "kept_sections": len(compiled_sections),
        "dropped_sections": max(0, submitted_sections - len(compiled_sections)),
        "submitted_paragraphs": submitted_paragraphs,
        "kept_paragraphs": kept_paragraphs,
        "dropped_paragraphs": dropped_paragraphs,
        "section_count": len(compiled_sections),
        "source_count": len(cited_source_ids),
        "auto_appended_conflict_ids": auto_appended_conflict_ids,
    }


def build_cited_evidence_report(request: str = "") -> str:
    """Build a deterministic cited report from every citation-ready evidence item."""
    registry = build_reference_registry()
    cited_source_ids: set[str] = set()
    seen_items: set[str] = set()
    is_chinese = bool(re.search(r"[\u4e00-\u9fff]", request or ""))
    parts = ["# 调研报告" if is_chinese else "# Research Report"]
    queries = graph_tools.search_nodes("query", {})
    queries.sort(key=lambda query: (query.get("handle") or "", query.get("id") or ""))
    for query in queries:
        items: list[dict] = []
        offset = 0
        while True:
            page = get_report_evidence(query["id"], offset=offset, limit=100)
            items.extend(item for item in page["items"] if item["id"] not in seen_items)
            if page["next_offset"] is None:
                break
            offset = page["next_offset"]
        if not items:
            continue
        heading = query.get("text") or query.get("handle") or query["id"]
        parts.append(f"## {heading}")
        for item in items:
            seen_items.add(item["id"])
            cited_source_ids.update(item["source_ids"])
            citations = "".join(f"[{number}]" for number in item["citations"])
            parts.append(f"- {item['text']} {citations}")
    if not seen_items:
        parts.extend([
            "## 结论" if is_chinese else "## Conclusion",
            "暂无可核实结论。" if is_chinese else "No verifiable findings are available.",
        ])
    if cited_source_ids:
        parts.append(_render_references(
            registry,
            cited_source_ids,
            "参考文献" if is_chinese else "References",
        ))
    return sanitize_report("\n\n".join(parts))


def _chunked(items: list[Any], size: int) -> list[list[Any]]:
    """Return fixed-size chunks while preserving order."""
    return [items[index : index + size] for index in range(0, len(items), size)]


def _guess_topic_title(query: dict, index: int, is_chinese: bool) -> str:
    """Derive a reader-facing fallback section title from a raw query."""
    handle = str(query.get("handle") or "").strip()
    if handle and not re.fullmatch(r"q\d+", handle, re.IGNORECASE):
        return handle.replace("_", " ").strip()
    text = str(query.get("text") or "").strip()
    lowered = text.lower()
    if is_chinese:
        if "技术路线" in text or "核心方案" in text:
            return "技术路线与核心方案"
        if "产品形态" in text or "落地进度" in text or "demo" in lowered:
            return "产品形态与落地进展"
        if "商业化" in text or "客户" in text or "应用场景" in text:
            return "商业化进度与应用场景"
        if "融资" in text or "投资方" in text:
            return "融资与资本进展"
        if "团队" in text or "创始人" in text or "科学家" in text:
            return "团队与人才背景"
        if "代表性公司" in text or "机构" in text:
            return "代表性公司与机构"
        if "主要" in text and "路线" in text:
            return "主要技术路线概览"
        return f"主题 {index}"
    if "technical route" in lowered or "core solution" in lowered:
        return "Technical Routes and Core Solutions"
    if "product" in lowered or "deployment" in lowered or "demo" in lowered:
        return "Product Form Factors and Deployment Progress"
    if "commercial" in lowered or "customer" in lowered or "application" in lowered:
        return "Commercial Progress and Use Cases"
    if "funding" in lowered or "investor" in lowered:
        return "Funding and Capital Progress"
    if "team" in lowered or "founder" in lowered or "scientist" in lowered:
        return "Team and Talent Background"
    return f"Topic {index}"


def _render_fact_paragraph(chunk: list[dict], registry_by_source: dict[str, dict], is_chinese: bool) -> tuple[str, set[str]]:
    """Render one paragraph from a small chunk of evidence items."""
    source_ids: list[str] = []
    statements: list[str] = []
    for item in chunk:
        text = re.sub(r"\s+", " ", str(item.get("text") or "").strip())
        text = re.sub(r"[。；;]+$", "", text)
        if not text:
            continue
        statements.append(text)
        source_ids.extend(item.get("source_ids") or [])
    unique_source_ids = list(dict.fromkeys(source_ids))
    citations = "".join(f"[{registry_by_source[source_id]['n']}]" for source_id in unique_source_ids if source_id in registry_by_source)
    if is_chinese:
        paragraph = f"现有公开资料显示：{'；'.join(statements)}。{citations}".strip()
    else:
        paragraph = f"Available public information indicates: {'; '.join(statements)}. {citations}".strip()
    return paragraph, set(unique_source_ids)


def build_context_fallback_report(request: str = "") -> str:
    """Build a prose-first fallback report from report context and validated evidence."""
    registry = build_reference_registry()
    registry_by_source = {entry["source_id"]: entry for entry in registry}
    if not registry_by_source:
        return ""

    goals = graph_tools.search_nodes("user_request", {})
    goal = goals[0] if goals else {}
    request_text = request or str(goal.get("request") or "")
    is_chinese = bool(re.search(r"[\u4e00-\u9fff]", request_text or str(goal.get("language") or "")))

    queries = graph_tools.search_nodes("query", {})
    queries.sort(key=lambda query: (query.get("importance") or 0), reverse=True)

    topic_sections: list[dict[str, Any]] = []
    all_source_ids: list[str] = []
    for index, query in enumerate(queries, start=1):
        items: list[dict] = []
        offset = 0
        while True:
            page = get_report_evidence(query["id"], offset=offset, limit=100)
            items.extend(page.get("items", []))
            if page.get("next_offset") is None:
                break
            offset = page["next_offset"]
        if not items:
            continue
        title = _guess_topic_title(query, index, is_chinese)
        paragraphs: list[str] = []
        section_source_ids: set[str] = set()
        for chunk in _chunked(items, 4):
            paragraph, chunk_source_ids = _render_fact_paragraph(chunk, registry_by_source, is_chinese)
            if paragraph:
                paragraphs.append(paragraph)
                section_source_ids.update(chunk_source_ids)
        if paragraphs:
            topic_sections.append({
                "title": title,
                "paragraphs": paragraphs,
                "source_ids": section_source_ids,
                "evidence_ids": {item["id"] for item in items if item.get("id")},
            })
            all_source_ids.extend(section_source_ids)

    deduped_fallback_ids = list(dict.fromkeys(all_source_ids))
    if not topic_sections or not deduped_fallback_ids:
        return ""

    report_title = str(request_text or ("调研报告" if is_chinese else "Research Report")).strip() or (
        "调研报告" if is_chinese else "Research Report"
    )
    cited_source_ids: set[str] = set()
    parts = [f"# {report_title}"]

    conflicts = [
        item
        for item in get_disclosed_conflicts()
        if item.get("description") and item.get("evidence_ids") and item.get("source_ids")
    ]
    wikipedia_task = is_wikipedia_task(request_text)
    lead_uncertainties: list[str] = []
    lead_source_ids: set[str] = set()
    if conflicts and wikipedia_task:
        for conflict in conflicts:
            source_ids = {
                source_id
                for source_id in conflict.get("source_ids") or []
                if source_id in registry_by_source
            }
            if not source_ids:
                continue
            paragraph, conflict_source_ids = _conflict_section_paragraph(
                {**conflict, "source_ids": sorted(source_ids)},
                registry_by_source,
                is_chinese,
            )
            evidence_ids = set(conflict.get("evidence_ids") or [])
            ranked_sections = sorted(
                topic_sections,
                key=lambda section: (
                    len(evidence_ids & section["evidence_ids"]),
                    len(source_ids & section["source_ids"]),
                ),
                reverse=True,
            )
            best = ranked_sections[0] if ranked_sections else None
            if best and (
                evidence_ids & best["evidence_ids"]
                or source_ids & best["source_ids"]
            ):
                best["paragraphs"].append(paragraph)
                best["source_ids"].update(conflict_source_ids)
            else:
                lead_uncertainties.append(paragraph)
                lead_source_ids.update(conflict_source_ids)

    if lead_uncertainties:
        parts.extend(lead_uncertainties)
        cited_source_ids.update(lead_source_ids)

    for section in topic_sections:
        parts.append(f"## {section['title']}")
        parts.extend(section["paragraphs"])
        cited_source_ids.update(section["source_ids"])

    if conflicts and not wikipedia_task:
        parts.append(f"## {_conflict_section_title(is_chinese)}")
        for conflict in conflicts:
            source_ids = [
                source_id for source_id in dict.fromkeys(conflict.get("source_ids") or [])
                if source_id in registry_by_source
            ]
            if not source_ids:
                continue
            paragraph, conflict_source_ids = _conflict_section_paragraph(
                {**conflict, "source_ids": source_ids},
                registry_by_source,
                is_chinese,
            )
            if paragraph:
                parts.append(paragraph)
            cited_source_ids.update(conflict_source_ids)

    parts.append(_render_references(
        registry,
        cited_source_ids,
        "参考文献" if is_chinese else "References",
    ))
    return sanitize_report("\n\n".join(parts))


def _references_label(text: str, match: Optional[re.Match]) -> str:
    """Return the references heading label: honor an existing one, else infer.

    Args:
        text: The full report text.
        match: The matched references heading, or ``None`` if absent.

    Returns:
        ``"参考文献"`` or ``"References"``.
    """
    if match is not None:
        return match.group(1)
    for heading in _ANY_HEADING_RE.finditer(text):
        if re.search(r"[一-鿿]", heading.group(1)):
            return "参考文献"
    return "References"


def finalize_report(report_text: str) -> str:
    """Normalize citations + references and restore section→source traceability.

    Conservative and safe: only ``[n]`` tokens and the references section are
    transformed; body prose is untouched. Returns ``report_text`` unchanged on
    any failure, when the graph has no sources, or when no in-text citation
    resolves to a source.

    Args:
        report_text: The final report markdown (the Orchestrator's terminal text).

    Returns:
        The finalized report text.
    """
    if not report_text or report_text.strip() == "(no report produced)":
        return report_text

    registry = build_reference_registry()
    if not registry:
        return report_text
    registry_by_n = {entry["n"]: entry for entry in registry}

    # 1. Split off the LLM-authored references section (where the garbage lives).
    ref_match = _REF_HEADING_RE.search(report_text)
    body = report_text[: ref_match.start()] if ref_match else report_text
    label = _references_label(report_text, ref_match)

    # 2. Collect resolvable in-text citations in first-appearance order.
    first_seen: list[int] = []
    seen_old: set[int] = set()
    for token in _CITE_TOKEN_RE.finditer(body):
        old = int(token.group(1))
        if old in seen_old or old not in registry_by_n:
            continue
        seen_old.add(old)
        first_seen.append(old)

    if not first_seen:
        # Nothing maps to a source — treat as a parse miss, leave the report as-is.
        return report_text

    # 3. Assign contiguous new numbers by first appearance.
    old_to_new = {old: i + 1 for i, old in enumerate(first_seen)}

    # 4. Rewrite body tokens in a single pass; drop danglers (no registry entry).
    def _renumber(match: re.Match) -> str:
        new = old_to_new.get(int(match.group(1)))
        return f"[{new}]" if new is not None else ""

    new_body = _CITE_TOKEN_RE.sub(_renumber, body).rstrip()

    # 5. Rebuild a clean references block from the cited registry entries only.
    lines = [f"## {label}", ""]
    for old, new in sorted(old_to_new.items(), key=lambda kv: kv[1]):
        entry = registry_by_n[old]
        # A title-less source falls back to its URL in the registry; render the
        # URL once rather than "[n] <url> <url>".
        if entry["title"] == entry["url"]:
            lines.append(f"[{new}] {entry['url']}")
        else:
            lines.append(f"[{new}] {entry['title']} {entry['url']}")
        lines.append("")
    references_block = "\n".join(lines).rstrip()

    finalized = f"{new_body}\n\n{references_block}\n"

    # 6. Restore traceability: ReportSection nodes + section→source USES edges.
    try:
        _persist_sections(new_body, old_to_new, registry_by_n)
    except Exception:  # noqa: BLE001 — graph writes must never break the report
        logger.warning("finalize_report: section persistence failed", exc_info=True)

    return finalized


def _persist_sections(body: str, old_to_new: dict, registry_by_n: dict) -> None:
    """Create ReportSection nodes + section→source USES edges from the body.

    Each ``[n]`` is attributed to its nearest preceding heading. Missing
    sections are created and existing sections receive any missing source
    bindings.

    Args:
        body: The renumbered report body (references section excluded).
        old_to_new: Mapping from original to contiguous citation numbers.
        registry_by_n: Registry keyed by original citation number.
    """
    existing = {
        section.get("title"): section
        for section in graph_tools.search_nodes("report_section", {})
        if section.get("title")
    }

    new_to_source = {new: registry_by_n[old]["source_id"] for old, new in old_to_new.items()}

    for section in _parse_sections(body):
        if not section["cites"]:
            continue
        content = section["content"]
        prior = existing.get(section["title"])
        section_id = prior["id"] if prior else graph_tools.create_report_section(section["title"], content, None)
        source_ids = {new_to_source.get(new) for new in section["cites"]}
        for source_id in source_ids:
            if source_id:
                graph_tools.add_edge(section_id, source_id, EdgeType.USES)


def _parse_sections(body: str) -> list[dict]:
    """Parse ATX-heading sections and their citation numbers."""
    sections: list[dict] = []
    current: Optional[dict] = None
    for line in body.splitlines():
        heading = _ANY_HEADING_RE.match(line)
        if heading:
            current = {"title": heading.group(1).strip(), "lines": [], "cites": set()}
            sections.append(current)
            continue
        if current is None:
            continue
        current["lines"].append(line)
        for token in _CITE_TOKEN_RE.finditer(line):
            current["cites"].add(int(token.group(1)))
    for section in sections:
        section["content"] = "\n".join(section.pop("lines")).strip()
    return sections


def _reference_sources(report_text: str) -> dict[int, dict]:
    """Map report reference numbers to Source nodes through their URLs."""
    by_url = {
        source.get("url"): source
        for source in graph_tools.search_nodes("source", {})
        if source.get("url")
    }
    result: dict[int, dict] = {}
    for line in report_text.splitlines():
        match = re.match(r"^\[(\d{1,4})\]\s+.*?(https?://\S+)\s*$", line.strip())
        if not match:
            continue
        url = match.group(2).rstrip(".,，。);）]")
        if url in by_url:
            result[int(match.group(1))] = by_url[url]
    return result


def validate_final_report(report_text: str) -> list[str]:
    """Return final-report consistency violations."""
    text = report_text or ""
    issues = _validate_compiled_report_content(text)
    ref_match = _REF_HEADING_RE.search(text)
    body = text[: ref_match.start()] if ref_match else text
    sections = _parse_sections(body)

    from tools import research_state

    goal = research_state.get_goal()
    years = [int(year) for year in re.findall(r"\b(?:19|20)\d{2}\b", str(goal.get("time_window") or ""))]
    references = _reference_sources(text)
    if years and references:
        lower, upper = min(years), max(years)
        for section in sections:
            is_background = bool(re.search(r"背景|background|context", section["title"], re.IGNORECASE))
            if is_background:
                continue
            for citation in section["cites"]:
                source = references.get(citation, {})
                published = re.search(
                    r"\b(?:19|20)\d{2}\b",
                    str(source.get("published_at") or source.get("publication_date") or ""),
                )
                if published and not lower <= int(published.group()) <= upper:
                    issues.append(
                        f"out-of-window source cited outside a background section: "
                        f"{section['title']} [{citation}]"
                    )
    for section in graph_tools.search_nodes("report_section", {}):
        if len(str(section.get("content") or "").strip()) < 80:
            continue
        uses = [
            edge for edge in graph_tools.get_node_edges(section["id"], direction="out")
            if str(edge.get("type", "")).lower() == "uses"
        ]
        if not uses:
            issues.append(f"report section has no evidence/source binding: {section.get('title')}")
    return list(dict.fromkeys(issues))
