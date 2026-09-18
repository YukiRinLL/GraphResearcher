"""
Jina API scraper for Wiki Live Challenge.

Uses Jina Reader API to fetch web page content for citation verification.
"""

import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple, Any
from threading import Lock


class JinaScraper:
    """
    Web scraper using Jina Reader API.
    
    Features:
    - Concurrent fetching with configurable workers
    - Automatic retry with exponential backoff
    - Rate limiting handling
    """
    
    # Common blocked content patterns
    BLOCKED_PATTERNS = [
        "you've been blocked",
        "access denied",
        "403 forbidden",
        "captcha",
        "please verify you are a human",
        "enable javascript",
        "checking your browser",
        "cloudflare",
        "rate limit",
        "too many requests",
    ]
    
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://r.jina.ai/",
        timeout: float = 60.0,
        max_retries: int = 3
    ):
        """
        Initialize Jina scraper.
        
        Args:
            api_key: Jina API key.
            base_url: Jina Reader API base URL.
            timeout: Request timeout in seconds.
            max_retries: Maximum retry attempts per URL.
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.max_retries = max_retries
        
        # Ensure Bearer prefix
        if not self.api_key.startswith('Bearer '):
            self.api_key = f'Bearer {self.api_key}'
    
    def _is_blocked(self, content: str, title: str = "") -> Optional[str]:
        """
        Check if content indicates blocked/invalid response.
        
        Returns:
            Reason string if blocked, None otherwise.
        """
        if not content:
            return None
        
        # Too short content
        if len(content.strip()) < 100:
            if title and title.lower() == 'error':
                return "Empty content with error title"
        
        content_lower = content.lower()
        for pattern in self.BLOCKED_PATTERNS:
            if pattern in content_lower:
                return f"Blocked: {pattern}"
        
        return None
    
    def fetch_url(self, url: str) -> Dict[str, Any]:
        """
        Fetch content from a single URL.
        
        Args:
            url: URL to fetch.
        
        Returns:
            Dictionary with url, title, content, and optionally error.
        """
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                # Jina Reader API format: GET https://r.jina.ai/{url}
                reader_url = f"{self.base_url}/{url}"
                
                headers = {
                    'Authorization': self.api_key,
                    'Accept': 'application/json',
                    'X-Return-Format': 'markdown',
                }
                
                response = requests.get(
                    reader_url,
                    headers=headers,
                    timeout=self.timeout
                )
                
                # Check for rate limit / quota errors
                if response.status_code == 402:
                    return {
                        'url': url,
                        'title': '',
                        'content': '',
                        'error': 'Failed to fetch'
                    }
                
                if response.status_code == 429:
                    # Rate limited, wait and retry
                    wait_time = (attempt + 1) * 5
                    time.sleep(wait_time)
                    continue
                
                if response.status_code != 200:
                    last_error = f"HTTP {response.status_code}"
                    if attempt < self.max_retries - 1:
                        time.sleep((attempt + 1) * 2)
                    continue
                
                # Parse response
                data = response.json()
                
                # Handle Jina's response format
                if 'data' in data and data['data'] is None and data.get('code') == 402:
                    # Insufficient balance
                    return {
                        'url': url,
                        'title': '',
                        'content': '',
                        'error': 'Failed to fetch'
                    }
                
                # Extract content from various response formats
                title = data.get('title', '')
                content = data.get('content', '') or data.get('text', '')
                
                # Some Jina responses have data wrapper
                if 'data' in data and isinstance(data['data'], dict):
                    title = data['data'].get('title', '') or title
                    content = data['data'].get('content', '') or data['data'].get('text', '') or content
                
                # Check for blocked content
                blocked = self._is_blocked(content, title)
                if blocked:
                    last_error = blocked
                    if attempt < self.max_retries - 1:
                        time.sleep((attempt + 1) * 2)
                    continue
                
                return {
                    'url': url,
                    'title': title,
                    'content': content,
                }
                
            except requests.exceptions.Timeout:
                last_error = "Timeout"
                if attempt < self.max_retries - 1:
                    time.sleep((attempt + 1) * 2)
                continue
                
            except requests.exceptions.RequestException as e:
                last_error = str(e)[:100]
                if attempt < self.max_retries - 1:
                    time.sleep((attempt + 1) * 2)
                continue
                
            except Exception as e:
                last_error = str(e)[:100]
                break
        
        return {
            'url': url,
            'title': '',
            'content': '',
            'error': 'Failed to fetch'
        }
    
    def fetch_urls(
        self,
        urls: Dict[str, str],
        concurrency: int = 5,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Fetch content from multiple URLs concurrently.
        
        Args:
            urls: Dictionary mapping citation numbers to URLs.
            concurrency: Number of concurrent workers.
            progress_callback: Optional callback(completed, total) for progress.
        
        Returns:
            Dictionary mapping citation numbers to fetch results.
        """
        results = {}
        total = len(urls)
        completed = 0
        lock = Lock()
        
        def fetch_and_track(item: Tuple[str, str]) -> Tuple[str, Dict]:
            nonlocal completed
            cite_num, url = item
            result = self.fetch_url(url)
            
            with lock:
                completed += 1
                if progress_callback:
                    progress_callback(completed, total)
            
            return cite_num, result
        
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {
                executor.submit(fetch_and_track, item): item[0]
                for item in urls.items()
            }
            
            for future in as_completed(futures):
                cite_num, result = future.result()
                results[cite_num] = result
        
        return results
    
    def fetch_missing(
        self,
        citation_urls: Dict[str, str],
        existing_contents: Dict[str, Dict[str, Any]],
        concurrency: int = 5,
        include_failed: bool = True,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Fetch only URLs that haven't been fetched yet or previously failed.
        
        Args:
            citation_urls: All citation URLs.
            existing_contents: Already fetched contents.
            concurrency: Number of concurrent workers.
            include_failed: Whether to retry previously failed URLs.
            progress_callback: Optional progress callback.
        
        Returns:
            Dictionary with newly fetched contents.
        """
        to_fetch = {}
        
        for cite_num, url in citation_urls.items():
            if cite_num not in existing_contents:
                to_fetch[cite_num] = url
            elif include_failed:
                existing = existing_contents[cite_num]
                if existing.get('error'):
                    to_fetch[cite_num] = url
        
        if not to_fetch:
            return {}
        
        return self.fetch_urls(to_fetch, concurrency, progress_callback)
