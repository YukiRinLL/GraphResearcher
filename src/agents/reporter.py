"""Reporter agent — a subagent that writes the report from the graph only.

The Reporter is defined purely by `prompts/reporter.md`. It is a plain
`SubAgent` spec (no model override; it inherits the Orchestrator's model) with
the Reporter-facing Graph Manager tools, and is delegated to by the
Orchestrator via the built-in `task` tool.
"""

import config
from tools.graph_manager_tools import REPORTER_TOOLS

reporter = {
    "name": "reporter",
    "description": (
        "Builds an evidence-grounded report through an outline, chapter bundles, "
        "Claim/Evidence-bound chapter commits, draft assembly, and targeted "
        "revisions. Citations and references are compiled deterministically."
    ),
    "system_prompt": config.reporter_system_prompt,
    "tools": REPORTER_TOOLS,
}
