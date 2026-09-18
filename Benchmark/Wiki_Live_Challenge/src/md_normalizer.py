"""
Markdown normalizer for Wiki Live Challenge.

Handles various MD formats from different sources and normalizes them to a standard format:
- Standard heading format (# Title, ## Section)
- Standard reference format ([n] url)
- Deduplication of references
- Removal of duplicate titles
"""

import re
from pathlib import Path
from typing import Tuple, List, Dict, Optional


class MDNormalizer:
    """
    Normalizes Markdown files to a standard format.
    
    Supported input formats:
    - gemini: References as "n. Title [url](url)"
    - openai: Various reference formats
    - perplexity: Standard [n] url format
    - doubao: Chinese reference headers
    - langchain: "n. [Title](url)" format
    - And more...
    """
    
    # Reference section headers (various formats)
    REF_HEADERS = [
        r'#{1,4}\s*(?:References?|Sources?|Citations?|参考资料)\s*\n',
        r'\*\*(?:References?|Sources?|参考资料).*?\*\*\s*\n',
        r'(?:References?|Sources?):?\s*\n',
    ]
    
    def __init__(self):
        self.ref_pattern = re.compile(
            '|'.join(f'({p})' for p in self.REF_HEADERS),
            re.IGNORECASE
        )
    
    def normalize(self, content: str, source: Optional[str] = None) -> str:
        """
        Normalize markdown content to standard format.
        
        Args:
            content: Raw markdown content.
            source: Optional source identifier (gemini, openai, etc.)
        
        Returns:
            Normalized markdown content.
        """
        # Step 1: Fix headings (Wiki-style to Markdown)
        content = self._fix_headings(content)
        
        # Step 2: Remove duplicate title
        content = self._remove_duplicate_title(content)
        
        # Step 3: Normalize reference format
        content = self._normalize_references(content, source)
        
        # Step 4: Deduplicate references
        content = self._deduplicate_references(content)
        
        # Step 5: Clean up whitespace
        content = self._clean_whitespace(content)
        
        return content
    
    def _fix_headings(self, content: str) -> str:
        """Convert Wiki-style headings to Markdown format."""
        # == Heading == -> ## Heading
        content = re.sub(r'^====\s*(.+?)\s*====\s*$', r'#### \1', content, flags=re.MULTILINE)
        content = re.sub(r'^===\s*(.+?)\s*===\s*$', r'### \1', content, flags=re.MULTILINE)
        content = re.sub(r'^==\s*(.+?)\s*==\s*$', r'## \1', content, flags=re.MULTILINE)
        return content
    
    def _remove_duplicate_title(self, content: str) -> str:
        """Remove duplicate title if first line matches # Title."""
        lines = content.split('\n')
        if len(lines) < 2:
            return content
        
        # Check if first line is plain text that matches the # Title
        first_line = lines[0].strip()
        if first_line.startswith('#'):
            return content
        
        # Look for # Title in first few lines
        for i, line in enumerate(lines[1:6], 1):
            if line.startswith('# '):
                title = line[2:].strip()
                # Check if first line is similar to title
                if self._is_similar_title(first_line, title):
                    lines = lines[1:]  # Remove first line
                    break
        
        return '\n'.join(lines)
    
    def _is_similar_title(self, line: str, title: str) -> bool:
        """Check if a line is similar to the title."""
        line_clean = re.sub(r'[^\w\s]', '', line.lower()).strip()
        title_clean = re.sub(r'[^\w\s]', '', title.lower()).strip()
        return line_clean == title_clean or line_clean in title_clean or title_clean in line_clean
    
    def _normalize_references(self, content: str, source: Optional[str] = None) -> str:
        """Normalize reference section to standard [n] url format."""
        # Find references section
        ref_match = self.ref_pattern.search(content)
        if not ref_match:
            return content
        
        main_text = content[:ref_match.end()]
        ref_section = content[ref_match.end():]
        
        # Normalize reference entries
        new_refs = []
        
        # Try different formats
        
        # Format 1: n. Title [url](url) -> [n] Title [url](url)
        ref_section = re.sub(
            r'^(\d+)\.\s+(.+)$',
            lambda m: f'[{m.group(1)}] {m.group(2)}',
            ref_section,
            flags=re.MULTILINE
        )
        
        # Ensure space after [n]
        ref_section = re.sub(r'\[(\d+)\]([^\s\[])', r'[\1] \2', ref_section)
        
        return main_text + ref_section
    
    def _deduplicate_references(self, content: str) -> str:
        """Remove duplicate reference entries."""
        ref_match = self.ref_pattern.search(content)
        if not ref_match:
            return content
        
        main_text = content[:ref_match.end()]
        ref_section = content[ref_match.end():]
        
        # Extract reference entries
        entries = []
        seen_urls = set()
        
        for line in ref_section.split('\n'):
            line_stripped = line.strip()
            if not line_stripped:
                continue
            
            # Extract URL from line
            url_match = re.search(r'https?://[^\s\)]+', line_stripped)
            if url_match:
                url = url_match.group(0).rstrip('.,;)')
                if url not in seen_urls:
                    seen_urls.add(url)
                    entries.append(line)
            else:
                entries.append(line)
        
        return main_text + '\n'.join(entries)
    
    def _clean_whitespace(self, content: str) -> str:
        """Clean up excessive whitespace."""
        # Remove trailing whitespace
        content = re.sub(r'[ \t]+$', '', content, flags=re.MULTILINE)
        # Normalize multiple newlines
        content = re.sub(r'\n{3,}', '\n\n', content)
        return content.strip()
    
    def detect_format(self, content: str) -> str:
        """
        Detect the format/source of markdown content.
        
        Returns:
            Detected format name (gemini, openai, perplexity, etc.)
        """
        # Check for specific patterns
        
        # Gemini: n. Title [url](url) in references
        if re.search(r'^\d+\.\s+.+\[https?://', content, re.MULTILINE):
            return 'gemini'
        
        # Doubao: Chinese reference header
        if re.search(r'\*\*参考资料', content):
            return 'doubao'
        
        # Langchain: n. [Title](url) format
        if re.search(r'^\d+\.\s+\[.+?\]\(https?://', content, re.MULTILINE):
            return 'langchain'
        
        # Standard format with [n] url
        if re.search(r'^\[(\d+)\]\s+https?://', content, re.MULTILINE):
            return 'standard'
        
        return 'unknown'
    
    def process_file(self, input_path: Path, output_path: Optional[Path] = None) -> str:
        """
        Process a single markdown file.
        
        Args:
            input_path: Path to input markdown file.
            output_path: Optional path to write normalized content.
        
        Returns:
            Normalized content.
        """
        content = input_path.read_text(encoding='utf-8')
        source = self.detect_format(content)
        normalized = self.normalize(content, source)
        
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(normalized, encoding='utf-8')
        
        return normalized
    
    def process_directory(
        self,
        input_dir: Path,
        output_dir: Optional[Path] = None,
        in_place: bool = False
    ) -> Dict[str, int]:
        """
        Process all markdown files in a directory.
        
        Args:
            input_dir: Input directory containing .md files.
            output_dir: Output directory for normalized files.
            in_place: If True, modify files in place (ignores output_dir).
        
        Returns:
            Statistics dict with counts.
        """
        stats = {'processed': 0, 'skipped': 0, 'errors': 0}
        
        for md_file in sorted(input_dir.glob('*.md')):
            try:
                if in_place:
                    out_path = md_file
                elif output_dir:
                    out_path = output_dir / md_file.name
                else:
                    out_path = None
                
                self.process_file(md_file, out_path)
                stats['processed'] += 1
            except Exception as e:
                print(f"Error processing {md_file.name}: {e}")
                stats['errors'] += 1
        
        return stats
