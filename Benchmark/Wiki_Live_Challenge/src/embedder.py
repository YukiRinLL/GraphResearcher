"""
Text Embedder for Wiki Live Challenge evaluation.

Uses OpenAI-compatible embedding API for semantic similarity.
"""

from __future__ import annotations
import os
import time
from typing import List, Optional

try:
    import openai
except ImportError:
    openai = None

try:
    import numpy as np
except ImportError:
    np = None


class TextEmbedder:
    """OpenAI-compatible embedding model for text similarity"""
    
    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
    ):
        if openai is None:
            raise ImportError("openai package is required for TextEmbedder")
        
        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "")
        self.timeout = timeout
        
        if not self.api_key:
            raise ValueError("OpenAI API key is required (set OPENAI_API_KEY or pass api_key)")
        
        client_kwargs = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
        
        self.client = openai.OpenAI(**client_kwargs)
    
    def embed(self, text: str) -> List[float]:
        """Get embedding for a single text"""
        response = self.client.embeddings.create(
            model=self.model,
            input=[text],
            timeout=self.timeout,
        )
        if not response.data:
            raise ValueError("No embedding data received")
        return response.data[0].embedding
    
    def embed_batch(
        self,
        texts: List[str],
        batch_size: int = 64,
        max_retries: int = 3
    ) -> List[List[float]]:
        """Batch embed texts with automatic batching and retry
        
        Args:
            texts: List of texts to embed
            batch_size: Maximum texts per API call
            max_retries: Number of retries on failure
            
        Returns:
            List of embeddings (same order as input)
        """
        results: List[List[float]] = []
        
        for i in range(0, len(texts), batch_size):
            chunk = texts[i:i + batch_size]
            chunk_results = None
            
            for attempt in range(max_retries):
                try:
                    response = self.client.embeddings.create(
                        model=self.model,
                        input=chunk,
                        timeout=self.timeout,
                    )
                    if not response.data or len(response.data) != len(chunk):
                        raise ValueError("Embedding count mismatch")
                    chunk_results = [item.embedding for item in response.data]
                    break
                except Exception as e:
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        print(f"[Embedder] Retry {attempt + 1}/{max_retries} after {wait_time}s: {e}")
                        time.sleep(wait_time)
                    else:
                        print(f"[Embedder] Failed after {max_retries} retries: {e}")
            
            if chunk_results is None:
                print(f"[Embedder] Batch failed, returning partial ({len(results)}/{len(texts)})")
                return results
            
            results.extend(chunk_results)
        
        return results
    
    def compute_similarity(self, text1: str, text2: str) -> float:
        """Compute cosine similarity between two texts"""
        if np is None:
            raise ImportError("numpy is required for compute_similarity")
        
        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=[text1, text2],
                timeout=self.timeout,
            )
            if not response.data or len(response.data) < 2:
                raise ValueError("Not enough embeddings")
            
            emb1 = np.array(response.data[0].embedding)
            emb2 = np.array(response.data[1].embedding)
            
            dot = np.dot(emb1, emb2)
            norm1 = np.linalg.norm(emb1)
            norm2 = np.linalg.norm(emb2)
            
            return float(dot / (norm1 * norm2))
        except Exception as e:
            print(f"[Embedder] Similarity error: {e}")
            return 0.0
    
    def find_top_k(
        self,
        query_embeddings: List[List[float]],
        corpus_embeddings: List[List[float]],
        k: int = 5
    ) -> tuple:
        """Find top-k most similar corpus items for each query
        
        Args:
            query_embeddings: Query embeddings (N x dim)
            corpus_embeddings: Corpus embeddings (M x dim)
            k: Number of top results
            
        Returns:
            Tuple of (indices, scores) each of shape (N x k)
        """
        if np is None:
            raise ImportError("numpy is required for find_top_k")
        
        query_arr = np.array(query_embeddings)
        corpus_arr = np.array(corpus_embeddings)
        
        # Normalize
        query_norm = query_arr / (np.linalg.norm(query_arr, axis=1, keepdims=True) + 1e-12)
        corpus_norm = corpus_arr / (np.linalg.norm(corpus_arr, axis=1, keepdims=True) + 1e-12)
        
        # Compute similarity matrix
        sim_matrix = query_norm @ corpus_norm.T  # (N, M)
        
        # Get top-k
        k = min(k, sim_matrix.shape[1])
        part_idx = np.argpartition(-sim_matrix, kth=k - 1, axis=1)[:, :k]
        part_scores = np.take_along_axis(sim_matrix, part_idx, axis=1)
        order = np.argsort(-part_scores, axis=1)
        
        top_idx = np.take_along_axis(part_idx, order, axis=1)
        top_scores = np.take_along_axis(part_scores, order, axis=1)
        
        return top_idx, top_scores


def create_embedder(
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: float = 60.0
) -> TextEmbedder:
    """Factory function to create TextEmbedder from environment variables"""
    model = model or os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    api_key = api_key or os.getenv("OPENAI_API_KEY", "")
    base_url = base_url or os.getenv("OPENAI_BASE_URL", "")
    
    return TextEmbedder(model, api_key, base_url, timeout)
