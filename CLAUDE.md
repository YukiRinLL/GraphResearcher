# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GraphResearcher is a graph-driven deep research agent framework built on LangChain / LangGraph. Instead of a flat TODO list and evidence store, it models the entire research process — task planning, search, evidence extraction, conflict resolution, and report writing — as a queryable, scoreable, traceable **Research Graph**.

The design (see `方案.md`, in Chinese) orchestrates four agents — **Orchestrator** (drives the loop: understands the request, plans the query hierarchy, dispatches searches, judges sub-graph sufficiency, decides horizontal/vertical expansion, triggers the report), **Searcher** (collects evidence), **Reporter** (writes citation-bound sections only from the graph), **Verifier** (conflict resolution and quality control) — backed by two infrastructure components: **Graph Manager** and **Middleware**.

> Project status: early scaffolding. The data layer (`memory/graph.py`) and the agent-facing toolkit (`tools/graph_tools.py`) work and are exercised by the integration test. The agents (`agents/*.py`), `main.py`, and the `middleware.py` / `report_tools.py` / `schema.py` stubs are placeholders — several reference an undefined `config` module or the `deepagents` package (not in `pyproject.toml`) and do not run yet. Treat them as design sketches, not working code.

## Commands

This project uses `uv` for dependency management and Python 3.12.

```bash
# Install dependencies
uv sync

# Run the integration test (a standalone script, NOT a pytest suite — run it directly)
uv run python tests/test_graph_tools.py

# Lint
uv run ruff check src/

# Format / auto-fix
uv run ruff check --fix src/
```

`tests/test_graph_tools.py` exercises graph CRUD end-to-end against a live `GraphManager`. It is plain `print`-based assertions, not pytest. Note it writes to the **real** default graph location (`~/.graphresearcher/`) unless `REPO_BASE_DIR` is set — set that env var to sandbox test runs.

## Import convention (important)

Source modules import from the top-level package names `memory.`, `tools.`, `prompts.` — **not** with a `src.` or `deep_research.` prefix (despite `pyproject.toml` mapping the `deep_research` package to `src/`). This means `src/` must be on `sys.path` to import anything. The test does this explicitly:

```python
src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))
```

Any new entry point or test must do the same, or run with `PYTHONPATH=src`.

## Architecture

### Core data layer: `src/memory/graph.py`

`GraphManager` stores the Research Graph as a flat JSONL file (`~/.graphresearcher/research_graph.jsonl` by default, or `$REPO_BASE_DIR/.graphresearcher/`; a `context` arg yields `research_graph-<context>.jsonl` for multiple isolated graphs). The file begins with a marker line `{"type": "_graphresearcher", "source": "graph-researcher"}` followed by one JSON object per line tagged `"kind": "node"` or `"kind": "edge"`.

- **All `GraphManager` methods are `async`.** In-memory adjacency maps (`_out_edges`, `_in_edges`) are rebuilt on load.
- Writes happen immediately after every mutation (no batching) via `_save_to_file`, which rewrites the whole file.
- File-modification-time is a lightweight staleness check (`_ensure_loaded`) that reloads when the file changes externally.
- Node IDs are auto-generated as `<timestamp>_<uuid8>`.

**Node types** (`NodeType` StrEnum): `user_request`, `query`, `search_run`, `source`, `document`, `statement`, `evidence`, `entity`, `conflict`, `analysis`, `report_section`.

**Edge types** (`EdgeType` StrEnum): `has_query`, `parent_of`, `searched_by`, `found_source`, `has_document`, `extracted_statement`, `supported_by`, `contradicted_by`, `mentions`, `related_to`, `has_conflict`, `resolves_gap`, `uses`.

### Agent-facing toolkit: `src/tools/graph_tools.py`

Synchronous convenience wrappers over the async `GraphManager` — this is the layer agents should call, not `GraphManager` directly. It bridges sync→async via `_run_async` (uses `nest_asyncio` when available; falls back to a `ThreadPoolExecutor`). `GraphManager` instances are cached by `cache_dir` key (`_manager_cache`); `clear_manager_cache()` resets it — the test calls this between runs.

Generic CRUD: `add_node`, `upsert_node`, `add_edge`, `get_node`, `search_nodes`, `get_subgraph`, `save_graph`. Domain helpers that create a node plus its edges in one call: `create_user_request`, `create_query`, `create_source`, `create_document`, `create_evidence`, `create_conflict`, `create_analysis`, `create_report_section`, `bind_evidence_to_section`, plus query-loop helpers `get_pending_queries`, `get_query_subgraph`, `mark_query_status`, and `list_graph_databases`.

> Note: the node-creating wrappers return the node-id **string** (the `add_node` return value), even though some docstrings say they return a dict. `get_node`/`search_nodes`/`get_subgraph` do return dicts.

### MemoryManager: `src/agents/memory_manager.py`

Wraps `GraphManager` with LLM-powered methods, configured per-agent via a `config` dict and `langchain.chat_models.init_chat_model`. `init_research(user_request)` and `submit_search_result(...)` have draft bodies; `analyze_subgraph`, `get_next_queries`, `analyze_query_state`, `export_report_context`, `bind_report_section`, etc. are stubs. The LLM prompts live in `src/prompts/memory_manager_prompts.py` (`init_research`, `extract_content`, `summarize_subgraph`).

> Two latent bugs to fix before this runs: (1) it calls async `GraphManager` methods (`add_node`, `add_edge`) directly without awaiting — route through `tools/graph_tools.py` sync wrappers instead; (2) `from prompts.memory_manager_prompts import *` pulls in names (`init_research`, `extract_content`) that collide with the method names of the same class.

### Research Graph data flow

```
UserRequest → (has_query) → Query → (searched_by) → SearchRun
                                                       ↓ (found_source)
                                                     Source → (has_document) → Document
                                                                                 ↓ (extracted_statement)
                                                                               Statement / Evidence
                                                                                 ↓ (supported_by / contradicted_by)
                                                                               Conflict → Analysis

ReportSection → (uses) → Evidence / Claim
```

### Visualization

`graph_viewer.html` is a standalone vis-network viewer. Open it in a browser and load a `research_graph*.jsonl` file via the file picker (client-side `FileReader`, no server).

## Environment variables

Set in `.env`:
- `TAVILY_API_KEY` — required for web search (`src/tools/search_tools.py`, `tavily_search`).
- `OPENAI_API_KEY` / `OPENAI_BASE_URL` — the project uses an alternative OpenAI-compatible proxy by default; `OPENAI_BASE_URL` overrides the endpoint.
- `REPO_BASE_DIR` — if set, graph data is stored under `$REPO_BASE_DIR/.graphresearcher/` instead of `~/.graphresearcher/`.

## Linting rules

Ruff selects `E`, `F`, `I`, `D` (Google docstring convention), `D401`, `T201`, `UP`. Ignored: `E501` (line length), `D417`, and the `UP006`/`UP007`/`UP035` modernizers (so `Optional[...]`, `List[...]`, `dict[...]` typing styles all coexist intentionally). Test files are exempt from `D` and `UP`.
