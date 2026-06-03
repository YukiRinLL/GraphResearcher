# GraphResearcher
A structured deep research agent framework built on LangChain Deep Agents.Leverage knowledge graph for task orchestration, claim-evidence management,conflict resolution, hierarchical memory and citation-aware long-form research.

## Usage

Run a research request end to end. The run streams progress to the console and
saves the research graph, final report, and run log under the output directory.
`run.log` mirrors **all** console output for the run — streamed progress, the
final report, Python `logging`, warnings, and any exception traceback — so a
failed run is fully diagnosable from the log.

```bash
uv run python main.py "your research request"
```

### Command-line arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `request` | — | The research request (positional; multiple words are joined). If omitted, you are prompted interactively. |
| `-r, --max-rounds N` | `6` | Maximum number of Searcher dispatches (search rounds). `0` means no limit. |
| `-o, --output-dir DIR` | current dir | Directory for `report.md`, `research_graph.jsonl`, and `run.log`. |
| `-v, --verbose {quiet,normal,debug}` | `normal` | Verbosity preset (see below). Individual flags override it. |
| `--show-tool-calls` / `--no-show-tool-calls` | from preset | Print tool calls (name + args) and tool results. |
| `--subgraphs` / `--no-subgraphs` | from preset | Stream subagent (searcher/reporter) internal steps too. |
| `--log-level {DEBUG,INFO,WARNING,ERROR,NONE}` | from preset | Python logging level; `NONE` leaves logging unconfigured. |
| `--truncate N` | from preset | Per-message content cap when printing; `0` means no truncation. |

### Verbosity presets

`-v/--verbose` sets defaults for the four low-level logging knobs. Any explicit
override flag wins over the preset value.

| Preset | show-tool-calls | subgraphs | log-level | truncate | per-message stream |
|--------|:---:|:---:|:---:|:---:|:---:|
| `quiet` | off | off | NONE | 500 | off (only the final report) |
| `normal` (default) | off | off | NONE | 500 | on |
| `debug` | on | on | INFO | 0 | on |

### Examples

```bash
# Default run (normal verbosity)
uv run python main.py "Compare RAG and long-context LLMs for enterprise search"

# Limit search rounds and choose an output directory
uv run python main.py "request" --max-rounds 8 --output-dir ./out

# No search-round limit
uv run python main.py "request" -r 0

# Most detailed: subgraphs, tool calls, INFO logs, no truncation
uv run python main.py "request" -v debug

# Quiet: only the final report
uv run python main.py "request" -v quiet

# Tweak individual aspects (overrides on top of the normal preset)
uv run python main.py "request" --show-tool-calls --truncate 0

# Start from the debug preset but disable subgraph streaming
uv run python main.py "request" -v debug --no-subgraphs

# Surface middleware logs (e.g. search-budget messages) without other detail
uv run python main.py "request" -r 1 --log-level INFO
```
