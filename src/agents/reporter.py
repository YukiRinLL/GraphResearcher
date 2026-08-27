"""Legacy Reporter Agent mapping retained for compatibility.

The active runtime is ``agents.reporter_workflow``: a deterministic LangGraph
that invokes report tools itself and limits the model to JSON candidates. This
mapping remains available for callers that still import ``reporter`` directly,
but ``workflow.report_node`` no longer uses it.
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
