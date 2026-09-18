"""
Wiki Fact Evaluation Module

Evaluates factual accuracy through:
1. Verifiability: Statement consistency between generated and ground truth articles
2. Citation: Statement support by cited sources

Usage:
    from evaluation.wiki_fact import WikiFactEvaluator
    
    evaluator = WikiFactEvaluator()
    
    # Verifiability evaluation
    result = evaluator.evaluate_verifiability(gen_article, gt_article)
    
    # Citation evaluation
    result = evaluator.evaluate_citation(gen_article)
"""

from __future__ import annotations
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.llm_client import LLMClient, create_llm_client
from src.article_loader import Article, load_article, get_article_sentences
from src.text_utils import strip_citations

try:
    from src.embedder import TextEmbedder, create_embedder
    HAS_EMBEDDER = True
except ImportError:
    HAS_EMBEDDER = False
    TextEmbedder = None

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    np = None


@dataclass
class Statement:
    """Statement with citation info"""
    fact: str
    ref_idx: List[str]
    url: List[str]
    index: int


class WikiFactEvaluator:
    """Wikipedia fact evaluation for verifiability and citation support"""
    
    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        embedder: Optional[TextEmbedder] = None,
    ):
        """Initialize evaluator
        
        Args:
            llm_client: LLM client for verification
            embedder: Text embedder for similarity
        """
        self.llm_client = llm_client
        self.embedder = embedder
    
    def _get_llm_client(self) -> LLMClient:
        """Get or create LLM client"""
        if self.llm_client is None:
            self.llm_client = create_llm_client(use_verifier=True)
        return self.llm_client
    
    def _get_embedder(self) -> TextEmbedder:
        """Get or create embedder"""
        if self.embedder is None:
            if not HAS_EMBEDDER:
                raise ImportError("openai package required for embedding")
            self.embedder = create_embedder()
        return self.embedder
    
    # ==================== Verifiability ====================
    
    def _extract_statements_text(self, article: Article, use_statements: bool = True) -> List[str]:
        """Extract statement texts from article
        
        Args:
            article: Article object
            use_statements: If True and article has statements, use them; else extract from text
            
        Returns:
            List of statement/sentence strings
        """
        # Prefer using pre-extracted statements if available
        if use_statements and article.statements:
            texts = []
            for stmt in article.statements:
                if isinstance(stmt, dict):
                    # Generated article format: {"fact": "...", "ref_idx": ...}
                    fact = stmt.get("fact", "").strip()
                    if not fact:
                        # Wiki statement format: {"statement": "..."}
                        fact = stmt.get("statement", "").strip()
                    if fact:
                        texts.append(fact)
                elif isinstance(stmt, str):
                    if stmt.strip():
                        texts.append(stmt.strip())
            if texts:
                return texts
        
        # Fallback: extract sentences from raw text
        return get_article_sentences(article, strip_citations_flag=True)
    
    def evaluate_verifiability(
        self,
        gen: Article,
        gt: Article,
        top_k: int = 10,
        max_workers: int = 20,
        include_coverage: bool = True,
        use_statements: bool = True,
    ) -> Dict[str, Any]:
        """Evaluate verifiability: how well gen statements match gt
        
        Args:
            gen: Generated article
            gt: Ground truth article
            top_k: Number of similar statements to consider
            max_workers: Parallel workers
            include_coverage: Also compute gt->gen coverage
            use_statements: If True, use pre-extracted statements when available
            
        Returns:
            Evaluation results with 6 core metrics
        """
        if not HAS_NUMPY:
            raise ImportError("numpy required for verifiability evaluation")
        
        client = self._get_llm_client()
        embedder = self._get_embedder()
        
        # Extract statements (prefer pre-extracted, fallback to sentence splitting)
        gen_sents = self._extract_statements_text(gen, use_statements=use_statements)
        gt_sents = self._extract_statements_text(gt, use_statements=use_statements)
        
        title = gen.title or gt.title or "Unknown"
        
        print(f"[Verifiability] Statements: GT={len(gt_sents)}, Gen={len(gen_sents)}, top_k={top_k}")
        
        if not gen_sents or not gt_sents:
            return self._empty_verifiability_result(title, len(gen_sents), len(gt_sents))
        
        # Get embeddings
        gen_emb = np.array(embedder.embed_batch(gen_sents, batch_size=64))
        gt_emb = np.array(embedder.embed_batch(gt_sents, batch_size=64))
        
        if gen_emb.size == 0 or gt_emb.size == 0:
            return self._empty_verifiability_result(title, len(gen_sents), len(gt_sents))
        
        # Compute similarity matrix
        gen_norm = gen_emb / (np.linalg.norm(gen_emb, axis=1, keepdims=True) + 1e-12)
        gt_norm = gt_emb / (np.linalg.norm(gt_emb, axis=1, keepdims=True) + 1e-12)
        sim_matrix = gen_norm @ gt_norm.T  # (num_gen, num_gt)
        
        # Get top-k for each gen sentence
        k = min(top_k, sim_matrix.shape[1])
        part_idx = np.argpartition(-sim_matrix, kth=k - 1, axis=1)[:, :k]
        part_scores = np.take_along_axis(sim_matrix, part_idx, axis=1)
        order = np.argsort(-part_scores, axis=1)
        top_idx = np.take_along_axis(part_idx, order, axis=1)
        top_scores = np.take_along_axis(part_scores, order, axis=1)
        
        # Verify gen -> gt
        gen_alignments = []
        for i in range(len(gen_sents)):
            cand_idx = [int(x) for x in top_idx[i]]
            cand_sents = [gt_sents[j] for j in cand_idx if j < len(gt_sents)]
            gen_alignments.append({
                "gen_sentence": gen_sents[i],
                "candidates": cand_sents,
                "top_score": float(top_scores[i, 0]),
            })
        
        # Coverage: gt -> gen
        coverage_alignments = []
        if include_coverage:
            sim_rev = sim_matrix.T  # (num_gt, num_gen)
            k_rev = min(top_k, sim_rev.shape[1])
            part_idx_rev = np.argpartition(-sim_rev, kth=k_rev - 1, axis=1)[:, :k_rev]
            part_scores_rev = np.take_along_axis(sim_rev, part_idx_rev, axis=1)
            order_rev = np.argsort(-part_scores_rev, axis=1)
            top_idx_rev = np.take_along_axis(part_idx_rev, order_rev, axis=1)
            top_scores_rev = np.take_along_axis(part_scores_rev, order_rev, axis=1)
            
            for i in range(len(gt_sents)):
                cand_idx = [int(x) for x in top_idx_rev[i]]
                cand_sents = [gen_sents[j] for j in cand_idx if j < len(gen_sents)]
                coverage_alignments.append({
                    "gt_sentence": gt_sents[i],
                    "candidates": cand_sents,
                    "top_score": float(top_scores_rev[i, 0]),
                })
        
        # Parallel verification
        supported_count = 0
        conflict_count = 0
        coverage_supported = 0
        coverage_conflict = 0
        
        def verify_gen(align):
            """Verify gen sentence against gt candidates"""
            if not align["candidates"]:
                return "not_support", {"verdict": "not_support", "reason": "no candidates"}
            evidence = "\n".join(align["candidates"])
            result = client.verify_statement(align["gen_sentence"], evidence, title=title)
            return result.get("verdict", "not_support"), result
        
        def verify_cov(align):
            """Verify gt sentence against gen candidates"""
            if not align["candidates"]:
                return "not_support", {"verdict": "not_support", "reason": "no candidates"}
            evidence = "\n".join(align["candidates"])
            result = client.verify_statement(align["gt_sentence"], evidence, title=title)
            return result.get("verdict", "not_support"), result
        
        # Collect tasks
        all_tasks = [(align, False) for align in gen_alignments]
        if include_coverage:
            all_tasks.extend([(align, True) for align in coverage_alignments])
        
        print(f"[Verifiability] Verifying {len(all_tasks)} alignments (max_workers={max_workers})...")
        
        with ThreadPoolExecutor(max_workers=min(len(all_tasks), max_workers)) as executor:
            futures = {}
            for align, is_cov in all_tasks:
                if is_cov:
                    futures[executor.submit(verify_cov, align)] = (align, True)
                else:
                    futures[executor.submit(verify_gen, align)] = (align, False)
            
            completed = 0
            for future in as_completed(futures):
                completed += 1
                if completed % 20 == 0:
                    print(f"  [Progress] {completed}/{len(futures)}")
                
                try:
                    verdict, result = future.result()
                    align, is_cov = futures[future]
                    align["verify"] = result
                    
                    if is_cov:
                        if verdict == "consistent":
                            coverage_supported += 1
                        elif verdict == "inconsistent":
                            coverage_conflict += 1
                    else:
                        if verdict == "consistent":
                            supported_count += 1
                        elif verdict == "inconsistent":
                            conflict_count += 1
                except Exception as e:
                    print(f"  [Warning] Verification failed: {e}")
        
        # Compute metrics
        gen_not_supported = len(gen_sents) - supported_count - conflict_count
        gt_not_covered = len(gt_sents) - coverage_supported - coverage_conflict
        
        return {
            "title": title,
            "num_gen_sentences": len(gen_sents),
            "num_gt_sentences": len(gt_sents),
            
            # Gen -> Wiki direction
            "gen_supported_by_wiki": supported_count,
            "gen_supported_by_wiki_ratio": supported_count / len(gen_sents) if gen_sents else 0.0,
            "gen_not_supported_by_wiki": gen_not_supported,
            "gen_not_supported_by_wiki_ratio": gen_not_supported / len(gen_sents) if gen_sents else 0.0,
            "gen_conflict_with_wiki": conflict_count,
            "gen_conflict_with_wiki_ratio": conflict_count / len(gen_sents) if gen_sents else 0.0,
            
            # Wiki -> Gen direction
            "wiki_covered_by_gen": coverage_supported,
            "wiki_covered_by_gen_ratio": coverage_supported / len(gt_sents) if gt_sents else 0.0,
            "wiki_not_covered_by_gen": gt_not_covered,
            "wiki_not_covered_by_gen_ratio": gt_not_covered / len(gt_sents) if gt_sents else 0.0,
            "wiki_conflict_with_gen": coverage_conflict,
            "wiki_conflict_with_gen_ratio": coverage_conflict / len(gt_sents) if gt_sents else 0.0,
            
            "top_k": top_k,
            "avg_top1_sim": float(top_scores[:, 0].mean()) if top_scores.size > 0 else 0.0,
            "alignments": gen_alignments,
            "coverage_alignments": coverage_alignments,
        }
    
    def _empty_verifiability_result(self, title: str, num_gen: int, num_gt: int) -> Dict[str, Any]:
        """Return empty verifiability result"""
        return {
            "title": title,
            "num_gen_sentences": num_gen,
            "num_gt_sentences": num_gt,
            "gen_supported_by_wiki": 0,
            "gen_supported_by_wiki_ratio": 0.0,
            "gen_not_supported_by_wiki": num_gen,
            "gen_not_supported_by_wiki_ratio": 1.0 if num_gen > 0 else 0.0,
            "gen_conflict_with_wiki": 0,
            "gen_conflict_with_wiki_ratio": 0.0,
            "wiki_covered_by_gen": 0,
            "wiki_covered_by_gen_ratio": 0.0,
            "wiki_not_covered_by_gen": num_gt,
            "wiki_not_covered_by_gen_ratio": 1.0 if num_gt > 0 else 0.0,
            "wiki_conflict_with_gen": 0,
            "wiki_conflict_with_gen_ratio": 0.0,
            "top_k": 0,
            "avg_top1_sim": 0.0,
            "alignments": [],
            "coverage_alignments": [],
        }
    
    # ==================== Citation ====================
    
    def evaluate_citation(
        self,
        article: Article,
        max_workers: int = 10,
    ) -> Dict[str, Any]:
        """Evaluate citation support
        
        Args:
            article: Article with statements and citation_contents
            max_workers: Parallel workers
            
        Returns:
            Evaluation results with support/conflict metrics
        """
        client = self._get_llm_client()
        title = article.title or "Unknown"
        
        # Parse statements
        statements = self._parse_statements(article)
        if not statements:
            return self._empty_citation_result(title, "no_statements")
        
        # Get citation contents
        citation_contents = article.citation_contents
        citation_urls = article.citation_urls
        
        if not citation_contents and not citation_urls:
            return self._empty_citation_result(title, "no_citations")
        
        # Group statements by citation
        groups = self._build_citation_groups(statements, citation_urls, citation_contents)
        valid_groups = {k: v for k, v in groups.items() if v["is_valid"]}
        
        if not valid_groups:
            return self._empty_citation_result(title, "no_valid_citations")
        
        print(f"[Citation] {len(statements)} statements, {len(valid_groups)} valid citations")
        
        # Evaluate each citation group
        all_results = []
        
        def eval_group(cite_num, group):
            """Evaluate a citation group"""
            stmts = [s.fact for s in group["statements"]]
            results = client.batch_verify_citations(stmts, group["content"])
            
            return [{
                "statement_index": s.index,
                "statement": s.fact,
                "citation_num": cite_num,
                "citation_url": group["url"],
                "verdict": r["verdict"],
                "reason": r["reason"],
            } for s, r in zip(group["statements"], results)]
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(eval_group, cite_num, group): cite_num
                for cite_num, group in valid_groups.items()
            }
            
            for future in as_completed(futures):
                cite_num = futures[future]
                try:
                    results = future.result()
                    all_results.extend(results)
                except Exception as e:
                    print(f"[Citation] Error for citation {cite_num}: {e}")
                    group = valid_groups[cite_num]
                    for s in group["statements"]:
                        all_results.append({
                            "statement_index": s.index,
                            "statement": s.fact,
                            "citation_num": cite_num,
                            "citation_url": group["url"],
                            "verdict": "error",
                            "reason": str(e),
                        })
        
        # Compute metrics (per statement, not per citation)
        stmt_results = defaultdict(list)
        for r in all_results:
            stmt_results[r["statement_index"]].append(r)
        
        support_count = 0
        conflict_count = 0
        not_support_count = 0
        
        for idx, results in stmt_results.items():
            verdicts = [r["verdict"] for r in results]
            # Priority: support > conflict > not_support
            if "support" in verdicts:
                support_count += 1
            elif "conflict" in verdicts:
                conflict_count += 1
            else:
                not_support_count += 1
        
        evaluated = len(stmt_results)
        skipped = len(statements) - evaluated
        
        return {
            "title": title,
            "status": "completed",
            "total_statements": len(statements),
            "total_citations": len(citation_urls),
            "valid_citations": len(valid_groups),
            "evaluated_statements": evaluated,
            "skipped_statements": skipped,
            "support": support_count,
            "not_support": not_support_count,
            "conflict": conflict_count,
            "support_ratio": support_count / evaluated if evaluated > 0 else 0.0,
            "conflict_ratio": conflict_count / evaluated if evaluated > 0 else 0.0,
            "results": sorted(all_results, key=lambda x: x["statement_index"]),
        }
    
    def _parse_statements(self, article: Article) -> List[Statement]:
        """Parse statements from article"""
        statements = []
        for idx, stmt in enumerate(article.statements):
            if not isinstance(stmt, dict):
                continue
            
            fact = stmt.get("fact", "").strip()
            if not fact:
                continue
            
            ref_idx = stmt.get("ref_idx", "")
            if isinstance(ref_idx, list):
                ref_list = [str(r) for r in ref_idx if r and str(r) != "0"]
            else:
                ref_list = [str(ref_idx)] if ref_idx and str(ref_idx) != "0" else []
            
            url = stmt.get("url", "")
            if isinstance(url, list):
                url_list = [str(u) for u in url if u]
            else:
                url_list = [str(url)] if url else []
            
            statements.append(Statement(
                fact=fact,
                ref_idx=ref_list,
                url=url_list,
                index=idx,
            ))
        
        return statements
    
    def _build_citation_groups(
        self,
        statements: List[Statement],
        citation_urls: Dict[str, str],
        citation_contents: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """Group statements by citation"""
        groups = {}
        
        for stmt in statements:
            for ref_idx in stmt.ref_idx:
                if ref_idx not in groups:
                    url = citation_urls.get(ref_idx, "")
                    content = None
                    
                    # Get content from citation_contents
                    content_data = citation_contents.get(ref_idx) or citation_contents.get(url)
                    if content_data:
                        if isinstance(content_data, dict):
                            if not content_data.get("error"):
                                content = content_data.get("content", "").strip()
                        elif isinstance(content_data, str):
                            content = content_data.strip()
                    
                    groups[ref_idx] = {
                        "url": url,
                        "content": content,
                        "statements": [],
                        "is_valid": bool(content and len(content) > 100),
                    }
                
                groups[ref_idx]["statements"].append(stmt)
        
        return groups
    
    def _empty_citation_result(self, title: str, reason: str) -> Dict[str, Any]:
        """Return empty citation result"""
        return {
            "title": title,
            "status": "skipped",
            "reason": reason,
            "total_statements": 0,
            "total_citations": 0,
            "valid_citations": 0,
            "evaluated_statements": 0,
            "skipped_statements": 0,
            "support": 0,
            "not_support": 0,
            "conflict": 0,
            "support_ratio": 0.0,
            "conflict_ratio": 0.0,
            "results": [],
        }
    
    # ==================== File-based evaluation ====================
    
    def evaluate_verifiability_files(
        self,
        gen_path: Path,
        gt_path: Path,
        top_k: int = 10,
        max_workers: int = 20,
    ) -> Dict[str, Any]:
        """Evaluate verifiability from file paths
        
        Automatically loads wiki statements if gt_path is in wiki_data structure
        """
        gen = load_article(gen_path)
        
        # For wiki articles, try to load corresponding statement file
        gt_path = Path(gt_path)
        if gt_path.suffix.lower() == ".md":
            # Try to find statement file: article/X.md -> statement/X_statements.json
            stmt_dir = gt_path.parent.parent / "statement"
            stmt_path = stmt_dir / f"{gt_path.stem}_statements.json"
            
            if stmt_path.exists():
                from src.article_loader import load_wiki_article_with_statements
                gt = load_wiki_article_with_statements(gt_path, stmt_path)
            else:
                gt = load_article(gt_path)
        else:
            gt = load_article(gt_path)
        
        return self.evaluate_verifiability(gen, gt, top_k, max_workers)
    
    def evaluate_citation_file(
        self,
        article_path: Path,
        max_workers: int = 10,
    ) -> Dict[str, Any]:
        """Evaluate citation from file path"""
        article = load_article(article_path)
        return self.evaluate_citation(article, max_workers)


# Convenience functions

def evaluate_verifiability(
    gen_path: Path,
    gt_path: Path,
    top_k: int = 10,
    max_workers: int = 20,
) -> Dict[str, Any]:
    """Evaluate verifiability between gen and gt articles"""
    evaluator = WikiFactEvaluator()
    return evaluator.evaluate_verifiability_files(gen_path, gt_path, top_k, max_workers)


def evaluate_citation(
    article_path: Path,
    max_workers: int = 10,
) -> Dict[str, Any]:
    """Evaluate citation support for an article"""
    evaluator = WikiFactEvaluator()
    return evaluator.evaluate_citation_file(article_path, max_workers)
