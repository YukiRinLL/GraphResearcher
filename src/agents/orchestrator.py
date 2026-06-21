"""Orchestrator agent — the main deep agent driving the research loop.

Built with `create_deep_agent` and defined purely by `prompts/orchestrator.md`.
It owns the Orchestrator-facing Graph Manager tools including the structured
``dispatch_searcher`` tool, and delegates report writing to the Reporter
sub-agent via the built-in ``task`` tool.

- ``dispatch_searcher``: a Graph Manager tool (query_id is a required, typed
  parameter — never guessed from free text).
- ``reporter``: a ``SubAgent`` spec for report writing.
"""

from deepagents import create_deep_agent
from langchain.agents.middleware import ModelRetryMiddleware

import config
from agents.reporter import reporter
from tools.graph_manager_tools import ORCHESTRATOR_TOOLS
from tools.middleware import (
    EmptyResponseRetryMiddleware,
    QueryIdValidationMiddleware,
    ReportValidationMiddleware,
    SearchRoundLimitMiddleware,
    SensitiveWordsRetryMiddleware,
)

orchestrator = create_deep_agent(
    model=config.orchestrator_model,
    system_prompt=config.orchestrator_system_prompt,
    tools=ORCHESTRATOR_TOOLS,
    subagents=[reporter],
    middleware=[
        SearchRoundLimitMiddleware(),
        QueryIdValidationMiddleware(),
        ReportValidationMiddleware(),
        EmptyResponseRetryMiddleware(),
        SensitiveWordsRetryMiddleware(),
        ModelRetryMiddleware(),
    ],
)
