"""
Article loader for Wiki Live Challenge evaluation.

Loads articles from various formats (Markdown, JSON).
Supports benchmark data structure with wiki_data and test_data.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import json
import re
from typing import List, Dict, Any, Optional, Tuple

from .text_utils import (
    strip_citations, strip_references_section, split_into_sentences,
    get_clean_text, extract_title_from_markdown
)


@dataclass
class Section:
    """Article section"""
    title: str
    level: int
    content: str


@dataclass
class Article:
    """Loaded article with metadata"""
    title: str
    sections: List[Section]
    raw: str  # Original raw text
    statements: List[Dict[str, Any]] = field(default_factory=list)
    citation_urls: Dict[str, str] = field(default_factory=dict)
    citation_contents: Dict[str, Dict[str, Any]] = field(default_factory=dict)


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_META_PREFIXES = (
    "Title:",
    "URL Source:",
    "Published Time:",
    "Markdown Content:",
    "Citations:",
)


def _parse_sections(markdown_text: str) -> List[Section]:
    """Parse Markdown into sections"""
    sections: List[Section] = []
    current_title = "lead"
    current_level = 1
    current_lines: List[str] = []
    
    for line in markdown_text.splitlines():
        m = _HEADING_RE.match(line.strip())
        if m:
            if current_lines:
                sections.append(Section(
                    current_title,
                    current_level,
                    "\n".join(current_lines).strip()
                ))
                current_lines = []
            current_level = len(m.group(1))
            current_title = m.group(2).strip()
        else:
            current_lines.append(line)
    
    if current_lines:
        sections.append(Section(
            current_title,
            current_level,
            "\n".join(current_lines).strip()
        ))
    
    return sections


def _strip_meta(md: str) -> tuple:
    """Remove metadata lines from Markdown"""
    lines = md.splitlines()
    body_lines: List[str] = []
    meta: Dict[str, str] = {}
    
    for line in lines:
        if any(line.startswith(p) for p in _META_PREFIXES):
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
            continue
        body_lines.append(line)
    
    body = "\n".join(body_lines).strip()
    return body, meta


def load_markdown_article(path: Path, strip_citations_flag: bool = False) -> Article:
    """Load article from Markdown file
    
    Args:
        path: Path to Markdown file
        strip_citations_flag: If True, remove citations and references
    """
    text = path.read_text(encoding="utf-8")
    body, meta = _strip_meta(text)
    
    if strip_citations_flag:
        body = strip_references_section(body)
        body = strip_citations(body)
    
    title = meta.get("Title", "").strip() or extract_title_from_markdown(body) or path.stem
    sections = _parse_sections(body)
    
    return Article(
        title=title,
        sections=sections,
        raw=body if strip_citations_flag else text
    )


def load_json_article(path: Path, strip_citations_flag: bool = False) -> Article:
    """Load article from Wiki JSON format
    
    Args:
        path: Path to JSON file
        strip_citations_flag: If True, remove citations and references
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return Article(title=path.stem, sections=[], raw="")
    
    pages = ((data or {}).get("query") or {}).get("pages") or {}
    page_obj = None
    for _, page in pages.items():
        page_obj = page
        break
    
    if not page_obj:
        return Article(title=path.stem, sections=[], raw="")
    
    title = str(page_obj.get("title") or path.stem)
    
    # Get raw text - priority: markdown > extract_with_tables > extract
    raw_text = str(
        page_obj.get("markdown") or
        page_obj.get("extract_with_tables") or
        page_obj.get("extract_with_citations") or
        page_obj.get("extract") or ""
    )
    
    if strip_citations_flag:
        raw_text = strip_references_section(raw_text)
        raw_text = strip_citations(raw_text)
    
    # Parse sections
    sections = _parse_sections(raw_text) if raw_text.strip() else []
    
    # Get statements
    statements = page_obj.get("statements", [])
    
    # Get citation URLs
    citation_urls_raw = page_obj.get("citation_urls", {})
    citation_urls = {str(k): v for k, v in citation_urls_raw.items()}
    
    # Get citation contents
    citation_contents = page_obj.get("citation_contents", {})
    if not citation_contents:
        citation_contents = page_obj.get("url_contents", {})
    
    return Article(
        title=title,
        sections=sections,
        raw=raw_text,
        statements=statements,
        citation_urls=citation_urls,
        citation_contents=citation_contents,
    )


def load_article(path: Path, strip_citations_flag: bool = False) -> Article:
    """Auto-detect format and load article
    
    Args:
        path: Path to article file
        strip_citations_flag: If True, remove citations and references
    """
    suffix = path.suffix.lower()
    if suffix == ".json":
        return load_json_article(path, strip_citations_flag)
    elif suffix in (".md", ".markdown"):
        return load_markdown_article(path, strip_citations_flag)
    else:
        # Try JSON first, then Markdown
        try:
            return load_json_article(path, strip_citations_flag)
        except Exception:
            return load_markdown_article(path, strip_citations_flag)


def get_article_sentences(
    article: Article,
    strip_citations_flag: bool = True
) -> List[str]:
    """Extract sentences from article
    
    Args:
        article: Article object
        strip_citations_flag: If True, remove citation markers
        
    Returns:
        List of sentences
    """
    text = article.raw
    if strip_citations_flag:
        text = strip_references_section(text)
        text = strip_citations(text)
    
    return split_into_sentences(text)


def get_clean_article_text(article: Article) -> str:
    """Get clean text without citations and references
    
    Args:
        article: Article object
        
    Returns:
        Clean text
    """
    return get_clean_text(article.raw)


def get_article_full_text(article: Article, clean: bool = True) -> str:
    """Get full article text
    
    Args:
        article: Article object
        clean: If True, remove citations and references
        
    Returns:
        Article text
    """
    if clean:
        return get_clean_article_text(article)
    
    if article.raw and article.raw.strip():
        return article.raw.strip()
    
    # Fallback to sections
    texts = []
    for section in article.sections:
        if section.title:
            texts.append(f"## {section.title}\n")
        if section.content:
            texts.append(section.content)
    
    return "\n\n".join(texts)


# ==================== Wiki Data Loaders ====================

def load_wiki_statements(path: Path) -> List[Dict[str, Any]]:
    """Load wiki statements from JSON file
    
    Wiki statements are stored as: [{"statement": "..."}, ...]
    
    Args:
        path: Path to statement JSON file
        
    Returns:
        List of statement dicts
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []


def load_wiki_article_with_statements(
    article_path: Path,
    statement_path: Optional[Path] = None,
    strip_citations_flag: bool = False
) -> Article:
    """Load wiki article with corresponding statements
    
    Args:
        article_path: Path to wiki MD file
        statement_path: Path to statement JSON (auto-detected if None)
        strip_citations_flag: If True, remove citations
        
    Returns:
        Article with statements loaded
    """
    article = load_markdown_article(article_path, strip_citations_flag)
    
    # Auto-detect statement file
    if statement_path is None:
        # Try: article/Name.md -> statement/Name_statements.json
        stmt_dir = article_path.parent.parent / "statement"
        statement_path = stmt_dir / f"{article_path.stem}_statements.json"
    
    if statement_path and statement_path.exists():
        wiki_stmts = load_wiki_statements(statement_path)
        # Convert wiki format to standard format
        article.statements = [
            {"fact": s.get("statement", ""), "ref_idx": None, "url": None}
            for s in wiki_stmts if s.get("statement")
        ]
    
    return article


def load_generated_article(path: Path, strip_citations_flag: bool = False) -> Article:
    """Load generated article from test_data JSON
    
    Generated articles use the nested format:
    {"query": {"pages": {"id": {...}}}} or {"batchcomplete": ..., "query": ...}
    
    Args:
        path: Path to generated JSON file
        strip_citations_flag: If True, remove citations
        
    Returns:
        Article object
    """
    return load_json_article(path, strip_citations_flag)


# ==================== Benchmark Article Pair Loader ====================

def find_article_pair(
    article_name: str,
    gen_dir: Path,
    wiki_dir: Path,
    gen_type: str = "json"
) -> Tuple[Optional[Path], Optional[Path]]:
    """Find matching generated and wiki article paths
    
    Args:
        article_name: Article name (without extension)
        gen_dir: Generated data directory (json_data or md_data)
        wiki_dir: Wiki data directory (cleaned_data/article)
        gen_type: "json" or "md" for generated article
        
    Returns:
        Tuple of (gen_path, wiki_path), None if not found
    """
    gen_ext = ".json" if gen_type == "json" else ".md"
    gen_path = gen_dir / f"{article_name}{gen_ext}"
    wiki_path = wiki_dir / f"{article_name}.md"
    
    if not gen_path.exists():
        gen_path = None
    if not wiki_path.exists():
        wiki_path = None
    
    return gen_path, wiki_path


def load_article_pair(
    article_name: str,
    gen_dir: Path,
    wiki_article_dir: Path,
    wiki_statement_dir: Optional[Path] = None,
    gen_type: str = "json",
    strip_citations_flag: bool = False
) -> Tuple[Optional[Article], Optional[Article]]:
    """Load a pair of generated and wiki articles
    
    Args:
        article_name: Article name
        gen_dir: Generated data directory
        wiki_article_dir: Wiki article directory
        wiki_statement_dir: Wiki statement directory (optional)
        gen_type: "json" or "md"
        strip_citations_flag: If True, remove citations
        
    Returns:
        Tuple of (gen_article, wiki_article)
    """
    gen_path, wiki_path = find_article_pair(
        article_name, gen_dir, wiki_article_dir, gen_type
    )
    
    gen_article = None
    wiki_article = None
    
    if gen_path:
        if gen_type == "json":
            gen_article = load_json_article(gen_path, strip_citations_flag)
        else:
            gen_article = load_markdown_article(gen_path, strip_citations_flag)
    
    if wiki_path:
        stmt_path = None
        if wiki_statement_dir:
            stmt_path = wiki_statement_dir / f"{article_name}_statements.json"
            if not stmt_path.exists():
                stmt_path = None
        wiki_article = load_wiki_article_with_statements(
            wiki_path, stmt_path, strip_citations_flag
        )
    
    return gen_article, wiki_article
