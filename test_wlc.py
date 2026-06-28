"""Run GraphResearcher on Wiki Live Challenge inputs and score the outputs.

This script covers the full single-run evaluation loop required by the local
WLC workflow:
1. sample benchmark prompts deterministically,
2. run GraphResearcher and save markdown reports,
3. convert reports into WLC JSON format with the official pipeline,
4. run the official writing / verifiability / citation evaluators,
5. aggregate and print the six headline metrics.
"""

from __future__ import annotations

import argparse
import inspect
import json
import random
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import dotenv
from tqdm import tqdm

from main import VERBOSITY_PRESETS, resolve_log_options, run

dotenv.load_dotenv(".env")

WLC_ROOT = Path("/mnt/h/projects/Wiki_Live_Challenge")
WLC_BENCHMARK_ID = "2025_Mar_Nov"
if str(WLC_ROOT) not in sys.path:
    sys.path.insert(0, str(WLC_ROOT))

# The official WLC conversion/evaluation code reads credentials directly from
# process environment variables, so load the benchmark's own .env as well.
dotenv.load_dotenv(WLC_ROOT / ".env")

PROMPT_PATH = Path("/mnt/h/projects/Wiki_Live_Challenge/data/2025_Mar_Nov/wiki_data/ga_100.json")
OUTPUT_PATH = Path("outputs/wlc_reports")
SAMPLE_SIZE = 5
MAX_ROUNDS = 1
VERBOSE = "debug"
RANDOM_SEED: int | None = None

_SAFE_NAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
_TRAILING_NUMBER_RE = re.compile(r"^(.*?)(\d+)$")


def choose_output_dir(requested: Path) -> Path:
    """Return a non-existing output directory without overwriting history."""
    if not requested.exists():
        return requested

    match = _TRAILING_NUMBER_RE.match(requested.name)
    if match:
        prefix = match.group(1)
        next_number = int(match.group(2)) + 1
    else:
        prefix = requested.name
        next_number = 2

    parent = requested.parent
    while True:
        candidate = parent / f"{prefix}{next_number}"
        if not candidate.exists():
            return candidate
        next_number += 1


def safe_filename(title: str) -> str:
    """Return a filesystem-safe markdown stem while preserving readability."""
    name = _SAFE_NAME_RE.sub("-", title).strip().strip(".")
    return name or "untitled"


def load_items(path: Path) -> list[dict[str, Any]]:
    """Load WLC-style JSON records from ``path``."""
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list in {path}")
    return data


def sample_items(items: list[dict[str, Any]], sample_size: int, seed: int | None) -> list[dict[str, Any]]:
    """Randomly sample at most ``sample_size`` records."""
    if sample_size <= 0 or len(items) <= sample_size:
        return items
    rng = random.Random(seed)
    return rng.sample(items, sample_size)


def write_sample_manifest(items: list[dict[str, Any]], output_dir: Path) -> None:
    """Persist the exact sampled items for reproducibility."""
    manifest = [
        {
            "id": item.get("id"),
            "title": item.get("title"),
            "question": item.get("question"),
        }
        for item in items
    ]
    (output_dir / "_sample_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def run_one(item: dict[str, Any], output_dir: Path, max_rounds: int, opts: dict[str, Any]) -> Path | None:
    """Run one item and copy its final report to ``{title}.md``."""
    id_ = str(item["id"])
    prompt = str(item["question"])
    title = str(item["title"])
    safe_title = safe_filename(title)

    out_file = output_dir / f"{safe_title}.md"
    if out_file.exists():
        print(f"Skip existing file: {out_file}")
        return out_file

    run_dir = output_dir / "_runs" / f"{id_}-{safe_title}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "input.json").write_text(
        json.dumps({"id": id_, "title": title, "question": prompt}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Processing: id={id_}, title={title}")
    print(f"Detailed artifacts: {run_dir}")
    run(prompt, run_dir, max_rounds, opts)

    report_path = run_dir / "report.md"
    if not report_path.exists():
        print(f"Warning: missing report.md for id={id_}, title={title}")
        return None

    shutil.copyfile(report_path, out_file)
    return out_file


def construct_with_supported_kwargs(cls: type[Any], **kwargs: Any) -> Any:
    """Instantiate ``cls`` with only the kwargs its current constructor accepts."""
    signature = inspect.signature(cls.__init__)
    supported = {name for name in signature.parameters if name != "self"}
    filtered = {key: value for key, value in kwargs.items() if key in supported}
    return cls(**filtered)


def build_wlc_json(
    markdown_dir: Path,
    json_dir: Path,
    concurrency: int,
) -> list[Path]:
    """Convert generated markdown reports into the official WLC JSON format."""
    from scripts.generate_json import process_single_file
    from src.citation_parser import CitationParser
    from src.config import Config as WLCConfig
    from src.jina_scraper import JinaScraper
    from src.json_builder import JSONBuilder
    from src.statement_extractor import StatementExtractor

    config = WLCConfig(WLC_ROOT / ".env")
    if not config.extract_api_key or not config.extract_base_url:
        raise RuntimeError("WLC extraction config missing: EXTRACT_API_KEY / EXTRACT_BASE_URL")
    if not config.jina_api_key:
        raise RuntimeError("WLC fetching config missing: JINA_API_KEY")

    citation_parser = CitationParser()
    json_builder = JSONBuilder()
    extractor = construct_with_supported_kwargs(
        StatementExtractor,
        model=config.extract_model,
        api_key=config.extract_api_key,
        base_url=config.extract_base_url,
        timeout=config.api_timeout,
        max_retries=config.max_retries,
    )
    scraper = construct_with_supported_kwargs(
        JinaScraper,
        api_key=config.jina_api_key,
        base_url=config.jina_base_url,
        timeout=config.api_timeout,
        max_retries=config.max_retries,
    )

    json_dir.mkdir(parents=True, exist_ok=True)
    json_paths: list[Path] = []
    for md_path in sorted(markdown_dir.glob("*.md")):
        json_path = json_dir / f"{md_path.stem}.json"
        stats = process_single_file(
            md_path=md_path,
            json_path=json_path,
            config=config,
            steps={"extract", "fetch"},
            citation_parser=citation_parser,
            json_builder=json_builder,
            extractor=extractor,
            scraper=scraper,
            base_dir=markdown_dir,
            verbose=True,
            print_lock=None,
        )
        if stats.get("status") != "success":
            raise RuntimeError(f"Failed to build WLC JSON for {md_path.name}: {stats}")
        json_paths.append(json_path)
    return json_paths


def aggregate_writing_result(results: list[dict[str, Any]]) -> dict[str, float]:
    """Aggregate WLC writing metrics exactly as the official batch script does."""
    category_totals: dict[str, dict[str, int]] = {}
    for result in results:
        aggregate = result.get("aggregate", {})
        for name, metric in aggregate.items():
            if name == "overall":
                continue
            category = category_totals.setdefault(name, {"gen_wins": 0, "total": 0})
            category["gen_wins"] += int(metric.get("gen_wins", 0))
            category["total"] += int(metric.get("total", 0))

    overall_gen_wins = sum(item["gen_wins"] for item in category_totals.values())
    overall_total = sum(item["total"] for item in category_totals.values())
    return {
        "overall": (overall_gen_wins / overall_total) if overall_total else 0.0,
        "well_written": (
            category_totals.get("Well-written", {}).get("gen_wins", 0)
            / max(category_totals.get("Well-written", {}).get("total", 0), 1)
        ),
        "neutral": (
            category_totals.get("Neutral", {}).get("gen_wins", 0)
            / max(category_totals.get("Neutral", {}).get("total", 0), 1)
        ),
        "broad": (
            category_totals.get("Broad in its coverage", {}).get("gen_wins", 0)
            / max(category_totals.get("Broad in its coverage", {}).get("total", 0), 1)
        ),
    }


def aggregate_ratio(results: list[dict[str, Any]], key: str) -> float:
    """Return the mean of a ratio field across files."""
    if not results:
        return 0.0
    return sum(float(item.get(key, 0.0)) for item in results) / len(results)


def evaluate_wlc_outputs(json_paths: list[Path], output_dir: Path) -> dict[str, Any]:
    """Run the official WLC evaluators on generated JSON outputs."""
    from evaluation.wiki_fact import WikiFactEvaluator
    from evaluation.wiki_writing import WikiWritingEvaluator
    from src.benchmark import get_benchmark_paths

    benchmark_paths = get_benchmark_paths(WLC_BENCHMARK_ID)
    result_root = output_dir / "_evaluation"
    writing_dir = result_root / "writing"
    verifiability_dir = result_root / "verifiability"
    citation_dir = result_root / "citation"
    for path in (writing_dir, verifiability_dir, citation_dir):
        path.mkdir(parents=True, exist_ok=True)

    writing_evaluator = WikiWritingEvaluator()
    fact_evaluator = WikiFactEvaluator()

    writing_results: list[dict[str, Any]] = []
    verifiability_results: list[dict[str, Any]] = []
    citation_results: list[dict[str, Any]] = []

    for json_path in json_paths:
        gt_path = benchmark_paths.wiki_article_dir / f"{json_path.stem}.md"
        if not gt_path.exists():
            raise FileNotFoundError(f"Missing ground-truth article for {json_path.stem}: {gt_path}")

        writing = writing_evaluator.evaluate_files(json_path, gt_path, allow_tie=False)
        verifiability = fact_evaluator.evaluate_verifiability_files(json_path, gt_path, top_k=10, max_workers=20)
        citation = fact_evaluator.evaluate_citation_file(json_path, max_workers=10)

        (writing_dir / f"{json_path.stem}_writing.json").write_text(
            json.dumps(writing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (verifiability_dir / f"{json_path.stem}_verifiability.json").write_text(
            json.dumps(verifiability, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (citation_dir / f"{json_path.stem}_citation.json").write_text(
            json.dumps(citation, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        writing_results.append(writing)
        verifiability_results.append(verifiability)
        citation_results.append(citation)

    writing_summary = aggregate_writing_result(writing_results)
    metrics = {
        "Overall": writing_summary["overall"] * 100,
        "Well-written": writing_summary["well_written"] * 100,
        "Neutral": writing_summary["neutral"] * 100,
        "Broad": writing_summary["broad"] * 100,
        "Cov. Wiki": aggregate_ratio(verifiability_results, "wiki_covered_by_gen_ratio") * 100,
        "Ref. Acc.": aggregate_ratio(citation_results, "support_ratio") * 100,
    }
    summary = {
        "benchmark": WLC_BENCHMARK_ID,
        "sample_size": len(json_paths),
        "metrics": metrics,
        "writing_results": [path.name for path in sorted(writing_dir.glob("*.json"))],
        "verifiability_results": [path.name for path in sorted(verifiability_dir.glob("*.json"))],
        "citation_results": [path.name for path in sorted(citation_dir.glob("*.json"))],
    }
    (result_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def print_metrics(summary: dict[str, Any], output_dir: Path) -> None:
    """Print the six headline WLC metrics."""
    print(f"\nResolved output path: {output_dir}")
    print("WLC headline metrics:")
    for key, value in summary.get("metrics", {}).items():
        print(f"  {key}: {value:.2f}")


def parse_args() -> argparse.Namespace:
    """Parse command-line overrides while keeping reference-script defaults."""
    parser = argparse.ArgumentParser(description="Run and score GraphResearcher on WLC benchmark inputs.")
    parser.add_argument("--prompt-path", type=Path, default=PROMPT_PATH, help="Input JSON path.")
    parser.add_argument("--output-path", type=Path, default=OUTPUT_PATH, help="Directory for markdown reports.")
    parser.add_argument("--sample-size", type=int, default=SAMPLE_SIZE, help="Random sample size; <=0 means all.")
    parser.add_argument("--seed", type=int, default=RANDOM_SEED, help="Optional random seed for sampling.")
    parser.add_argument(
        "-r",
        "--max-rounds",
        type=int,
        default=MAX_ROUNDS,
        help="Maximum Searcher dispatches per item; 0 means unlimited.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        choices=list(VERBOSITY_PRESETS),
        default=VERBOSE,
        help="GraphResearcher verbosity preset.",
    )
    args = parser.parse_args()
    # main.resolve_log_options expects these fields because main.py supports
    # fine-grained log overrides. This batch script only exposes the preset
    # (`-v/--verbose`) to keep the test command simple; None means "use preset".
    args.show_tool_calls = None
    args.subgraphs = None
    args.log_level = None
    args.truncate = None
    return args


def main() -> None:
    """Run GraphResearcher and the official WLC evaluation pipeline."""
    args = parse_args()
    output_dir = choose_output_dir(args.output_path)
    output_dir.mkdir(parents=True, exist_ok=False)

    items = sample_items(load_items(args.prompt_path), args.sample_size, args.seed)
    write_sample_manifest(items, output_dir)
    opts = resolve_log_options(args)

    generated_reports: list[Path] = []
    for item in tqdm(items, desc="Processing items"):
        try:
            report_path = run_one(item, output_dir, args.max_rounds, opts)
            if report_path is not None:
                generated_reports.append(report_path)
        except KeyError as exc:
            print(f"Skip malformed item missing {exc!s}: {item}")
        except Exception as exc:  # noqa: BLE001 - keep long batch runs moving
            print(f"Error processing id={item.get('id')}, title={item.get('title')}: {exc}")

    if not generated_reports:
        raise RuntimeError("No markdown reports were generated; aborting WLC evaluation.")

    json_paths = build_wlc_json(output_dir, output_dir / "_json_data", concurrency=10)
    summary = evaluate_wlc_outputs(json_paths, output_dir)
    print_metrics(summary, output_dir)


if __name__ == "__main__":
    main()
