"""快照存储与截断前捕获的离线回归，不访问数据库、Tavily 或模型。

运行方式：``uv run python tests/test_source_snapshots.py``。
"""

import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agents import searcher  # noqa: E402
from memory import source_snapshots as snapshots  # noqa: E402
from tools import graph_manager_tools, graph_tools, search_tools  # noqa: E402


class FakeTavily:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def search(self, query, **kwargs):
        self.calls.append({"query": query, **kwargs})
        return deepcopy(next(self.responses))


def capture(body="原文。", url="https://example.com/article", **kwargs):
    return snapshots.capture_source(
        {"raw_content": body, "url": url, "content": "搜索摘要", "title": "来源标题"},
        query=kwargs.get("query", "research query"),
        stage="single",
        search_parameters={"topic": "general"},
        response={"request_id": "request-1"},
        result_index=0,
        raw_content_limit=20_000,
    )


def records(root):
    return [json.loads(path.read_bytes()) for path in (root / "captures").glob("*.json")]


def assert_raises(exception, function, *args):
    try:
        function(*args)
    except exception:
        return
    raise AssertionError(f"Expected {exception.__name__}")


def test_roundtrip_and_structural_offsets():
    paragraph = "原始中文、emoji 🧪 与 English sentence. " * 900
    table = "| 指标 | 数值 |\r\n| --- | --- |\r\n" + "| 温度 | 20 °C |\r\n" * 250
    table += "\r\n[^unit]: 单位和条件保持原样。\r\n    脚注续行。\r\n"
    code = "```python\r\n# 这不是标题\r\n\r\nvalue = '原始值'\r\n```\r\n"
    body = "# 标题\r\n重复段落。\r\n\r\n重复段落。\r\n\r\n## 数据\r\n" + table
    body += "\r\n" + code + "\r\n- 项目一\r\n- 项目二\r\n\r\n" + paragraph + "\r\n"
    with TemporaryDirectory() as directory:
        root = Path(directory)
        index = snapshots.save_snapshot(root, "https://example.com/article", body)
        restored, loaded_index = snapshots.read_snapshot(root, index["snapshot_id"])
        assert restored == body and loaded_index == index
        assert index["body_sha256"] == hashlib.sha256(body.encode("utf-8")).hexdigest()
        assert (root / "snapshots" / index["snapshot_id"] / "body.txt").read_bytes() == body.encode("utf-8")
        texts = [body[block["start_char"]:block["end_char"]] for block in index["blocks"]]
        repeats = [block for block, text in zip(index["blocks"], texts) if text.strip() == "重复段落。"]
        assert len(repeats) == 2 and repeats[0]["block_id"] != repeats[1]["block_id"]
        assert table in texts and code in texts
        assert {block["kind"] for block in index["blocks"]} == {"heading", "paragraph", "table", "code", "list"}
        previous = 0
        seen = set()
        for block, text in zip(index["blocks"], texts):
            assert not body[previous:block["start_char"]].strip()
            assert text.strip() and 0 <= block["start_char"] < block["end_char"] <= len(body)
            assert set(block["dependency_refs"]).issubset(seen)
            seen.add(block["block_id"])
            previous = block["end_char"]
        assert not body[previous:].strip()
        table_block = next(block for block in index["blocks"] if block["kind"] == "table")
        assert len(table_block["dependency_refs"]) == 2
        assert len([block for block in index["blocks"] if block["kind"] == "paragraph"]) > 3


def test_snapshot_identity_and_observations():
    with TemporaryDirectory() as directory:
        root = Path(directory) / "source_snapshots"
        snapshots.configure(directory, "run-a")
        with snapshots.search_capture_scope("q1", "sr1"):
            first = capture(url="HTTPS://Example.COM/article/?utm_source=one#anchor")
        with snapshots.search_capture_scope("q2", "sr2"):
            second = capture(query="another query")
        assert first["snapshot_id"] == second["snapshot_id"]
        assert first["capture_id"] != second["capture_id"]
        changed = capture(body="更新的原文。")
        mirrored = capture(url="https://other.example/article")
        assert len({first["snapshot_id"], changed["snapshot_id"], mirrored["snapshot_id"]}) == 3
        observations = {row["query_id"]: row for row in records(root) if row["query_id"]}
        assert observations["q1"]["search_run_id"] == "sr1"
        assert observations["q2"]["search_run_id"] == "sr2"
        assert observations["q2"]["query"] == "another query"
        assert observations["q1"]["url"].startswith("HTTPS:")
        assert observations["q1"]["content"] == "搜索摘要"
        assert observations["q1"]["requested_depth"] == "provider_default"
        assert observations["q1"]["provider_completeness"] == "unknown"
        assert len(list((root / "snapshots").glob("*/body.txt"))) == 3


def test_unbreakable_units_remain_whole():
    body = "原" * 21_000 + "\n\n```text\n未闭合代码块\n\n# 围栏内的标题\n"
    index = snapshots.build_snapshot_index("source", body)
    assert [block["kind"] for block in index["blocks"]] == ["paragraph", "code"]
    first, second = index["blocks"]
    assert body[first["start_char"]:first["end_char"]] == "原" * 21_000 + "\n"
    assert body[second["start_char"]:second["end_char"]].startswith("```text\n")
    assert second["end_char"] == len(body)


def test_index_is_the_publication_boundary():
    body_ready = Event()
    publish_index = Event()
    publish = snapshots._publish_file
    body = "原始正文。\r\n" * 4_000
    identity = snapshots.build_snapshot_index("source", body)["snapshot_id"]

    def delayed_publish(path, data):
        if path.name == "index-v1.json":
            body_ready.set()
            assert publish_index.wait(timeout=5)
        return publish(path, data)

    with TemporaryDirectory() as directory:
        root = Path(directory)
        with ThreadPoolExecutor(max_workers=1) as pool, patch.object(snapshots, "_publish_file", delayed_publish):
            future = pool.submit(snapshots.save_snapshot, root, "source", body)
            try:
                assert body_ready.wait(timeout=5)
                assert_raises(FileNotFoundError, snapshots.read_snapshot, root, identity)
            finally:
                publish_index.set()
            future.result(timeout=5)
        assert snapshots.read_snapshot(root, identity)[0] == body
        with patch.object(snapshots.os, "fsync", side_effect=OSError("fixture flush failure")):
            assert_raises(OSError, snapshots.save_snapshot, root, "other", body)
        assert not list(root.rglob(".snapshot-*"))


def test_concurrent_captures():
    body = "足够长的完整原文。\r\n" * 3_000
    with TemporaryDirectory() as directory:
        snapshots.configure(directory, "parallel")
        root = Path(directory) / "source_snapshots"

        def worker(number):
            with snapshots.search_capture_scope(f"q{number}", f"sr{number}"):
                return capture(body=body)

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(worker, range(16)))
        assert all(result["status"] == "stored" for result in results)
        assert len({result["snapshot_id"] for result in results}) == 1
        assert len({result["capture_id"] for result in results}) == 16
        assert snapshots.read_snapshot(root, results[0]["snapshot_id"])[0] == body
        assert {row["query_id"] for row in records(root)} == {f"q{number}" for number in range(16)}
        assert all(row["search_run_id"] == "sr" + row["query_id"][1:] for row in records(root))
        assert not list(root.rglob(".snapshot-*"))


def test_incomplete_and_corrupted_snapshots():
    with TemporaryDirectory() as directory:
        root = Path(directory) / "source_snapshots"
        snapshots.configure(directory, "failure")
        publish = snapshots._publish_file

        def fail_index(path, data):
            if path.name == "index-v1.json":
                raise OSError("fixture index write failure")
            return publish(path, data)

        with patch.object(snapshots, "_publish_file", fail_index):
            result = capture()
        assert result["status"] == "error"
        assert records(root)[0]["status"] == "error"
        identity = snapshots.build_snapshot_index("https://example.com/article", "原文。")["snapshot_id"]
        assert_raises(FileNotFoundError, snapshots.read_snapshot, root, identity)
        recovered = capture()
        assert recovered["status"] == "stored" and recovered["snapshot_id"] == identity
        body_path = root / "snapshots" / identity / "body.txt"
        original_body = body_path.read_bytes()
        body_path.write_bytes(b"corrupt")
        assert_raises(ValueError, snapshots.read_snapshot, root, identity)
        assert capture()["status"] == "error"
        assert body_path.read_bytes() == b"corrupt"
        body_path.write_bytes(original_body)
        index_path = body_path.with_name("index-v1.json")
        index = json.loads(index_path.read_bytes())
        index["blocks"][0]["end_char"] += 1
        index_path.write_text(json.dumps(index), encoding="utf-8")
        assert_raises(ValueError, snapshots.read_snapshot, root, identity)
        assert capture()["status"] == "error"
        assert not list(root.rglob(".snapshot-*"))


def test_run_scoping_and_disabled_capture():
    with TemporaryDirectory() as directory:
        output_a = Path(directory) / "run-a"
        output_b = Path(directory) / "run-b"
        snapshots.configure(str(output_a), "a")
        with snapshots.search_capture_scope("qa", "sra"):
            first = capture()
            snapshots.configure(str(output_b), "b")
            # 已进入的搜索使用进入时固定的根，不会被顺序重新配置改写。
            assert capture()["snapshot_id"] == first["snapshot_id"]
        assert len(records(output_a / "source_snapshots")) == 2
        assert not output_b.exists()
        assert_raises(FileNotFoundError, snapshots.read_snapshot, output_b / "source_snapshots", first["snapshot_id"])
        try:
            with snapshots.search_capture_scope("temporary", "temporary"):
                raise RuntimeError("restore scope")
        except RuntimeError:
            pass
        capture()
        assert records(output_b / "source_snapshots")[0]["query_id"] is None
        snapshots.configure(None, "default")
        before = list(Path(directory).rglob("*"))
        assert capture() == {"status": "disabled", "reason": "no_output_dir"}
        assert list(Path(directory).rglob("*")) == before


def test_configure_preserves_snapshots():
    with TemporaryDirectory() as directory:
        with patch.object(graph_tools, "set_context") as set_context, patch.object(graph_tools, "clear_current_context"):
            graph_manager_tools.configure(directory)
            result = capture()
            graph_manager_tools.configure(directory)
            context = set_context.call_args.args[0]
        root = Path(directory) / "source_snapshots"
        assert snapshots.read_snapshot(root, result["snapshot_id"])[0] == "原文。"
        assert records(root)[0]["context"] == context
        with patch.object(graph_tools, "set_context"), patch.object(graph_tools, "clear_current_context"):
            graph_manager_tools.configure(None)
        assert capture()["status"] == "disabled"


def test_paths_and_unknown_versions():
    with TemporaryDirectory() as directory, TemporaryDirectory() as outside:
        root = Path(directory)
        valid_id = snapshots.build_snapshot_index("source", "body")["snapshot_id"]
        assert_raises(ValueError, snapshots.read_snapshot, root, "../outside")
        assert_raises(ValueError, snapshots.read_snapshot, root, valid_id, "../../v2")
        (root / "snapshots").symlink_to(outside, target_is_directory=True)
        assert_raises(ValueError, snapshots.save_snapshot, root, "source", "body")
        assert_raises(ValueError, snapshots.read_snapshot, root, valid_id)
        assert list(Path(outside).iterdir()) == []


def test_capture_precedes_truncation_and_filtering():
    body = "捕获的原始全文 🧪。\r\n" * 3_000
    response = {"request_id": "r-full", "results": [
        {"url": "https://example.com/article", "raw_content": body, "content": "相关原句", "title": "完整正文"},
        {"url": "https://example.com/article#duplicate", "raw_content": "重复结果的不同正文"},
        {"url": None, "raw_content": "缺少 URL 的返回正文"},
        {"url": "https://example.com/empty", "raw_content": None},
    ]}
    with TemporaryDirectory() as directory:
        snapshots.configure(directory, "pipeline")
        fake = FakeTavily([response])
        with patch.object(search_tools, "_tavily_client", fake):
            searched = searcher.web_search_node({"query_id": "q1", "search_run_id": "sr1", "query_text": "query"})
        root = Path(directory) / "source_snapshots"
        results = searched["search_results"]
        assert results["dropped_duplicates"] == 1
        assert results["dropped_without_url"] == 1
        assert results["dropped_without_raw_content"] == 1
        assert len(results["results"]) == 1 and len(fake.calls) == 1
        item = results["results"][0]
        assert item["raw_content"] == body[:20_000] and item["raw_content_truncated"]
        assert snapshots.read_snapshot(root, item["source_snapshot"]["snapshot_id"])[0] == body
        observations = records(root)
        assert len(observations) == 4
        assert all(row["query_id"] == "q1" and row["search_run_id"] == "sr1" for row in observations)
        record = next(row for row in observations if row["result_index"] == 0)
        assert record["application_truncated"] and record["raw_content_chars"] == len(body)
        assert record["request_id"] == "r-full"
        assert body[:100] not in searched["search_output"]


def test_academic_stages_and_empty_response():
    responses = [
        {"results": [{"url": "https://example.com/first", "raw_content": "首阶段正文"}]},
        {"results": []},
        {"results": [{"url": "https://example.com/final", "raw_content": "最后阶段正文"}]},
    ]
    with TemporaryDirectory() as directory:
        snapshots.configure(directory, "academic")
        fake = FakeTavily(responses)
        with patch.object(search_tools, "_tavily_client", fake), snapshots.search_capture_scope("q-a", "sr-a"):
            response = search_tools.tavily_search.invoke({
                "query": "paper query", "topic": "general", "search_depth": "advanced",
                "include_domains": search_tools._ACADEMIC_INCLUDE_DOMAINS,
            })
        assert len(fake.calls) == 3
        assert response["results"][0]["url"] == "https://example.com/final"
        assert response["academic_fallback"]["stage"] == "wide-basic (final)"
        observations = {row["stage"]: row for row in records(Path(directory) / "source_snapshots")}
        assert set(observations) == {"narrow-advanced", "narrow-basic", "wide-basic"}
        assert observations["narrow-advanced"]["requested_depth"] == "advanced"
        assert observations["narrow-basic"]["status"] == "unavailable"
        assert observations["narrow-basic"]["result_index"] is None
        assert observations["wide-basic"]["requested_depth"] == "basic"
        assert all(row["search_run_id"] == "sr-a" for row in observations.values())


def test_query_sanitization_retry_is_captured():
    fake = FakeTavily([
        {"results": []},
        {"results": [{"url": "https://example.com", "raw_content": "正文。"}]},
    ])
    with TemporaryDirectory() as directory:
        snapshots.configure(directory, "query-retry")
        with patch.object(search_tools, "_tavily_client", fake):
            searched = searcher.web_search_node({"query_id": "q1", "search_run_id": "sr1", "query_text": 'a "quoted" word'})
        assert len(fake.calls) == 2
        assert searched["search_results"]["query"] == "a quoted word"
        observations = records(Path(directory) / "source_snapshots")
        assert {row["query"] for row in observations} == {'a "quoted" word', "a quoted word"}
        assert all(row["query_id"] == "q1" for row in observations)


def test_capture_failures_preserve_search():
    response = {"results": [{"url": "https://example.com", "raw_content": "x" * 21_000}]}
    with TemporaryDirectory() as directory:
        snapshots.configure(directory, "disk-failure")
        with patch.object(search_tools, "_tavily_client", FakeTavily([response])), patch.object(snapshots, "save_snapshot", side_effect=OSError("disk full")):
            result = search_tools.tavily_search.invoke({"query": "query"})
        assert "error" not in result
        item = result["results"][0]
        assert item["raw_content"] == "x" * 20_000 + "...(truncated)"
        assert item["source_snapshot"]["status"] == "error"
        assert records(Path(directory) / "source_snapshots")[0]["status"] == "error"
        with patch.object(search_tools, "_tavily_client", FakeTavily([response])), patch.object(snapshots, "_publish_file", side_effect=OSError("disk full")):
            result = search_tools.tavily_search.invoke({"query": "query"})
        assert "error" not in result and result["results"][0]["raw_content"].startswith("x" * 20_000)
        assert result["results"][0]["source_snapshot"]["reason"] == "capture_record_write_failed"


def test_analyzer_blocks_preserve_single_call_and_facts():
    source_text = "The instrument measured the sample at 20 degrees Celsius. " * 15
    response = {"results": [{"url": "https://example.com", "title": "Measurement", "content": source_text, "raw_content": source_text}]}
    packet = {
        "source": {"source_type": "paper"},
        "document": {"document_summary": "The measurement used a temperature of 20 degrees Celsius."},
        "statements": [{"local_ref": "st1", "text": "The temperature was 20 degrees Celsius."}],
        "evidence": [{"local_ref": "e1", "text": source_text[:55], "statement_refs": ["st1"]}],
        "conflicts": [],
    }
    prompts = []

    class Model:
        def invoke(self, messages):
            prompts.append([message.content for message in messages])
            return json.dumps(packet)

    state = {"query_id": "q1", "search_run_id": "sr1", "query_text": "sample measurement"}
    with TemporaryDirectory() as directory:
        packages = []
        for output_dir in (None, directory):
            snapshots.configure(output_dir, "comparison")
            with patch.object(search_tools, "_tavily_client", FakeTavily([response])), patch.dict(searcher.config._model_cache, {"default": Model()}):
                searched = searcher.web_search_node(state)
                extracted = searcher.extract_evidence_package_node({**state, **searched})
            packages.append(extracted["evidence_package"])
        assert len(prompts) == 2 and prompts[0][0] == prompts[1][0]
        legacy = json.loads(prompts[0][-1])["source"]
        located = json.loads(prompts[1][-1])["source"]
        assert legacy["raw_content"] == source_text and "blocks" not in legacy
        assert "raw_content" not in located and located["blocks"][0]["text"] == source_text
        assert located["reading_coverage"]["unloaded_blocks"] == 0
        for key in ("sources", "statements", "evidence", "conflicts"):
            assert packages[0][key] == packages[1][key]
        assert packages[0]["documents"][0] == {
            key: value for key, value in packages[1]["documents"][0].items()
            if key not in {"snapshot_id", "chunker_version", "capture_id"}
        }
        assert packages[1]["documents"][0]["capture_id"]
        assert packages[1]["evidence"][0]["block_refs"] == []
        assert packages[1]["evidence"][0]["location_status"] == "missing"
        assert len(packages[0]["sources"]) == 1 and len(packages[0]["evidence"]) == 1


def main():
    tests = [value for name, value in globals().items() if name.startswith("test_") and callable(value)]
    original_run = snapshots._run_context
    try:
        for test in tests:
            test()
            snapshots.configure(None, None)
    finally:
        snapshots._run_context = original_run
    print(f"ALL {len(tests)} SOURCE SNAPSHOT CHECKS PASSED")  # noqa: T201


if __name__ == "__main__":
    main()
