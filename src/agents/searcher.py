# 仿照 ms-agents 中的 search agent，创建一个搜索代理，使用 tavily 的 web search 工具进行搜索，并使

import os
from typing import Literal
from tavily import TavilyClient
from deepagents import create_deep_agent

analyzer = {
    "name": "analyzer",
    "description": "Analyzes the search results.",
    "system_prompt": config.analyzer_system_prompt,
    "tools": [],
}

extractor = {
    "name": "extractor",
    "description": "Extract the search result"
}

web_searcher = {
    "name": "web_searcher",
    "description": "Searches the web for information.",
    "system_prompt": config.web_searcher_system_prompt,
    "tools": [web_search],
}


searcher = create_deep_agent(
    model=config.orchestrator_model,
    system_prompt=config.orchestrator_system_prompt,
    middleware=(),
    tools=[],
)