"""
Wiki Writing Evaluation Module

Evaluates Wikipedia article writing quality using LLM-based comparison.
Based on Wikipedia Manual of Style criteria.

Usage:
    from evaluation.wiki_writing import WikiWritingEvaluator
    
    evaluator = WikiWritingEvaluator(criteria_path="evaluation/data/wiki_writing_criteria.json")
    result = evaluator.evaluate(gen_article, gt_article, allow_tie=False)
"""

from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Literal
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.llm_client import LLMClient, create_llm_client
from src.article_loader import Article, load_article, get_article_full_text


@dataclass
class Criterion:
    """Single evaluation criterion"""
    id: str
    index: int
    text: str
    category_id: str
    subcategory_id: Optional[str] = None


@dataclass
class Category:
    """Evaluation category containing criteria"""
    id: str
    name: str
    description: str
    criteria: List[Criterion]


class WikiWritingEvaluator:
    """Wikipedia writing quality evaluator"""
    
    def __init__(
        self,
        criteria_path: Optional[Path] = None,
        llm_client: Optional[LLMClient] = None,
    ):
        """Initialize evaluator
        
        Args:
            criteria_path: Path to criteria JSON file
            llm_client: LLM client for evaluation (created from env if None)
        """
        if criteria_path is None:
            criteria_path = Path(__file__).parent / "data" / "wiki_writing_criteria.json"
        
        self.criteria_path = Path(criteria_path)
        self.categories = self._load_criteria()
        self.llm_client = llm_client
    
    def _load_criteria(self) -> List[Category]:
        """Load criteria from JSON file"""
        if not self.criteria_path.exists():
            raise FileNotFoundError(f"Criteria file not found: {self.criteria_path}")
        
        data = json.loads(self.criteria_path.read_text(encoding='utf-8'))
        categories = []
        
        for cat_data in data.get("categories", []):
            cat_id = cat_data["id"]
            criteria = []
            
            # Handle criteria at category level
            for c in cat_data.get("criteria", []):
                criteria.append(Criterion(
                    id=c["id"],
                    index=c["index"],
                    text=c["text"],
                    category_id=cat_id,
                    subcategory_id=None,
                ))
            
            # Handle subcategories
            for subcat in cat_data.get("subcategories", []):
                subcat_id = subcat["id"]
                for c in subcat.get("criteria", []):
                    criteria.append(Criterion(
                        id=c["id"],
                        index=c["index"],
                        text=c["text"],
                        category_id=cat_id,
                        subcategory_id=subcat_id,
                    ))
            
            categories.append(Category(
                id=cat_id,
                name=cat_data["name"],
                description=cat_data.get("description", ""),
                criteria=criteria,
            ))
        
        return categories
    
    def _get_llm_client(self) -> LLMClient:
        """Get or create LLM client for writing evaluation
        
        Uses WRITING_* env vars if available, falls back to VERIFIER_*
        """
        if self.llm_client is None:
            self.llm_client = create_llm_client(use_writing=True)
        return self.llm_client
    
    def _evaluate_category_batch(
        self,
        gen_text: str,
        gt_text: str,
        category: Category,
        topic: str,
        allow_tie: bool = True,
    ) -> List[Dict[str, Any]]:
        """Evaluate all criteria in a category with single LLM call
        
        Args:
            gen_text: Generated article text
            gt_text: Ground truth article text
            category: Category to evaluate
            topic: Article topic
            allow_tie: If False, force winner selection
            
        Returns:
            List of evaluation results
        """
        client = self._get_llm_client()
        criteria = category.criteria
        k = len(criteria)
        
        # Build criteria list for prompt
        criteria_lines = []
        for i, c in enumerate(criteria, 1):
            criteria_lines.append(f"{i}. {c.text}")
        criteria_list = "\n".join(criteria_lines)
        
        # Build prompt
        if allow_tie:
            system_prompt = (
                "You are a strict, meticulous, and objective Wikipedia article evaluation expert. "
                "You excel at using specific criteria to compare two Wikipedia-style articles on the same topic, "
                "and for each criterion you must decide whether Article 1 wins, Article 2 wins, or they tie."
            )
            winner_note = """Note: winner value should be:
- 0 = tie
- 1 = Article 1 wins
- 2 = Article 2 wins"""
        else:
            system_prompt = (
                "You are a strict, meticulous, and objective Wikipedia article evaluation expert. "
                "You excel at using specific criteria to compare two Wikipedia-style articles on the same topic, "
                "and for each criterion you MUST decide a clear winner - either Article 1 wins or Article 2 wins. "
                "No ties are allowed."
            )
            winner_note = """Note: winner value should be:
- 1 = Article 1 wins
- 2 = Article 2 wins
IMPORTANT: You MUST choose either 1 or 2. Ties (0) are NOT allowed."""
        
        user_prompt = f"""**Articles to Evaluate**
Topic: {topic}

<article_1>
{gt_text}
</article_1>

<article_2>
{gen_text}
</article_2>

**Evaluation Category: {category.name}**
{category.description}

There are {k} criteria under this category:
{criteria_list}

Compare which article better satisfies each criterion.

Output your response in strict JSON format with exactly {k} results (one per criterion):
{{
  "results": [
    {{
      "criterion_index": 1,
      "reason": "Brief explanation for criterion 1",
      "winner": 1
    }},
    {{
      "criterion_index": 2,
      "reason": "Brief explanation for criterion 2",
      "winner": 2
    }}
  ]
}}

{winner_note}"""
        
        try:
            result = client.call_json(system_prompt, user_prompt)
            results_list = result.get("results", [])
            
            output = []
            for i, criterion in enumerate(criteria):
                # Find matching result
                matched = None
                for res in results_list:
                    if res.get("criterion_index") == i + 1:
                        matched = res
                        break
                
                if matched is None and i < len(results_list):
                    matched = results_list[i]
                
                if matched:
                    winner_code = matched.get("winner", 0)
                    if winner_code not in [0, 1, 2]:
                        winner_code = 0
                    # Map: 0=tie, 1=gt wins, 2=gen wins
                    winner_str = "tie" if winner_code == 0 else "gt" if winner_code == 1 else "gen"
                    reason = matched.get("reason", "")
                else:
                    winner_code = 0
                    winner_str = "tie"
                    reason = "No result for this criterion"
                
                output.append({
                    "criterion_id": criterion.id,
                    "criterion_index": criterion.index,
                    "criterion_text": criterion.text,
                    "category": category.name,
                    "winner": winner_str,
                    "winner_code": winner_code,
                    "reason": reason,
                })
            
            return output
        
        except Exception as e:
            return [
                {
                    "criterion_id": c.id,
                    "criterion_index": c.index,
                    "criterion_text": c.text,
                    "category": category.name,
                    "winner": "tie",
                    "winner_code": 0,
                    "reason": f"Error: {str(e)}",
                }
                for c in criteria
            ]
    
    def evaluate(
        self,
        gen: Article,
        gt: Article,
        allow_tie: bool = False,
        categories: Optional[List[str]] = None,
        max_workers: int = 3,
    ) -> Dict[str, Any]:
        """Evaluate writing quality
        
        Args:
            gen: Generated article
            gt: Ground truth article
            allow_tie: If False, force winner selection (strict mode)
            categories: Category IDs to evaluate (None = all)
            max_workers: Parallel workers for category evaluation
            
        Returns:
            Evaluation results with aggregate and per-criterion details
        """
        gen_text = get_article_full_text(gen, clean=True)
        gt_text = get_article_full_text(gt, clean=True)
        topic = gen.title or gt.title or "Unknown"
        
        # Filter categories
        eval_categories = self.categories
        if categories:
            categories_lower = [c.lower() for c in categories]
            eval_categories = [
                cat for cat in self.categories
                if cat.id.lower() in categories_lower or cat.name.lower() in categories_lower
            ]
        
        if not eval_categories:
            return {
                "topic": topic,
                "mode": "winrate",
                "allow_tie": allow_tie,
                "error": "No valid categories found",
                "aggregate": {},
                "details": {},
            }
        
        print(f"[WikiWriting] Evaluating {len(eval_categories)} categories, allow_tie={allow_tie}")
        
        # Parallel evaluation of categories
        results_by_category: Dict[str, List[Dict[str, Any]]] = {}
        
        def eval_cat(cat):
            print(f"  [Parallel] Evaluating '{cat.name}' ({len(cat.criteria)} criteria)")
            return cat.name, self._evaluate_category_batch(gen_text, gt_text, cat, topic, allow_tie)
        
        with ThreadPoolExecutor(max_workers=min(len(eval_categories), max_workers)) as executor:
            futures = {executor.submit(eval_cat, cat): cat for cat in eval_categories}
            for future in as_completed(futures):
                try:
                    cat_name, results = future.result()
                    results_by_category[cat_name] = results
                    print(f"  [Done] Category '{cat_name}' completed")
                except Exception as e:
                    cat = futures[future]
                    print(f"  [Error] Category '{cat.name}' failed: {e}")
                    results_by_category[cat.name] = []
        
        # Compute aggregates
        aggregate = {}
        for cat_name, results in results_by_category.items():
            gen_wins = sum(1 for r in results if r["winner"] == "gen")
            gt_wins = sum(1 for r in results if r["winner"] == "gt")
            ties = sum(1 for r in results if r["winner"] == "tie")
            total = len(results)
            
            aggregate[cat_name] = {
                "gen_wins": gen_wins,
                "gt_wins": gt_wins,
                "ties": ties,
                "total": total,
                "gen_win_rate": gen_wins / total if total > 0 else 0.0,
            }
        
        # Overall
        total_gen = sum(agg["gen_wins"] for agg in aggregate.values())
        total_gt = sum(agg["gt_wins"] for agg in aggregate.values())
        total_ties = sum(agg["ties"] for agg in aggregate.values())
        total_criteria = sum(agg["total"] for agg in aggregate.values())
        
        aggregate["overall"] = {
            "gen_wins": total_gen,
            "gt_wins": total_gt,
            "ties": total_ties,
            "total": total_criteria,
            "gen_win_rate": total_gen / total_criteria if total_criteria > 0 else 0.0,
        }
        
        return {
            "topic": topic,
            "mode": "winrate",
            "allow_tie": allow_tie,
            "aggregate": aggregate,
            "details": results_by_category,
        }
    
    def evaluate_files(
        self,
        gen_path: Path,
        gt_path: Path,
        allow_tie: bool = False,
        categories: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Evaluate writing quality from file paths
        
        Args:
            gen_path: Path to generated article
            gt_path: Path to ground truth article
            allow_tie: If False, force winner selection
            categories: Category IDs to evaluate
            
        Returns:
            Evaluation results
        """
        gen = load_article(gen_path, strip_citations_flag=True)
        gt = load_article(gt_path, strip_citations_flag=True)
        return self.evaluate(gen, gt, allow_tie, categories)


def evaluate_wiki_writing(
    gen_path: Path,
    gt_path: Path,
    allow_tie: bool = False,
    categories: Optional[List[str]] = None,
    criteria_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Convenience function for wiki writing evaluation
    
    Args:
        gen_path: Path to generated article
        gt_path: Path to ground truth article
        allow_tie: If False, force winner selection
        categories: Category IDs to evaluate
        criteria_path: Path to criteria JSON
        
    Returns:
        Evaluation results
    """
    evaluator = WikiWritingEvaluator(criteria_path=criteria_path)
    return evaluator.evaluate_files(gen_path, gt_path, allow_tie, categories)
