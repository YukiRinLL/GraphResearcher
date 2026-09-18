"""
Benchmark configuration and data paths for Wiki Live Challenge.

Supports multiple live evaluation sets (e.g., 2025_Mar_Nov, 2026_Jan_Mar, etc.)
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


# Default benchmark
DEFAULT_BENCHMARK = "2025_Mar_Nov"

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent


@dataclass
class BenchmarkPaths:
    """Paths for a specific benchmark dataset"""
    benchmark_id: str
    root: Path
    
    @property
    def wiki_data_dir(self) -> Path:
        """Wiki ground truth data directory"""
        return self.root / "wiki_data" / "cleaned_data"
    
    @property
    def wiki_article_dir(self) -> Path:
        """Wiki article markdown files"""
        return self.wiki_data_dir / "article"
    
    @property
    def wiki_statement_dir(self) -> Path:
        """Wiki statement JSON files"""
        return self.wiki_data_dir / "statement"
    
    @property
    def test_data_dir(self) -> Path:
        """Test data directory (agencies)"""
        return self.root / "test_data"
    
    @property
    def agencies_file(self) -> Path:
        """Agency registry file"""
        return self.test_data_dir / "agencies.json"
    
    def get_agency_dir(self, agency_id: str) -> Path:
        """Get agency data directory"""
        return self.test_data_dir / agency_id
    
    def get_agency_md_dir(self, agency_id: str) -> Path:
        """Get agency markdown data directory"""
        return self.get_agency_dir(agency_id) / "md_data"
    
    def get_agency_json_dir(self, agency_id: str) -> Path:
        """Get agency JSON data directory"""
        return self.get_agency_dir(agency_id) / "json_data"


class BenchmarkManager:
    """Manage benchmark datasets"""
    
    def __init__(self, data_root: Optional[Path] = None):
        """Initialize benchmark manager
        
        Args:
            data_root: Root data directory (default: PROJECT_ROOT/data)
        """
        self.data_root = Path(data_root) if data_root else PROJECT_ROOT / "data"
    
    def list_benchmarks(self) -> List[str]:
        """List all available benchmarks"""
        benchmarks = []
        if self.data_root.exists():
            for item in self.data_root.iterdir():
                if item.is_dir() and (item / "wiki_data").exists():
                    benchmarks.append(item.name)
        return sorted(benchmarks)
    
    def get_benchmark(self, benchmark_id: Optional[str] = None) -> BenchmarkPaths:
        """Get paths for a specific benchmark
        
        Args:
            benchmark_id: Benchmark ID (e.g., "2025_Mar_Nov")
                         Default: DEFAULT_BENCHMARK
        """
        benchmark_id = benchmark_id or DEFAULT_BENCHMARK
        root = self.data_root / benchmark_id
        
        if not root.exists():
            available = self.list_benchmarks()
            raise ValueError(
                f"Benchmark '{benchmark_id}' not found. "
                f"Available: {available}"
            )
        
        return BenchmarkPaths(benchmark_id=benchmark_id, root=root)
    
    def get_agencies(self, benchmark_id: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """Get registered agencies for a benchmark
        
        Args:
            benchmark_id: Benchmark ID
            
        Returns:
            Dict of agency_id -> agency info
        """
        paths = self.get_benchmark(benchmark_id)
        
        if not paths.agencies_file.exists():
            return {}
        
        data = json.loads(paths.agencies_file.read_text(encoding='utf-8'))
        return data.get("agencies", {})
    
    def get_wiki_articles(self, benchmark_id: Optional[str] = None) -> List[str]:
        """Get list of wiki article names in the benchmark
        
        Args:
            benchmark_id: Benchmark ID
            
        Returns:
            List of article names (without extension)
        """
        paths = self.get_benchmark(benchmark_id)
        articles = []
        
        if paths.wiki_article_dir.exists():
            for f in paths.wiki_article_dir.glob("*.md"):
                articles.append(f.stem)
        
        return sorted(articles)
    
    def get_agency_articles(
        self, 
        agency_id: str, 
        benchmark_id: Optional[str] = None,
        data_type: str = "json"
    ) -> List[str]:
        """Get list of article names for an agency
        
        Args:
            agency_id: Agency ID
            benchmark_id: Benchmark ID
            data_type: "json" or "md"
            
        Returns:
            List of article names (without extension)
        """
        paths = self.get_benchmark(benchmark_id)
        
        if data_type == "json":
            data_dir = paths.get_agency_json_dir(agency_id)
            ext = "*.json"
        else:
            data_dir = paths.get_agency_md_dir(agency_id)
            ext = "*.md"
        
        articles = []
        if data_dir.exists():
            for f in data_dir.glob(ext):
                articles.append(f.stem)
        
        return sorted(articles)


# Global instance
_manager: Optional[BenchmarkManager] = None


def get_benchmark_manager() -> BenchmarkManager:
    """Get global benchmark manager instance"""
    global _manager
    if _manager is None:
        _manager = BenchmarkManager()
    return _manager


def get_benchmark_paths(benchmark_id: Optional[str] = None) -> BenchmarkPaths:
    """Get paths for a benchmark (convenience function)"""
    return get_benchmark_manager().get_benchmark(benchmark_id)


def list_benchmarks() -> List[str]:
    """List available benchmarks (convenience function)"""
    return get_benchmark_manager().list_benchmarks()
