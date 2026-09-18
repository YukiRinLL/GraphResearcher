"""
JSON builder for Wiki Live Challenge.

Builds the final JSON structure from processed markdown data.
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional


class JSONBuilder:
    """
    Builds JSON data structure from markdown processing results.
    
    JSON Structure:
    {
        "batchcomplete": "",
        "query": {
            "pages": {
                "<page_id>": {
                    "pageid": <int>,
                    "ns": 0,
                    "title": "<title>",
                    "extract": "<clean text without citations>",
                    "citation_urls": {"1": "url1", "2": "url2", ...},
                    "statements": [...],
                    "citation_contents": {...},
                    "source_file": "<relative path>"
                }
            }
        }
    }
    """
    
    def __init__(self):
        pass
    
    def _generate_page_id(self, title: str) -> int:
        """Generate a consistent page ID from title."""
        return abs(int(hashlib.md5(title.encode()).hexdigest()[:8], 16)) % (10**8)
    
    def build(
        self,
        title: str,
        extract: str,
        citation_urls: Dict[str, str],
        statements: List[Dict[str, Any]],
        citation_contents: Optional[Dict[str, Dict[str, Any]]] = None,
        source_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Build the JSON structure.
        
        Args:
            title: Article title.
            extract: Clean text without citations.
            citation_urls: Citation number to URL mapping.
            statements: Extracted statements list.
            citation_contents: Optional fetched citation contents.
            source_file: Optional source file path.
        
        Returns:
            Complete JSON structure.
        """
        page_id = self._generate_page_id(title)
        
        page_data = {
            "pageid": page_id,
            "ns": 0,
            "title": title,
            "extract": extract,
            "citation_urls": citation_urls,
            "statements": statements,
        }
        
        if citation_contents is not None:
            page_data["citation_contents"] = citation_contents
        
        if source_file is not None:
            page_data["source_file"] = source_file
        
        return {
            "batchcomplete": "",
            "query": {
                "pages": {
                    str(page_id): page_data
                }
            }
        }
    
    def build_from_md(
        self,
        md_path: Path,
        citation_parser,
        statements: List[Dict[str, Any]],
        citation_contents: Optional[Dict[str, Dict[str, Any]]] = None,
        base_dir: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        Build JSON from a markdown file.
        
        Args:
            md_path: Path to markdown file.
            citation_parser: CitationParser instance.
            statements: Extracted statements.
            citation_contents: Optional fetched contents.
            base_dir: Base directory for relative source_file path.
        
        Returns:
            Complete JSON structure.
        """
        content = md_path.read_text(encoding='utf-8')
        
        # Extract title from first heading
        import re
        title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else md_path.stem
        
        # Get citation data
        citation_urls = citation_parser.extract_citation_urls(content)
        extract = citation_parser.extract_clean_text(content)
        
        # Compute relative source path
        if base_dir:
            try:
                source_file = str(md_path.relative_to(base_dir))
            except ValueError:
                source_file = md_path.name
        else:
            source_file = md_path.name
        
        return self.build(
            title=title,
            extract=extract,
            citation_urls=citation_urls,
            statements=statements,
            citation_contents=citation_contents,
            source_file=source_file
        )
    
    def save(self, data: Dict[str, Any], output_path: Path) -> None:
        """
        Save JSON data to file.
        
        Args:
            data: JSON data structure.
            output_path: Output file path.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def load(self, json_path: Path) -> Dict[str, Any]:
        """
        Load JSON data from file.
        
        Args:
            json_path: Path to JSON file.
        
        Returns:
            JSON data structure.
        """
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def update_statements(
        self,
        data: Dict[str, Any],
        statements: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Update statements in existing JSON data.
        
        Args:
            data: Existing JSON data.
            statements: New statements list.
        
        Returns:
            Updated JSON data.
        """
        page = list(data['query']['pages'].values())[0]
        page['statements'] = statements
        return data
    
    def update_citation_contents(
        self,
        data: Dict[str, Any],
        new_contents: Dict[str, Dict[str, Any]],
        merge: bool = True
    ) -> Dict[str, Any]:
        """
        Update citation contents in existing JSON data.
        
        Args:
            data: Existing JSON data.
            new_contents: New citation contents.
            merge: If True, merge with existing; if False, replace.
        
        Returns:
            Updated JSON data.
        """
        page = list(data['query']['pages'].values())[0]
        
        if merge and 'citation_contents' in page:
            page['citation_contents'].update(new_contents)
        else:
            page['citation_contents'] = new_contents
        
        return data
    
    def get_page(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get the page data from JSON structure.
        
        Args:
            data: JSON data structure.
        
        Returns:
            Page data dictionary.
        """
        return list(data['query']['pages'].values())[0]
    
    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate JSON structure and return statistics.
        
        Args:
            data: JSON data structure.
        
        Returns:
            Validation results with statistics.
        """
        page = self.get_page(data)
        
        citation_urls = page.get('citation_urls', {})
        statements = page.get('statements', [])
        citation_contents = page.get('citation_contents', {})
        
        # Count valid/invalid ref_idx
        valid_refs = 0
        null_refs = 0
        invalid_refs = 0
        
        for stmt in statements:
            ref_idx = stmt.get('ref_idx')
            if ref_idx is None:
                null_refs += 1
            elif isinstance(ref_idx, list):
                for r in ref_idx:
                    if str(r) in citation_urls:
                        valid_refs += 1
                    else:
                        invalid_refs += 1
            else:
                if str(ref_idx) in citation_urls:
                    valid_refs += 1
                else:
                    invalid_refs += 1
        
        # Count fetched/failed contents
        fetched = 0
        failed = 0
        for content in citation_contents.values():
            if content.get('error'):
                failed += 1
            else:
                fetched += 1
        
        return {
            'title': page.get('title', ''),
            'extract_length': len(page.get('extract', '')),
            'citation_urls_count': len(citation_urls),
            'statements_count': len(statements),
            'valid_refs': valid_refs,
            'null_refs': null_refs,
            'invalid_refs': invalid_refs,
            'contents_fetched': fetched,
            'contents_failed': failed,
            'is_valid': invalid_refs == 0,
        }
