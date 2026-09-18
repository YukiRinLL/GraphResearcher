#!/usr/bin/env python3
"""
Wiki Live Challenge Evaluation CLI

Supports multiple live evaluation benchmarks (e.g., 2025_Mar_Nov).

Usage:
    # List available benchmarks and agencies
    python scripts/run_evaluation.py list --benchmark 2025_Mar_Nov
    
    # Wiki Writing evaluation (by agency)
    python scripts/run_evaluation.py writing \
        --benchmark 2025_Mar_Nov \
        --agency gemini_2.5_pro
    
    # Wiki Writing evaluation (single article)
    python scripts/run_evaluation.py writing \
        --gen data/2025_Mar_Nov/test_data/openai/json_data/Article.json \
        --gt data/2025_Mar_Nov/wiki_data/cleaned_data/article/Article.md
    
    # Verifiability evaluation
    python scripts/run_evaluation.py verifiability \
        --benchmark 2025_Mar_Nov \
        --agency gemini_2.5_pro
    
    # Citation evaluation
    python scripts/run_evaluation.py citation \
        --benchmark 2025_Mar_Nov \
        --agency gemini_2.5_pro
    
    # Full evaluation (all dimensions)
    python scripts/run_evaluation.py all \
        --benchmark 2025_Mar_Nov \
        --agency gemini_2.5_pro
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, List

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Config
from src.benchmark import (
    get_benchmark_manager, get_benchmark_paths, list_benchmarks,
    DEFAULT_BENCHMARK, BenchmarkPaths
)


def run_list_command(benchmark_id: Optional[str]):
    """List benchmarks and agencies"""
    manager = get_benchmark_manager()
    
    print("=" * 60)
    print("AVAILABLE BENCHMARKS")
    print("=" * 60)
    
    benchmarks = manager.list_benchmarks()
    if not benchmarks:
        print("  No benchmarks found.")
        return
    
    for b in benchmarks:
        marker = " (default)" if b == DEFAULT_BENCHMARK else ""
        print(f"  - {b}{marker}")
    
    # If benchmark specified, show agencies
    if benchmark_id:
        print(f"\n" + "=" * 60)
        print(f"AGENCIES IN '{benchmark_id}'")
        print("=" * 60)
        
        try:
            agencies = manager.get_agencies(benchmark_id)
            if agencies:
                for aid, info in agencies.items():
                    enabled = "✓" if info.get("enabled", True) else "✗"
                    citations = "with citations" if info.get("has_citations", True) else "no citations"
                    print(f"  [{enabled}] {aid}: {info.get('name', aid)} ({citations})")
            else:
                print("  No agencies registered.")
            
            # Show wiki articles count
            articles = manager.get_wiki_articles(benchmark_id)
            print(f"\n  Wiki articles: {len(articles)}")
        except Exception as e:
            print(f"  Error: {e}")


def get_evaluation_paths(
    benchmark_id: Optional[str],
    agency_id: Optional[str],
    gen_path: Optional[Path],
    gt_path: Optional[Path],
    gen_dir: Optional[Path],
    gt_dir: Optional[Path],
    use_json: bool = True
) -> tuple:
    """Resolve evaluation paths from benchmark/agency or explicit paths
    
    Returns:
        Tuple of (gen_path, gt_path, gen_dir, gt_dir, benchmark_paths)
    """
    benchmark_paths = None
    
    if agency_id and benchmark_id:
        # Use benchmark structure
        benchmark_paths = get_benchmark_paths(benchmark_id)
        
        if use_json:
            gen_dir = benchmark_paths.get_agency_json_dir(agency_id)
        else:
            gen_dir = benchmark_paths.get_agency_md_dir(agency_id)
        
        gt_dir = benchmark_paths.wiki_article_dir
    
    elif benchmark_id and not agency_id:
        benchmark_paths = get_benchmark_paths(benchmark_id)
    
    return gen_path, gt_path, gen_dir, gt_dir, benchmark_paths


def run_writing_evaluation(
    gen_path: Optional[Path],
    gt_path: Optional[Path],
    gen_dir: Optional[Path],
    gt_dir: Optional[Path],
    output_dir: Optional[Path],
    allow_tie: bool,
    categories: Optional[List[str]],
    benchmark_paths: Optional[BenchmarkPaths] = None,
):
    """Run wiki writing evaluation
    
    For writing evaluation, we compare:
    - Gen: extract from test_data/<agency>/json_data/*.json
    - GT: wiki_data/cleaned_data/article/*.md
    """
    from evaluation.wiki_writing import WikiWritingEvaluator, evaluate_wiki_writing
    
    if gen_path and gt_path:
        # Single file evaluation
        print(f"[WikiWriting] Evaluating: {gen_path.name}")
        result = evaluate_wiki_writing(gen_path, gt_path, allow_tie=allow_tie, categories=categories)
        
        # Print summary
        agg = result.get("aggregate", {}).get("overall", {})
        print(f"  Gen wins: {agg.get('gen_wins', 0)}/{agg.get('total', 0)}")
        print(f"  GT wins:  {agg.get('gt_wins', 0)}/{agg.get('total', 0)}")
        print(f"  Ties:     {agg.get('ties', 0)}/{agg.get('total', 0)}")
        print(f"  Gen win rate: {agg.get('gen_win_rate', 0):.2%}")
        
        # Save result
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / f"{gen_path.stem}_writing.json"
            output_file.write_text(json.dumps(result, indent=2, ensure_ascii=False))
            print(f"  Result saved to: {output_file}")
        
        return result
    
    elif gen_dir and gt_dir:
        # Batch evaluation
        evaluator = WikiWritingEvaluator()
        results = []
        
        # Find matching files
        if gen_dir.is_dir():
            gen_files = list(gen_dir.glob("*.json")) + list(gen_dir.glob("*.md"))
        else:
            gen_files = [gen_dir]
        
        for gen_file in sorted(gen_files):
            # Find matching gt file (try .md first for wiki_data)
            gt_file = None
            for ext in [".md", ".json"]:
                candidate = gt_dir / f"{gen_file.stem}{ext}"
                if candidate.exists():
                    gt_file = candidate
                    break
            
            if not gt_file:
                print(f"[Skip] No GT found for: {gen_file.name}")
                continue
            
            print(f"[WikiWriting] Evaluating: {gen_file.name}")
            try:
                result = evaluator.evaluate_files(gen_file, gt_file, allow_tie=allow_tie, categories=categories)
                results.append({"file": gen_file.name, **result})
                
                agg = result.get("aggregate", {}).get("overall", {})
                print(f"  Gen win rate: {agg.get('gen_win_rate', 0):.2%}")
                
                # Save individual result
                if output_dir:
                    output_dir.mkdir(parents=True, exist_ok=True)
                    output_file = output_dir / f"{gen_file.stem}_writing.json"
                    output_file.write_text(json.dumps(result, indent=2, ensure_ascii=False))
            except Exception as e:
                print(f"  Error: {e}")
        
        # Compute summary
        if results:
            total_gen_wins = sum(r.get("aggregate", {}).get("overall", {}).get("gen_wins", 0) for r in results)
            total_gt_wins = sum(r.get("aggregate", {}).get("overall", {}).get("gt_wins", 0) for r in results)
            total_ties = sum(r.get("aggregate", {}).get("overall", {}).get("ties", 0) for r in results)
            total = total_gen_wins + total_gt_wins + total_ties
            
            print(f"\n[Summary] {len(results)} articles evaluated")
            print(f"  Total Gen wins: {total_gen_wins}/{total}")
            print(f"  Total GT wins:  {total_gt_wins}/{total}")
            print(f"  Total Ties:     {total_ties}/{total}")
            if total > 0:
                print(f"  Overall Gen win rate: {total_gen_wins/total:.2%}")
            
            # Save summary
            if output_dir:
                summary_file = output_dir / "_summary.json"
                summary = {
                    "total_articles": len(results),
                    "total_gen_wins": total_gen_wins,
                    "total_gt_wins": total_gt_wins,
                    "total_ties": total_ties,
                    "gen_win_rate": total_gen_wins / total if total > 0 else 0,
                }
                summary_file.write_text(json.dumps(summary, indent=2))
        
        return results
    
    else:
        print("Error: Must provide --gen/--gt, --gen-dir/--gt-dir, or --benchmark/--agency")
        return None


def run_verifiability_evaluation(
    gen_path: Optional[Path],
    gt_path: Optional[Path],
    gen_dir: Optional[Path],
    gt_dir: Optional[Path],
    output_dir: Optional[Path],
    top_k: int,
    max_workers: int,
    benchmark_paths: Optional[BenchmarkPaths] = None,
):
    """Run verifiability evaluation
    
    Compares statements between:
    - Gen: test_data/<agency>/json_data/*.json
    - GT: wiki_data/cleaned_data/article/*.md
    """
    from evaluation.wiki_fact import WikiFactEvaluator
    
    evaluator = WikiFactEvaluator()
    
    if gen_path and gt_path:
        # Single file
        print(f"[Verifiability] Evaluating: {gen_path.name}")
        result = evaluator.evaluate_verifiability_files(gen_path, gt_path, top_k=top_k, max_workers=max_workers)
        
        print(f"  Gen supported by Wiki: {result['gen_supported_by_wiki_ratio']:.2%}")
        print(f"  Gen conflict with Wiki: {result['gen_conflict_with_wiki_ratio']:.2%}")
        print(f"  Wiki covered by Gen: {result['wiki_covered_by_gen_ratio']:.2%}")
        
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / f"{gen_path.stem}_verifiability.json"
            output_file.write_text(json.dumps(result, indent=2, ensure_ascii=False))
            print(f"  Result saved to: {output_file}")
        
        return result
    
    elif gen_dir and gt_dir:
        # Batch
        results = []
        gen_files = sorted(gen_dir.glob("*.json"))
        
        for gen_file in gen_files:
            # Find GT file (.md for wiki_data)
            gt_file = None
            for ext in [".md", ".json"]:
                candidate = gt_dir / f"{gen_file.stem}{ext}"
                if candidate.exists():
                    gt_file = candidate
                    break
            
            if not gt_file:
                print(f"[Skip] No GT found for: {gen_file.name}")
                continue
            
            print(f"[Verifiability] Evaluating: {gen_file.name}")
            try:
                result = evaluator.evaluate_verifiability_files(gen_file, gt_file, top_k=top_k, max_workers=max_workers)
                results.append({"file": gen_file.name, **result})
                print(f"  Gen supported: {result['gen_supported_by_wiki_ratio']:.2%}")
                
                if output_dir:
                    output_dir.mkdir(parents=True, exist_ok=True)
                    output_file = output_dir / f"{gen_file.stem}_verifiability.json"
                    output_file.write_text(json.dumps(result, indent=2, ensure_ascii=False))
            except Exception as e:
                print(f"  Error: {e}")
        
        # Summary
        if results:
            avg_supported = sum(r['gen_supported_by_wiki_ratio'] for r in results) / len(results)
            avg_conflict = sum(r['gen_conflict_with_wiki_ratio'] for r in results) / len(results)
            avg_coverage = sum(r['wiki_covered_by_gen_ratio'] for r in results) / len(results)
            
            print(f"\n[Summary] {len(results)} articles evaluated")
            print(f"  Avg Gen supported by Wiki: {avg_supported:.2%}")
            print(f"  Avg Gen conflict with Wiki: {avg_conflict:.2%}")
            print(f"  Avg Wiki covered by Gen: {avg_coverage:.2%}")
            
            if output_dir:
                summary_file = output_dir / "_summary.json"
                summary = {
                    "total_articles": len(results),
                    "avg_gen_supported_by_wiki": avg_supported,
                    "avg_gen_conflict_with_wiki": avg_conflict,
                    "avg_wiki_covered_by_gen": avg_coverage,
                }
                summary_file.write_text(json.dumps(summary, indent=2))
        
        return results
    
    else:
        print("Error: Must provide --gen/--gt, --gen-dir/--gt-dir, or --benchmark/--agency")
        return None


def run_citation_evaluation(
    gen_path: Optional[Path],
    gen_dir: Optional[Path],
    output_dir: Optional[Path],
    max_workers: int,
    benchmark_paths: Optional[BenchmarkPaths] = None,
):
    """Run citation evaluation
    
    Evaluates citation support from:
    - Gen: test_data/<agency>/json_data/*.json (statements + citation_contents)
    """
    from evaluation.wiki_fact import WikiFactEvaluator
    
    evaluator = WikiFactEvaluator()
    
    if gen_path:
        # Single file
        print(f"[Citation] Evaluating: {gen_path.name}")
        result = evaluator.evaluate_citation_file(gen_path, max_workers=max_workers)
        
        if result["status"] == "completed":
            print(f"  Support ratio: {result['support_ratio']:.2%}")
            print(f"  Conflict ratio: {result['conflict_ratio']:.2%}")
            print(f"  Evaluated: {result['evaluated_statements']}/{result['total_statements']}")
        else:
            print(f"  Skipped: {result.get('reason', 'unknown')}")
        
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / f"{gen_path.stem}_citation.json"
            output_file.write_text(json.dumps(result, indent=2, ensure_ascii=False))
            print(f"  Result saved to: {output_file}")
        
        return result
    
    elif gen_dir:
        # Batch
        results = []
        gen_files = sorted(gen_dir.glob("*.json"))
        
        for gen_file in gen_files:
            print(f"[Citation] Evaluating: {gen_file.name}")
            try:
                result = evaluator.evaluate_citation_file(gen_file, max_workers=max_workers)
                results.append({"file": gen_file.name, **result})
                
                if result["status"] == "completed":
                    print(f"  Support ratio: {result['support_ratio']:.2%}")
                else:
                    print(f"  Skipped: {result.get('reason', 'unknown')}")
                
                if output_dir:
                    output_dir.mkdir(parents=True, exist_ok=True)
                    output_file = output_dir / f"{gen_file.stem}_citation.json"
                    output_file.write_text(json.dumps(result, indent=2, ensure_ascii=False))
            except Exception as e:
                print(f"  Error: {e}")
        
        # Summary
        completed = [r for r in results if r.get("status") == "completed"]
        if completed:
            avg_support = sum(r["support_ratio"] for r in completed) / len(completed)
            avg_conflict = sum(r["conflict_ratio"] for r in completed) / len(completed)
            print(f"\n[Summary] {len(completed)}/{len(results)} articles evaluated")
            print(f"  Average support ratio: {avg_support:.2%}")
            print(f"  Average conflict ratio: {avg_conflict:.2%}")
            
            if output_dir:
                summary_file = output_dir / "_summary.json"
                summary = {
                    "total_articles": len(results),
                    "completed_articles": len(completed),
                    "avg_support_ratio": avg_support,
                    "avg_conflict_ratio": avg_conflict,
                }
                summary_file.write_text(json.dumps(summary, indent=2))
        
        return results
    
    else:
        print("Error: Must provide --gen, --gen-dir, or --benchmark/--agency")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Wiki Live Challenge Evaluation CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="Evaluation type")
    
    # Common arguments for benchmark-based evaluation
    def add_benchmark_args(p):
        p.add_argument("-b", "--benchmark", type=str, default=DEFAULT_BENCHMARK,
                      help=f"Benchmark ID (default: {DEFAULT_BENCHMARK})")
        p.add_argument("-a", "--agency", type=str, help="Agency ID to evaluate")
    
    # Common arguments for path-based evaluation
    def add_path_args(p):
        p.add_argument("--gen", type=Path, help="Generated article path")
        p.add_argument("--gt", type=Path, help="Ground truth article path")
        p.add_argument("--gen-dir", type=Path, help="Generated articles directory")
        p.add_argument("--gt-dir", type=Path, help="Ground truth articles directory")
    
    def add_common_args(p):
        add_benchmark_args(p)
        add_path_args(p)
        p.add_argument("-o", "--output", type=Path, help="Output directory")
        p.add_argument("--max-workers", type=int, default=20, help="Max parallel workers")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List benchmarks and agencies")
    list_parser.add_argument("-b", "--benchmark", type=str, help="Benchmark ID to show details")
    
    # Writing evaluation
    writing_parser = subparsers.add_parser("writing", help="Wiki writing quality evaluation")
    add_common_args(writing_parser)
    writing_parser.add_argument("--allow-tie", action="store_true", help="Allow tie results")
    writing_parser.add_argument("--categories", nargs="+", help="Categories to evaluate")
    
    # Verifiability evaluation
    verify_parser = subparsers.add_parser("verifiability", help="Verifiability evaluation")
    add_common_args(verify_parser)
    verify_parser.add_argument("--top-k", type=int, default=10, help="Top-k similar statements")
    
    # Citation evaluation
    cite_parser = subparsers.add_parser("citation", help="Citation support evaluation")
    add_benchmark_args(cite_parser)
    cite_parser.add_argument("--gen", type=Path, help="Generated article path")
    cite_parser.add_argument("--gen-dir", type=Path, help="Generated articles directory")
    cite_parser.add_argument("-o", "--output", type=Path, help="Output directory")
    cite_parser.add_argument("--max-workers", type=int, default=10, help="Max parallel workers")
    
    # All evaluation
    all_parser = subparsers.add_parser("all", help="Run all evaluations")
    add_common_args(all_parser)
    all_parser.add_argument("--allow-tie", action="store_true", help="Allow tie in writing")
    all_parser.add_argument("--top-k", type=int, default=10, help="Top-k for verifiability")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Load config
    Config()
    
    # Handle list command
    if args.command == "list":
        run_list_command(args.benchmark)
        return
    
    # Resolve paths for benchmark/agency-based evaluation
    gen_path = getattr(args, 'gen', None)
    gt_path = getattr(args, 'gt', None)
    gen_dir = getattr(args, 'gen_dir', None)
    gt_dir = getattr(args, 'gt_dir', None)
    benchmark_id = getattr(args, 'benchmark', DEFAULT_BENCHMARK)
    agency_id = getattr(args, 'agency', None)
    
    # Get evaluation paths
    gen_path, gt_path, gen_dir, gt_dir, benchmark_paths = get_evaluation_paths(
        benchmark_id, agency_id, gen_path, gt_path, gen_dir, gt_dir,
        use_json=True  # Default to JSON for evaluation
    )
    
    if args.command == "writing":
        run_writing_evaluation(
            gen_path, gt_path, gen_dir, gt_dir, args.output,
            args.allow_tie, args.categories, benchmark_paths
        )
    
    elif args.command == "verifiability":
        run_verifiability_evaluation(
            gen_path, gt_path, gen_dir, gt_dir, args.output,
            args.top_k, args.max_workers, benchmark_paths
        )
    
    elif args.command == "citation":
        # Citation only needs gen data
        if agency_id and benchmark_id:
            benchmark_paths = get_benchmark_paths(benchmark_id)
            gen_dir = benchmark_paths.get_agency_json_dir(agency_id)
        
        run_citation_evaluation(
            gen_path, gen_dir, args.output, args.max_workers, benchmark_paths
        )
    
    elif args.command == "all":
        print("=" * 60)
        print(f"WIKI LIVE CHALLENGE EVALUATION")
        if benchmark_paths:
            print(f"Benchmark: {benchmark_paths.benchmark_id}")
        if agency_id:
            print(f"Agency: {agency_id}")
        print("=" * 60)
        
        print("\n" + "=" * 60)
        print("WIKI WRITING EVALUATION")
        print("=" * 60)
        run_writing_evaluation(
            gen_path, gt_path, gen_dir, gt_dir,
            args.output / "writing" if args.output else None,
            args.allow_tie, None, benchmark_paths
        )
        
        print("\n" + "=" * 60)
        print("VERIFIABILITY EVALUATION")
        print("=" * 60)
        run_verifiability_evaluation(
            gen_path, gt_path, gen_dir, gt_dir,
            args.output / "verifiability" if args.output else None,
            args.top_k, args.max_workers, benchmark_paths
        )
        
        print("\n" + "=" * 60)
        print("CITATION EVALUATION")
        print("=" * 60)
        # Citation only needs gen data
        if agency_id and benchmark_id:
            cite_gen_dir = benchmark_paths.get_agency_json_dir(agency_id)
        else:
            cite_gen_dir = gen_dir
        
        run_citation_evaluation(
            gen_path, cite_gen_dir,
            args.output / "citation" if args.output else None,
            args.max_workers, benchmark_paths
        )


if __name__ == "__main__":
    main()
