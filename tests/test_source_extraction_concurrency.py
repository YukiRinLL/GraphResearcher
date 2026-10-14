"""验证来源抽取的并发、顺序、上下文和提交边界，不调用外部服务。"""

import json
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from threading import Barrier, BoundedSemaphore, Condition, Event, Lock
from types import SimpleNamespace
from unittest.mock import Mock, patch

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables import RunnableLambda
from langchain_core.runnables.config import ensure_config

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agents import searcher  # noqa: E402
from memory import source_snapshots  # noqa: E402

MARKER = ContextVar("extraction_test_marker", default=None)


def state(query_id="q1", count=3):
    return {
        "messages": [], "query_id": query_id, "search_run_id": f"run-{query_id}",
        "query_text": query_id, "query_role": "evidence_gap",
        "search_results": {"results": [
            {"url": f"https://example.com/{query_id}/{i}", "title": str(i),
             "raw_content": "Measurement results and supporting observations. " * 30}
            for i in range(count)
        ]},
    }


def packet(data):
    title = data["source"]["title"]
    return {
        "source": {}, "document": {"document_summary": f"summary {title}"},
        "statements": [{"local_ref": "st", "text": f"statement {title}"}],
        "evidence": [{"local_ref": "ev", "text": f"evidence {title}", "statement_refs": ["st"]}],
        "conflicts": [],
    }


class Model:
    def __init__(self, handler=None):
        self.handler = handler or packet
        self.lock = Lock()
        self.active = self.peak = 0
        self.calls = []

    def invoke(self, messages):
        data = json.loads(messages[-1].content)
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
            self.calls.append((
                data, MARKER.get(), source_snapshots.current_capture_context(), ensure_config(),
            ))
        try:
            return json.dumps(self.handler(data))
        finally:
            with self.lock:
                self.active -= 1


class ObservedSlots:
    """记录真实信号量的等待情况，使跨 Query 测试可以确定性地协调任务。"""

    def __init__(self, limit):
        self.semaphore = BoundedSemaphore(limit)
        self.condition = Condition()
        self.attempts = 0

    def __enter__(self):
        with self.condition:
            self.attempts += 1
            self.condition.notify_all()
        self.semaphore.acquire()

    def __exit__(self, *_args):
        self.semaphore.release()


@contextmanager
def settings(model, limit=3, slots=None):
    with (
        patch.object(searcher.config, "SOURCE_EXTRACTION_CONCURRENCY", limit),
        patch.object(searcher, "_source_analyzer_slots", slots or BoundedSemaphore(limit)),
        patch.dict(searcher.config._model_cache, {"purpose.source_analyzer": model}),
        patch.object(searcher.config, "build_model", side_effect=AssertionError("离线抽取不能构建真实模型")),
    ):
        yield


def test_parallel_and_order():
    for count in (2, 3):
        barrier = Barrier(count)

        def concurrent(data):
            barrier.wait(timeout=10)
            return packet(data)

        model = Model(concurrent)
        with settings(model):
            actual = searcher.extract_evidence_package_node(state(count=count))["evidence_package"]
        assert model.peak == count and len(model.calls) == count

        model = Model()
        with settings(model, 1):
            serial = searcher.extract_evidence_package_node(state(count=count))["evidence_package"]
        assert actual == serial

    original_extract = searcher._extract_source_packet
    last_finished = Event()
    finished = []

    def reversed_completion(*args, **kwargs):
        title = args[2]["title"]
        if title != "2":
            assert last_finished.wait(10)
        result = original_extract(*args, **kwargs)
        finished.append(title)
        if title == "2":
            last_finished.set()
        return result

    with settings(Model()), patch.object(searcher, "_extract_source_packet", reversed_completion):
        reversed_package = searcher.extract_evidence_package_node(state())["evidence_package"]
    assert finished[0] == "2" and reversed_package == serial
    assert [item["local_ref"] for item in serial["evidence"]] == ["e1", "e2", "e3"]


def test_shared_limit_and_context(limit=2):
    release = Event()
    started = Event()
    slots = ObservedSlots(limit)
    callback = BaseCallbackHandler()

    def blocked(data):
        with model.lock:
            if model.active == limit:
                started.set()
        assert release.wait(10)
        return packet(data)

    model = Model(blocked)

    def extract(query_id):
        token = MARKER.set(query_id)
        try:
            with source_snapshots.search_capture_scope(query_id, f"run-{query_id}"):
                return RunnableLambda(searcher.extract_evidence_package_node).invoke(
                    state(query_id, 2), config={
                        "tags": [query_id], "metadata": {"query_id": query_id},
                        "callbacks": [callback],
                    },
                )
        finally:
            MARKER.reset(token)

    with settings(model, limit, slots), ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(extract, query_id) for query_id in ("q1", "q2")]
        try:
            with slots.condition:
                assert slots.condition.wait_for(lambda: slots.attempts == 2 * limit, timeout=10)
            assert started.wait(10)
            with model.lock:
                assert model.active == limit and model.peak == limit
        finally:
            release.set()
        for future in futures:
            future.result(timeout=10)
    assert len(model.calls) == 4 and model.peak == limit
    for data, marker, capture, runnable_config in model.calls:
        query_id = data["query"]["text"]
        assert marker == capture.query_id == query_id
        assert capture.search_run_id == f"run-{query_id}"
        assert query_id in runnable_config["tags"]
        assert runnable_config["metadata"]["query_id"] == query_id
        assert callback in runnable_config["callbacks"].inheritable_handlers
    assert MARKER.get() is None


def test_small_empty_and_serial():
    for count, limit in ((0, 3), (1, 3), (2, 1)):
        model = Model()
        with settings(model, limit):
            result = searcher.extract_evidence_package_node(state(count=count))
        assert len(model.calls) == count
        assert model.peak == (0 if count == 0 else 1)
        assert len(result["evidence_package"]["sources"]) == count

    def empty_one(data):
        result = packet(data)
        if data["source"]["title"] == "0":
            result["document"] = {}
        return result

    model = Model(empty_one)
    with settings(model):
        result = searcher.extract_evidence_package_node(state(count=2))["evidence_package"]
    assert len(model.calls) == 2 and len(result["sources"]) == 1
    assert result["sources"][0]["title"] == "1"


def graph():
    with patch.object(searcher, "init_node", lambda _state: {}), patch.object(
        searcher, "web_search_node", lambda _state: {},
    ):
        return searcher._build_graph().compile()


def test_failure_cleanup_and_submission():
    running = Event()
    failed = Event()
    release = Event()

    def fail_one(data):
        if data["source"]["title"] == "0":
            assert running.wait(10)
            failed.set()
            raise RuntimeError("analyzer failed")
        running.set()
        assert release.wait(10)
        return packet(data)

    submit = Mock(return_value={"status": "succeeded"})
    model = Model(fail_one)
    with settings(model, 2), patch.object(
        searcher, "submit_search_result", SimpleNamespace(invoke=submit),
    ):
        pipeline = graph()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(pipeline.invoke, state(count=2))
            try:
                assert failed.wait(10)
                assert not future.done(), "失败后必须等待仍在执行的抽取任务退出"
                submit.assert_not_called()
            finally:
                release.set()
            try:
                future.result(timeout=10)
            except RuntimeError as exc:
                assert str(exc) == "analyzer failed"
            else:
                raise AssertionError("抽取异常必须继续向上抛出")
        assert model.active == 0
        submit.assert_not_called()

        # 同一信号量上的后续 Query 必须能正常完成并且只提交一次。
        restored = Barrier(2)

        def after_failure(data):
            restored.wait(timeout=10)
            return packet(data)

        model.handler = after_failure
        result = pipeline.invoke(state("q2", 2))
        submit.assert_called_once()
        payload = submit.call_args.args[0]
        assert payload["query_id"] == "q2" and payload["search_run_id"] == "run-q2"
        assert len(payload["evidence_package"]["sources"]) == 2
        assert result["submit_result"]["status"] == "succeeded"


def test_pending_cancellation():
    pending = []
    closed = Event()

    class Pool:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def submit(self, *_args, **_kwargs):
            future = Future()
            if not pending:
                future.set_exception(RuntimeError("first source failed"))
            pending.append(future)
            return future

        def __exit__(self, *_args):
            closed.set()

    with settings(Model()), patch.object(searcher, "ThreadPoolExecutor", Pool):
        try:
            searcher.extract_evidence_package_node(state())
        except RuntimeError as exc:
            assert str(exc) == "first source failed"
        else:
            raise AssertionError("抽取失败必须阻止合并")
    assert len(pending) == 3 and all(future.cancelled() for future in pending[1:])
    assert closed.is_set()


def main():
    test_parallel_and_order()
    test_shared_limit_and_context()
    test_shared_limit_and_context(1)
    test_small_empty_and_serial()
    test_failure_cleanup_and_submission()
    test_pending_cancellation()


if __name__ == "__main__":
    main()
