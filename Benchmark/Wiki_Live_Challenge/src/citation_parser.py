"""
Citation parser for Wiki Live Challenge.

Extracts citation information from markdown files:
- Citation URLs from References section
- Inline citation markers [n]
- Mapping between citation numbers and URLs
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional


class CitationParser:
    """
    Parses citation information from markdown content.
    
    Supports various reference formats:
    - [n] url
    - [n] Title [url](url)
    - [n] Title: url
    - n. [Title](url)
    - Multi-number format: [1] [2] Title\\nurl
    """
    
    # Reference section header patterns
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
    
    def extract_citation_urls(self, content: str) -> Dict[str, str]:
        """
        Extract citation number to URL mapping from markdown content.
        
        Args:
            content: Markdown content.
        
        Returns:
            Dictionary mapping citation numbers (as strings) to URLs.
        """
        citation_urls = {}
        
        # First try: inline citations [[n](url)] format (e.g., qwen articles)
        for m in re.finditer(r'\[\[(\d+)\]\((https?://[^)]+)\)', content):
            num = m.group(1)
            url = m.group(2)
            if num not in citation_urls:
                citation_urls[num] = url
        
        if citation_urls:
            return citation_urls
        
        # Find references section
        ref_match = self.ref_pattern.search(content)
        if not ref_match:
            return citation_urls
        
        ref_section = content[ref_match.end():]
        
        # Try different formats
        
        # Format 1: Multi-number per URL ([1] [2]... title\nurl)
        lines = ref_section.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            
            # Check for [n] patterns
            nums = re.findall(r'\[(\d+)\]', line)
            if nums and i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                # Check if next line is a bare URL
                if re.match(r'^https?://\S+$', next_line):
                    for num in nums:
                        citation_urls[num] = next_line
                    i += 2
                    continue
            i += 1
        
        if citation_urls:
            return citation_urls
        
        # Format 2: [n] url (standard)
        for m in re.finditer(r'^\[(\d+)\]\s+(https?://\S+)', ref_section, re.MULTILINE):
            num = m.group(1)
            url = m.group(2).rstrip(')')
            if num not in citation_urls:
                citation_urls[num] = url
        
        if citation_urls:
            return citation_urls
        
        # Format 3: [n] Title: url or [n] ... URL: url
        for m in re.finditer(r'\[(\d+)\].*?(?:URL:|:)\s*(https?://\S+)', ref_section, re.IGNORECASE):
            num = m.group(1)
            url = m.group(2).rstrip(')')
            if num not in citation_urls:
                citation_urls[num] = url
        
        if citation_urls:
            return citation_urls
        
        # Format 4: [n] Title [url](url) or [n] ...(url)
        for m in re.finditer(r'\\?\[(\d+)\].*?\((https?://[^)]+)\)', ref_section):
            num = m.group(1)
            url = m.group(2)
            if num not in citation_urls:
                citation_urls[num] = url
        
        if citation_urls:
            return citation_urls
        
        # Format 5: n. [Title](url)
        for m in re.finditer(r'^(\d+)\.\s+\[.*?\]\((https?://[^)]+)\)', ref_section, re.MULTILINE):
            num = m.group(1)
            url = m.group(2)
            if num not in citation_urls:
                citation_urls[num] = url
        
        return citation_urls
    
    def extract_clean_text(self, content: str) -> str:
        """
        Extract main text without citations and references section.
        
        Args:
            content: Markdown content.
        
        Returns:
            Clean text without [n] markers and References section.
        """
        # Remove references section
        ref_match = self.ref_pattern.search(content)
        if ref_match:
            content = content[:ref_match.start()]
        
        # Remove citation markers [n]
        clean = re.sub(r'\[\d+\]', '', content)
        
        # Clean up whitespace
        clean = re.sub(r'  +', ' ', clean)
        clean = re.sub(r'\n{3,}', '\n\n', clean)
        
        return clean.strip()
    
    def extract_inline_citations(self, content: str) -> List[Tuple[str, List[str]]]:
        """
        Extract inline citations and their context.
        
        Args:
            content: Markdown content.
        
        Returns:
            List of (sentence, [citation_numbers]) tuples.
        """
        # Remove references section first
        ref_match = self.ref_pattern.search(content)
        if ref_match:
            content = content[:ref_match.start()]
        
        results = []
        
        # Split into sentences (roughly)
        sentences = re.split(r'(?<=[.!?])\s+', content)
        
        for sentence in sentences:
            # Find all citation markers
            citations = re.findall(r'\[(\d+)\]', sentence)
            if citations:
                # Clean the sentence
                clean_sentence = re.sub(r'\[\d+\]', '', sentence).strip()
                results.append((clean_sentence, citations))
        
        return results
    
    def validate_citations(
        self,
        content: str,
        citation_urls: Dict[str, str]
    ) -> Dict[str, List[str]]:
        """
        Validate that all inline citations have corresponding URLs.
        
        Args:
            content: Markdown content.
            citation_urls: Citation URL mapping.
        
        Returns:
            Dictionary with 'valid', 'missing', and 'unused' citation numbers.
        """
        # Get all inline citation numbers
        ref_match = self.ref_pattern.search(content)
        main_text = content[:ref_match.start()] if ref_match else content
        
        inline_citations = set(re.findall(r'\[(\d+)\]', main_text))
        url_citations = set(citation_urls.keys())
        
        return {
            'valid': sorted(inline_citations & url_citations, key=int),
            'missing': sorted(inline_citations - url_citations, key=int),
            'unused': sorted(url_citations - inline_citations, key=int),
        }
    
    def process_file(self, file_path: Path) -> Dict:
        """
        Process a markdown file and extract all citation information.
        
        Args:
            file_path: Path to markdown file.
        
        Returns:
            Dictionary with citation_urls, clean_text, and validation results.
        """
        content = file_path.read_text(encoding='utf-8')
        
        citation_urls = self.extract_citation_urls(content)
        clean_text = self.extract_clean_text(content)
        validation = self.validate_citations(content, citation_urls)
        
        return {
            'citation_urls': citation_urls,
            'clean_text': clean_text,
            'validation': validation,
            'citation_count': len(citation_urls),
        }
