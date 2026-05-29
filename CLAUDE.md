# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GraphResearcher is a graph-driven deep research agent framework. Instead of a flat TODO list and evidence store, it models the entire research process — task planning, search, evidence extraction, conflict resolution, and report writing — as a queryable, scoreable, traceable **Research Graph**.

The system orchestrates four agents (Orchestrator, Searcher, Reporter, Verifier) backed by two infrastructure components (Graph Manager, Middleware). The Orchestrator drives the research loop; the Searcher collects evidence; the Reporter writes citation-bound sections; the Verifier handles quality control and conflict resolution.

## Commands

This project uses `uv` for dependency management and Python 3.12.

```bash
# Install dependencies
uv sync

# Run tests (the test file is an integration test, not a pytest suite)
uv run python tests/test_graph_tools.py

# Lint
uv run ruff check src/

# Format / auto-fix
uv run ruff check --fix src/
```

> The test in `tests/test_graph_tools.py` is a standalone script that exercises graph CRUD operations end-to-end against a live `GraphManager`. Run it directly, not via pytest.

## Architecture

### Source layout

```
src/
  agents/          # Agent implementations (Orchestrator, Searcher, Reporter, MemoryManager)
  memory/
    graph.py       # GraphManager + GraphNode/GraphEdge dataclasses + NodeType/EdgeType enums
    schema.py      # (stub — planned Pydantic schemas)
  prompts/
    orchestrator.md          # Orchestrator system prompt (Chinese)
    searcher.md              # Searcher system prompt with full I/O protocol (Chinese)
    memory_manager_prompts.py  # LLM prompts for MemoryManager (init_research, extract_content)
  tools/
    graph_tools.py   # Sync wrapper functions over GraphManager (the agent-facing toolkit)
    search_tools.py  # Tavily web search wrapper
    middleware.py    # (stub — planned system guardrails)
    report_tools.py  # (stub — planned report writing helpers)
```

### Core data layer: `src/memory/graph.py`

`GraphManager` stores the Research Graph as a flat JSONL file (`~/.graphresearcher/research_graph.jsonl` by default, or `$REPO_BASE_DIR/.graphresearcher/`). The file begins with a marker line `{"type": "_graphresearcher", "source": "graph-researcher"}` followed by one JSON object per line tagged with `"kind": "node"` or `"kind": "edge"`.

All `GraphManager` methods are `async`. In-memory adjacency maps (`_out_edges`, `_in_edges`) are rebuilt on load. Writes happen immediately after every mutation (no batching). File-modification-time is used as a lightweight staleness check to reload when the file changes externally.

**Node types** (`NodeType` enum): `user_request`, `query`, `search_run`, `source`, `document`, `statement`, `evidence`, `entity`, `conflict`, `analysis`, `report_section`.

**Edge types** (`EdgeType` enum): `has_query`, `parent_of`, `searched_by`, `found_source`, `has_document`, `extracted_statement`, `supported_by`, `contradicted_by`, `mentions`, `related_to`, `has_conflict`, `resolves_gap`, `uses`.

### Agent-facing toolkit: `src/tools/graph_tools.py`

Provides synchronous convenience wrappers (`add_node`, `upsert_node`, `add_edge`, `get_node`, `search_nodes`, `get_subgraph`, `save_graph`, plus domain-specific helpers like `create_query`, `create_source`, `create_evidence`, etc.) over the async `GraphManager`. Uses `nest_asyncio` to handle nested event loops; falls back to a `ThreadPoolExecutor` if unavailable. `GraphManager` instances are cached by `cache_dir` key to avoid re-loading.

### MemoryManager: `src/agents/memory_manager.py`

Wraps `GraphManager` with LLM-powered methods callable by agents:
- `init_research(user_request)` — parses the request with an LLM, creates a `user_request` node and initial `query` nodes in the graph.
- `submit_search_result(query_id, search_result)` — ingests a document, LLM-extracts statements and a summary, writes them as nodes with edges.
- `extract_content(content)` — LLM call that returns `{keywords, statement, summary}` JSON.
- `analyze_subgraph`, `get_next_queries`, `analyze_query_state`, `export_report_context`, `bind_report_section` — stubs to be implemented.

Uses LangChain `init_chat_model` configured per-agent via a `config` dict.

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

### Environment variables

- `TAVILY_API_KEY` — required for web search (`src/tools/search_tools.py`).
- `OPENAI_BASE_URL` — overrides the OpenAI API endpoint (set in `.env`; the project uses an alternative proxy by default).
- `REPO_BASE_DIR` — if set, graph data is stored under `$REPO_BASE_DIR/.graphresearcher/` instead of `~/.graphresearcher/`.

### Linting rules

Ruff is configured with `E`, `F`, `I`, `D` (Google docstring convention), `D401`, `T201`, and `UP` rule sets. `E501` (line length) is ignored. Test files are exempt from `D` and `UP` rules.
