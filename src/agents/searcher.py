"""Searcher agent — a nested deep agent for evidence collection.

The Searcher is itself a deep agent built with `create_deep_agent`. It drives
the search workflow defined in `prompts/searcher.md` and delegates to two
sub-agents: `web_searcher` (runs `tavily_search`, reads pages) and `analyzer`
(structured extraction and conflict detection). It submits the resulting
evidence package to the Research Graph via the Graph Manager tools.
"""

from deepagents import create_deep_agent

import config
from tools.graph_manager_tools import SEARCHER_TOOLS
from tools.search_tools import serper_search, tavily_search

web_searcher = {
    "name": "web_searcher",
    "description": "Runs web searches and reads page content; returns raw, traceable source material.",
    "system_prompt": config.web_searcher_system_prompt,
    "tools": [serper_search, tavily_search],
}

analyzer = {
    "name": "analyzer",
    "description": "Performs structured knowledge extraction and conflict detection on collected sources.",
    "system_prompt": config.analyzer_system_prompt,
    "tools": [],
}

searcher = create_deep_agent(
    model=config.searcher_model,
    system_prompt=config.searcher_system_prompt,
    tools=SEARCHER_TOOLS,
    subagents=[web_searcher, analyzer],
)
