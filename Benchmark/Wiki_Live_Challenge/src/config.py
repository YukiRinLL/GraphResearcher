"""
Configuration loader for Wiki Live Challenge.

Loads settings from .env file and environment variables.
"""

import os
from pathlib import Path
from typing import Optional


def load_env_file(env_path: Optional[Path] = None) -> None:
    """
    Load environment variables from .env file.
    
    Args:
        env_path: Path to .env file. If None, searches in current directory
                  and parent directories up to project root.
    """
    if env_path is None:
        # Search for .env file
        current = Path.cwd()
        for _ in range(10):  # Max 10 levels up
            candidate = current / '.env'
            if candidate.exists():
                env_path = candidate
                break
            if current.parent == current:
                break
            current = current.parent
    
    if env_path is None or not env_path.exists():
        return
    
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


class Config:
    """
    Configuration class for Wiki Live Challenge.
    
    Loads settings from environment variables with defaults.
    """
    
    def __init__(self, env_path: Optional[Path] = None):
        """
        Initialize configuration.
        
        Args:
            env_path: Optional path to .env file.
        """
        load_env_file(env_path)
        
        # Jina API configuration
        self.jina_api_key = os.getenv('JINA_API_KEY', '')
        self.jina_base_url = os.getenv('JINA_BASE_URL', 'https://r.jina.ai/')
        
        # LLM configuration for statement extraction
        self.extract_model = os.getenv('EXTRACT_MODEL', 'gemini-2.5-flash')
        self.extract_api_key = os.getenv('EXTRACT_API_KEY', '')
        self.extract_base_url = os.getenv('EXTRACT_BASE_URL', '')
        
        # LLM configuration for verification
        self.verifier_model = os.getenv('VERIFIER_MODEL', 'gemini-2.5-flash')
        self.verifier_api_key = os.getenv('VERIFIER_API_KEY', '')
        self.verifier_base_url = os.getenv('VERIFIER_BASE_URL', '')
        
        # Evaluation criteria
        self.criteria = os.getenv('CRITERIA', 'default')
        
        # Timeouts and retries
        self.api_timeout = float(os.getenv('API_TIMEOUT', '300'))
        self.max_retries = int(os.getenv('MAX_RETRIES', '3'))
        self.concurrency = int(os.getenv('CONCURRENCY', '10'))
    
    def get_jina_headers(self) -> dict:
        """Get headers for Jina API requests."""
        headers = {
            'Accept': 'application/json',
        }
        if self.jina_api_key:
            key = self.jina_api_key
            if not key.startswith('Bearer '):
                key = f'Bearer {key}'
            headers['Authorization'] = key
        return headers
    
    def validate(self) -> list:
        """
        Validate configuration and return list of missing required settings.
        
        Returns:
            List of missing setting names.
        """
        missing = []
        
        if not self.jina_api_key:
            missing.append('JINA_API_KEY')
        
        if not self.extract_api_key:
            missing.append('EXTRACT_API_KEY')
        
        if not self.extract_base_url:
            missing.append('EXTRACT_BASE_URL')
        
        return missing
    
    def __repr__(self) -> str:
        return (
            f"Config(\n"
            f"  jina_api_key={'*' * 8 if self.jina_api_key else 'NOT SET'},\n"
            f"  extract_model={self.extract_model},\n"
            f"  extract_base_url={self.extract_base_url or 'NOT SET'},\n"
            f"  verifier_model={self.verifier_model},\n"
            f"  criteria={self.criteria},\n"
            f"  concurrency={self.concurrency}\n"
            f")"
        )
