"""Graph Manager tools exposed to the agents.

Wraps the LLM-powered :class:`agents.memory_manager.MemoryManager` as
LangChain tools with clean, LLM-friendly signatures (no ``cache_dir`` / model
plumbing). Tools are grouped per agent: ``ORCHESTRATOR_TOOLS``,
``SEARCHER_TOOLS`` and ``REPORTER_TOOLS``.

The underlying ``MemoryManager`` is created lazily on first tool call so that
importing this module (for assembly checks) does not require API credentials.
"""

from typing import Any, Optional

from langchain_core.tools import tool

from agents.memory_manager import MemoryManager

_manager: Optional[MemoryManager] = None
_cache_dir: Optional[str] = None


def configure(output_dir: Optional[str] = None) -> None:
    """Set where the Research Graph is stored for the current run.

    Args:
        output_dir: Directory for the graph file (``<output_dir>/research_graph.jsonl``);
            ``None`` falls back to the default location. Rebuilds the shared
            MemoryManager so the new location takes effect.
    """
    global _cache_dir, _manager
    _cache_dir = output_dir
    _manager = None


def _mm() -> MemoryManager:
    """Return the shared MemoryManager, creating it on first use."""
    global _manager
    if _manager is None:
        _manager = MemoryManager(cache_dir=_cache_dir)
    return _manager


# -----------------------------
# Orchestrator tools
# -----------------------------
@tool
def init_research(user_request: str) -> dict:
    """Parse the user's research request and initialize the Research Graph.

    Creates the user-request node and a set of parallel initial query nodes.

    Args:
        user_request: The original research request from the user.

    Returns:
        dict with ``goal_id``, ``research_goal``, ``language`` and the created
        ``queries`` (each ``{id, text}``).
    """
    return _mm().init_research(user_request)


@tool
def get_next_queries(limit: int = 4) -> list:
    """List high-priority queries awaiting work.

    Returns queries whose status is ``pending``, ``needs_horizontal`` or
    ``needs_vertical``.

    Args:
        limit: Maximum number of queries to return.

    Returns:
        A list of ``{id, text, status}`` dicts.
    """
    return _mm().get_next_queries(limit)


@tool
def analyze_subgraph(query_id: str) -> dict:
    """Score whether a query's collected evidence is sufficient.

    Args:
        query_id: The query node ID to evaluate.

    Returns:
        dict with ``sufficiency_score``, ``covered``, ``gaps``, ``conflicts``,
        ``recommendation`` and ``reason``.
    """
    return _mm().analyze_subgraph(query_id)


@tool
def add_followup_query(parent_query_id: str, query_text: str, expansion_type: str, reason: str) -> str:
    """Add a follow-up query as a child of an existing query.

    Args:
        parent_query_id: The parent query node ID.
        query_text: The new query text.
        expansion_type: ``horizontal`` or ``vertical``.
        reason: Why this follow-up is needed.

    Returns:
        The new query node ID.
    """
    return _mm().add_followup_query(parent_query_id, query_text, expansion_type, reason)


@tool
def mark_query(query_id: str, status: str, sufficiency_score: Optional[float] = None) -> dict:
    """Update a query's status (and optional sufficiency score).

    Args:
        query_id: The query node ID.
        status: New status, e.g. ``sufficient``, ``blocked``, ``needs_vertical``.
        sufficiency_score: Optional score in [0, 1] to store on the node.

    Returns:
        The updated query node.
    """
    metrics = {} if sufficiency_score is None else {"sufficiency_score": sufficiency_score}
    return _mm().mark_query(query_id, status, **metrics)


@tool
def create_analysis(text: str, query_id: Optional[str] = None) -> str:
    """Record an intermediate analysis note in the graph for later reuse.

    Args:
        text: The analysis content (a staged conclusion, framework or trade-off).
        query_id: Optional query node this analysis resolves a gap for.

    Returns:
        The created analysis node ID.
    """
    from tools import graph_tools

    return graph_tools.create_analysis(text=text, query_id=query_id, cache_dir=_mm().cache_dir)


@tool
def get_subgraph(node_id: str, depth: int = 2) -> dict:
    """Read the sub-graph (nodes and edges) around a node.

    Args:
        node_id: The center node ID.
        depth: Traversal depth.

    Returns:
        dict with ``nodes`` and ``edges``.
    """
    from tools import graph_tools

    return graph_tools.get_subgraph(node_id, depth=depth, cache_dir=_mm().cache_dir)


@tool
def get_node(node_id: str) -> dict:
    """Read a single node by ID.

    Args:
        node_id: The node ID.

    Returns:
        The node dict, or an empty dict if not found.
    """
    from tools import graph_tools

    return graph_tools.get_node(node_id, cache_dir=_mm().cache_dir)


# -----------------------------
# Searcher tools
# -----------------------------
@tool
def get_query_context(query_id: str) -> dict:
    """Read existing context for a query to avoid duplicate searching.

    Args:
        query_id: The query node ID.

    Returns:
        dict with the ``query`` node and its ``existing_subgraph``.
    """
    return _mm().get_query_context(query_id)


@tool
def submit_search_result(query_id: str, evidence_package: dict) -> dict:
    """Write a structured evidence package into the Research Graph.

    The package may contain ``sources``, ``documents``, ``claims``,
    ``evidence`` and ``conflicts`` (each item may carry a ``local_ref`` used to
    cross-reference items within the package). The Graph Manager creates the
    nodes/edges and connects them to the query.

    Args:
        query_id: The query the evidence answers.
        evidence_package: The structured evidence package.

    Returns:
        dict with the created ``search_run_id``, a ``ref_map`` from local
        references to graph IDs, and written counts.
    """
    return _mm().submit_search_result(query_id, evidence_package)


# -----------------------------
# Reporter tools
# -----------------------------
@tool
def export_report_context(goal_id: Optional[str] = None) -> dict:
    """Export the graph context needed to write the report.

    Args:
        goal_id: The user-request (research goal) node ID. Optional — resolved
            automatically from the graph when omitted or unknown.

    Returns:
        dict with the goal node, full sub-graph, and nodes grouped by type
        (``queries``, ``evidence``, ``conflicts``, ``analysis``, ``sources``,
        ``report_sections``).
    """
    return _mm().export_report_context(goal_id)


@tool
def bind_report_section(
    title: str,
    content: str,
    evidence_ids: Optional[list] = None,
    claim_ids: Optional[list] = None,
    section_type: Optional[str] = None,
) -> str:
    """Create a report-section node and bind it to the evidence/claims it uses.

    Args:
        title: Section title.
        content: Section body text (with numbered citations).
        evidence_ids: Evidence node IDs the section cites.
        claim_ids: Claim/evidence node IDs the section cites.
        section_type: Optional section type, e.g. ``introduction``.

    Returns:
        The created report-section node ID.
    """
    section = {"title": title, "content": content, "section_type": section_type}
    return _mm().bind_report_section(section, claim_ids=claim_ids, evidence_ids=evidence_ids)


ORCHESTRATOR_TOOLS: list[Any] = [
    init_research,
    get_next_queries,
    analyze_subgraph,
    add_followup_query,
    mark_query,
    create_analysis,
    get_subgraph,
    get_node,
    export_report_context,
]

SEARCHER_TOOLS: list[Any] = [
    get_query_context,
    submit_search_result,
]

REPORTER_TOOLS: list[Any] = [
    export_report_context,
    get_subgraph,
    get_node,
    bind_report_section,
]
