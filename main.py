"""GraphResearcher entry point.

Loads environment, assembles the Orchestrator deep agent, and runs a research
request end to end. Streams progress to the console while saving the research
graph, final report, and run log under the output directory.

Usage:
    uv run python main.py "your research request"
    uv run python main.py "request" --max-rounds 8 --output-dir ./out
    uv run python main.py "request" -r 0     # 0 = no search-round limit
"""

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

# Repo import convention: `src/` must be on sys.path (see CLAUDE.md).
SRC_DIR = Path(__file__).parent / "src"
sys.path.insert(0, str(SRC_DIR))

load_dotenv()

try:  # Use system trust store for TLS when behind a proxy.
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

from rich.console import Console  # noqa: E402  (import after sys.path setup)
from rich.markdown import Markdown  # noqa: E402

console = Console()


def run(request: str, output_dir: Path, max_rounds: int) -> None:
    """Run the research loop for a single request and save the artifacts.

    Args:
        request: The user's research request.
        output_dir: Directory for the research graph, report, and log.
        max_rounds: Maximum number of Searcher dispatches; 0 means no limit.
    """
    from tools import graph_manager_tools, middleware

    middleware.configure(max_search_rounds=max_rounds)
    graph_manager_tools.configure(output_dir=str(output_dir))

    from agents.orchestrator import orchestrator

    log_path = output_dir / "run.log"
    report_path = output_dir / "report.md"

    def emit(line: str) -> None:
        console.print(line)
        log_file.write(line + "\n")
        log_file.flush()

    final_text = ""
    with open(log_path, "w", encoding="utf-8") as log_file:
        emit(f"Request: {request}")
        emit(f"Output dir: {output_dir} | max search rounds: {max_rounds or 'unlimited'}\n")
        for chunk in orchestrator.stream(
            {"messages": [{"role": "user", "content": request}]},
            config={"recursion_limit": 1000},
            stream_mode="values",
        ):
            messages = chunk.get("messages", [])
            if not messages:
                continue
            last = messages[-1]
            text = getattr(last, "content", "")
            if isinstance(text, list):
                text = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in text)
            if text:
                emit(f"[{last.__class__.__name__}] {text[:500]}")
                final_text = text

    report_path.write_text(final_text or "(no report produced)", encoding="utf-8")

    console.rule("[bold green]Final Report")
    console.print(Markdown(final_text or "(no report produced)"))
    console.print(f"\n[dim]Saved: {report_path}, {output_dir / 'research_graph.jsonl'}, {log_path}[/]")


def main() -> None:
    """Parse arguments and run the research loop."""
    parser = argparse.ArgumentParser(description="GraphResearcher — graph-driven deep research agent.")
    parser.add_argument("request", nargs="*", help="The research request.")
    parser.add_argument(
        "-r",
        "--max-rounds",
        type=int,
        default=6,
        help="Maximum number of Searcher dispatches (search rounds); 0 means no limit. Default: 6.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path.cwd(),
        help="Directory for the research graph, report, and log. Default: current directory.",
    )
    args = parser.parse_args()

    request = " ".join(args.request).strip() or console.input("[bold]Enter your research request:[/] ").strip()
    if not request:
        console.print("[red]No request provided.[/]")
        return

    args.output_dir.mkdir(parents=True, exist_ok=True)
    run(request, args.output_dir, args.max_rounds)


if __name__ == "__main__":
    main()
