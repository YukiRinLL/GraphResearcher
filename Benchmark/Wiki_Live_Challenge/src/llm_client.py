"""
LLM Client for Wiki Live Challenge evaluation.

Supports OpenAI-compatible APIs and Gemini native format.
"""

from __future__ import annotations
import os
import json
import re
import requests
import threading
import time
from dataclasses import dataclass
from typing import Dict, Any, List, Optional


@dataclass
class TokenUsage:
    """Token usage for a single API call"""
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    timestamp: float = 0.0


class TokenTracker:
    """Global thread-safe token usage tracker (singleton)"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance
    
    def _init(self):
        self._usages: List[TokenUsage] = []
        self._usage_lock = threading.Lock()
        self._enabled = True
    
    def add_usage(self, usage: TokenUsage):
        """Add a token usage record"""
        if not self._enabled:
            return
        with self._usage_lock:
            self._usages.append(usage)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get token usage summary"""
        with self._usage_lock:
            total_input = sum(u.input_tokens for u in self._usages)
            total_output = sum(u.output_tokens for u in self._usages)
            total_calls = len(self._usages)
            
            by_model: Dict[str, Dict[str, int]] = {}
            for u in self._usages:
                if u.model not in by_model:
                    by_model[u.model] = {"input": 0, "output": 0, "calls": 0}
                by_model[u.model]["input"] += u.input_tokens
                by_model[u.model]["output"] += u.output_tokens
                by_model[u.model]["calls"] += 1
            
            return {
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "total_tokens": total_input + total_output,
                "total_calls": total_calls,
                "by_model": by_model,
            }
    
    def reset(self):
        """Reset statistics"""
        with self._usage_lock:
            self._usages.clear()
    
    def enable(self):
        self._enabled = True
    
    def disable(self):
        self._enabled = False
    
    def print_summary(self, prefix: str = "[Token]"):
        """Print token usage summary"""
        summary = self.get_summary()
        print(f"{prefix} Token Usage Summary:")
        print(f"  Total Calls: {summary['total_calls']}")
        print(f"  Total Input Tokens: {summary['total_input_tokens']:,}")
        print(f"  Total Output Tokens: {summary['total_output_tokens']:,}")
        print(f"  Total Tokens: {summary['total_tokens']:,}")
        if summary['by_model']:
            print(f"  By Model:")
            for model, stats in summary['by_model'].items():
                print(f"    {model}: {stats['calls']} calls, {stats['input']:,} in, {stats['output']:,} out")


# Global tracker instance
token_tracker = TokenTracker()


def _is_gemini_native(model: str, base_url: str) -> bool:
    """Check if using Gemini native API format"""
    model_lower = (model or "").lower()
    url_lower = (base_url or "").lower()
    return ("gemini" in model_lower and 
            "deepseek" not in model_lower and 
            "gpt" not in model_lower) or \
           "wenxiaobai" in url_lower or \
           "yuanshi" in model_lower


def _parse_json_response(content: str) -> Dict[str, Any]:
    """Parse JSON from LLM response, handling code blocks"""
    content = content.strip()
    
    # Try direct parse
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    
    # Try extracting from markdown code block
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
    
    # Try finding JSON object
    json_match = re.search(r'\{[\s\S]*\}', content)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass
    
    # Try finding JSON array
    json_match = re.search(r'\[[\s\S]*\]', content)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass
    
    return {"error": f"Failed to parse JSON: {content[:200]}"}


class LLMClient:
    """Unified LLM client supporting OpenAI-compatible and Gemini native APIs"""
    
    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str,
        timeout: float = 300.0,
        temperature: float = 0.0,
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip('/') if base_url else ""
        self.timeout = timeout
        self.temperature = temperature
        self._is_gemini = _is_gemini_native(model, base_url)
    
    def _call_gemini_api(self, system_prompt: str, user_content: str) -> str:
        """Call Gemini native format API"""
        combined_content = f"{system_prompt}\n\n{user_content}" if system_prompt else user_content
        
        contents = [{
            "role": "user",
            "parts": [{"text": combined_content}]
        }]
        
        payload = {
            "model": self.model,
            "contents": contents,
            "generationConfig": {
                "temperature": self.temperature,
                "thinkingConfig": {"thinkingBudget": 8192}
            }
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        
        url = self.base_url
        if not url.endswith("/chat/completions"):
            url = url + "/chat/completions"
        
        response = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
        
        if response.status_code != 200:
            raise Exception(f"API request failed: {response.status_code}, {response.text[:500]}")
        
        response_data = response.json()
        
        # Track token usage
        usage_data = response_data.get("usage", {})
        input_tokens = usage_data.get("prompt_tokens", 0) or usage_data.get("input_tokens", 0)
        output_tokens = usage_data.get("completion_tokens", 0) or usage_data.get("output_tokens", 0)
        
        if input_tokens == 0:
            input_tokens = len(combined_content) // 4
        
        # Parse response - new format: data array
        text = ""
        if 'data' in response_data and len(response_data['data']) > 0:
            text = response_data['data'][-1].get('text', '')
        elif 'candidates' in response_data and len(response_data['candidates']) > 0:
            candidate = response_data['candidates'][0]
            if 'content' in candidate and 'parts' in candidate['content']:
                text = ''.join(p.get('text', '') for p in candidate['content']['parts'])
        elif 'choices' in response_data and len(response_data['choices']) > 0:
            text = response_data['choices'][0].get('message', {}).get('content', '')
        
        if output_tokens == 0:
            output_tokens = len(text) // 4
        
        token_tracker.add_usage(TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self.model,
            timestamp=time.time()
        ))
        
        return text
    
    def _call_openai_api(self, system_prompt: str, user_content: str) -> str:
        """Call OpenAI-compatible API"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_content})
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        
        url = self.base_url
        if not url.endswith("/chat/completions"):
            url = url + "/chat/completions"
        
        response = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
        
        if response.status_code != 200:
            raise Exception(f"API request failed: {response.status_code}, {response.text[:500]}")
        
        response_data = response.json()
        
        # Track token usage
        usage_data = response_data.get("usage", {})
        input_tokens = usage_data.get("prompt_tokens", 0)
        output_tokens = usage_data.get("completion_tokens", 0)
        
        text = ""
        if 'choices' in response_data and len(response_data['choices']) > 0:
            text = response_data['choices'][0].get('message', {}).get('content', '')
        
        if input_tokens == 0:
            input_tokens = len(system_prompt + user_content) // 4
        if output_tokens == 0:
            output_tokens = len(text) // 4
        
        token_tracker.add_usage(TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self.model,
            timestamp=time.time()
        ))
        
        return text
    
    def call(self, system_prompt: str, user_content: str) -> str:
        """Call LLM API and return raw response text"""
        if self._is_gemini:
            return self._call_gemini_api(system_prompt, user_content)
        else:
            return self._call_openai_api(system_prompt, user_content)
    
    def call_json(self, system_prompt: str, user_content: str) -> Dict[str, Any]:
        """Call LLM API and parse response as JSON"""
        response = self.call(system_prompt, user_content)
        return _parse_json_response(response)
    
    def verify_statement(
        self,
        statement: str,
        evidence: str,
        title: str = "",
        section: str = ""
    ) -> Dict[str, Any]:
        """Verify if a statement is supported by evidence
        
        Returns:
            Dict with keys: verdict, reason, is_supported, is_conflict
        """
        system_prompt = (
            "You are a professional data annotator. Given a sentence and a paragraph composed of "
            "several gold factual support sentences, your task is to verify whether the sentence "
            "is consistent with the facts. Matching any single support sentence is enough for consistency.\n"
            "Decision policy:\n"
            "consistent: At least one support sentence directly entails or clearly confirms the statement.\n"
            "inconsistent: At least one support sentence clearly contradicts the statement.\n"
            "not_support: No support sentence clearly confirms or contradicts the statement (insufficient evidence)."
        )
        
        context_info = ""
        if title:
            context_info += f"Article Title: {title}\n"
        if section:
            context_info += f"Section: {section}\n"
        
        user_content = (
            f"{context_info}"
            f"Below are the sentence to judge and the factual paragraph:\n"
            f"<judge_sentence>\n{statement}\n</judge_sentence>\n"
            f"<factual_paragraph>\n{evidence}\n</factual_paragraph>\n"
            f"Output Format (strict JSON only):\n"
            '{\n"reason": "...",\n"verdict": "consistent | inconsistent | not_support"\n}'
        )
        
        try:
            result = self.call_json(system_prompt, user_content)
            verdict = str(result.get("verdict", "not_support")).strip().lower()
            reason = str(result.get("reason", ""))
            
            is_supported = verdict == "consistent"
            is_conflict = verdict == "inconsistent"
            
            return {
                "verdict": verdict,
                "reason": reason,
                "is_supported": is_supported,
                "is_conflict": is_conflict,
            }
        except Exception as e:
            return {
                "verdict": "not_support",
                "reason": f"Error: {str(e)[:200]}",
                "is_supported": False,
                "is_conflict": False,
            }
    
    def batch_verify_citations(
        self,
        statements: List[str],
        citation_content: str
    ) -> List[Dict[str, str]]:
        """Batch verify multiple statements against citation content
        
        Returns:
            List of dicts with keys: verdict, reason
        """
        if not citation_content or not statements:
            return [{"verdict": "not_support", "reason": "No content"} for _ in statements]
        
        prompt = f"""You are a fact verification expert. Given a citation content and multiple statements, verify whether each statement is supported by the citation content.

**Citation Content:**
{citation_content}

**Statements to Verify:**
"""
        for i, stmt in enumerate(statements, 1):
            prompt += f"{i}. {stmt}\n"
        
        prompt += """
**Task:**
For each statement, determine if it is:
- "support": The citation content clearly supports or is consistent with the statement
- "not_support": The citation content does not provide enough information to support the statement
- "conflict": The citation content contradicts the statement

**Output Format (JSON):**
Return a JSON array with one object per statement, in the same order. Each object should have:
- "verdict": "support" | "not_support" | "conflict"
- "reason": Brief explanation (one sentence)

Please output only the JSON array, no additional text.
"""
        
        try:
            response = self.call("", prompt)
            results = self._parse_batch_response(response, len(statements))
            return results
        except Exception as e:
            return [{"verdict": "not_support", "reason": str(e)} for _ in statements]
    
    def _parse_batch_response(self, response: str, expected_count: int) -> List[Dict[str, str]]:
        """Parse batch verification response"""
        response = response.strip()
        
        # Remove markdown code block markers
        if response.startswith("```json"):
            response = response[7:]
        elif response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()
        
        try:
            results = json.loads(response)
            if not isinstance(results, list):
                raise ValueError("Response is not a list")
            
            standardized = []
            for r in results:
                if not isinstance(r, dict):
                    continue
                
                verdict = r.get("verdict", "not_support")
                if verdict in ["consistent", "support", "supported"]:
                    verdict = "support"
                elif verdict in ["inconsistent", "conflict", "contradictory"]:
                    verdict = "conflict"
                else:
                    verdict = "not_support"
                
                standardized.append({
                    "verdict": verdict,
                    "reason": r.get("reason", "")
                })
            
            # Pad or truncate to expected count
            while len(standardized) < expected_count:
                standardized.append({"verdict": "not_support", "reason": "Response incomplete"})
            
            return standardized[:expected_count]
        
        except (json.JSONDecodeError, ValueError):
            # Fallback: try regex extraction
            pattern = r'"verdict"\s*:\s*"([^"]+)"'
            matches = re.findall(pattern, response)
            
            if matches:
                results = []
                for verdict in matches[:expected_count]:
                    if verdict in ["consistent", "support", "supported"]:
                        verdict = "support"
                    elif verdict in ["inconsistent", "conflict", "contradictory"]:
                        verdict = "conflict"
                    else:
                        verdict = "not_support"
                    results.append({"verdict": verdict, "reason": "Extracted from partial response"})
                
                while len(results) < expected_count:
                    results.append({"verdict": "not_support", "reason": "Parse failed"})
                
                return results
            
            return [{"verdict": "not_support", "reason": "Parse failed"} for _ in range(expected_count)]


def create_llm_client(
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: float = 300.0,
    temperature: float = 0.0,
    use_verifier: bool = True,
    use_writing: bool = False
) -> LLMClient:
    """Factory function to create LLM client from environment variables
    
    Args:
        model: Model name (default from env vars based on use_* flags)
        api_key: API key (default from env vars)
        base_url: API base URL (default from env vars)
        timeout: Request timeout
        temperature: Sampling temperature
        use_verifier: If True, use VERIFIER_* env vars
        use_writing: If True, use WRITING_* env vars (falls back to VERIFIER_*)
    
    Priority: use_writing > use_verifier > EXTRACT_*
    """
    if use_writing:
        # Try WRITING_* first, fall back to VERIFIER_*
        model = model or os.getenv("WRITING_MODEL") or os.getenv("VERIFIER_MODEL", "gemini-2.5-pro")
        api_key = api_key or os.getenv("WRITING_API_KEY") or os.getenv("VERIFIER_API_KEY", "")
        base_url = base_url or os.getenv("WRITING_BASE_URL") or os.getenv("VERIFIER_BASE_URL", "")
    elif use_verifier:
        model = model or os.getenv("VERIFIER_MODEL", "gemini-2.5-flash")
        api_key = api_key or os.getenv("VERIFIER_API_KEY", "")
        base_url = base_url or os.getenv("VERIFIER_BASE_URL", "")
    else:
        model = model or os.getenv("EXTRACT_MODEL", "gemini-2.5-flash")
        api_key = api_key or os.getenv("EXTRACT_API_KEY", "")
        base_url = base_url or os.getenv("EXTRACT_BASE_URL", "")
    
    if not api_key:
        raise ValueError("API key is required")
    if not base_url:
        raise ValueError("Base URL is required")
    
    return LLMClient(model, api_key, base_url, timeout, temperature)
