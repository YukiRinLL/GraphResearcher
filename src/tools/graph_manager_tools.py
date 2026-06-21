"""Graph Manager tools exposed to the agents.

Wraps the LLM-powered :class:`agents.memory_manager.MemoryManager` as
LangChain tools with clean, LLM-friendly signatures (no ``cache_dir`` / model
plumbing). Tools are grouped per agent: ``ORCHESTRATOR_TOOLS``,
``SEARCHER_TOOLS`` and ``REPORTER_TOOLS``.

The underlying ``MemoryManager`` is created lazily on first tool call so that
importing this module (for assembly checks) does not require API credentials.
"""

from typing import Any, Optional

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from memory.graph import NodeType

from agents.memory_manager import MemoryManager
from tools import workflow_state

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

    # Scope graph storage to this run so neo4j (a single shared DB) keeps each
    # run's nodes isolated instead of cross-matching against earlier runs.
    from tools import convergence, graph_tools

    graph_tools.set_context(output_dir)
    convergence.reset()


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
    result = _mm().init_research(user_request)
    workflow_state.set_goal_id(result.get("goal_id"))
    workflow_state.set_phase("research")
    return result


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
    result = _mm().get_next_queries(limit)
    workflow_state.open_research_round()
    return result


@tool
def analyze_subgraph(query_id: str) -> dict:
    """Score whether a query's collected evidence is sufficient.

    Args:
        query_id: The query node ID to evaluate.

    Returns:
        dict with ``sufficiency_score``, ``covered``, ``gaps``, ``conflicts``,
        ``recommendation`` and ``reason``.
    """
    result = _mm().analyze_subgraph(query_id)
    workflow_state.record_subgraph_analysis(query_id, result)
    return result


@tool
def analyze_coverage(parent_id: str) -> dict:
    """Check whether the parallel sub-dimensions under a parent are complete.

    Drives HORIZONTAL expansion, which is the exception (vertical is the
    default). Call this only reactively to confirm a genuine missing parallel
    dimension — not as a routine sweep, and not to re-slice already-covered
    content by region/application/comparison. Reads only the parent and its
    direct child queries — not their evidence.

    Args:
        parent_id: The parent node ID (research goal or a query).

    Returns:
        dict with ``covered_dimensions``, ``missing_dimensions``,
        ``recommendation`` (``complete``/``needs_horizontal``) and ``reason``.
    """
    return _mm().analyze_coverage(parent_id)


@tool
def assess_convergence(goal_id: Optional[str] = None) -> dict:
    """Judge whether the whole research effort has converged enough to report.

    A global stop/continue verdict across all queries: it weighs each query's
    status and sufficiency score, every conflict's type and resolution status,
    and the system-computed evidence novelty and source diversity. Call it
    before writing the report and whenever the loop looks ready to wrap up.

    Args:
        goal_id: The research-goal node ID; optional, the run-scoped graph is
            used regardless.

    Returns:
        dict with ``converged``, ``fatal_unresolved_conflicts``,
        ``core_threatening_gaps``, ``recommendation`` (``stop``/``continue``)
        and ``reason``.
    """
    result = _mm().assess_convergence(goal_id)
    workflow_state.record_convergence(result)
    return result


@tool
def expand_query(anchor_query_id: str, direction: str, reason: str = "", gaps: Optional[list] = None) -> dict:
    """Author and attach self-contained follow-up query node(s); return them.

    The Query Planner writes the query text — you only choose the anchor,
    direction, reason, and the gaps/missing dimensions to cover. You never write
    query text yourself.

    Args:
        anchor_query_id: The query to expand from.
        direction: ``vertical`` (deepen the anchor — a child under it) or
            ``horizontal`` (add missing parallel dimension(s) under the anchor's
            parent; works at goal level too).
        reason: Why this expansion is needed.
        gaps: Gaps (vertical, from ``analyze_subgraph``) or missing dimensions
            (horizontal, from ``analyze_coverage``) to cover.

    Returns:
        dict with ``attach_point``, ``edge_type``, ``direction`` and ``created``
        (each ``{id, text}``).
    """
    if direction == "horizontal":
        max_new = min(max(len(gaps or []), 1), 3)
    else:
        max_new = 1
    return _mm().expand_query(anchor_query_id, direction, reason=reason, gaps=gaps, max_new=max_new)


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
    result = _mm().mark_query(query_id, status, **metrics)
    workflow_state.consume_mark_query(query_id, status, sufficiency_score)
    return result


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

    return graph_tools.create_analysis(text=text, query_id=query_id)


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

    return graph_tools.get_subgraph(node_id, depth=depth)


@tool
def get_node(node_id: str) -> dict:
    """Read a single node by ID.

    Args:
        node_id: The node ID.

    Returns:
        The node dict, or an empty dict if not found.
    """
    from tools import graph_tools

    return graph_tools.get_node(node_id)


# -----------------------------
# Searcher tools
# -----------------------------
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


@tool
def dispatch_searcher(query_id: str, description: str) -> dict:
    """Dispatch the Searcher to collect evidence for a single query.

    This is the **only** way to send work to the Searcher. ``query_id`` is a
    required, typed parameter — it is never guessed or parsed from free text,
    so the evidence is always correctly linked to its query node.

    Args:
        query_id: The exact query node ID (from ``init_research`` or
            ``expand_query`` return values). Must exist in the graph.
        description: What to search for, acceptance criteria, time window,
            source preferences, and output format expected.

    Returns:
        A compact structured dict containing the query ID, whether evidence was
        really written into the graph, write counts, and a short summary.
    """
    from tools import graph_tools

    # Validate the query node exists before invoking the searcher.
    node = graph_tools.get_node(query_id)
    if not node or node.get("type") != NodeType.QUERY.value:
        result = {
            "query_id": query_id,
            "ok": False,
            "error": (
                f"dispatch_searcher 失败：query_id {query_id!r} 不存在或不是 query 节点。"
                "请使用 init_research / expand_query 返回的精确 query 节点 ID。"
            ),
            "search_run_id": None,
            "written": {},
            "summary": "",
        }
        workflow_state.record_search_result(query_id, result)
        return result

    query_text = node.get("text") or ""
    workflow_state.record_search_dispatch(query_id)

    # Lazy import — searcher imports from this module, so import at call time
    # to avoid a circular dependency.
    from agents.searcher import searcher as searcher_graph

    search_state = searcher_graph.invoke({
        "messages": [HumanMessage(content=description)],
        "query_id": query_id,
        "query_text": query_text,
    })

    submit_result = search_state.get("submit_result") if isinstance(search_state, dict) else None
    written = submit_result.get("written", {}) if isinstance(submit_result, dict) else {}
    search_run_id = submit_result.get("search_run_id") if isinstance(submit_result, dict) else None
    ok = bool(search_run_id) and any((written or {}).values())

    # Extract the last AIMessage as the human-readable summary.
    summary = ""
    for msg in reversed(search_state.get("messages", [])):
        if hasattr(msg, "content") and msg.content and getattr(msg, "tool_calls", None) is None:
            content = msg.content
            if isinstance(content, list):
                content = "".join(
                    p.get("text", "") if isinstance(p, dict) else str(p) for p in content
                )
            summary = str(content)
            break

    result = {
        "query_id": query_id,
        "ok": ok,
        "search_run_id": search_run_id,
        "written": written,
        "summary": (summary or "Searcher 已完成但未返回文本结果。")[:2000],
    }
    workflow_state.record_search_result(query_id, result)
    return result


ORCHESTRATOR_TOOLS: list[Any] = [
    init_research,
    get_next_queries,
    analyze_subgraph,
    analyze_coverage,
    assess_convergence,
    expand_query,
    mark_query,
    create_analysis,
    get_subgraph,
    get_node,
    dispatch_searcher,
    export_report_context,
]

SEARCHER_TOOLS: list[Any] = [
    submit_search_result,
]

REPORTER_TOOLS: list[Any] = [
    export_report_context,
    get_subgraph,
    get_node,
    bind_report_section,
]
