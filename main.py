"""GraphResearcher entry point.

Loads environment, assembles the Orchestrator deep agent, and runs a research
request end to end, streaming progress to the console.

Usage:
    uv run python main.py "your research request"
    uv run python main.py            # then type the request when prompted
"""

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


def run(request: str) -> None:
    """Run the research loop for a single request and print the result.

    Args:
        request: The user's research request.
    """
    from agents.orchestrator import orchestrator

    console.rule("[bold]GraphResearcher")
    console.print(f"[bold cyan]Request:[/] {request}\n")

    final_text = ""
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
        kind = last.__class__.__name__
        if text:
            console.print(f"[dim]{kind}:[/] {text[:500]}")
            final_text = text

    console.rule("[bold green]Final Report")
    console.print(Markdown(final_text or "(no report produced)"))


def main() -> None:
    """Parse the request from argv or stdin and run the research loop."""
    if len(sys.argv) > 1:
        request = " ".join(sys.argv[1:])
    else:
        request = console.input("[bold]Enter your research request:[/] ").strip()
    if not request:
        console.print("[red]No request provided.[/]")
        return
    run(request)


if __name__ == "__main__":
    main()
