"""Deterministic report finalization for GraphResearcher.

The final report is the Orchestrator's terminal message — the graph stores only
nodes/edges, never the report text. LLM-authored reference lists drift over a
long report: duplicates, "同上" / "见 [x]" cross-references, and URL-less
pseudo-sources (figures, sub-sections). This module rebuilds citations
deterministically from the graph's ``Source`` nodes so every reference maps to a
real, unique, URL-bearing node, and restores the ``ReportSection``→``Source``
traceability the Reporter often skips.

``finalize_report`` is conservative: it only rewrites ``[n]`` citation tokens
and the references section; body prose is never altered, and on any failure (no
sources, nothing resolvable, parse error) it returns the input unchanged so the
report is never broken.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from memory.graph import EdgeType
from tools import graph_tools

logger = logging.getLogger(__name__)

# In-text citation token, e.g. ``[12]``; adjacency ``[1][3]`` is two matches.
_CITE_TOKEN_RE = re.compile(r"\[(\d{1,4})\]")
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
)
_FORBIDDEN_META_RE = re.compile(
    r"research graph|研究图谱|本次图谱|图谱覆盖范围|导出片段|"
    r"由于引用系统限制|引用系统限制|无法.{0,20}引用|正文不逐条打|"
    r"如果你(?:后续|接下来|希望|需要|想)|可以指定维度|可直接进\s*ppt|"
    r"帮你补全|如需.{0,40}可",
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
_TIMESTAMP_NODE_ID_RE = re.compile(r"\b20\d{12,20}_[0-9a-f]{6,12}\b", re.IGNORECASE)
_SHORT_INTERNAL_ID_RE = re.compile(r"(?<![A-Za-z0-9_])(st\d{1,6}|e\d{1,6}|c\d{1,6})(?![A-Za-z0-9_])")
_EVIDENCE_LABEL_RE = re.compile(
    r"(?:证据|evidence|claim|statement)(?:_id| id|编号)?\s*[:：]\s*"
    r"(?:20\d{12,20}_[0-9a-f]{6,12}|st\d{1,6}|e\d{1,6}|c\d{1,6})",
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
_DRAFT_FILE = ".report_draft.md"
_CHAPTER_META_SUFFIX = ".meta.json"
_ASCII_SLOT_LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9 _-]*$")
_LEAD_SLOT_KEYWORDS = (
    "lead",
    "summary",
    "overview",
    "executive summary",
    "introduction",
    "摘要",
    "总览",
    "概览",
    "概述",
    "导读",
    "引言",
)
_COMPARISON_SLOT_KEYWORDS = (
    "comparison",
    "compare",
    "difference",
    "vs",
    "比较",
    "对比",
    "矩阵",
    "差异",
)
_ENTITY_PROFILE_SLOT_KEYWORDS = (
    "entity profile",
    "company profile",
    "profile",
    "画像",
    "主体画像",
    "企业画像",
    "公司画像",
    "团队画像",
)
_CANONICAL_SLOT_ALIASES = {
    "comparison": (
        "comparison",
        "compare",
        "comparison matrix",
        "matrix comparison",
        "vs",
        "difference",
        "比较",
        "对比",
        "比较矩阵",
        "对比矩阵",
        "跨公司对比矩阵",
        "公司对比矩阵",
        "差异对比",
    ),
    "lead": (
        "lead",
        "lead section",
        "summary",
        "overview",
        "executive summary",
        "introduction",
        "摘要",
        "总览",
        "概览",
        "概述",
        "导读",
        "引言",
    ),
    "entity_profile": (
        "entity_profile",
        "entity profile",
        "company profile",
        "profile",
        "画像",
        "主体画像",
        "企业画像",
        "公司画像",
        "团队画像",
    ),
    "technical_routes_overview": (
        "technical_routes_overview",
        "technical routes overview",
        "technical route overview",
        "technology routes overview",
        "技术路线概览",
        "技术路径概览",
        "技术路线总览",
        "技术路径总览",
    ),
    "industry_landscape_summary": (
        "industry_landscape_summary",
        "industry landscape summary",
        "industry landscape",
        "market landscape summary",
        "行业格局总结",
        "行业格局概览",
        "产业格局概览",
        "行业景观总结",
    ),
    "commercialization_progress": (
        "commercialization_progress",
        "commercialization progress",
        "commercial progress",
        "go to market progress",
        "商业化进展",
        "商业化推进",
        "商业落地进展",
        "落地进展",
    ),
    "financing_status": (
        "financing_status",
        "financing status",
        "funding status",
        "fundraising status",
        "融资状态",
        "融资情况",
        "融资进展",
        "资本状态",
        "融资公开信息",
    ),
    "team_profile": (
        "team_profile",
        "team profile",
        "team overview",
        "团队画像",
        "团队概况",
        "团队简介",
        "核心团队画像",
    ),
}
_SLOT_ALIAS_TO_CANONICAL = {
    re.sub(r"\s+", " ", alias.replace("_", " ").replace("-", " ").strip().lower()): canonical
    for canonical, aliases in _CANONICAL_SLOT_ALIASES.items()
    for alias in (canonical, *aliases)
}


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


def _draft_path(output_dir: Optional[str]) -> Path:
    return _artifact_root(output_dir) / _DRAFT_FILE


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


def _slot_alias_key(value: Any) -> str:
    """Return a normalized lookup key for one slot label alias."""
    return re.sub(
        r"\s+",
        " ",
        str(value or "").strip().lower().replace("_", " ").replace("-", " "),
    ).strip()


def canonicalize_slot_label(value: Any) -> str:
    """Return one canonical slot label from an explicit whitelist plus mild formatting normalization."""
    text = str(value or "").strip()
    if not text:
        return ""
    key = _slot_alias_key(text)
    if key in _SLOT_ALIAS_TO_CANONICAL:
        return _SLOT_ALIAS_TO_CANONICAL[key]
    if _ASCII_SLOT_LABEL_RE.fullmatch(key):
        return re.sub(r"[\s-]+", "_", key).strip("_")
    return text


def canonicalize_slot_labels(values: Any) -> list[str]:
    """Return canonical, de-duplicated slot labels in first-seen order."""
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    canonical = [canonicalize_slot_label(value) for value in values]
    return list(dict.fromkeys([value for value in canonical if value]))


def infer_slot_labels_from_section(
    *,
    title: str = "",
    section_plan: str = "",
    section_type: Optional[str] = None,
    goals: Optional[list[str]] = None,
) -> list[str]:
    """Infer structural delivery slots from chapter semantics without changing persisted schema."""
    section_slots = canonicalize_slot_labels([section_type] if section_type else [])
    coverage = set(section_slots)
    haystack = "\n".join([
        str(title or ""),
        str(section_plan or ""),
        "\n".join(str(goal or "") for goal in goals or []),
    ]).lower()
    if any(keyword in haystack for keyword in _LEAD_SLOT_KEYWORDS):
        coverage.add("lead")
    if any(keyword in haystack for keyword in _COMPARISON_SLOT_KEYWORDS):
        coverage.add("comparison")
    if any(keyword in haystack for keyword in _ENTITY_PROFILE_SLOT_KEYWORDS):
        coverage.add("entity_profile")
    return sorted(coverage)


def infer_delivery_slot_coverage(
    output_dir: Optional[str],
    planning_assets: Optional[dict[str, Any]] = None,
) -> list[str]:
    """Return canonical slots covered by existing planning assets and report artifacts."""
    coverage: set[str] = set()
    assets = planning_assets or {}
    if assets.get("lead_candidates"):
        coverage.add("lead")
    if assets.get("comparison_slots"):
        coverage.add("comparison")
    if assets.get("entity_profiles"):
        coverage.add("entity_profile")

    outline = _read_json_file(_outline_path(output_dir))
    outline_assets = outline.get("planning_assets") or {}
    if outline_assets.get("lead_candidates"):
        coverage.add("lead")
    if outline_assets.get("comparison_slots"):
        coverage.add("comparison")
    if outline_assets.get("entity_profiles"):
        coverage.add("entity_profile")
    for chapter in outline.get("chapters") or []:
        coverage.update(infer_slot_labels_from_section(
            title=str(chapter.get("title") or ""),
            section_plan=str(chapter.get("section_plan") or ""),
            section_type=chapter.get("section_type"),
            goals=[str(goal) for goal in chapter.get("goals") or [] if str(goal).strip()],
        ))

    chapter_root = (Path(output_dir) if output_dir else Path(".")) / _CHAPTER_DIR
    if chapter_root.exists():
        for meta_path in chapter_root.glob(f"*{_CHAPTER_META_SUFFIX}"):
            meta = _read_json_file(meta_path)
            if meta.get("lead_candidates"):
                coverage.add("lead")
            if meta.get("comparison_slots"):
                coverage.add("comparison")
            if meta.get("entity_profiles"):
                coverage.add("entity_profile")
            brief = meta.get("section_brief") or {}
            coverage.update(infer_slot_labels_from_section(
                title=str(meta.get("title") or brief.get("chapter_title") or ""),
                section_plan=str(brief.get("section_plan") or ""),
                section_type=meta.get("section_type"),
                goals=[str(goal) for goal in brief.get("chapter_goals") or [] if str(goal).strip()],
            ))
    return sorted(coverage)


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
        query_ids = [str(query_id).strip() for query_id in chapter.get("query_ids") or [] if str(query_id).strip()]
        if query_ids:
            lines.extend(["", f"Queries: {', '.join(query_ids)}"])
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _goal_source_blocklist() -> set[str]:
    """Return normalized blocked source domains declared on the current goal."""
    from tools import research_state

    goal = research_state.get_goal()
    raw_values: list[str] = []
    for key in (
        "forbidden_sources",
        "forbidden_source_domains",
        "blocked_source_domains",
        "source_blocklist",
        "source_exclude_domains",
    ):
        value = goal.get(key)
        if isinstance(value, list):
            raw_values.extend(str(item).strip() for item in value if str(item).strip())
        elif isinstance(value, str) and value.strip():
            raw_values.extend(
                bit.strip() for bit in re.split(r"[,;\n]", value) if bit.strip()
            )
    for item in goal.get("source_preferences") or []:
        text = str(item).strip()
        lowered = text.lower()
        if lowered.startswith(("exclude:", "avoid:", "forbid:", "blocked:")):
            raw_values.append(text.split(":", 1)[1].strip())
        elif text.startswith("!"):
            raw_values.append(text[1:].strip())

    blocked: set[str] = set()
    for value in raw_values:
        if not value:
            continue
        normalized = value if "://" in value else f"https://{value}"
        domain = urlparse(normalized).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        if domain:
            blocked.add(domain)
    return blocked


def _source_domain(source: dict[str, Any]) -> str:
    """Return one normalized Source domain for blocklist checks."""
    url = str(source.get("url") or "").strip()
    if not url:
        return ""
    domain = urlparse(url).netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def _matches_blocked_domain(domain: str, blocked: set[str]) -> bool:
    """Return whether one source domain matches the run's blocklist."""
    return any(domain == item or domain.endswith(f".{item}") for item in blocked)


def _internal_id_issues(report_text: str) -> list[str]:
    """Return user-visible internal graph identifier leaks."""
    text = report_text or ""
    issues: list[str] = []
    for match in _TIMESTAMP_NODE_ID_RE.finditer(text):
        issues.append(f"internal node id leaked into report: {match.group(0)}")
    for match in _EVIDENCE_LABEL_RE.finditer(text):
        issues.append(f"internal evidence label leaked into report: {match.group(0)}")
    for match in _SHORT_INTERNAL_ID_RE.finditer(text):
        token = match.group(1)
        start = max(0, match.start() - 8)
        end = min(len(text), match.end() + 8)
        window = text[start:end]
        if re.search(r"[（(,，;；:\s]", window) or re.search(r"[）),，;；:\s]", window):
            issues.append(f"internal short id leaked into report: {token}")
    return list(dict.fromkeys(issues))


def build_reference_registry() -> list[dict]:
    """Return the canonical, URL-deduped, stably-numbered reference registry.

    Reads every ``Source`` node for the current run context, drops entries
    without a URL, deduplicates by URL (first node in id order wins), and sorts
    by node id — the ``<timestamp>_<uuid8>`` id sorts lexicographically, i.e. in
    creation order, which neo4j does not otherwise guarantee. Assigns 1-based
    numbers.

    Both ``export_report_context`` (what the Reporter cites from) and
    :func:`finalize_report` build the registry through this one function, so the
    ``n``→source mapping is identical on both sides.

    Returns:
        A list of ``{"n", "source_id", "title", "url"}`` dicts.
    """
    sources = [s for s in graph_tools.search_nodes("source", {}) if s.get("url")]
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
    offset = max(0, int(offset or 0))
    limit = min(100, max(1, int(limit or 20)))
    nodes = {node["id"]: node for node in graph_tools.get_all_nodes()}
    edges = graph_tools.get_all_edges()
    registry = build_reference_registry()
    registry_by_source = {entry["source_id"]: entry for entry in registry}
    evaluation = graph_tools.get_query_evaluation_subgraph(query_id)
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
        items.append({
            "id": node["id"],
            "type": node["type"],
            "text": str(text).strip(),
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


def _all_report_evidence_items(query_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return all citation-ready evidence items for one Query."""
    first_page = get_report_evidence(query_id, offset=0, limit=100)
    if first_page.get("error"):
        return {"id": query_id}, []
    query_info = dict(first_page.get("query") or {"id": query_id})
    items = list(first_page.get("items") or [])
    next_offset = first_page.get("next_offset")
    while next_offset is not None:
        page = get_report_evidence(query_id, offset=int(next_offset), limit=100)
        items.extend(page.get("items") or [])
        next_offset = page.get("next_offset")
    return query_info, items


def _normalize_digest_lines(value: Any) -> list[str]:
    """Return a normalized list of digest lines from one Query property."""
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    """Return unique non-empty values in first-seen order."""
    return list(dict.fromkeys([value for value in values if value]))


def _importance_rank(value: Any) -> int:
    """Return a stable numeric rank for Query importance labels."""
    return {"core": 3, "supporting": 2, "peripheral": 1}.get(str(value or "").lower(), 0)


def _candidate_from_item(item: dict[str, Any], query_id: str) -> dict[str, Any]:
    """Project one evidence item into a lightweight reusable candidate shape."""
    return {
        "text": str(item.get("text") or "").strip(),
        "query_ids": [query_id],
        "evidence_ids": [str(item.get("id") or "").strip()] if str(item.get("id") or "").strip() else [],
        "source_ids": [str(source_id).strip() for source_id in item.get("source_ids") or [] if str(source_id).strip()],
    }


def _merge_candidates(candidates: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    """Merge candidates by text and keep the highest-coverage subset."""
    merged: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        text = str(candidate.get("text") or "").strip()
        if not text:
            continue
        current = merged.setdefault(text, {"text": text, "query_ids": [], "evidence_ids": [], "source_ids": []})
        current["query_ids"] = _dedupe_preserve_order(current["query_ids"] + list(candidate.get("query_ids") or []))
        current["evidence_ids"] = _dedupe_preserve_order(current["evidence_ids"] + list(candidate.get("evidence_ids") or []))
        current["source_ids"] = _dedupe_preserve_order(current["source_ids"] + list(candidate.get("source_ids") or []))
    ranked = sorted(
        merged.values(),
        key=lambda item: (-len(item["query_ids"]), -len(item["source_ids"]), item["text"]),
    )
    return ranked[:limit]


def _comparison_requested(query_digests: list[dict[str, Any]], title: str = "", section_plan: str = "") -> bool:
    """Return whether one section should receive comparison scaffolding."""
    if len(query_digests) >= 2:
        return True
    haystack = f"{title}\n{section_plan}".lower()
    return any(keyword in haystack for keyword in ("比较", "对比", " vs ", "difference", "comparison"))


def _build_comparison_slots(
    query_digests: list[dict[str, Any]],
    *,
    title: str = "",
    section_plan: str = "",
) -> list[dict[str, Any]]:
    """Build chapter- or report-level comparison scaffolds from query digests."""
    if not _comparison_requested(query_digests, title=title, section_plan=section_plan):
        return []
    supporting_points: list[dict[str, Any]] = []
    query_ids: list[str] = []
    evidence_ids: list[str] = []
    source_ids: list[str] = []
    for digest in query_digests:
        query_id = str(digest.get("query_id") or "").strip()
        if not query_id:
            continue
        query_ids.append(query_id)
        evidence_ids.extend(digest.get("top_evidence_ids") or [])
        source_ids.extend(digest.get("top_source_ids") or [])
        text = next((line for line in digest.get("digest_lines") or [] if str(line).strip()), "")
        if not text:
            continue
        supporting_points.append({
            "query_id": query_id,
            "query_handle": digest.get("query_handle"),
            "text": text,
            "evidence_ids": list(digest.get("top_evidence_ids") or []),
            "source_ids": list(digest.get("top_source_ids") or []),
        })
    if not supporting_points:
        return []
    return [{
        "slot_label": title or "Cross-query comparison",
        "query_ids": _dedupe_preserve_order(query_ids),
        "evidence_ids": _dedupe_preserve_order(evidence_ids),
        "source_ids": _dedupe_preserve_order(source_ids),
        "supporting_points": supporting_points,
    }]


def build_report_planning_assets(query_ids: Optional[list[str]] = None) -> dict[str, Any]:
    """Build reusable compressed writing assets for Reporter-facing tools."""
    wanted_query_ids = {
        str(query_id).strip()
        for query_id in query_ids or []
        if str(query_id).strip()
    }
    queries = sorted(
        graph_tools.search_nodes("query", {}),
        key=lambda query: (_importance_rank(query.get("importance")), query.get("id") or ""),
        reverse=True,
    )
    if wanted_query_ids:
        queries = [query for query in queries if str(query.get("id") or "").strip() in wanted_query_ids]

    query_digests: list[dict[str, Any]] = []
    raw_candidates: list[dict[str, Any]] = []
    entity_group_candidates: dict[str, list[dict[str, Any]]] = {}

    for query in queries:
        query_id = str(query.get("id") or "").strip()
        if not query_id:
            continue
        query_info, all_items = _all_report_evidence_items(query_id)
        items_by_id = {str(item.get("id") or ""): item for item in all_items}

        explicit_top_ids = [
            str(item_id).strip()
            for item_id in query.get("top_evidence_ids") or []
            if str(item_id).strip()
        ]
        top_items = [items_by_id[item_id] for item_id in explicit_top_ids if item_id in items_by_id]
        if len(top_items) < 3:
            for item in all_items:
                item_id = str(item.get("id") or "").strip()
                if item_id and item_id not in {str(existing.get("id") or "") for existing in top_items}:
                    top_items.append(item)
                if len(top_items) >= 3:
                    break
        digest_lines = _normalize_digest_lines(query.get("evidence_digest"))
        if not digest_lines:
            digest_lines = [str(item.get("text") or "").strip() for item in top_items if str(item.get("text") or "").strip()][:3]

        top_source_ids = _dedupe_preserve_order([
            str(source_id).strip()
            for item in top_items
            for source_id in item.get("source_ids") or []
            if str(source_id).strip()
        ])
        top_evidence_ids = _dedupe_preserve_order([
            str(item.get("id") or "").strip()
            for item in top_items
            if str(item.get("id") or "").strip()
        ])

        query_digest = {
            "query_id": query_id,
            "query_handle": query_info.get("handle") or query.get("handle"),
            "query_text": query_info.get("text") or query.get("text"),
            "importance": query.get("importance"),
            "source_count_snapshot": query.get("source_count_snapshot"),
            "top_evidence_ids": top_evidence_ids,
            "top_source_ids": top_source_ids,
            "digest_lines": digest_lines,
        }
        query_digests.append(query_digest)

        for item in top_items:
            raw_candidates.append(_candidate_from_item(item, query_id))

        subject_key = str(query.get("search_subject_key") or "").strip()
        if subject_key:
            entity_group_candidates.setdefault(subject_key, []).extend(
                _candidate_from_item(item, query_id)
                for item in top_items
            )

    lead_candidates = _merge_candidates(raw_candidates, limit=5)
    comparison_slots = _build_comparison_slots(query_digests)
    entity_profiles = []
    for entity_key, candidates in entity_group_candidates.items():
        merged = _merge_candidates(candidates, limit=3)
        if not merged:
            continue
        entity_profiles.append({
            "entity_key": entity_key,
            "display_label": entity_key,
            "query_ids": _dedupe_preserve_order([
                query_id for item in merged for query_id in item.get("query_ids") or []
            ]),
            "evidence_ids": _dedupe_preserve_order([
                evidence_id for item in merged for evidence_id in item.get("evidence_ids") or []
            ]),
            "source_ids": _dedupe_preserve_order([
                source_id for item in merged for source_id in item.get("source_ids") or []
            ]),
            "profile_points": [item["text"] for item in merged if item.get("text")],
        })

    return {
        "query_evidence_digests": query_digests,
        "lead_candidates": lead_candidates,
        "comparison_slots": comparison_slots,
        "entity_profiles": entity_profiles,
    }


def persist_report_planning_assets(output_dir: Optional[str], planning_assets: dict[str, Any]) -> dict[str, Any]:
    """Persist global Reporter planning assets into the outline artifact."""
    path = _outline_path(output_dir)
    outline = _read_json_file(path)
    outline.setdefault("title", "Research Report")
    outline.setdefault("chapters", [])
    outline["planning_assets"] = {
        "query_evidence_digests": list(planning_assets.get("query_evidence_digests") or []),
        "lead_candidates": list(planning_assets.get("lead_candidates") or []),
        "comparison_slots": list(planning_assets.get("comparison_slots") or []),
        "entity_profiles": list(planning_assets.get("entity_profiles") or []),
    }
    _write_json_file(path, outline)
    return outline


def _subset_planning_assets(
    planning_assets: dict[str, Any],
    query_ids: list[str],
) -> dict[str, list[dict[str, Any]]]:
    """Return the subset of planning assets relevant to one chapter."""
    wanted = set(query_ids)

    def relevant(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            item
            for item in items or []
            if wanted.intersection(str(query_id).strip() for query_id in item.get("query_ids") or [])
        ]

    return {
        "query_evidence_digests": [
            item for item in planning_assets.get("query_evidence_digests") or []
            if str(item.get("query_id") or "").strip() in wanted
        ],
        "lead_candidates": relevant(planning_assets.get("lead_candidates") or []),
        "comparison_slots": relevant(planning_assets.get("comparison_slots") or []),
        "entity_profiles": relevant(planning_assets.get("entity_profiles") or []),
    }


def commit_report_outline(output_dir: Optional[str], title: str, chapters: list[dict]) -> dict[str, Any]:
    """Persist the chapter-level report outline for the current run."""
    existing = _read_json_file(_outline_path(output_dir))
    normalized: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for index, chapter in enumerate(chapters or [], start=1):
        chapter_id = int(chapter.get("chapter_id") or index)
        if chapter_id in seen_ids:
            chapter_id = max(seen_ids) + 1 if seen_ids else chapter_id
        seen_ids.add(chapter_id)
        normalized.append({
            "chapter_id": chapter_id,
            "title": str(chapter.get("title") or "").strip() or f"Section {chapter_id}",
            "goals": [str(goal).strip() for goal in chapter.get("goals") or [] if str(goal).strip()],
            "query_ids": [
                str(query_id).strip()
                for query_id in chapter.get("query_ids") or []
                if str(query_id).strip()
            ],
            "section_plan": str(chapter.get("section_plan") or "").strip(),
            "status": str(chapter.get("status") or "pending"),
        })
    outline = {
        "title": str(title).strip() or "Research Report",
        "chapters": normalized,
    }
    if existing.get("planning_assets"):
        outline["planning_assets"] = existing["planning_assets"]
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


def prepare_report_chapter_bundle(
    output_dir: Optional[str],
    chapter_id: int,
    extra_query_ids: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Load one chapter plan together with the evidence needed to write it."""
    outline = _read_json_file(_outline_path(output_dir))
    chapters = outline.get("chapters") or []
    chapter = next((item for item in chapters if int(item.get("chapter_id") or 0) == int(chapter_id)), None)
    if chapter is None:
        return {"status": "error", "message": f"Unknown chapter_id: {chapter_id}"}

    query_ids = list(dict.fromkeys([
        *[str(query_id).strip() for query_id in chapter.get("query_ids") or [] if str(query_id).strip()],
        *[str(query_id).strip() for query_id in extra_query_ids or [] if str(query_id).strip()],
    ]))
    evidence_items: list[dict[str, Any]] = []
    seen_items: set[str] = set()
    for query_id in query_ids:
        offset = 0
        while True:
            page = get_report_evidence(query_id, offset=offset, limit=100)
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

    source_ids = sorted({
        source_id
        for item in evidence_items
        for source_id in item.get("source_ids") or []
    })
    planning_assets = outline.get("planning_assets") or build_report_planning_assets(query_ids)
    chapter_assets = _subset_planning_assets(planning_assets, query_ids)
    top_evidence_items: list[dict[str, Any]] = []
    seen_top_items: set[str] = set()
    evidence_items_by_id = {
        str(item.get("id") or "").strip(): item
        for item in evidence_items
        if str(item.get("id") or "").strip()
    }
    for digest in chapter_assets["query_evidence_digests"]:
        for item_id in digest.get("top_evidence_ids") or []:
            resolved = evidence_items_by_id.get(str(item_id).strip())
            if not resolved or resolved["id"] in seen_top_items:
                continue
            top_evidence_items.append(resolved)
            seen_top_items.add(resolved["id"])
            if len(top_evidence_items) >= 8:
                break
        if len(top_evidence_items) >= 8:
            break
    if len(top_evidence_items) < 8:
        for item in evidence_items:
            if item["id"] in seen_top_items:
                continue
            top_evidence_items.append(item)
            seen_top_items.add(item["id"])
            if len(top_evidence_items) >= 8:
                break

    chapter_comparison_slots = _build_comparison_slots(
        chapter_assets["query_evidence_digests"],
        title=str(chapter.get("title") or ""),
        section_plan=str(chapter.get("section_plan") or ""),
    )
    relevant_conflicts = [
        conflict
        for conflict in get_disclosed_conflicts()
        if set(conflict.get("source_ids") or []).intersection(source_ids)
    ]
    summary_lines = [
        item["text"]
        for item in chapter_assets["lead_candidates"][:2]
        if str(item.get("text") or "").strip()
    ] or [
        line
        for digest in chapter_assets["query_evidence_digests"][:2]
        for line in digest.get("digest_lines")[:1]
        if str(line).strip()
    ]
    section_brief = {
        "chapter_id": int(chapter_id),
        "chapter_title": chapter.get("title"),
        "chapter_goals": chapter.get("goals") or [],
        "section_plan": chapter.get("section_plan") or "",
        "focus_queries": [
            {
                "query_id": digest.get("query_id"),
                "query_handle": digest.get("query_handle"),
                "query_text": digest.get("query_text"),
            }
            for digest in chapter_assets["query_evidence_digests"]
        ],
        "summary": " ".join(summary_lines).strip(),
        "coverage_notes": [
            note
            for note in (
                f"top_evidence_items={len(top_evidence_items)}",
                f"disclosed_conflicts={len(relevant_conflicts)}",
                "comparison scaffolding available" if chapter_comparison_slots else "comparison scaffolding not needed",
            )
            if note
        ],
    }
    bundle = {
        "status": "ok",
        "chapter_id": int(chapter_id),
        "chapter_title": chapter.get("title"),
        "chapter_goals": chapter.get("goals") or [],
        "section_plan": chapter.get("section_plan") or "",
        "query_ids": query_ids,
        "section_brief": section_brief,
        "evidence_items": evidence_items,
        "top_evidence_items": top_evidence_items,
        "query_evidence_digests": chapter_assets["query_evidence_digests"],
        "lead_candidates": chapter_assets["lead_candidates"],
        "comparison_slots": chapter_comparison_slots,
        "entity_profiles": chapter_assets["entity_profiles"],
        "reference_registry_subset": [
            entry for entry in build_reference_registry()
            if entry.get("source_id") in source_ids
        ],
        "disclosed_conflicts": relevant_conflicts,
    }
    meta = {
        "chapter_id": int(chapter_id),
        "title": chapter.get("title"),
        "query_ids": query_ids,
        "source_ids": source_ids,
        "evidence_ids": [item["id"] for item in evidence_items],
        "section_brief": section_brief,
        "top_evidence_ids": [item["id"] for item in top_evidence_items],
        "top_source_ids": _dedupe_preserve_order([
            source_id
            for item in top_evidence_items
            for source_id in item.get("source_ids") or []
        ]),
        "query_evidence_digests": chapter_assets["query_evidence_digests"],
        "lead_candidates": chapter_assets["lead_candidates"],
        "comparison_slots": chapter_comparison_slots,
        "entity_profiles": chapter_assets["entity_profiles"],
    }
    _write_json_file(_chapter_meta_path(output_dir, int(chapter_id)), meta)
    return bundle


def commit_report_chapter(
    output_dir: Optional[str],
    chapter_id: int,
    title: str,
    content: str,
    source_ids: list[str],
    evidence_ids: Optional[list[str]] = None,
    disclosed_conflict_ids: Optional[list[str]] = None,
    section_type: Optional[str] = None,
) -> dict[str, Any]:
    """Persist one chapter draft and its traceability metadata."""
    outline_path = _outline_path(output_dir)
    outline = _read_json_file(outline_path)
    chapters = outline.get("chapters") or []
    chapter = next((item for item in chapters if int(item.get("chapter_id") or 0) == int(chapter_id)), None)
    if chapter is None:
        return {"status": "error", "message": f"Unknown chapter_id: {chapter_id}"}

    chapter["title"] = str(title).strip() or chapter.get("title") or f"Section {chapter_id}"
    chapter["status"] = "completed"
    chapter["source_ids"] = list(dict.fromkeys(source_ids or []))
    chapter["evidence_ids"] = list(dict.fromkeys(evidence_ids or []))
    chapter["disclosed_conflict_ids"] = list(dict.fromkeys(disclosed_conflict_ids or []))
    chapter["section_type"] = section_type
    _write_json_file(outline_path, outline)
    _outline_markdown_path(output_dir).write_text(
        _render_outline_markdown(outline.get("title") or "Research Report", chapters),
        encoding="utf-8",
    )

    chapter_file = _chapter_path(output_dir, int(chapter_id))
    chapter_file.write_text(str(content).strip() + "\n", encoding="utf-8")
    existing_meta = _read_json_file(_chapter_meta_path(output_dir, int(chapter_id)))
    _write_json_file(_chapter_meta_path(output_dir, int(chapter_id)), {
        **existing_meta,
        "chapter_id": int(chapter_id),
        "title": chapter["title"],
        "source_ids": chapter["source_ids"],
        "evidence_ids": chapter["evidence_ids"],
        "disclosed_conflict_ids": chapter["disclosed_conflict_ids"],
        "section_type": chapter["section_type"],
    })
    return {
        "status": "ok",
        "chapter_id": int(chapter_id),
        "path": str(chapter_file),
        "content_length": len(str(content or "")),
    }


def assemble_report_draft(output_dir: Optional[str]) -> dict[str, Any]:
    """Assemble all completed chapters into one draft markdown report."""
    outline = _read_json_file(_outline_path(output_dir))
    chapters = outline.get("chapters") or []
    if not chapters:
        return {"status": "error", "message": "Report outline not found."}

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
    if missing:
        return {"status": "error", "message": f"Missing chapter drafts: {missing}"}

    draft = compile_structured_report(str(outline.get("title") or "Research Report"), sections)
    draft_text = str(draft.get("report") or draft.get("salvaged_report") or "")
    if not draft_text:
        return {
            "status": "error",
            "message": "Draft assembly produced no report text.",
            "issues": draft.get("issues", []),
        }
    path = _draft_path(output_dir)
    path.write_text(draft_text, encoding="utf-8")
    return {
        "status": "ok",
        "draft_path": str(path),
        "draft": draft_text,
        "issues": draft.get("issues", []),
        "revision_requested": bool(draft.get("revision_requested")),
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
    kept: list[str] = []
    for block in re.split(r"\n\s*\n", report_text or ""):
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
    issues.extend(_internal_id_issues(text))
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


def _conflict_source_ids(conflict_id: str, nodes: dict[str, dict], edges: list[dict]) -> list[str]:
    """Return URL-backed Source IDs supporting one disclosed conflict."""
    evidence_ids = [
        edge.get("target")
        for edge in edges
        if edge.get("source") == conflict_id and str(edge.get("type") or "").lower() == "has_conflict"
    ]
    source_ids: list[str] = []
    for evidence_id in evidence_ids:
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
            "source_ids": _conflict_source_ids(str(item.get("id") or ""), nodes, edges),
        })
    conflicts.sort(key=lambda item: item.get("id") or "")
    return conflicts


def _conflict_section_title(is_chinese: bool) -> str:
    """Return the localized conflict-disclosure section title."""
    return "冲突披露" if is_chinese else "Disclosed Conflicts"


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
) -> tuple[list[dict[str, Any]], list[str]]:
    """Ensure every disclosed conflict is structurally covered in the compiled report."""
    disclosed_conflicts = [item for item in get_disclosed_conflicts() if item.get("id") and item.get("description")]
    if not disclosed_conflicts:
        return compiled_sections, []

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
        return compiled_sections, []

    added_ids: list[str] = []
    paragraphs: list[str] = []
    source_ids: set[str] = set()
    for conflict in missing:
        paragraph, conflict_sources = _conflict_section_paragraph(conflict, registry_by_source, is_chinese)
        if not paragraph or not conflict_sources:
            continue
        paragraphs.append(paragraph)
        source_ids.update(conflict_sources)
        added_ids.append(str(conflict["id"]))

    if not paragraphs:
        return compiled_sections, []

    if conflict_section_index is None:
        compiled_sections.append({
            "title": _conflict_section_title(is_chinese),
            "content": "\n\n".join(paragraphs),
            "source_ids": sorted(source_ids),
            "section_type": "conflict_disclosure",
            "disclosed_conflict_ids": added_ids,
        })
    else:
        section = compiled_sections[conflict_section_index]
        section["content"] = "\n\n".join([section["content"], *paragraphs]).strip()
        section["source_ids"] = sorted(set(section.get("source_ids") or []) | source_ids)
        existing_ids = [str(conflict_id) for conflict_id in section.get("disclosed_conflict_ids") or [] if conflict_id]
        section["disclosed_conflict_ids"] = list(dict.fromkeys(existing_ids + added_ids))
        section["section_type"] = "conflict_disclosure"

    return compiled_sections, added_ids


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


def _append_citations_to_block(block: str, citations: str) -> str:
    """Append one section-level citation cluster to the last substantive line."""
    block = _CITE_TOKEN_RE.sub("", str(block or "")).strip()
    if not block or not citations:
        return block
    if _CITE_TOKEN_RE.search(block):
        return block
    lines = block.splitlines()
    for index in range(len(lines) - 1, -1, -1):
        if not lines[index].strip():
            continue
        lines[index] = f"{lines[index].rstrip()} {citations}".rstrip()
        return "\n".join(lines).strip()
    return block


def _compile_section_content(content: str, source_ids: list[str], registry_by_source: dict[str, dict]) -> str:
    """Normalize one chapter body into cited prose blocks."""
    citations = "".join(
        f"[{registry_by_source[source_id]['n']}]"
        for source_id in source_ids
        if source_id in registry_by_source
    )
    blocks, _, _ = _sanitize_section_blocks(content)
    rendered: list[str] = []
    for block in blocks:
        if _ANY_HEADING_RE.match(block):
            rendered.append(_CITE_TOKEN_RE.sub("", block).strip())
            continue
        rendered.append(_append_citations_to_block(block, citations))
    return "\n\n".join(item for item in rendered if item).strip()


def _compile_section_report(
    title: str,
    compiled_sections: list[dict[str, Any]],
    registry: list[dict],
    cited_source_ids: set[str],
) -> str:
    """Render a structured report from already-validated sections."""
    is_chinese = bool(re.search(r"[\u4e00-\u9fff]", title or ""))
    report_title = str(title or ("调研报告" if is_chinese else "Research Report")).strip()
    parts = [f"# {report_title}"]
    for section in compiled_sections:
        parts.extend([f"## {section['title']}", section["content"]])
    parts.append(_render_references(
        registry,
        cited_source_ids,
        "参考文献" if is_chinese else "References",
    ))
    return sanitize_report("\n\n".join(parts))


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


def compile_structured_report(title: str, sections: list[dict]) -> dict:
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
                "hard",
                f"section {section_title!r} requires valid URL-backed source_ids",
                "Replace missing or invalid source_ids with valid URL-backed sources for this section.",
                section_title=section_title,
            ))
            continue
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
        compiled_sections, auto_appended_conflict_ids = _append_missing_conflicts(
            compiled_sections,
            registry_by_source,
            is_chinese,
        )
        cited_source_ids = {
            source_id
            for section in compiled_sections
            for source_id in section.get("source_ids") or []
        }
        candidate = _compile_section_report(title, compiled_sections, registry, cited_source_ids)
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

    if accepted:
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


def _source_ids_for_conflict(conflict_text: str, items: list[dict], fallback_ids: list[str]) -> list[str]:
    """Find likely supporting sources for a disclosed conflict description."""
    fragments = [
        fragment.lower()
        for fragment in re.split(r"[\s,，。:：;；/]+", conflict_text or "")
        if len(fragment) >= 4
    ][:4]
    matched: list[str] = []
    for item in items:
        item_text = str(item.get("text") or "").lower()
        if fragments and any(fragment in item_text for fragment in fragments):
            matched.extend(item.get("source_ids") or [])
    return list(dict.fromkeys(matched or fallback_ids[:3]))


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

    topic_sections: list[tuple[str, list[str], set[str]]] = []
    all_items: list[dict] = []
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
        all_items.extend(items)
        title = _guess_topic_title(query, index, is_chinese)
        paragraphs: list[str] = []
        section_source_ids: set[str] = set()
        for chunk in _chunked(items, 4):
            paragraph, chunk_source_ids = _render_fact_paragraph(chunk, registry_by_source, is_chinese)
            if paragraph:
                paragraphs.append(paragraph)
                section_source_ids.update(chunk_source_ids)
        if paragraphs:
            topic_sections.append((title, paragraphs, section_source_ids))
            all_source_ids.extend(section_source_ids)

    deduped_fallback_ids = list(dict.fromkeys(all_source_ids))
    if not topic_sections or not deduped_fallback_ids:
        return ""

    report_title = str(request_text or ("调研报告" if is_chinese else "Research Report")).strip() or (
        "调研报告" if is_chinese else "Research Report"
    )
    cited_source_ids: set[str] = set()
    parts = [f"# {report_title}"]

    time_window = str(goal.get("time_window") or "").strip()
    region_scope = str(goal.get("region_scope") or "").strip()
    limitations = [
        str(item.get("description") or item.get("text") or "").strip()
        for item in graph_tools.search_nodes("analysis", {"analysis_type": "objective"})
        if item.get("status") == "blocked_best_effort"
    ]
    limitations = [item for item in limitations if item]
    scope_citations = "".join(
        f"[{registry_by_source[source_id]['n']}]"
        for source_id in deduped_fallback_ids[:3]
        if source_id in registry_by_source
    )
    scope_bits = [bit for bit in (time_window, region_scope) if bit]
    if limitations:
        scope_bits.append("；".join(limitations[:3]) if is_chinese else "; ".join(limitations[:3]))
    scope_paragraph = (
        f"本报告主要依据{ '，'.join(scope_bits) }范围内已核实的公开资料展开；"
        f"对于公开信息不足的维度，正文仅保留已能确认的结论。{scope_citations}"
    ) if scope_bits and is_chinese else (
        f"This report is based on verified public information within the following scope: "
        f"{', '.join(scope_bits)}. Where public information remains limited, the report keeps only"
        f" the conclusions that can be verified. {scope_citations}"
    ) if scope_bits else (
        f"本报告基于本轮已核实的公开资料组织为主题化综述；对于无法进一步核实的维度，"
        f"正文仅保留可确认的事实与明确披露的限制。{scope_citations}"
    ) if is_chinese else (
        f"This report is organized as a topic-based synthesis of the verified public information collected in the"
        f" current run. Where verification remains incomplete, the report keeps only confirmed facts and explicitly"
        f" disclosed limitations. {scope_citations}"
    )
    parts.extend([
        "## 研究范围与局限" if is_chinese else "## Scope and Limitations",
        scope_paragraph,
    ])
    cited_source_ids.update(source_id for source_id in deduped_fallback_ids[:3] if source_id in registry_by_source)

    for title, paragraphs, section_source_ids in topic_sections:
        parts.append(f"## {title}")
        parts.extend(paragraphs)
        cited_source_ids.update(section_source_ids)

    conflicts = [item for item in get_disclosed_conflicts() if item.get("description")]
    if conflicts:
        parts.append(f"## {_conflict_section_title(is_chinese)}")
        for conflict in conflicts:
            source_ids = [
                source_id for source_id in dict.fromkeys(conflict.get("source_ids") or [])
                if source_id in registry_by_source
            ] or _source_ids_for_conflict(str(conflict.get("description") or ""), all_items, deduped_fallback_ids)
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
    issues.extend(_internal_id_issues(text))
    ref_match = _REF_HEADING_RE.search(text)
    body = text[: ref_match.start()] if ref_match else text
    sections = _parse_sections(body)

    from tools import research_state

    goal = research_state.get_goal()
    years = [int(year) for year in re.findall(r"\b(?:19|20)\d{2}\b", str(goal.get("time_window") or ""))]
    references = _reference_sources(text)
    blocked_domains = _goal_source_blocklist()
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
    if blocked_domains and references:
        for section in sections:
            for citation in section["cites"]:
                source = references.get(citation, {})
                domain = _source_domain(source)
                if domain and _matches_blocked_domain(domain, blocked_domains):
                    issues.append(
                        f"forbidden source cited in report: {section['title']} [{citation}] {domain}"
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
