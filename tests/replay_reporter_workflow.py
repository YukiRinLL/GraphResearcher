"""Replay the real Reporter workflow against an exported run graph.

This is an explicit, API-consuming integration check rather than part of the
default offline test suite. It reads a prior ``research_graph.jsonl`` into an
in-memory graph adapter and writes fresh Reporter artifacts to a new directory.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import uuid
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

from dotenv import load_dotenv

repo_dir = Path(__file__).parent.parent
sys.path.insert(0, str(repo_dir / "src"))
load_dotenv(repo_dir / ".env")

import config  # noqa: E402
from agents.reporter_workflow import run_report_workflow  # noqa: E402
from observability import LangfuseRun, start_langfuse_run  # noqa: E402
from tools import graph_manager_tools, graph_tools  # noqa: E402


def _normalized_type(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").replace("_", "").lower()


class JsonlReplayGraph:
    """Minimal mutable graph adapter backed by one exported JSONL snapshot."""

    def __init__(self, path: Path):
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            if item.get("kind") == "node":
                self.nodes[str(item["id"])] = {
                    key: value for key, value in item.items() if key != "kind"
                }
            elif item.get("kind") == "edge":
                self.edges.append(
                    {key: value for key, value in item.items() if key != "kind"}
                )

        goals = self.search_nodes("user_request", {})
        if len(goals) != 1:
            raise ValueError(
                f"Replay requires exactly one UserRequest, found {len(goals)}"
            )
        goal = self.nodes[goals[0]["id"]]
        authorized_state = goal.get("reporting_from_state")
        if authorized_state not in {
            "REPORT_READY",
            "LIMITED_REPORT_READY",
            "BUDGET_EXHAUSTED",
        }:
            raise ValueError(
                "Completed replay graph does not retain an authorized reporting_from_state"
            )
        goal["research_state"] = authorized_state

    def get_node(self, node_id: str) -> dict[str, Any]:
        return dict(self.nodes.get(str(node_id), {}))

    def search_nodes(
        self, node_type: str, filters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        expected_type = _normalized_type(node_type)
        return [
            dict(node)
            for node in self.nodes.values()
            if _normalized_type(node.get("type")) == expected_type
            and all(node.get(key) == value for key, value in filters.items())
        ]

    def get_all_nodes(self) -> list[dict[str, Any]]:
        return [dict(node) for node in self.nodes.values()]

    def get_all_edges(self) -> list[dict[str, Any]]:
        return [dict(edge) for edge in self.edges]

    def get_node_edges(
        self, node_id: str, direction: str = "both"
    ) -> list[dict[str, Any]]:
        node_id = str(node_id)
        return [
            dict(edge)
            for edge in self.edges
            if (direction in {"out", "both"} and edge.get("source") == node_id)
            or (direction in {"in", "both"} and edge.get("target") == node_id)
        ]

    def get_query_children(self, node_id: str) -> list[str]:
        return [
            str(edge["target"])
            for edge in self.get_node_edges(node_id, direction="out")
            if _normalized_type(edge.get("type")) in {"hasquery", "parentof"}
        ]

    def upsert_node(
        self,
        node_type: str,
        attributes: dict[str, Any],
        dedupe_key: str | None = None,
    ) -> str:
        node_id = str(dedupe_key or uuid.uuid4().hex)
        existing = self.nodes.get(node_id, {"id": node_id, "type": str(node_type)})
        existing.update(attributes)
        self.nodes[node_id] = existing
        return node_id

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: str,
        attributes: dict[str, Any] | None = None,
    ) -> str:
        edge = {
            "source": str(source_id),
            "target": str(target_id),
            "type": getattr(edge_type, "value", edge_type),
            **(attributes or {}),
        }
        if edge not in self.edges:
            self.edges.append(edge)
        return f"{source_id}_{edge['type']}_{target_id}"

    def create_report_section(
        self, title: str, content: str, section_type: str | None = None
    ) -> str:
        node_id = f"replay_report_section_{uuid.uuid4().hex}"
        self.nodes[node_id] = {
            "id": node_id,
            "type": "ReportSection",
            "title": title,
            "content": content,
            "section_type": section_type,
        }
        return node_id

    def bind_evidence_to_section(
        self,
        section_id: str,
        evidence_ids: list[str],
        claim_ids: list[str] | None = None,
    ) -> None:
        for item_id in [*evidence_ids, *(claim_ids or [])]:
            self.add_edge(section_id, item_id, "USES")

    def write_jsonl(self, path: Path) -> None:
        lines = [json.dumps({"type": "_graphresearcher", "source": "reporter-replay"})]
        lines.extend(
            json.dumps({"kind": "node", **node}, ensure_ascii=False)
            for node in self.nodes.values()
        )
        lines.extend(
            json.dumps({"kind": "edge", **edge}, ensure_ascii=False)
            for edge in self.edges
        )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _patch_graph(graph: JsonlReplayGraph) -> ExitStack:
    stack = ExitStack()
    for name, replacement in {
        "get_node": graph.get_node,
        "search_nodes": graph.search_nodes,
        "get_all_nodes": graph.get_all_nodes,
        "get_all_edges": graph.get_all_edges,
        "get_node_edges": graph.get_node_edges,
        "get_query_children": graph.get_query_children,
        "upsert_node": graph.upsert_node,
        "add_edge": graph.add_edge,
        "create_report_section": graph.create_report_section,
        "bind_evidence_to_section": graph.bind_evidence_to_section,
    }.items():
        stack.enter_context(patch.object(graph_tools, name, replacement))
    return stack


def _reset_report_runtime(output_dir: Path, user_request: str) -> None:
    graph_manager_tools._cache_dir = str(output_dir)
    graph_manager_tools._user_request = user_request
    graph_manager_tools._manager = None
    graph_manager_tools._report_review_completed = False
    graph_manager_tools._report_review_had_issues = False
    graph_manager_tools._report_submit_count = 0
    graph_manager_tools._report_model_call_count = 0
    graph_manager_tools._compiled_report = ""
    graph_manager_tools._salvaged_report = ""
    graph_manager_tools._best_report = ""
    graph_manager_tools._last_report_attempt = {}


def run_replay(
    source_run: Path,
    output_dir: Path,
    *,
    enable_langfuse: bool = True,
) -> dict[str, Any]:
    """Run the public Reporter workflow against one exported graph snapshot."""
    graph_path = source_run / "research_graph.jsonl"
    input_path = source_run / "input.json"
    if not graph_path.is_file() or not input_path.is_file():
        raise FileNotFoundError(
            "Replay source must contain input.json and research_graph.jsonl"
        )

    graph = JsonlReplayGraph(graph_path)
    goal = graph.search_nodes("user_request", {})[0]
    user_request = str(goal.get("request") or "")
    output_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(input_path, output_dir / "input.json")
    _reset_report_runtime(output_dir, user_request)

    langfuse_run = (
        start_langfuse_run(
            output_dir=output_dir,
            max_search_rounds=0,
            model_name=config.DEFAULT_MODEL,
        )
        if enable_langfuse
        else LangfuseRun()
    )
    runnable_config = langfuse_run.langchain_config()
    if langfuse_run.enabled:
        runnable_config = {
            **runnable_config,
            "run_name": "graphresearcher.reporter-replay",
            "metadata": {
                **runnable_config.get("metadata", {}),
                "replay_source_run": source_run.name,
                "replay_mode": "reporter_only",
            },
        }
    manifest = {
        "source_run": str(source_run),
        "output_dir": str(output_dir),
        "model": config.DEFAULT_MODEL,
        "langfuse_enabled": langfuse_run.enabled,
        "langfuse_session_id": langfuse_run.session_id,
    }
    (output_dir / "replay_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    try:
        with _patch_graph(graph):
            result = run_report_workflow(runnable_config=runnable_config)
            report = graph_manager_tools.get_compiled_report()
            if not report:
                attempt = graph_manager_tools.get_last_report_attempt()
                report = str(
                    attempt.get("report") or attempt.get("salvaged_report") or ""
                )
    except BaseException as exc:
        failure = {
            "status": "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
            "success": False,
            "delivered": False,
            "validated": False,
            "error": f"{type(exc).__name__}: {exc}",
            **manifest,
            "reporter_model_calls": graph_manager_tools.get_reporter_model_call_count(),
            "report_submissions": graph_manager_tools.get_report_submit_count(),
        }
        graph.write_jsonl(output_dir / "research_graph.replay.jsonl")
        (output_dir / "replay_result.json").write_text(
            json.dumps(failure, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        raise
    finally:
        langfuse_run.flush()

    if report:
        (output_dir / "report.md").write_text(report, encoding="utf-8")
    if result.get("delivered") and report:
        replay_goal = graph.search_nodes("user_request", {})[0]
        graph.nodes[replay_goal["id"]]["research_state"] = "COMPLETED"
    graph.write_jsonl(output_dir / "research_graph.replay.jsonl")
    summary = {
        "status": "completed",
        **result,
        **manifest,
        "report_chars": len(report),
        "reporter_model_calls": graph_manager_tools.get_reporter_model_call_count(),
        "report_submissions": graph_manager_tools.get_report_submit_count(),
    }
    (output_dir / "replay_result.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_run", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--no-langfuse",
        action="store_true",
        help="Disable Langfuse even when credentials are configured.",
    )
    args = parser.parse_args()
    source_run = args.source_run.resolve()
    output_dir = args.output_dir
    if output_dir is None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_dir = (
            source_run.parent.parent / "reporter_replays" / f"{source_run.name}-{stamp}"
        )
    output_dir = output_dir.resolve()
    result = run_replay(
        source_run,
        output_dir,
        enable_langfuse=not args.no_langfuse,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))  # noqa: T201
    if not result.get("delivered"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
