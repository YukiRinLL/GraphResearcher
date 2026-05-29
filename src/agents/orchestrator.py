"""Orchestrator agent — the main deep agent driving the research loop.

Built with `create_deep_agent` and defined purely by `prompts/orchestrator.md`.
It owns the Orchestrator-facing Graph Manager tools and delegates to two
sub-agents via the built-in `task` tool:

- `searcher`: a nested deep agent (injected as a `CompiledSubAgent`).
- `reporter`: a `SubAgent` spec for report writing.
"""

from deepagents import create_deep_agent

import config
from agents.reporter import reporter
from agents.searcher import searcher
from tools.graph_manager_tools import ORCHESTRATOR_TOOLS

searcher_subagent = {
    "name": "searcher",
    "description": (
        "Collects evidence for one or a few queries: searches the web, reads "
        "sources, extracts structured knowledge, and submits the evidence "
        "package to the Research Graph. Use it to fill or deepen a query."
    ),
    "runnable": searcher,
}

orchestrator = create_deep_agent(
    model=config.orchestrator_model,
    system_prompt=config.orchestrator_system_prompt,
    tools=ORCHESTRATOR_TOOLS,
    subagents=[searcher_subagent, reporter],
)
