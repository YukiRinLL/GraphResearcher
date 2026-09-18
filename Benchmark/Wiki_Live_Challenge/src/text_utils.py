"""
Text processing utilities for Wiki Live Challenge.
"""

from __future__ import annotations
import re
from typing import List


# Regex patterns
_FOOTNOTE_BRACKET_RE = re.compile(r"\[[^\]]+\]")
_SENT_BOUNDARY_RE = re.compile(r"(?<!\b[A-Z])([.!?])[ \t\n\r\f\v]+(?=[A-Z0-9\[])")
_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\([^)]+\)")
_EMPTY_LABEL_LINK_RE = re.compile(r"\[\]\([^)]+\)")
_CLOSE_BRACKET_PAREN_URL_RE = re.compile(r"\]\([^)]+\)")
_PAREN_URL_WITH_HTTP_RE = re.compile(r"\((?:https?://|www\.)[^)]+\)")
_CITATION_RE = re.compile(r'\[(?:\d+(?:,\s*\d+)*(?:\]\[)?)+\]')
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def normalize_whitespace(text: str) -> str:
    """Collapse all whitespace to single spaces and trim"""
    return re.sub(r"\s+", " ", text).strip()


def strip_footnotes(text: str) -> str:
    """Remove bracket-style footnote markers like [1], [a], etc."""
    return _FOOTNOTE_BRACKET_RE.sub(" ", text)


def strip_citations(text: str) -> str:
    """Remove citation markers like [1], [2,3], [1][2], etc."""
    return _CITATION_RE.sub('', text).strip()


def strip_links(text: str) -> str:
    """Remove Markdown links and images
    
    - Removes ![alt](url) images
    - Removes [label](url) links
    - Removes [](url) empty links
    - Removes residual ](url)
    - Removes (https://...) parenthesized URLs
    """
    text = _MARKDOWN_IMAGE_RE.sub(" ", text)
    text = _MARKDOWN_LINK_RE.sub(" ", text)
    text = _EMPTY_LABEL_LINK_RE.sub(" ", text)
    text = _CLOSE_BRACKET_PAREN_URL_RE.sub(" ", text)
    text = _PAREN_URL_WITH_HTTP_RE.sub(" ", text)
    return text


def strip_references_section(md_text: str) -> str:
    """Remove References/See Also and similar sections from Markdown"""
    lines = md_text.splitlines()
    result_lines = []
    in_references = False
    
    skip_sections = {
        'references', 'reference', 'see also', 'external links',
        'further reading', 'notes', 'bibliography', 'sources'
    }
    
    for line in lines:
        match = _HEADING_RE.match(line.strip())
        if match:
            heading_text = match.group(2).lower().strip()
            if heading_text in skip_sections:
                in_references = True
                continue
            else:
                in_references = False
        
        if not in_references:
            result_lines.append(line)
    
    return '\n'.join(result_lines)


def split_into_sentences(text: str) -> List[str]:
    """Split text into sentences
    
    - Removes inline Markdown links
    - Removes footnote markers
    - Normalizes whitespace
    - Splits on sentence boundaries
    """
    cleaned = strip_links(text)
    normalized = normalize_whitespace(strip_footnotes(cleaned))
    if not normalized:
        return []
    
    parts = _SENT_BOUNDARY_RE.split(normalized)
    sentences: List[str] = []
    buffer: list[str] = []
    
    for token in parts:
        if token in {".", "!", "?"}:
            buffer.append(token)
            sentence = "".join(buffer).strip()
            if sentence:
                sentences.append(sentence)
            buffer = []
        else:
            buffer.append(token)
    
    tail = "".join(buffer).strip()
    if tail:
        sentences.append(tail)
    
    return sentences


def get_clean_text(text: str) -> str:
    """Get clean text without citations and references section
    
    Args:
        text: Raw text (may contain citations and references)
        
    Returns:
        Clean text without [1] markers and References section
    """
    text = strip_references_section(text)
    text = strip_citations(text)
    return text.strip()


def extract_title_from_markdown(md_text: str) -> str:
    """Extract title from the first heading in Markdown"""
    for line in md_text.splitlines():
        match = _HEADING_RE.match(line.strip())
        if match:
            return match.group(2).strip()
    return ""


def extract_headings(md_text: str) -> List[tuple]:
    """Extract all headings from Markdown
    
    Returns:
        List of (level, title) tuples
    """
    headings = []
    for line in md_text.splitlines():
        match = _HEADING_RE.match(line.strip())
        if match:
            level = len(match.group(1))
            title = match.group(2).strip()
            headings.append((level, title))
    return headings
