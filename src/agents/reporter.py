from deepagents import create_deep_agent

analyzer = {
    "name": "analyzer",
    "description": "Analyzes the search results.",
    "system_prompt": config.analyzer_system_prompt,
    "tools": [],
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