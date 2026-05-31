"""GraphResearcher entry point.

Loads environment, assembles the Orchestrator deep agent, and runs a research
request end to end. Streams progress to the console while saving the research
graph, final report, and run log under the output directory.

How much of the run is shown is controlled by ``-v/--verbose`` (a preset) plus
individual override flags. The no-argument default reproduces the quiet
``normal`` behaviour.

Usage:
    uv run python main.py "your research request"
    uv run python main.py "request" --max-rounds 8 --output-dir ./out
    uv run python main.py "request" -r 0          # 0 = no search-round limit
    uv run python main.py "request" -v debug      # most detailed (subgraphs, tool calls, INFO logs, no truncation)
    uv run python main.py "request" -v quiet      # only the final report
    uv run python main.py "request" --show-tool-calls --truncate 0   # tweak individual aspects
"""

import argparse
import logging
import re
import sys
import traceback
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

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


class _Tee:
    """Mirror a text stream to a log file (ANSI-stripped) while passing through.

    Wrapping ``sys.stdout``/``sys.stderr`` with this captures *everything* the
    process prints — rich output, ``logging``, warnings, and tracebacks — into
    the run log, while the terminal still gets the original (colored) stream.
    ``isatty``/``fileno`` proxy to the wrapped stream so rich keeps the real
    terminal's width and color.
    """

    def __init__(self, stream: object, log_file: object) -> None:
        """Wrap ``stream`` and tee writes into ``log_file``."""
        self._stream = stream
        self._log = log_file

    def write(self, data: str) -> int:
        """Write to the terminal stream and an ANSI-stripped copy to the log."""
        self._stream.write(data)
        self._log.write(_ANSI_RE.sub("", data))
        self._log.flush()
        return len(data)

    def flush(self) -> None:
        """Flush both the terminal stream and the log file."""
        self._stream.flush()
        self._log.flush()

    def isatty(self) -> bool:
        """Proxy ``isatty`` so rich detects the real terminal."""
        return self._stream.isatty()

    def fileno(self) -> int:
        """Proxy ``fileno`` so rich can read the real terminal size."""
        return self._stream.fileno()

    def __getattr__(self, name: str) -> object:
        """Delegate any other attribute to the wrapped stream."""
        return getattr(self._stream, name)


# Verbosity presets. Each maps to defaults for the four low-level log knobs;
# any explicit override flag wins over the preset value.
#   show_tool_calls: print AIMessage tool calls (name + args) and ToolMessage results
#   subgraphs:       stream subagent (searcher/reporter) internal steps too
#   log_level:       Python logging level, or "NONE" to leave logging unconfigured
#   truncate:        per-message content cap (0 = no truncation)
VERBOSITY_PRESETS = {
    "quiet": {"show_tool_calls": False, "subgraphs": False, "log_level": "NONE", "truncate": 500, "stream": False},
    "normal": {"show_tool_calls": False, "subgraphs": False, "log_level": "NONE", "truncate": 500, "stream": True},
    "debug": {"show_tool_calls": True, "subgraphs": True, "log_level": "INFO", "truncate": 0, "stream": True},
}


def resolve_log_options(args: argparse.Namespace) -> dict:
    """Merge the ``-v`` preset with any explicit override flags.

    Args:
        args: Parsed CLI arguments. Override flags default to ``None`` and only
            win when the user set them explicitly.

    Returns:
        A dict with keys ``show_tool_calls``, ``subgraphs``, ``log_level``,
        ``truncate``, and ``stream``.
    """
    opts = dict(VERBOSITY_PRESETS[args.verbose])
    if args.show_tool_calls is not None:
        opts["show_tool_calls"] = args.show_tool_calls
    if args.subgraphs is not None:
        opts["subgraphs"] = args.subgraphs
    if args.log_level is not None:
        opts["log_level"] = args.log_level
    if args.truncate is not None:
        opts["truncate"] = args.truncate
    return opts


def _content_text(message: object) -> str:
    """Extract plain text from a message's ``content`` (string or content blocks)."""
    text = getattr(message, "content", "")
    if isinstance(text, list):
        text = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in text)
    return text or ""


def run(request: str, output_dir: Path, max_rounds: int, opts: dict) -> None:
    """Run the research loop for a single request and save the artifacts.

    Args:
        request: The user's research request.
        output_dir: Directory for the research graph, report, and log.
        max_rounds: Maximum number of Searcher dispatches; 0 means no limit.
        opts: Resolved logging options from :func:`resolve_log_options`.
    """
    log_path = output_dir / "run.log"
    report_path = output_dir / "report.md"

    truncate = opts["truncate"]
    show_tool_calls = opts["show_tool_calls"]
    stream_progress = opts["stream"]

    def emit(line: str) -> None:
        # markup=False / highlight=False: message text contains literal "[...]"
        # tags; the _Tee on sys.stdout mirrors this into the log file.
        console.print(line, markup=False, highlight=False)

    def clip(text: str) -> str:
        return text[:truncate] if truncate and len(text) > truncate else text

    def emit_message(message: object, prefix: str) -> None:
        """Print a single message: its tool calls/results and/or its text."""
        kind = message.__class__.__name__
        if show_tool_calls:
            for call in getattr(message, "tool_calls", None) or []:
                emit(f"{prefix}[{kind} → tool] {call.get('name')}({call.get('args')})")
            tool_name = getattr(message, "name", None)
            if kind == "ToolMessage" and tool_name:
                emit(f"{prefix}[{tool_name} result] {clip(_content_text(message))}")
                return
        text = _content_text(message)
        if text:
            emit(f"{prefix}[{kind}] {clip(text)}")

    final_text = ""
    orig_stdout, orig_stderr = sys.stdout, sys.stderr
    # Tee stdout+stderr into run.log so EVERYTHING printed — rich output,
    # logging, warnings, and tracebacks — is captured, not just emitted lines.
    with open(log_path, "w", encoding="utf-8") as log_file:
        sys.stdout = _Tee(orig_stdout, log_file)
        sys.stderr = _Tee(orig_stderr, log_file)
        try:
            if opts["log_level"] != "NONE":
                logging.basicConfig(level=getattr(logging, opts["log_level"]))

            from tools import graph_manager_tools, middleware

            middleware.configure(max_search_rounds=max_rounds)
            graph_manager_tools.configure(output_dir=str(output_dir))

            from agents.orchestrator import orchestrator

            emit(f"Request: {request}")
            emit(f"Output dir: {output_dir} | max search rounds: {max_rounds or 'unlimited'}\n")

            stream_kwargs = {"config": {"recursion_limit": 1000}, "stream_mode": "values"}
            if opts["subgraphs"]:
                stream_kwargs["subgraphs"] = True

            # In "values" mode each chunk is the full state snapshot; track how
            # many messages we have already printed so we surface every new one,
            # not just the last of each superstep.
            seen_by_ns: dict[tuple, int] = {}
            for chunk in orchestrator.stream({"messages": [{"role": "user", "content": request}]}, **stream_kwargs):
                namespace: tuple = ()
                if opts["subgraphs"]:
                    namespace, chunk = chunk
                messages = chunk.get("messages", []) if isinstance(chunk, dict) else []
                if not messages:
                    continue

                # The report is the Orchestrator's final reviewed message, so only
                # capture top-level (namespace == ()) text — never a subagent's draft.
                last_text = _content_text(messages[-1])
                if last_text and not namespace:
                    final_text = last_text

                if not stream_progress:
                    continue

                prefix = f"[{'/'.join(namespace)}] " if namespace else ""
                start = seen_by_ns.get(namespace, 0)
                for message in messages[start:]:
                    emit_message(message, prefix)
                seen_by_ns[namespace] = len(messages)
        except Exception:
            console.print("[red]Run failed with an exception (captured in run.log):[/]")
            console.print(traceback.format_exc(), markup=False, highlight=False)
        finally:
            # The report is the Orchestrator's final reviewed message (it aggregates
            # the Reporter's draft and revises it). The graph holds evidence and
            # section→evidence bindings only, not the report itself.
            report_text = final_text or "(no report produced)"
            report_path.write_text(report_text, encoding="utf-8")
            console.rule("[bold green]Final Report")
            console.print(Markdown(report_text))
            console.print(f"\n[dim]Saved: {report_path}, {output_dir / 'research_graph.jsonl'}, {log_path}[/]")
            sys.stdout, sys.stderr = orig_stdout, orig_stderr


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
    parser.add_argument(
        "-v",
        "--verbose",
        choices=list(VERBOSITY_PRESETS),
        default="normal",
        help="Verbosity preset: quiet (only the final report), normal (default, current behaviour), "
        "or debug (subgraphs, tool calls, INFO logs, no truncation). Individual flags below override it.",
    )
    parser.add_argument(
        "--show-tool-calls",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Print AIMessage tool calls (name + args) and ToolMessage results. Overrides the -v preset.",
    )
    parser.add_argument(
        "--subgraphs",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Stream subagent (searcher/reporter) internal steps too. Overrides the -v preset.",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "NONE"],
        default=None,
        help="Python logging level; NONE leaves logging unconfigured. Overrides the -v preset.",
    )
    parser.add_argument(
        "--truncate",
        type=int,
        default=None,
        help="Per-message content cap when printing; 0 means no truncation. Overrides the -v preset.",
    )
    args = parser.parse_args()

    request = " ".join(args.request).strip() or console.input("[bold]Enter your research request:[/] ").strip()
    if not request:
        console.print("[red]No request provided.[/]")
        return

    args.output_dir.mkdir(parents=True, exist_ok=True)
    run(request, args.output_dir, args.max_rounds, resolve_log_options(args))


if __name__ == "__main__":
    main()
