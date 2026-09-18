"""
Wiki Live Challenge - Source Package

Provides utilities for:
- MD file preprocessing and normalization
- Statement extraction using LLM
- Citation parsing and URL scraping
- JSON data generation
- Agency registry management
- LLM client for evaluation
- Text embedding for similarity
- Article loading and text processing
- Benchmark dataset management
"""

from .config import Config
from .md_normalizer import MDNormalizer
from .citation_parser import CitationParser
from .statement_extractor import StatementExtractor
from .jina_scraper import JinaScraper
from .json_builder import JSONBuilder
from .agency_registry import AgencyRegistry
from .llm_client import LLMClient, create_llm_client, token_tracker
from .text_utils import (
    strip_citations, strip_references_section, split_into_sentences,
    get_clean_text, normalize_whitespace
)
from .article_loader import (
    Article, Section, load_article, load_json_article, load_markdown_article,
    get_article_sentences, get_clean_article_text,
    load_wiki_article_with_statements, load_article_pair
)
from .benchmark import (
    BenchmarkManager, BenchmarkPaths, get_benchmark_manager, get_benchmark_paths,
    list_benchmarks, DEFAULT_BENCHMARK
)

# Optional: embedder (requires openai package)
try:
    from .embedder import TextEmbedder, create_embedder
    _HAS_EMBEDDER = True
except ImportError:
    _HAS_EMBEDDER = False
    TextEmbedder = None
    create_embedder = None

__all__ = [
    # Config
    'Config',
    # Preprocessing
    'MDNormalizer',
    'CitationParser',
    'StatementExtractor',
    'JinaScraper',
    'JSONBuilder',
    'AgencyRegistry',
    # LLM
    'LLMClient',
    'create_llm_client',
    'token_tracker',
    # Text processing
    'strip_citations',
    'strip_references_section',
    'split_into_sentences',
    'get_clean_text',
    'normalize_whitespace',
    # Article loading
    'Article',
    'Section',
    'load_article',
    'load_json_article',
    'load_markdown_article',
    'get_article_sentences',
    'get_clean_article_text',
    'load_wiki_article_with_statements',
    'load_article_pair',
    # Benchmark management
    'BenchmarkManager',
    'BenchmarkPaths',
    'get_benchmark_manager',
    'get_benchmark_paths',
    'list_benchmarks',
    'DEFAULT_BENCHMARK',
    # Embedder (optional)
    'TextEmbedder',
    'create_embedder',
]
