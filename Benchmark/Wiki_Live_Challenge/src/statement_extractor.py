"""
Statement extractor for Wiki Live Challenge.

Uses LLM to extract factual statements from markdown content.
"""

import json
import re
import requests
from typing import Dict, List, Any, Optional


class StatementExtractor:
    """
    Extracts factual statements from text using LLM.
    
    Supports:
    - OpenAI-compatible API
    - Gemini API (via OpenAI-compatible proxy)
    - Extraction with or without citation references
    """
    
    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str,
        timeout: float = 300.0,
        temperature: float = 0.0
    ):
        """
        Initialize statement extractor.
        
        Args:
            model: Model name/identifier.
            api_key: API key for the model.
            base_url: API base URL.
            timeout: Request timeout in seconds.
            temperature: Generation temperature.
        """
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.temperature = temperature
    
    def _build_prompt_with_citations(self, text: str) -> str:
        """Build prompt for extracting statements with citation references."""
        return f"""You will be provided with a research report. The body of the report contains text with citations to references.

Citations in the main text may appear in the following forms:
1. A segment of text + [number], for example: "Li Qiang constructed a socioeconomic status index... 7 levels[15]"
2. A segment of text + [number][number], for example: "This was confirmed[1][2][3]"

**Your Task:**
Please extract **all** informative statements (facts) from the main text. Each statement **must** be associated with its corresponding citation number(s). Return the result as a list of (fact, ref_idx) pairs.

**Citation Assignment Rule (Critical):**
For each statement, find the **nearest citation(s) that immediately follow it** in the text.
- If a statement is followed directly by citations (e.g., `[1]` or `[1][2][3]`), those are the citations for that statement.
- If a statement has no citation immediately after it, look forward to find the **next citation(s)**.
- Citations at the end of a sentence or paragraph typically cover all the preceding uncited statements.

**Extraction Rules:**

1. **Completeness & Context:** Every extracted `fact` must be a complete, self-contained statement. Do not extract fragmented phrases. If a sentence relies on previous context (e.g., uses "It", "They"), resolve these references.

2. **Handling Citations:**
   - If a statement has **multiple** references (e.g., `[1][2]`), return `ref_idx` as a **list**: `ref_idx: ["1", "2"]`.
   - If a statement has only **one** reference, return `ref_idx` as a **single string**.

3. **Formatting:**
   - Return a JSON list.
   - Ensure proper escaping for JSON parsing.

**Output Format Example:**

[
    {{
        "fact": "Li Qiang constructed a socioeconomic status index.",
        "ref_idx": "15"
    }},
    {{
        "fact": "This method has been validated by multiple studies.",
        "ref_idx": ["3", "7", "12"]
    }}
]

Here is the research report:

{text}

Please extract all statements now. Output only the JSON list directly, without any explanations."""
    
    def _build_prompt_without_citations(self, text: str) -> str:
        """Build prompt for extracting statements without citation references."""
        return f"""You will be provided with a research report or article. Your task is to extract all factual statements from the main text.

Please identify **all** factual statements and extract them as a list. When extracting:

1. Each statement should be a complete, self-contained factual claim.
2. Look for context to ensure each statement is understandable on its own.
3. Do not include section headers, table of contents, or reference lists.
4. Focus on meaningful factual claims.
5. Ensure all statements are extracted without omissions.

Return a JSON list format:

[
    {{
        "statement": "The complete factual statement."
    }},
    {{
        "statement": "Another factual statement."
    }}
]

Here is the text:

{text}

Please extract all statements now. Output only the JSON list directly."""
    
    def _parse_response(self, content: str) -> List[Dict[str, Any]]:
        """Parse JSON response, handling potential truncation."""
        
        def try_parse(json_str: str) -> List[Dict]:
            try:
                data = json.loads(json_str)
                return data if isinstance(data, list) else []
            except json.JSONDecodeError:
                pass
            
            # Try to fix truncated JSON array
            json_str = json_str.strip()
            if json_str.startswith('['):
                # Find last complete object
                last_complete = -1
                depth = 0
                in_string = False
                escape = False
                
                for i, c in enumerate(json_str):
                    if escape:
                        escape = False
                        continue
                    if c == '\\':
                        escape = True
                        continue
                    if c == '"' and not escape:
                        in_string = not in_string
                        continue
                    if in_string:
                        continue
                    
                    if c == '{':
                        depth += 1
                    elif c == '}':
                        depth -= 1
                        if depth == 0:
                            last_complete = i
                
                if last_complete > 0:
                    truncated = json_str[:last_complete + 1].rstrip().rstrip(',') + ']'
                    try:
                        data = json.loads(truncated)
                        return data if isinstance(data, list) else []
                    except json.JSONDecodeError:
                        pass
            
            return []
        
        # Try direct parse
        result = try_parse(content)
        if result:
            return result
        
        # Try extracting from markdown code block
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
        if match:
            result = try_parse(match.group(1))
            if result:
                return result
        
        # Try finding JSON array
        match = re.search(r'\[[\s\S]*', content)
        if match:
            result = try_parse(match.group(0))
            if result:
                return result
        
        return []
    
    def _is_gemini_native(self) -> bool:
        """Check if API uses Gemini native format."""
        return 'wenxiaobai' in self.base_url.lower() or 'yuanshi' in self.model.lower()
    
    def _call_api(self, prompt: str) -> str:
        """Call the LLM API."""
        url = self.base_url
        if not url.endswith('/chat/completions'):
            url = f"{url}/chat/completions"
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}',
        }
        
        # Use Gemini native format for wenxiaobai API
        if self._is_gemini_native():
            payload = {
                'model': self.model,
                'contents': [
                    {
                        'role': 'user',
                        'parts': [{'text': prompt}]
                    }
                ],
                'generationConfig': {
                    'temperature': self.temperature,
                    'thinkingConfig': {
                        'thinkingBudget': 8192
                    }
                }
            }
        else:
            # OpenAI compatible format
            payload = {
                'model': self.model,
                'messages': [{'role': 'user', 'content': prompt}],
                'temperature': self.temperature,
                'max_tokens': 65536,
            }
        
        response = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
        
        if response.status_code != 200:
            raise Exception(f"API error: {response.status_code}, {response.text[:200]}")
        
        data = response.json()
        
        # Handle different response formats
        # New format: data array
        if 'data' in data and data['data']:
            return data['data'][-1].get('text', '')
        
        # Gemini format: candidates -> content -> parts
        if 'candidates' in data and data['candidates']:
            parts = data['candidates'][0].get('content', {}).get('parts', [])
            return ''.join(p.get('text', '') for p in parts)
        
        # OpenAI format
        if 'choices' in data and data['choices']:
            return data['choices'][0].get('message', {}).get('content', '')
        
        raise Exception(f"Cannot parse response: {str(data)[:200]}")
    
    def extract(
        self,
        text: str,
        has_citations: bool = True,
        citation_urls: Optional[Dict[str, str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract statements from text.
        
        Args:
            text: Text content to extract from.
            has_citations: Whether text contains citation markers [n].
            citation_urls: Optional citation URL mapping for adding URLs to statements.
        
        Returns:
            List of statement dictionaries.
        """
        # Check if text actually has citations
        if has_citations:
            # Check main text (exclude References section)
            main_text = text
            for marker in ['## References', '## Reference', '# References']:
                if marker in main_text:
                    main_text = main_text.split(marker)[0]
                    break
            
            if not re.search(r'\[\d+\]', main_text):
                has_citations = False
        
        # Build appropriate prompt
        if has_citations:
            prompt = self._build_prompt_with_citations(text)
        else:
            prompt = self._build_prompt_without_citations(text)
        
        # Call API and parse response
        try:
            response = self._call_api(prompt)
            statements = self._parse_response(response)
        except Exception as e:
            print(f"Extraction error: {str(e)[:100]}")
            return []
        
        # Add URLs to statements if citation_urls provided
        if citation_urls and has_citations:
            for stmt in statements:
                ref_idx = stmt.get('ref_idx')
                if ref_idx is None:
                    stmt['url'] = None
                elif isinstance(ref_idx, list):
                    urls = [citation_urls.get(str(r)) for r in ref_idx]
                    stmt['url'] = [u for u in urls if u]
                else:
                    stmt['url'] = citation_urls.get(str(ref_idx))
        
        return statements
    
    def extract_from_file(
        self,
        file_path: str,
        citation_urls: Optional[Dict[str, str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract statements from a markdown file.
        
        Args:
            file_path: Path to markdown file.
            citation_urls: Optional citation URL mapping.
        
        Returns:
            List of statement dictionaries.
        """
        from pathlib import Path
        content = Path(file_path).read_text(encoding='utf-8')
        return self.extract(content, has_citations=True, citation_urls=citation_urls)
