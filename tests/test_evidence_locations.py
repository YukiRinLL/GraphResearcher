"""原文选块、Evidence 定位及真实入库函数的离线回归。

运行方式：``uv run python tests/test_evidence_locations.py``。
"""

import asyncio
import json
import sys
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agents import searcher  # noqa: E402
from agents.memory_manager import MemoryManager  # noqa: E402
from memory import evidence_locations as locations  # noqa: E402
from memory import source_snapshots as snapshots  # noqa: E402
from tools import graph_tools, research_state  # noqa: E402

URL = "https://example.com/study"
BODY = "# Measurement\n\n" + "The instrument measured a sample at 20 degrees Celsius. " * 15 + "\n\n"
BODY += "## Mechanism\n\n" + "Thermal drift limits the measurement accuracy. " * 12 + "\n"


def captured_source(body=BODY, *, query_id="q1", search_run_id="sr1", url=URL, content=None):
    item = {"url": url, "title": "Study", "raw_content": body, "content": content or body}
    with snapshots.search_capture_scope(query_id, search_run_id):
        item["source_snapshot"] = snapshots.capture_source(
            item, query="measurement", stage="single", search_parameters={}, response={},
            result_index=0, raw_content_limit=20_000,
        )
    normalized, reason = searcher._normalize_search_result(item)
    assert reason is None
    return normalized


def model_packet(source_view):
    refs = [block["block_id"] for block in source_view.get("blocks", []) if "instrument" in block["text"]]
    return {
        "source": {"source_type": "paper"},
        "document": {"document_summary": "The sample was measured at 20 degrees Celsius."},
        "statements": [{"local_ref": "st1", "text": "The sample temperature was 20 degrees Celsius."}],
        "evidence": [{
            "local_ref": "e1", "text": "The instrument measured a sample at 20 degrees Celsius.",
            "statement_refs": ["st1"], "block_refs": refs,
        }],
        "conflicts": [],
    }


def extract(source, response_factory=model_packet, *, query_id="q1", search_run_id="sr1"):
    prompts = []

    class Model:
        def invoke(self, messages):
            data = json.loads(messages[-1].content)
            prompts.append(data)
            return json.dumps(response_factory(data["source"]))

    with patch.dict(searcher.config._model_cache, {"default": Model()}):
        packet = searcher._extract_source_packet(
            {"text": "sample measurement", "acceptance_criteria": ["measurement temperature"]},
            {"research_goal": "measurement accuracy and thermal drift"}, source,
            query_id=query_id, search_run_id=search_run_id,
        )
    assert len(prompts) == 1
    return packet, prompts[0]


def assert_raises(exception, function, *args, **kwargs):
    try:
        function(*args, **kwargs)
    except exception:
        return
    raise AssertionError(f"Expected {exception.__name__}")


class FakeGraph:
    """仅替换图存储边界，保留实际 Document/Evidence 创建及 MemoryManager 入库逻辑。"""

    def __init__(self):
        self.nodes = {"goal": {"id": "goal", "type": "UserRequest"}}
        self.edges = []
        self.open_run("q1", "sr1")

    def open_run(self, query_id, run_id):
        self.nodes[query_id] = {"id": query_id, "type": "Query", "status": "searching", "text": "measurement"}
        self.nodes[run_id] = {"id": run_id, "type": "SearchRun", "query_id": query_id, "status": "running"}

    @staticmethod
    def type_name(kind):
        return kind.value if hasattr(kind, "value") else str(kind)

    def get_node(self, node_id):
        return deepcopy(self.nodes.get(node_id, {}))

    def search_nodes(self, kind, filters=None):
        name = self.type_name(kind).replace("_", "").lower()
        return [deepcopy(node) for node in self.nodes.values()
                if node["type"].replace("_", "").lower() == name
                and all(node.get(key) == value for key, value in (filters or {}).items())]

    async def add_node(self, kind, attributes):
        node_id = f"n{len(self.nodes)}"
        self.nodes[node_id] = {"id": node_id, "type": self.type_name(kind), **deepcopy(attributes)}
        return node_id

    async def add_edge(self, source, target, kind, attributes=None):
        self.edges.append({"source": source, "target": target, "type": self.type_name(kind), **(attributes or {})})
        return f"edge{len(self.edges)}"

    def upsert_node(self, kind, attributes, node_id):
        self.nodes[node_id].update(deepcopy(attributes))
        return node_id

    @contextmanager
    def install(self):
        with patch.multiple(
            graph_tools,
            _context="test-run",
            _get_manager=lambda: self,
            _run_async=asyncio.run,
            get_node=self.get_node,
            search_nodes=self.search_nodes,
            upsert_node=self.upsert_node,
            get_query_parent=lambda _query: "goal",
            transition_query=lambda query_id, status, **attrs: self.nodes[query_id].update(status=status, **attrs),
            increment_successful_search_rounds=lambda _goal: None,
            save_graph=lambda: None,
        ), patch.object(research_state, "get_goal", lambda: self.get_node("goal")):
            yield self


def submit(graph, package, query_id="q1", run_id="sr1"):
    manager = MemoryManager(model=object())
    manager._resolve_query_id = lambda ref: ref
    manager._ancestor_evidence_keys = lambda ref: set()
    manager._bump_portfolio_revision = lambda: None
    with graph.install():
        result = manager.submit_search_result(run_id, query_id, package)
    assert result["status"] == "succeeded", result
    assert graph.nodes[query_id]["status"] == "assessing"
    assert graph.nodes[run_id]["status"] == "succeeded"
    return result


def test_exact_selection_after_truncated_prefix():
    body = "# Background\n\n" + ("Historical background unrelated to experiments. " * 50 + "\n\n") * 12
    needle = "The sample was measured at 42 degrees Celsius."
    body += "# Experiment\n\n" + needle + "\n"
    index = snapshots.build_snapshot_index(URL, body)
    selected = locations.select_source_blocks(body, index, {"text": "sample temperature"}, {}, needle)
    assert body.find(needle) > 20_000
    assert any(needle in block["text"] for block in selected["blocks"])
    assert sum(len(block["text"]) for block in selected["blocks"]) <= 20_000
    assert selected["reading_coverage"]["unloaded_blocks"] > 0
    assert len({block["block_id"] for block in selected["blocks"]}) == len(selected["blocks"])
    by_ref = {block["block_id"]: block for block in index["blocks"]}
    positions = [by_ref[block["block_id"]]["start_char"] for block in selected["blocks"]]
    assert positions == sorted(positions)
    assert all(block["text"] == body[by_ref[block["block_id"]]["start_char"]:by_ref[block["block_id"]]["end_char"]]
               for block in selected["blocks"])


def test_goal_coverage_and_lexical_fallback():
    body = "# Measurement\n\n" + ("sample measurement temperature " * 8 + ".\n\n") * 5
    body += "# Mechanism\n\nThermal drift introduces a systematic uncertainty.\n"
    body += "# Context\n\nA separate physical mechanism changes the calibration.\n"
    index = snapshots.build_snapshot_index(URL, body)
    selected = locations.select_source_blocks(
        body, index, {"text": "sample measurement"}, {"research_goal": "thermal drift uncertainty"}, "", max_chars=750,
    )
    assert any("Thermal drift" in block["text"] for block in selected["blocks"])
    assert any("sample measurement" in block["text"] for block in selected["blocks"])
    assert selected == locations.select_source_blocks(
        body, index, {"text": "sample measurement"}, {"research_goal": "thermal drift uncertainty"}, "", max_chars=750,
    )
    chinese = "# 测量\n\n实验温度限定为二十摄氏度。\n\n# 背景\n\n研究对象属于光学器件。\n"
    lexical = locations.select_source_blocks(
        chinese, snapshots.build_snapshot_index(URL, chinese), {"text": "实验温度"}, {}, "摘要改写了测量条件", max_chars=45,
    )
    assert any("实验温度" in block["text"] for block in lexical["blocks"])
    assert all("摘要改写" not in block["text"] for block in lexical["blocks"])
    fallback = locations.select_source_blocks(body, index, {"text": "zzzz"}, {}, "yyyy", max_chars=750)
    assert fallback["reading_coverage"]["selection"] == "coverage_fallback"
    assert fallback["blocks"] and fallback["reading_coverage"]["selected_chars"] <= 750
    assert any("systematic uncertainty" in block["text"] for block in fallback["blocks"])


def test_table_dependencies_and_budget():
    table = "| condition | value |\n| --- | --- |\n| temperature | 20 C |\n\n[^unit]: Measured in the laboratory.\n"
    body = "# Results\n\n" + table
    index = snapshots.build_snapshot_index(URL, body)
    selected = locations.select_source_blocks(body, index, {"text": "temperature"}, {}, "", max_chars=len(body))
    assert [block["text"] for block in selected["blocks"]] == ["# Results\n", table]
    assert selected["reading_coverage"]["selected_chars"] == len("# Results\n") + len(table)
    small = locations.select_source_blocks(body, index, {"text": "temperature"}, {}, "", max_chars=len(table) - 1)
    assert small["blocks"] == []


def test_location_validation_and_repeated_quotes():
    body = "同一句话。\r\n\r\n同一句话。\r\n"
    index = snapshots.build_snapshot_index(URL, body)
    first, second = [block["block_id"] for block in index["blocks"]]
    assert locations.validate_block_refs([second, second], {second}) == {"block_refs": [second], "location_status": "valid"}
    for invalid in ([first], [second, first], [123], "b1", {}, [None]):
        assert locations.validate_block_refs(invalid, {second}) == {"block_refs": [], "location_status": "invalid"}
    assert locations.validate_block_refs([], {second})["location_status"] == "missing"
    assert locations.quote_locations("同一句话。", [second], body, index) == [{"start_char": 9, "end_char": 14}]
    assert len(locations.quote_locations("同一句话。", [first, second], body, index)) == 2
    assert not locations.quote_locations("改写的表格事实", [first], body, index)


def test_capture_binding_checks():
    with TemporaryDirectory() as directory:
        snapshots.configure(directory, "test-run")
        source = captured_source()
        reference = source["source_snapshot"]
        _, index, _ = snapshots.load_captured_snapshot(reference, URL, context="test-run", query_id="q1", search_run_id="sr1")
        assert index["source_key"] == URL
        for url, context, query_id, run_id in [
            ("https://other.example/study", "test-run", "q1", "sr1"),
            (URL, "other-run", "q1", "sr1"),
            (URL, "test-run", "q2", "sr1"),
            (URL, "test-run", "q1", "sr2"),
        ]:
            assert_raises(ValueError, snapshots.load_captured_snapshot, reference, url, context=context, query_id=query_id, search_run_id=run_id)
        for field, value in [("capture_id", "../other"), ("snapshot_id", "s_wrong"), ("chunker_version", "v2")]:
            assert_raises(ValueError, snapshots.load_captured_snapshot, {**reference, field: value}, URL, context="test-run")


def test_analyzer_rejects_unseen_and_forged_metadata():
    with TemporaryDirectory() as directory:
        snapshots.configure(directory, "test-run")
        source = captured_source()

        def malicious(view):
            packet = model_packet(view)
            packet["document"].update(snapshot_id="forged", chunker_version="v9", capture_id="forged")
            packet["evidence"][0].update(block_refs=["unseen-block"], location_status="valid")
            packet["_location_log"] = [{"stage": "forged"}]
            return packet

        packet, prompt = extract(source, malicious)
        assert packet["document"]["snapshot_id"] == source["source_snapshot"]["snapshot_id"]
        assert packet["evidence"][0]["block_refs"] == []
        assert packet["evidence"][0]["location_status"] == "invalid"
        assert len(packet["statements"]) == len(packet["evidence"]) == 1
        assert packet["_location_log"][1]["reason"] == "ref_not_in_analyzer_input"
        assert "raw_content" not in prompt["source"] and prompt["source"]["blocks"]
        assert all(entry["stage"] != "forged" for entry in packet["_location_log"])
        valid, _ = extract(source)
        assert valid["evidence"][0]["location_status"] == "valid"
        audit = valid["_location_log"][1]
        assert audit["quote_match"] == "exact"
        assert all(BODY[span["start_char"]:span["end_char"]] == valid["evidence"][0]["text"] for span in audit["quote_spans"])


def test_analyzer_cannot_reference_unselected_snapshot_blocks():
    with TemporaryDirectory() as directory:
        snapshots.configure(directory, "test-run")
        body = BODY + "\n\n" + "x" * 22_000
        source = captured_source(body)
        index = snapshots.build_snapshot_index(URL, body)
        unseen = index["blocks"][-1]["block_id"]

        def response(view):
            assert unseen not in {block["block_id"] for block in view["blocks"]}
            packet = model_packet(view)
            packet["evidence"][0]["block_refs"] = [unseen]
            return packet

        packet, _ = extract(source, response)
        assert packet["evidence"][0]["location_status"] == "invalid"


def test_table_summary_uses_refs_without_fabricated_quote():
    table = "| quantity | value |\n| --- | --- |\n| temperature | 20 C |\n"
    body = BODY + "\n\n## Data\n\n" + table
    with TemporaryDirectory() as directory:
        snapshots.configure(directory, "test-run")
        source = captured_source(body)

        def response(view):
            packet = model_packet(view)
            packet["evidence"][0]["text"] = "temperature: 20 C"
            packet["evidence"][0]["block_refs"] = [block["block_id"] for block in view["blocks"] if "| quantity |" in block["text"]]
            return packet

        packet, _ = extract(source, response)
        assert packet["evidence"][0]["location_status"] == "valid"
        assert packet["_location_log"][1]["quote_match"] == "not_exact"
        assert packet["_location_log"][1]["quote_spans"] == []
        graph = FakeGraph()
        result = submit(graph, searcher._merge_source_packets({"results": [source]}, [packet]))
        evidence = graph.get_node(result["ref_map"]["e1"])
        assert evidence["location_status"] == "valid" and evidence["text"] == "temperature: 20 C"
        assert not evidence.get("locator") and "quote_spans" not in evidence


def test_analyzer_unavailable_snapshot_and_oversized_fallback():
    with TemporaryDirectory() as directory:
        snapshots.configure(directory, "test-run")
        source = captured_source()
        packet, prompt = extract(source, query_id="q-other")
        assert "raw_content" in prompt["source"] and "blocks" not in prompt["source"]
        assert prompt["source"]["reading_coverage"]["reason"] == "snapshot_unavailable"
        assert not locations.snapshot_fields(packet["document"])
        oversized = captured_source("The instrument " + "x" * 22_000)
        _, prompt = extract(oversized)
        assert prompt["source"]["reading_coverage"]["reason"] == "no_blocks_fit"
        assert len(prompt["source"]["raw_content"]) == 20_000
        path = Path(directory) / "source_snapshots" / "snapshots" / source["source_snapshot"]["snapshot_id"] / "body.txt"
        path.unlink()
        packet, prompt = extract(source)
        assert prompt["source"]["reading_coverage"]["reason"] == "snapshot_unavailable"
        assert packet["evidence"][0]["location_status"] == "missing"


def test_many_to_many_graph_binding_and_legacy_updates():
    with TemporaryDirectory() as directory:
        snapshots.configure(directory, "test-run")
        source = captured_source()

        def response(view):
            packet = model_packet(view)
            packet["statements"].append({"local_ref": "st2", "text": "Thermal drift limits accuracy."})
            packet["evidence"][0]["statement_refs"] = ["st1", "st2"]
            packet["evidence"][0]["block_refs"] = [block["block_id"] for block in view["blocks"]]
            packet["evidence"].append({
                "local_ref": "e2", "text": "Thermal drift limits the measurement accuracy.",
                "statement_refs": ["st2"], "block_refs": packet["evidence"][0]["block_refs"],
            })
            return packet

        packet, _ = extract(source, response)
        package = searcher._merge_source_packets({"results": [source]}, [packet])
        graph = FakeGraph()
        result = submit(graph, package)
        doc = graph.get_node(result["ref_map"]["d1"])
        first = graph.get_node(result["ref_map"]["e1"])
        second = graph.get_node(result["ref_map"]["e2"])
        assert doc["snapshot_id"] == source["source_snapshot"]["snapshot_id"]
        assert first["document_id"] == second["document_id"] == doc["id"]
        assert first["block_refs"] == second["block_refs"] and len(first["block_refs"]) >= 2
        assert first["location_status"] == second["location_status"] == "valid"
        assert len(first["statement_refs"]) == 2 and len(second["statement_refs"]) == 1
        restored, index, _ = snapshots.load_captured_snapshot(doc, URL, context="test-run")
        assert restored == BODY and set(first["block_refs"]).issubset({block["block_id"] for block in index["blocks"]})
        assert all("blocks" not in node and "quote_spans" not in node for node in graph.nodes.values())
        with graph.install():
            repeated_id = graph_tools.create_evidence(text=first["text"], document_id=doc["id"], source_id=doc["source_id"])
        assert repeated_id == first["id"]
        assert graph.nodes[repeated_id]["block_refs"] == first["block_refs"]
        assert graph.nodes[repeated_id]["evidence_key"] == first["evidence_key"]


def test_bad_locations_do_not_fail_ingestion():
    with TemporaryDirectory() as directory:
        snapshots.configure(directory, "test-run")
        source = captured_source()
        packet, _ = extract(source)
        package = searcher._merge_source_packets({"results": [source]}, [packet])
        package["evidence"][0]["block_refs"] = ["other-snapshot:v1:b000001"]
        graph = FakeGraph()
        result = submit(graph, package)
        evidence = graph.get_node(result["ref_map"]["e1"])
        assert evidence["block_refs"] == [] and evidence["location_status"] == "invalid"
        assert evidence["text"] == packet["evidence"][0]["text"]
        assert result["written"]["evidence"] == 1
        # 其他 SearchRun 的捕获关联也只降级定位，不改变原有事实入库结果。
        graph.open_run("q2", "sr2")
        result = submit(graph, package, "q2", "sr2")
        assert not locations.snapshot_fields(graph.get_node(result["ref_map"]["d1"]))
        assert graph.get_node(result["ref_map"]["e1"])["location_status"] == "invalid"


def test_same_snapshot_keeps_distinct_documents():
    with TemporaryDirectory() as directory:
        snapshots.configure(directory, "test-run")
        graph = FakeGraph()
        documents = []
        for number in (1, 2):
            query_id, run_id = f"q{number}", f"sr{number}"
            graph.open_run(query_id, run_id)
            source = captured_source(query_id=query_id, search_run_id=run_id)
            packet, _ = extract(source, query_id=query_id, search_run_id=run_id)
            package = searcher._merge_source_packets({"results": [source]}, [packet])
            result = submit(graph, package, query_id, run_id)
            documents.append(graph.get_node(result["ref_map"]["d1"]))
        assert documents[0]["snapshot_id"] == documents[1]["snapshot_id"]
        assert documents[0]["capture_id"] != documents[1]["capture_id"]
        assert documents[0]["id"] != documents[1]["id"]
        assert documents[0]["source_id"] == documents[1]["source_id"]


def test_old_packets_and_cross_source_locations():
    graph = FakeGraph()
    source = {"url": URL, "raw_content": BODY, "content": BODY}
    packet = model_packet({})
    packet["evidence"][0].pop("block_refs")
    package = searcher._merge_source_packets({"results": [source]}, [packet])
    result = submit(graph, package)
    doc = graph.get_node(result["ref_map"]["d1"])
    evidence = graph.get_node(result["ref_map"]["e1"])
    assert not locations.snapshot_fields(doc)
    assert "block_refs" not in evidence and "location_status" not in evidence
    with TemporaryDirectory() as directory:
        snapshots.configure(directory, "test-run")
        source = captured_source()
        packet, _ = extract(source)
        with graph.install():
            other = graph_tools.create_source("https://other.example/study")
            invalid_doc = graph_tools.create_document("summary", source_id=other, **locations.snapshot_fields(packet["document"]))
            assert not locations.snapshot_fields(graph.get_node(invalid_doc))
            valid_doc = graph_tools.create_document("summary", source_id=doc["source_id"], **locations.snapshot_fields(packet["document"]))
            for status in ("valid", ["invalid-type"]):
                invalid_evidence = graph_tools.create_evidence(
                    text="table data", document_id=valid_doc, source_id=other,
                    block_refs=packet["evidence"][0]["block_refs"], location_status=status,
                )
                assert graph.get_node(invalid_evidence)["location_status"] == "invalid"


def main():
    tests = [value for name, value in globals().items() if name.startswith("test_") and callable(value)]
    original = snapshots._run_context
    try:
        for test in tests:
            snapshots.configure(None, None)
            test()
    finally:
        snapshots._run_context = original
    print(f"ALL {len(tests)} EVIDENCE LOCATION CHECKS PASSED")  # noqa: T201


if __name__ == "__main__":
    main()
