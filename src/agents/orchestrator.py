"""Orchestrator: main research workflow controller implemented as a LangGraph StateGraph."""

import asyncio
import logging
from typing import Any, Literal

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from agents.memory_manager import MemoryManager
from agents.reporter import Reporter
from agents.searcher import Searcher

logger = logging.getLogger(__name__)


# ── State schema ───────────────────────────────────────────────────────────────


class ResearchState(TypedDict):  # noqa: D101
    user_request: str
    user_request_id: str
    research_goal: str
    language: str
    round: int
    max_rounds: int
    phase: str  # "init" | "research" | "report" | "done"
    selected_queries: list[dict]
    search_results: list[dict]
    analyses: list[dict]
    final_report: str


# ── Orchestrator class ─────────────────────────────────────────────────────────


class Orchestrator:
    """Graph-driven deep research orchestrator.

    Manages the full research lifecycle:
      Stage 1 — intent parsing and graph initialization
      Stage 2 — iterative search-analyze-expand loop
      Stage 3 — evidence-bound report generation

    Usage::

        orchestrator = Orchestrator(config)
        report = await orchestrator.run("What are the latest advances in LLM reasoning?")
    """

    def __init__(self, config: dict):  # noqa: D107
        self.config = config
        self.memory = MemoryManager(config)
        self.searcher = Searcher(config)
        self.reporter = Reporter(config)
        self._graph = self._build_graph()

    # ── Public API ─────────────────────────────────────────────────────────────

    async def run(self, user_request: str, max_rounds: int = 6) -> str:
        """Execute a full research workflow and return the final report as Markdown.

        Args:
            user_request: The user's research question or topic.
            max_rounds: Maximum number of search-analyze-expand iterations.

        Returns:
            Full research report as a Markdown string.
        """
        logger.info("Orchestrator starting research: '%s' (max_rounds=%d)", user_request, max_rounds)

        initial_state: ResearchState = {
            "user_request": user_request,
            "user_request_id": "",
            "research_goal": "",
            "language": "auto",
            "round": 0,
            "max_rounds": max_rounds,
            "phase": "init",
            "selected_queries": [],
            "search_results": [],
            "analyses": [],
            "final_report": "",
        }

        final_state = await self._graph.ainvoke(initial_state)
        return final_state.get("final_report", "No report generated.")

    # ── Graph construction ─────────────────────────────────────────────────────

    def _build_graph(self) -> Any:
        memory = self.memory
        searcher = self.searcher
        reporter = self.reporter

        # ── Node functions ─────────────────────────────────────────────────────

        async def init_node(state: ResearchState) -> dict:
            """Stage 1: Parse user request and initialize the Research Graph."""
            logger.info("[Orchestrator] Stage 1: Initializing research graph")
            result = await memory.init_research(state["user_request"])
            return {
                "user_request_id": result["user_request_id"],
                "research_goal": result["research_goal"],
                "language": result["language"],
                "phase": "research",
            }

        async def select_queries_node(state: ResearchState) -> dict:
            """Stage 2a: Select the next batch of pending queries."""
            queries = await memory.get_next_queries(limit=4)
            logger.info(
                "[Orchestrator] Round %d: selected %d queries", state["round"] + 1, len(queries)
            )
            return {"selected_queries": queries}

        async def run_searches_node(state: ResearchState) -> dict:
            """Stage 2b: Dispatch Searcher in parallel, then write evidence to graph."""
            queries = state.get("selected_queries", [])
            if not queries:
                return {"search_results": []}

            tasks = [searcher.run(_build_search_task(q, state)) for q in queries]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            valid_results: list[dict] = []
            for q, r in zip(queries, results):
                if isinstance(r, Exception):
                    logger.error("Search failed for query '%s': %s", q.get("text", "?"), r)
                    valid_results.append({
                        "status": "failed",
                        "task_id": q.get("id"),
                        "query_text": q.get("text", ""),
                        "error": str(r),
                        "evidence_package": {
                            "sources": [], "documents": [], "evidence": [], "conflicts": []
                        },
                        "suggested_followups": [],
                    })
                else:
                    result = r  # type: ignore[assignment]
                    # Always write evidence through MemoryManager — this is the authoritative
                    # write path regardless of whether the Searcher called graph tools directly.
                    ep = result.get("evidence_package", {})
                    has_evidence = any(ep.get(k) for k in ("sources", "documents", "evidence"))
                    if has_evidence:
                        written = await memory.submit_search_result(q["id"], ep)
                        logger.info(
                            "[Orchestrator] Query '%s': wrote %d nodes, %d edges",
                            q.get("text", "?")[:50],
                            written.get("nodes_written", 0),
                            written.get("edges_written", 0),
                        )
                    valid_results.append(result)

            return {"search_results": valid_results}

        async def analyze_node(state: ResearchState) -> dict:
            """Stage 2c: Evaluate evidence coverage for each searched query."""
            queries = state.get("selected_queries", [])
            analyses: list[dict] = []
            for q in queries:
                analysis = await memory.analyze_subgraph(q["id"])
                analyses.append({"query_id": q["id"], "query_text": q.get("text", ""), **analysis})
                logger.info(
                    "[Orchestrator] Query '%s' coverage=%.2f sufficient=%s",
                    q.get("text", "?")[:60],
                    analysis.get("coverage_score", 0),
                    analysis.get("sufficient", False),
                )
            return {"analyses": analyses}

        async def decide_node(state: ResearchState) -> dict:
            """Stage 2d: Update query statuses and decide whether to continue or finalize."""
            analyses = state.get("analyses", [])
            search_results_map = {
                r.get("task_id"): r for r in state.get("search_results", []) if r.get("task_id")
            }

            for analysis in analyses:
                query_id = analysis["query_id"]
                sufficient = analysis.get("sufficient", False)
                suggest_vertical = analysis.get("suggest_vertical", False)
                suggest_horizontal = analysis.get("suggest_horizontal", False)
                coverage_score = analysis.get("coverage_score", 0.0)

                if sufficient:
                    await memory.mark_query(query_id, "sufficient", coverage_score=coverage_score)
                elif suggest_vertical:
                    await memory.mark_query(query_id, "needs_vertical", coverage_score=coverage_score)
                    # Create high-priority vertical follow-up queries from Searcher suggestions
                    searcher_result = search_results_map.get(query_id, {})
                    for followup in searcher_result.get("suggested_followups", []):
                        if (
                            followup.get("priority") == "high"
                            and followup.get("type") == "vertical"
                        ):
                            child_id = await memory.add_followup_query(
                                parent_id=query_id,
                                text=followup["query_text"],
                                expansion_type="vertical",
                                reason=followup.get("reason", ""),
                            )
                            logger.info(
                                "[Orchestrator] Added vertical follow-up: '%s' (id=%s)",
                                followup["query_text"][:60],
                                child_id,
                            )
                elif suggest_horizontal:
                    await memory.mark_query(query_id, "sufficient", coverage_score=coverage_score)
                else:
                    # Low coverage but no clear expansion direction — mark blocked
                    await memory.mark_query(query_id, "blocked", coverage_score=coverage_score)

            new_round = state["round"] + 1
            remaining = await memory.get_next_queries(limit=1)

            if new_round >= state["max_rounds"] or not remaining:
                logger.info(
                    "[Orchestrator] Converging after %d rounds (remaining pending: %d)",
                    new_round,
                    len(remaining),
                )
                return {"round": new_round, "phase": "report", "selected_queries": []}
            else:
                return {"round": new_round, "phase": "research", "selected_queries": []}

        async def generate_report_node(state: ResearchState) -> dict:
            """Stage 3: Export graph context and generate the final report."""
            logger.info("[Orchestrator] Stage 3: Generating report")
            user_request_id = state.get("user_request_id", "")
            if not user_request_id:
                return {"final_report": "Error: research graph was not initialized.", "phase": "done"}

            context = await memory.export_report_context(user_request_id)
            report = await reporter.run(context)

            logger.info("[Orchestrator] Report generated (%d chars)", len(report))
            return {"final_report": report, "phase": "done"}

        # ── Conditional routing ────────────────────────────────────────────────

        def should_continue(state: ResearchState) -> Literal["select_queries", "generate_report"]:
            if state.get("phase") == "research":
                return "select_queries"
            return "generate_report"

        # ── Build graph ────────────────────────────────────────────────────────

        builder = StateGraph(ResearchState)

        builder.add_node("init", init_node)
        builder.add_node("select_queries", select_queries_node)
        builder.add_node("run_searches", run_searches_node)
        builder.add_node("analyze", analyze_node)
        builder.add_node("decide", decide_node)
        builder.add_node("generate_report", generate_report_node)

        builder.set_entry_point("init")
        builder.add_edge("init", "select_queries")
        builder.add_edge("select_queries", "run_searches")
        builder.add_edge("run_searches", "analyze")
        builder.add_edge("analyze", "decide")
        builder.add_conditional_edges(
            "decide",
            should_continue,
            {"select_queries": "select_queries", "generate_report": "generate_report"},
        )
        builder.add_edge("generate_report", END)

        return builder.compile()


# ── Helpers ────────────────────────────────────────────────────────────────────


def _build_search_task(query: dict, state: ResearchState) -> dict:
    """Build a task specification dict for the Searcher from a query node and current state."""
    return {
        "task_id": query["id"],
        "search_task_id": None,
        "query_text": query.get("text", ""),
        "task_description": query.get("text", ""),
        "parent_context": {
            "research_goal": state.get("research_goal", ""),
            "language": state.get("language", "auto"),
            "user_request": state.get("user_request", ""),
        },
        "sibling_context": [],
        "acceptance_criteria": [
            f"Find reliable, specific evidence addressing: {query.get('text', '')}",
            "Include at least 2 independent, high-quality sources",
            "Extract concrete facts, data points, or examples — not just summaries",
            "Record source metadata (title, URL, publication date, author)",
        ],
        "source_preferences": ["official", "academic", "news", "industry_report"],
        "time_window": "preferably last 2-3 years unless historical context is explicitly needed",
        "existing_graph_context": f"Research round {state.get('round', 0) + 1} of {state.get('max_rounds', 6)}",
        "max_search_rounds": state.get("config", {}).get("max_search_rounds", 4),
    }
