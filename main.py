"""GraphResearcher entry point.

Loads environment, assembles the LangGraph research workflow, and runs a research
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
import json
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

from observability import LangfuseRun, start_langfuse_run  # noqa: E402

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

    def _safe_write(self, stream: object, data: str) -> int:
        """Safely write data to stream, handling encoding errors on Windows."""
        try:
            stream.write(data)
            return len(data)
        except UnicodeEncodeError:
            # Replace characters that can't be encoded with safe alternatives
            safe_data = data.encode('utf-8', errors='replace').decode('utf-8')
            try:
                stream.write(safe_data)
                return len(safe_data)
            except Exception:
                # If still failing, try writing directly as bytes if stream supports it
                try:
                    if hasattr(stream, 'buffer'):
                        stream.buffer.write(safe_data.encode('utf-8', errors='replace'))
                        return len(safe_data)
                except Exception:
                    pass
                return 0

    def write(self, data: str) -> int:
        """Write to the terminal stream and an ANSI-stripped copy to the log."""
        self._safe_write(self._stream, data)
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


def _evidence_fallback_report(request: str, status_summary: dict) -> str:
    """Build the last-resort deterministic evidence-list report."""
    del status_summary
    try:
        from tools import report_tools

        return report_tools.build_cited_evidence_report(request)
    except Exception:  # noqa: BLE001 - a minimal neutral report must always exist
        if re.search(r"[\u4e00-\u9fff]", request or ""):
            return "# 调研报告\n\n## 结论\n\n暂无可核实结论。\n"
        return "# Research Report\n\n## Conclusion\n\nNo verifiable findings are available.\n"


def _delivery_contract_mode(status_summary: dict) -> str | None:
    """将报告授权状态映射为 v2 交付契约."""
    state = status_summary.get("reporting_from_state") or status_summary.get("research_state")
    if state == "REPORT_READY":
        return "complete"
    if state in {"LIMITED_REPORT_READY", "BUDGET_EXHAUSTED"}:
        return "limited"
    return None


def _prepare_report_for_delivery(
    final_text: str,
    request: str,
    status_summary: dict,
    compiled_text: str = "",
    salvaged_text: str = "",
    attempt_summary: dict | None = None,
) -> tuple[str, list[str], str]:
    """Deliver the best complete Reporter artifact with validation warnings."""
    del final_text  # Workflow terminal prose is never a canonical report.
    issues: list[str] = []
    from tools import report_tools

    def audit_candidate(text: str, mode: str) -> tuple[str, list[str]]:
        local_issues: list[str] = []
        try:
            report_text = report_tools.sanitize_report(text)
            # Global compiler and final delivery must agree about structural
            # blocks: headings, table scaffolding, and recommendation lead-ins
            # do not need standalone citations. Citation validity and quality
            # checks remain active for every report.
            require_citation_per_unit = mode not in {
                "compiled_reporter",
                "salvaged_reporter",
            }
            hard_issues = report_tools.validate_delivery_invariants(
                report_text,
                require_citation_per_unit=require_citation_per_unit,
            )
            quality_issues = report_tools.validate_report_quality(report_text)
            consistency_issues = report_tools.validate_final_report(report_text)
            local_issues.extend(hard_issues)
            local_issues.extend(quality_issues)
            local_issues.extend(consistency_issues)
        except Exception as exc:  # noqa: BLE001 - preserve delivery diagnostics
            local_issues.append(f"{mode} audit failed: {exc}")
            report_text = text
        return report_text, list(dict.fromkeys(local_issues))

    if compiled_text.strip():
        report_text, local_issues = audit_candidate(compiled_text, "compiled_reporter")
        mode = (
            "compiled_reporter_validated"
            if (attempt_summary or {}).get("validated")
            else "compiled_reporter_unvalidated"
        )
        return report_text, local_issues, mode

    if salvaged_text.strip():
        report_text, local_issues = audit_candidate(salvaged_text, "salvaged_reporter")
        return report_text, local_issues, "compiled_reporter_unvalidated"

    if attempt_summary:
        for issue in attempt_summary.get("issues", []):
            message = issue.get("message") if isinstance(issue, dict) else str(issue)
            if message:
                issues.append(f"report attempt: {message}")
    else:
        state = status_summary.get("research_state")
        if state in {"REPORT_READY", "LIMITED_REPORT_READY", "BUDGET_EXHAUSTED"}:
            issues.append("Reporter was authorized but never submitted a structured report")
        elif state == "REPORTING":
            issues.append("Reporter was invoked but did not submit a structured report")
        else:
            issues.append("Reporter submitted no valid structured report")

    report_text = _evidence_fallback_report(request, status_summary)
    report_text, local_issues = audit_candidate(report_text, "evidence_fallback")
    return report_text, list(dict.fromkeys([*issues, *local_issues])), "evidence_fallback"


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
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    original_level = root_logger.level
    run_log_handler: logging.Handler | None = None
    langfuse_run = LangfuseRun()
    # Tee stdout+stderr into run.log so EVERYTHING printed — rich output,
    # logging, warnings, and tracebacks — is captured, not just emitted lines.
    with open(log_path, "w", encoding="utf-8") as log_file:
        sys.stdout = _Tee(orig_stdout, log_file)
        sys.stderr = _Tee(orig_stderr, log_file)
        try:
            if opts["log_level"] != "NONE":
                run_log_handler = logging.StreamHandler(sys.stderr)
                run_log_handler.setFormatter(logging.Formatter(logging.BASIC_FORMAT))
                root_logger.handlers = [run_log_handler]
                root_logger.setLevel(getattr(logging, opts["log_level"]))

            from tools import graph_manager_tools, middleware

            middleware.configure(max_search_rounds=max_rounds)
            graph_manager_tools.configure(output_dir=str(output_dir), user_request=request)

            import config
            from workflow import workflow

            langfuse_run = start_langfuse_run(
                output_dir=output_dir,
                max_search_rounds=max_rounds,
                model_name=config.DEFAULT_MODEL,
            )

            emit(f"Request: {request}")
            emit(f"Output dir: {output_dir} | max search rounds: {max_rounds or 'unlimited'}\n")
            if langfuse_run.enabled:
                emit(f"Langfuse session: {langfuse_run.session_id}")

            stream_config = {"recursion_limit": 400, **langfuse_run.langchain_config()}
            stream_kwargs = {"config": stream_config, "stream_mode": "values"}
            if opts["subgraphs"]:
                stream_kwargs["subgraphs"] = True

            # In "values" mode each chunk is the full state snapshot; track how
            # many messages we have already printed so we surface every new one,
            # not just the last of each superstep.
            seen_by_ns: dict[tuple, int] = {}
            for chunk in workflow.stream({"messages": [{"role": "user", "content": request}]}, **stream_kwargs):
                namespace: tuple = ()
                if opts["subgraphs"]:
                    namespace, chunk = chunk
                messages = chunk.get("messages", []) if isinstance(chunk, dict) else []
                if not messages:
                    continue

                # Keep top-level text for diagnostics only. The canonical report
                # must come from Reporter's structured submit_final_report tool.
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
            try:
                from tools import research_state

                if research_state.get_goal():
                    research_state.update_goal({
                        "research_state": research_state.FAILED,
                        "last_error": traceback.format_exc(),
                    })
            except Exception:
                pass
        finally:
            from tools import research_state

            try:
                status_summary = research_state.get_status()
            except Exception as exc:
                status_summary = {"research_state": None, "status_error": str(exc)}
            state_before_write = status_summary.get("research_state")
            try:
                compiled_text = graph_manager_tools.get_compiled_report()
            except Exception:
                compiled_text = ""
            try:
                salvaged_text = graph_manager_tools.get_salvaged_report()
            except Exception:
                salvaged_text = ""
            try:
                attempt_summary = graph_manager_tools.get_last_report_attempt()
            except Exception:
                attempt_summary = {}
            attempt_summary_brief = {
                key: value
                for key, value in attempt_summary.items()
                if key not in {"report", "salvaged_report"}
            }
            report_text, validation_issues, artifact_delivery_mode = _prepare_report_for_delivery(
                final_text,
                request,
                status_summary,
                compiled_text=compiled_text,
                salvaged_text=salvaged_text,
                attempt_summary=attempt_summary,
            )
            report_saved = False
            try:
                if report_text.strip():
                    report_path.write_text(report_text, encoding="utf-8")
                    report_saved = True
            except Exception:
                console.print("[yellow]Report write failed (captured in run.log):[/]")
                console.print(traceback.format_exc(), markup=False, highlight=False)

            if validation_issues:
                console.print(
                    f"[yellow]Report delivered with {len(validation_issues)} validation warning(s).[/]"
                )
            try:
                report_delivery_mode = _delivery_contract_mode(status_summary)
                attempt_summary_brief["artifact_delivery_mode"] = artifact_delivery_mode
                goal_update = {
                    "report_delivery_mode": report_delivery_mode,
                    "report_validation_issues": validation_issues,
                    "report_attempt_summary": attempt_summary_brief,
                }
                if report_saved and state_before_write == research_state.REPORTING:
                    goal_update["research_state"] = research_state.COMPLETED
                research_state.update_goal(goal_update)
                status_summary = research_state.get_status()
            except Exception:
                console.print("[yellow]Report delivery status update failed (captured in run.log):[/]")
                console.print(traceback.format_exc(), markup=False, highlight=False)

            # Export the run's graph from neo4j to JSONL for graph_viewer.html.
            graph_path = output_dir / "research_graph.jsonl"
            try:
                from tools import graph_tools

                graph_tools.export_graph_jsonl(str(graph_path))
            except Exception:
                console.print("[yellow]Graph export to JSONL failed (captured in run.log):[/]")
                console.print(traceback.format_exc(), markup=False, highlight=False)

            langfuse_run.flush()

            console.rule("[bold green]Final Report" if report_saved else "[bold yellow]Research Status")
            console.print(Markdown(report_text))
            console.print(f"\n[dim]State summary: {json.dumps(status_summary, ensure_ascii=False)}[/]")
            saved = f"{report_path}, {graph_path}, {log_path}" if report_saved else f"{graph_path}, {log_path}"
            console.print(f"\n[dim]Saved: {saved}[/]")
            if run_log_handler is not None:
                root_logger.removeHandler(run_log_handler)
                run_log_handler.close()
                run_log_handler = None
                root_logger.handlers = original_handlers
                root_logger.setLevel(original_level)
            sys.stdout, sys.stderr = orig_stdout, orig_stderr


def main() -> None:
    """Parse arguments and run the research loop."""
    parser = argparse.ArgumentParser(description="GraphResearcher — graph-driven deep research agent.")
    parser.add_argument("request", nargs="*", help="The research request.")
    parser.add_argument(
        "-r",
        "--max-rounds",
        type=int,
        default=30,
        help="Maximum number of Searcher dispatches (search rounds); 0 means no limit. "
        "Default: 30 — leaves ample budget for depth-breadth balanced expansion.",
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
