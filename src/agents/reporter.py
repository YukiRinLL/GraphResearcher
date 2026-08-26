"""Reporter agent — a subagent that writes the report from the graph only.

The Reporter is defined purely by `prompts/reporter.md`. It is a plain
`SubAgent` spec (no model override; it inherits the workflow's default model)
with the Reporter-facing Graph Manager tools, and is invoked by the workflow's
``report_node`` via ``langchain.agents.create_agent``.
"""

import config
from tools.graph_manager_tools import REPORTER_TOOLS
from tools.middleware import ReporterWorkflowMiddleware

reporter = {
    "name": "reporter",
    "description": (
        "Writes the final, citation-bound research report strictly from the "
        "Research Graph. Reads the verbatim request, commits evidence-bound chapters, "
        "and returns the full report with "
        "numbered citations and a references list."
    ),
    "system_prompt": config.reporter_system_prompt,
    "tools": REPORTER_TOOLS,
    "middleware": [ReporterWorkflowMiddleware()],
}
