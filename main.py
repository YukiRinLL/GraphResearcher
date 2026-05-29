"""GraphResearcher — graph-driven deep research agent CLI."""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# Load .env before anything else so API keys are available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Allow imports from src/ without installing the package
sys.path.insert(0, str(Path(__file__).parent / "src"))


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    # Suppress noisy library loggers unless verbose
    if not verbose:
        for name in ("httpx", "httpcore", "openai", "anthropic", "langchain", "langgraph"):
            logging.getLogger(name).setLevel(logging.WARNING)


async def _run(args: argparse.Namespace) -> int:
    from agents.orchestrator import Orchestrator

    config = {
        "model_name": args.model,
        "cache_dir": args.cache_dir,
        "temperature": 0.3,
        "max_tokens": 8192,
        "max_retries": 3,
    }

    orchestrator = Orchestrator(config)

    # Tell the user where graph data will be stored
    from memory.graph import get_default_graph_cache_dir
    graph_dir = args.cache_dir or str(get_default_graph_cache_dir())
    print(f"[GraphResearcher] Graph storage: {graph_dir}", file=sys.stderr)  # noqa: T201
    print(f"[GraphResearcher] Starting research: {args.query!r}", file=sys.stderr)  # noqa: T201

    try:
        report = await orchestrator.run(
            user_request=args.query,
            max_rounds=args.max_rounds,
        )
    except KeyboardInterrupt:
        print("\n[Interrupted by user]", file=sys.stderr)  # noqa: T201
        return 130

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(report, encoding="utf-8")
        print(f"Report saved to: {output_path}")  # noqa: T201
    else:
        print(report)  # noqa: T201

    return 0


def main() -> None:
    """Parse CLI arguments and run the research workflow."""
    parser = argparse.ArgumentParser(
        prog="graphresearcher",
        description="Graph-driven deep research agent — searches the web and writes a cited report.",
    )
    parser.add_argument("query", help="Research question or topic")
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=6,
        metavar="N",
        help="Maximum search-analyze-expand iterations (default: 6)",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="Write report to FILE instead of stdout",
    )
    parser.add_argument(
        "--cache-dir",
        metavar="PATH",
        default=None,
        help="Graph storage directory (default: ~/.graphresearcher)",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("GRAPHRESEARCHER_MODEL", "gpt-4o-mini"),
        metavar="MODEL",
        help="LLM model name (default: gpt-4o-mini or $GRAPHRESEARCHER_MODEL)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()
    _configure_logging(args.verbose)

    sys.exit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
