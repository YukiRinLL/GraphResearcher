"""离线比较章节原文预算，并复现历史章节材料统计。

模型响应与章节保存使用确定性替身，快照在临时目录构造，原始运行只读。
运行方式：uv run python tests/eval_report_source_context.py --output-dir outputs/source_context_eval。
历史目录缺失会写入结果；--fixtures-only 可在没有本地运行产物时执行构造案例。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import config  # noqa: E402
from agents import reporter_workflow as workflow  # noqa: E402
from memory import source_snapshots as snapshots  # noqa: E402
from tools import report_source_context as sources  # noqa: E402

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "report_source_context"
BUDGET_DEFAULTS = (1000, 2000, 4000)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def text_of(node):
    return str(node.get("statement") or node.get("claim") or node.get("text") or "").strip()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize_history(chapters):
    """按章节分别统计 Evidence 数及全部候选正文的 token，不混用分母."""
    if not chapters:
        return {"chapters": 0}
    return {
        "chapters": len(chapters),
        "evidence_count_median": statistics.median(row["evidence_count"] for row in chapters),
        "evidence_count_max": max(row["evidence_count"] for row in chapters),
        "chapters_with_100_evidence": sum(row["evidence_count"] >= 100 for row in chapters),
        "candidate_text_tokens_median": statistics.median(row["candidate_text_tokens"] for row in chapters),
        "candidate_text_tokens_max": max(row["candidate_text_tokens"] for row in chapters),
    }


def read_history(run_paths, encoding):
    """读取明确指定的运行，保存每个章节的原始引用映射与输入文件哈希."""
    runs, chapters, cases = [], [], []
    for run_path in run_paths:
        path = Path(run_path)
        label = path.relative_to(REPO_ROOT).as_posix() if path.is_relative_to(REPO_ROOT) else path.as_posix()
        graph_path, outline_path = path / "research_graph.jsonl", path / ".report_outline.json"
        meta_paths = sorted((path / ".report_chapters").glob("*.meta.json"))
        if not graph_path.is_file() or not outline_path.is_file() or not meta_paths:
            runs.append({"path": label, "status": "missing_inputs"})
            continue
        records = [json.loads(line) for line in graph_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        nodes = {item["id"]: item for item in records if item.get("kind") == "node"}
        edges = [item for item in records if item.get("kind") == "edge"]
        outline = read_json(outline_path)
        by_id = {chapter["chapter_id"]: chapter for chapter in outline["chapters"]}
        goal = next((node for node in nodes.values() if node.get("type") == "UserRequest"), {})
        runs.append({
            "path": label, "status": "loaded", "chapter_count": len(meta_paths),
            "files_sha256": {p.relative_to(path).as_posix(): digest(p) for p in [graph_path, outline_path, *meta_paths]},
            "snapshot_index_count": len(list((path / "source_snapshots/snapshots").glob("*/index-v1.json"))),
        })
        for meta_path in meta_paths:
            meta = read_json(meta_path)
            chapter = by_id[meta["chapter_id"]]
            ref_map = meta["evidence_ref_map"]
            candidates = [(ref, nodes[node_id]) for ref, node_id in ref_map.items() if node_id in nodes]
            evidence = [node for _, node in candidates if node.get("type") == "Evidence"]
            repeated = Counter(text_of(node) for node in evidence)
            row = {
                "run": label, "chapter_id": chapter["chapter_id"], "title": chapter["title"],
                "candidate_count": len(candidates), "evidence_count": len(evidence),
                "claim_count": sum(node.get("type") == "Claim" for _, node in candidates),
                "unique_evidence_texts": len(repeated), "max_text_multiplicity": max(repeated.values(), default=0),
                "candidate_text_tokens": sum(len(encoding.encode(text_of(node), disallowed_special=())) for _, node in candidates),
                "missing_node_ids": [node_id for node_id in ref_map.values() if node_id not in nodes],
                "candidate_ids": sorted(ref_map.values()),
            }
            chapters.append(row)
            # 保留候选正文、现有关系及章节规划，引用编号为合成 fixture 分配。
            # 该视图没有宣称还原历史 prompt，也没有把摘要充当历史原文。
            id_to_ref = {node_id: ref for ref, node_id in ref_map.items()}
            stances = {"SUPPORTED_BY": "supports", "QUALIFIED_BY": "qualifies", "CONTRADICTED_BY": "contradicts"}
            items = [{
                "ref": ref, "type": node["type"], "text": text_of(node),
                "confidence": node.get("confidence"), "qualifiers": node.get("qualifiers") or [],
                "limitations": node.get("limitations") or [], "source_numbers": [1] if node["type"] == "Evidence" else [],
                "evidence_relations": [
                    {"target_ref": id_to_ref[edge["source"]], "stance": stances[edge["type"]]}
                    for edge in edges if edge.get("target") == node["id"] and edge.get("source") in id_to_ref
                    and nodes.get(edge["source"], {}).get("type") == "Evidence" and edge.get("type") in stances
                ],
                "claim_relations": [
                    {"target_ref": id_to_ref[edge["target"]], "stance": stances[edge["type"]]}
                    for edge in edges if edge.get("source") == node["id"] and edge.get("target") in id_to_ref
                    and nodes.get(edge["target"], {}).get("type") == "Claim" and edge.get("type") in stances
                ],
            } for ref, node in candidates]
            cases.append({
                "name": f"history-{len(chapters):02d}", "origin": "archived_material_constructed_context",
                "history": {"run": label, "chapter_id": chapter["chapter_id"], "candidate_text_tokens": row["candidate_text_tokens"]},
                "bundle": bundle_for(chapter, items), "outline": outline,
                "request": goal.get("request") or "按章节目标撰写报告。", "language": goal.get("language") or "English",
                "sources": [], "steps": ["read", "final"], "read_ref": next((item["ref"] for item in items if item["type"] == "Evidence"), "e1"),
            })
    # 选取候选正文 token 最少、中位和最多的章节，保持取样可复现。
    ordered = sorted(cases, key=lambda case: (case["history"]["candidate_text_tokens"], case["name"]))
    selected = [ordered[index] for index in sorted({0, len(ordered) // 2, len(ordered) - 1})] if ordered else []
    for case in selected:
        evidence = [item for item in case["bundle"]["evidence_items"] if item["type"] == "Evidence"]
        for i, item in enumerate(evidence[:3]):
            case["sources"].append({
                "name": f"archived-{i}", "body": item["text"] + "\n\n" + "这是离线构造的上下文，只用于测试阅读预算，不能作为原始来源或新增事实。" * 25,
                "refs": [item["ref"]], "direct": [0], "goal_indices": [],
            })
    return {"runs": runs, "chapters": chapters, "summary": summarize_history(chapters)}, selected


def bundle_for(chapter, items):
    return {
        "status": "ok", "chapter_id": chapter["chapter_id"], "bundle_token": "offline-fixture",
        "chapter_title": chapter["title"], "chapter_goals": chapter["goals"],
        "section_plan": chapter.get("section_plan") or "解释各项实验条件。",
        "section_type": chapter.get("section_type") or "body", "evidence_items": items,
        "disclosed_conflicts": [],
    }


def fixture_cases():
    """预先标注块与目标的对应关系，覆盖率不根据词法排序反推."""
    def case(name, goals, documents, steps=None, **extra):
        items = [{"ref": ref, "type": "Evidence", "text": f"构造材料 {ref}。", "source_numbers": [i + 1]}
                 for i, document in enumerate(documents) for ref in document["refs"]]
        return {
            "name": name, "origin": "constructed", "bundle": bundle_for({"chapter_id": 1, "title": "实验条件", "goals": goals}, items),
            "outline": {}, "request": "说明不同实验条件与测量范围。", "language": "简体中文",
            "sources": documents, "steps": steps or ["final"], "read_ref": "e1", **extra,
        }

    temperature = "温度控制在固定区间，测量前需等待仪器稳定，并记录样品温度和校准时间。" * 35
    pressure = "压力测量使用同一量程，实验记录包含初始压力、环境变化和传感器校准条件。" * 35
    humidity = "湿度实验需记录样品平衡时间、环境湿度、重复测量次数以及异常值处理方式。" * 35
    table = "# 仪器与条件\n\n| 项目 | 数值 | 条件 |\n|---|---|---|\n" + "".join(f"| 样品 {i} | {i + 20} | 恒温 |\n" for i in range(35)) + "\n[^1]: 数据是构造示例，使用同一校准范围。\n\n表格之后的补充说明。"
    docs = [
        {"name": "temperature", "body": temperature, "refs": ["e1"], "direct": [0], "goal_indices": [0]},
        {"name": "pressure", "body": pressure, "refs": ["e2"], "direct": [0], "goal_indices": [1]},
        {"name": "humidity", "body": humidity, "refs": ["e3"], "direct": [0], "goal_indices": [2]},
    ]
    duplicate = deepcopy(docs[:2])
    duplicate[0]["refs"] = ["e1", *[f"e{i}" for i in range(4, 12)]]
    return [
        case("two_goals", ["温度", "压力"], deepcopy(docs[:2])),
        case("duplicate_evidence", ["温度", "压力"], duplicate),
        case("three_goals", ["温度", "压力", "湿度"], deepcopy(docs)),
        case("table_dependency", ["样品与恒温测量条件"], [{"name": "table", "body": table, "refs": ["e1"], "direct": [1], "goal_indices": [0]}], ["read", "final"], read_positions=[0]),
        case("replacement", ["温度", "压力"], deepcopy(docs[:2]), ["read", "final"], read_ref="e2"),
        case("missing_snapshot", ["温度"], deepcopy(docs[:1]), ["read", "final"], missing_snapshot=True),
        case("retry_readback", ["温度"], deepcopy(docs[:1]), ["invalid", "read", "timeout", "final"]),
        case("base_overflow", ["温度"], deepcopy(docs[:1]), oversized_base=True),
    ]


def materialize(case, root):
    """只在临时目录生成带固定身份的合成快照与捕获记录."""
    bundle = deepcopy(case["bundle"])
    bundle["_snapshot_binding"] = {"root": str(root), "context": "offline-evaluation", "replay": False}
    refs_by_item, goal_blocks, labels = {}, {}, {}
    for i, source in enumerate(case["sources"], start=1):
        url = f"https://fixture.invalid/{case['name']}/{source['name']}"
        index = snapshots.save_snapshot(root, url, source["body"])
        capture_id = "cap_" + hashlib.sha256(url.encode()).hexdigest()[:32]
        reference = {"snapshot_id": index["snapshot_id"], "chunker_version": "v1", "capture_id": capture_id}
        capture_path = root / "captures" / f"{capture_id}.json"
        capture_path.parent.mkdir(parents=True, exist_ok=True)
        capture_path.write_text(json.dumps({"schema_version": 1, "status": "stored", "context": "offline-evaluation", "url": url, **reference}), encoding="utf-8")
        block_refs = [block["block_id"] for block in index["blocks"]]
        direct = [block_refs[position] for position in source["direct"]]
        for position, block_ref in enumerate(block_refs):
            labels[block_ref] = f"{source['name']}:b{position + 1}"
        for goal in source["goal_indices"]:
            goal_blocks.setdefault(goal, set()).update(direct)
        for item in bundle["evidence_items"]:
            if item["ref"] in source["refs"]:
                refs_by_item[item["ref"]] = block_refs
                item["_source_location"] = {
                    **reference, "url": url, "title": f"构造来源 {source['name']}", "citation": f"[{i}]",
                    "block_refs": direct, "location_status": "valid",
                }
                item["source_numbers"] = [i]
        if case.get("missing_snapshot"):
            (root / "snapshots" / index["snapshot_id"] / "body.txt").unlink()
    if case.get("oversized_base"):
        bundle["evidence_items"][0]["text"] = "用于验证基础输入超限的构造材料。" * 4000
    return bundle, refs_by_item, goal_blocks, labels


def measure_views(audit, goal_blocks, labels):
    rows = []
    for view in audit.get("views", []):
        loaded = [block["block_ref"] for block in view["view"]["context_blocks"]]
        selected = set(loaded)
        rows.append({
            "input_tokens": view["input_tokens"], "base_tokens": view["base_tokens"],
            "source_tokens": view["source_tokens"], "input_limit": view["input_limit"], "source_limit": view["source_limit"],
            "selected_blocks": [labels[ref] for ref in loaded],
            "covered_goals": [goal for goal, refs in goal_blocks.items() if refs & selected],
            "annotated_goals": len(goal_blocks),
            "selection_results": dict(Counter(item["status"] for item in view["selection"])),
            "read_results": dict(Counter(result["status"] for request in view["view"]["read_results"] for result in request["results"])),
            "unique_blocks": len(loaded) == len(selected),
            "within_budget": view["input_tokens"] <= view["input_limit"] and view["source_tokens"] <= view["source_limit"],
        })
    return rows


def evaluate_case(case, budget, output_dir):
    """执行真实章节状态机，用脚本指定响应，不测量 LLM 阅读决策或正文质量."""
    case_output = output_dir / case["name"] / str(budget)
    with TemporaryDirectory(prefix="source-context-fixture-") as temp_dir:
        bundle, refs, goal_blocks, labels = materialize(case, Path(temp_dir))
        bundle["_source_audit_dir"] = str(case_output)
        steps = iter(case["steps"])
        count = sources.SourceContext({"evidence_items": []}).count
        base_prompt_tokens = count(workflow._chapter_prompt(
            case["request"], case["outline"], bundle, language=case["language"],
        ))
        actual_prompts = []
        committed = []

        def invoke(prompt, *, phase):
            actual_prompts.append(prompt)
            step = next(steps)
            if step == "invalid":
                raise ValueError("fixture invalid JSON")
            if step == "timeout":
                raise TimeoutError("fixture provider timeout")
            if step == "read":
                return {"read_requests": [{
                    "evidence_ref": case["read_ref"], "purpose": "核对构造材料的测量条件。",
                    "block_refs": [refs[case["read_ref"]][position] for position in case.get("read_positions", [])],
                }]}
            return {"chapters": [{
                "chapter_id": bundle["chapter_id"], "content": "离线响应替身。[1]",
                "evidence_refs": [case["read_ref"]], "disclosed_conflict_refs": [],
            }]}

        def commit(*, chapters):
            committed.extend(chapters)
            return {"status": "ok", "chapters": [{"chapter_id": bundle["chapter_id"], "candidate_saved": True}]}

        with patch.object(config, "REPORTER_SOURCE_TOKENS", budget), patch.object(workflow, "_invoke_reporter_json", invoke), patch.object(workflow.graph_manager_tools, "commit_report_chapter_batch", commit):
            result = workflow.draft_chapter_node({
                "chapter_bundle": bundle, "outline": case["outline"],
                "report_context": {"user_request": case["request"], "language": case["language"]},
            })["chapter_results"][0]
        audit_path = case_output / "report_source_context" / f"chapter-{bundle['chapter_id']}" / "audit.json"
        audit = read_json(audit_path)
        views = measure_views(audit, goal_blocks, labels)
        prompt_counts = [count(prompt) for prompt in actual_prompts]
        expected_base_failure = base_prompt_tokens > config.REPORTER_CONTEXT_TOKENS - config.REPORTER_OUTPUT_TOKENS - config.REPORTER_SAFETY_TOKENS
        checks = {
            "expected_completion": result["success"] == (not expected_base_failure),
            "expected_error": result["error"] == ("base_prompt_over_budget" if expected_base_failure else ""),
            "expected_readback": audit["readback_used"] == ("read" in case["steps"] and not expected_base_failure),
            "expected_failures": audit["failed_attempts"] == (0 if expected_base_failure else sum(step in {"invalid", "timeout"} for step in case["steps"])),
            "token_counts_match_prompts": prompt_counts == [view["input_tokens"] for view in views],
            "within_budget": all(view["within_budget"] for view in views),
            "deduplicated": all(view["unique_blocks"] for view in views),
            "bounded_calls": audit["model_invocations"] <= 4 and audit["failed_attempts"] <= 3,
            "expected_calls": audit["model_invocations"] == (
                0 if expected_base_failure else len(case["steps"])
            ),
            "binding_preserved": all(chapter["bundle_token"] == bundle["bundle_token"] for chapter in committed),
        }
        # 原始 prompt 与审计都保留在评估输出目录，正文不进入版本控制。
        (case_output / "prompts.json").write_text(json.dumps(actual_prompts, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "case": case["name"], "origin": case["origin"], "history": case.get("history"),
            "source_budget": budget, "base_prompt_tokens": base_prompt_tokens,
            "chapter_result": result, "checks": checks,
            "model_invocations": audit["model_invocations"], "failed_attempts": audit["failed_attempts"],
            "readback_used": audit["readback_used"], "views": views,
            "audit": audit_path.relative_to(output_dir).as_posix(),
        }


def run_evaluation(output_dir, *, run_paths=(), budgets=BUDGET_DEFAULTS):
    """固定评估配置并恢复调用方状态，输出目录须为新目录."""
    output_dir = Path(output_dir).resolve()
    run_paths = [Path(path).resolve() for path in run_paths]
    if any(output_dir == run or run in output_dir.parents or output_dir in run.parents for run in run_paths):
        raise ValueError("output-dir must be separate from all source runs")
    output_dir.mkdir(parents=True, exist_ok=False)
    with ExitStack() as stack:
        for name, value in {
            "REPORTER_TOKENIZER": "o200k_base", "DEFAULT_MODEL": "gpt-5.1",
            "REPORTER_CONTEXT_TOKENS": 32768, "REPORTER_OUTPUT_TOKENS": 8192,
            "REPORTER_SAFETY_TOKENS": 1024,
        }.items():
            stack.enter_context(patch.object(config, name, value))
        # 固定模板时间，以便逐字重建 prompt 和比较 token。
        template = (REPO_ROOT / "src/prompts/reporter.md").read_text(encoding="utf-8")
        template = template.replace("<current_date>", "2026-09-08").replace("<current_time>", "00:00:00")
        stack.enter_context(patch.object(config, "reporter_system_prompt", template))
        context = sources.SourceContext({"evidence_items": []})
        history, archived_cases = read_history(run_paths, context.encoding)
        cases = fixture_cases() + archived_cases
        results = [evaluate_case(case, budget, output_dir) for case in cases for budget in budgets]
        summary = {
            "schema_version": 1, "evaluation": "offline_scripted_responses",
            "tokenizer": context.encoding.name, "context_tokens": 32768, "output_tokens": 8192, "safety_tokens": 1024,
            "budgets": list(budgets),
            "implementation_sha256": {p: digest(REPO_ROOT / p) for p in [
                "tests/eval_report_source_context.py", "src/agents/reporter_workflow.py",
                "src/tools/report_source_context.py", "src/memory/source_snapshots.py",
            ]},
            "prompt_template_sha256": hashlib.sha256(template.encode()).hexdigest(),
            "history": history, "cases": results,
            "checks_passed": all(all(result["checks"].values()) for result in results),
            "limitations": ["构造正文不是真实来源快照。", "响应替身不测量真实回读率、自动选择命中率或报告质量。", "历史 candidate_text_tokens 仅统计正文，不是历史 API 输入。"],
        }
        (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        (output_dir / "summary.md").write_text(render_summary(summary), encoding="utf-8")
        return summary


def render_summary(summary):
    lines = ["# 原文上下文离线评估", "", "本次只运行构造快照与确定性响应替身，覆盖率来自 fixture 标注。", "",
             "| 案例 | 原文预算 | 每次输入 tokens | 每次覆盖目标数 | 每次选中块数 | 调用／失败 | 结果 |",
             "| --- | ---: | --- | --- | --- | --- | --- |"]
    for result in summary["cases"]:
        views = result["views"]
        lines.append("| " + " | ".join([
            result["case"], str(result["source_budget"]), "/".join(str(view["input_tokens"]) for view in views) or "—",
            "/".join(f"{len(view['covered_goals'])}/{view['annotated_goals']}" if view["annotated_goals"] else "未标注" for view in views) or "—",
            "/".join(str(len(view["selected_blocks"])) for view in views) or "0",
            f"{result['model_invocations']}/{result['failed_attempts']}", result["chapter_result"]["error"] or "已保存替身章节",
        ]) + " |")
    lines.extend(["", "## 历史材料规模", "", "```json", json.dumps(summary["history"]["summary"], ensure_ascii=False, indent=2), "```", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--history-manifest", type=Path, default=FIXTURE_DIR / "history_runs.json")
    parser.add_argument("--fixtures-only", action="store_true")
    parser.add_argument("--budgets", type=int, nargs="+", default=list(BUDGET_DEFAULTS))
    args = parser.parse_args()
    if any(budget <= 0 for budget in args.budgets) or len(set(args.budgets)) != len(args.budgets):
        parser.error("budgets must be distinct positive integers")
    run_paths = [] if args.fixtures_only else [(REPO_ROOT / path).resolve() for path in read_json(args.history_manifest)]
    output_dir = args.output_dir.resolve()
    if any(output_dir == run or run in output_dir.parents or output_dir in run.parents for run in run_paths):
        parser.error("output-dir must be separate from all source runs")
    result = run_evaluation(output_dir, run_paths=run_paths, budgets=args.budgets)
    sys.stdout.write(json.dumps({"output_dir": str(output_dir), "cases": len(result["cases"]), "checks_passed": result["checks_passed"]}, ensure_ascii=False) + "\n")
    return 0 if result["checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
