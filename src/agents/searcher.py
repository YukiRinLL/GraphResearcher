"""Searcher agent: web search, evidence extraction, and structured JSON output."""

import json
import logging
from datetime import datetime
from pathlib import Path

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from tools.graph_tools import get_query_subgraph
from tools.search_tools import fetch_page_content, tavily_search

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "searcher.md"


def _load_searcher_prompt() -> str:
    if _PROMPT_PATH.exists():
        return _PROMPT_PATH.read_text(encoding="utf-8")
    return "You are a research search agent. Search the web and extract structured evidence."


def _build_tools(cache_dir: str | None) -> list:
    """Build search and context tools for the Searcher.

    Graph-writing is intentionally omitted: the Orchestrator writes evidence to the
    graph via MemoryManager after receiving the Searcher's structured JSON output.
    The Searcher prompt handles the no-graph-manager case by setting
    graph_manager_status.called = false.
    """

    @tool
    def web_search(query: str, topic: str = "general", max_results: int = 5) -> str:
        """Search the web for information.

        Args:
            query: The search query string.
            topic: Search category — 'general', 'news', or 'finance'.
            max_results: Maximum number of results to return (1-10).
        """
        try:
            results = tavily_search(
                query,
                max_results=max_results,
                topic=topic,  # type: ignore[arg-type]
                include_raw_content=True,
            )
            return json.dumps(results, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    @tool
    def fetch_url_content(url: str) -> str:
        """Fetch the full text content of a specific URL.

        Use this after web_search to read a high-value source in full.

        Args:
            url: The URL to fetch content from.
        """
        result = fetch_page_content(url)
        return json.dumps(result, ensure_ascii=False)

    @tool
    def view_query_context(query_id: str) -> str:
        """View the existing research graph context for a query to avoid duplicate work.

        Args:
            query_id: The query node ID to inspect.
        """
        result = get_query_subgraph(query_id=query_id, depth=2, cache_dir=cache_dir)
        return json.dumps(result, ensure_ascii=False)

    return [web_search, fetch_url_content, view_query_context]


class Searcher:
    """Searcher sub-agent driven by a ReAct loop.

    Receives a task specification from the Orchestrator, searches the web,
    extracts evidence, and returns a structured JSON result.

    The Orchestrator is responsible for writing the returned evidence_package
    to the Research Graph via MemoryManager.submit_search_result().
    """

    def __init__(self, config: dict):  # noqa: D107
        self.config = config
        cache_dir = config.get("cache_dir")

        llm = init_chat_model(
            config.get("model_name", "gpt-4o-mini"),
            temperature=config.get("temperature", 0.3),
            max_tokens=config.get("max_tokens", 8192),
            max_retries=config.get("max_retries", 3),
        )

        base_prompt = _load_searcher_prompt()
        now = datetime.now()
        system_prompt = (
            base_prompt
            .replace("<current_date>", now.strftime("%Y-%m-%d"))
            .replace("<current_time>", now.strftime("%H:%M:%S"))
        )

        self._agent = create_react_agent(
            model=llm,
            tools=_build_tools(cache_dir),
            prompt=SystemMessage(content=system_prompt),
        )

    async def run(self, task: dict) -> dict:
        """Execute a search task and return a structured evidence result.

        Args:
            task: Dict with task_id, query_text, acceptance_criteria, parent_context, etc.

        Returns:
            Structured dict with evidence_package, coverage, findings, gaps, etc.
            The caller (Orchestrator) writes evidence_package to the graph.
        """
        task_message = json.dumps(task, ensure_ascii=False, indent=2)
        logger.info(
            "Searcher starting task: %s — %s",
            task.get("task_id", "?"),
            task.get("query_text", "")[:60],
        )

        try:
            result = await self._agent.ainvoke(
                {"messages": [("user", task_message)]}
            )
        except Exception as exc:
            logger.error("Searcher agent invocation failed: %s", exc)
            return _error_result(task, str(exc))

        messages = result.get("messages", [])
        last_content = ""
        for msg in reversed(messages):
            if hasattr(msg, "content") and msg.content:
                last_content = msg.content
                break

        try:
            parsed = _parse_json(last_content)
            logger.info(
                "Searcher finished task %s: status=%s coverage=%.2f sources=%d",
                task.get("task_id", "?"),
                parsed.get("status", "?"),
                parsed.get("coverage", {}).get("coverage_score", 0),
                len(parsed.get("evidence_package", {}).get("sources", [])),
            )
            return parsed
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning(
                "Searcher output JSON parse failed (%s); returning partial result", exc
            )
            return {
                "status": "partial",
                "task_id": task.get("task_id"),
                "query_text": task.get("query_text", ""),
                "raw_output": last_content[:2000],
                "coverage": {"coverage_score": 0.3, "confidence_score": 0.2},
                "graph_manager_status": {"called": False},
                "evidence_package": {
                    "sources": [], "documents": [], "evidence": [], "conflicts": []
                },
                "findings": [last_content[:500]] if last_content else [],
                "remaining_gaps": ["Output was not valid JSON; manual review needed"],
                "suggested_followups": [],
            }


def _parse_json(content: str) -> dict:
    """Parse JSON from an agent response, stripping markdown fences."""
    content = content.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        content = "\n".join(ln for ln in lines if not ln.startswith("```")).strip()
    return json.loads(content)


def _error_result(task: dict, error: str) -> dict:
    """Return a minimal failed-status result dict."""
    return {
        "status": "failed",
        "task_id": task.get("task_id"),
        "query_text": task.get("query_text", ""),
        "error": error,
        "coverage": {"coverage_score": 0.0},
        "graph_manager_status": {"called": False},
        "evidence_package": {
            "sources": [], "documents": [], "evidence": [], "conflicts": []
        },
        "findings": [],
        "remaining_gaps": ["Search failed due to agent error"],
        "suggested_followups": [],
    }
