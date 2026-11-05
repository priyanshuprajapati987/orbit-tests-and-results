"""Tests for P2 Execution Traces — full observability."""

import os
import time

import pytest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")

from orbit.orbit.core.execution_trace import (
    ExecutionTracer,
    Span,
    Trace,
    get_execution_tracer,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_tracer(tmp_path):
    """Create a tracer with a temp storage dir."""
    return ExecutionTracer(storage_dir=str(tmp_path / "traces"), max_traces=100)


# ── Span dataclass ───────────────────────────────────────────────────────────


class TestSpan:
    def test_defaults(self):
        s = Span()
        assert s.id
        assert s.trace_id == ""
        assert s.status == "running"
        assert s.duration_ms == 0.0

    def test_fields(self):
        s = Span(
            trace_id="t1",
            name="llm",
            span_type="llm",
            agent_id="COD",
            tool_name="web_search",
            provider="ollama",
            model="qwen2.5",
            input_preview="hello",
            tokens_in=10,
            tokens_out=20,
            cost_usd=0.001,
        )
        assert s.trace_id == "t1"
        assert s.agent_id == "COD"
        assert s.tokens_in == 10


# ── Trace dataclass ─────────────────────────────────────────────────────────


class TestTrace:
    def test_defaults(self):
        t = Trace()
        assert t.id
        assert t.status == "running"
        assert t.spans == []
        assert t.total_cost_usd == 0.0

    def test_query(self):
        t = Trace(query="what is python")
        assert t.query == "what is python"


# ── ExecutionTracer core ────────────────────────────────────────────────────


class TestExecutionTracer:
    def test_start_end_trace(self, tmp_path):
        tracer = _make_tracer(tmp_path)
        tid = tracer.start_trace(query="hello world")
        assert tid
        assert tid in tracer._active

        tracer.end_trace(tid, status="ok", result="hi there")
        assert tid not in tracer._active
        assert len(tracer._traces) == 1
        t = tracer._traces[0]
        assert t.status == "ok"
        assert t.result == "hi there"
        assert t.total_duration_ms >= 0

    def test_start_end_span(self, tmp_path):
        tracer = _make_tracer(tmp_path)
        tid = tracer.start_trace(query="test")
        sid = tracer.start_span(tid, "llm_call", "llm", provider="ollama")
        assert sid

        time.sleep(0.01)
        tracer.end_span(tid, sid, status="ok", tokens_in=10, tokens_out=20)
        t = tracer.get_trace(tid)
        assert len(t["spans"]) == 1
        assert t["spans"][0]["status"] == "ok"
        assert t["spans"][0]["duration_ms"] >= 0
        assert t["spans"][0]["tokens_in"] == 10
        assert t["spans"][0]["tokens_out"] == 20

    def test_nested_spans(self, tmp_path):
        tracer = _make_tracer(tmp_path)
        tid = tracer.start_trace(query="complex task")
        s1 = tracer.start_span(tid, "agent:TAS", "agent", agent_id="TAS")
        s2 = tracer.start_span(
            tid, "tool:file_write", "tool", parent_id=s1, tool_name="file_write"
        )
        tracer.end_span(tid, s2, status="ok")
        tracer.end_span(tid, s1, status="ok")
        t = tracer.get_trace(tid)
        assert len(t["spans"]) == 2
        assert t["spans"][1]["parent_id"] == s1

    def test_span_context_manager(self, tmp_path):
        tracer = _make_tracer(tmp_path)
        tid = tracer.start_trace(query="ctx test")
        with tracer.trace_span(tid, "auto_span", "llm") as ctx:
            assert ctx.span_id is not None
            time.sleep(0.01)
        t = tracer.get_trace(tid)
        assert len(t["spans"]) == 1
        assert t["spans"][0]["status"] == "ok"

    def test_span_context_manager_exception(self, tmp_path):
        tracer = _make_tracer(tmp_path)
        tid = tracer.start_trace(query="err test")
        with pytest.raises(ValueError):  # noqa: SIM117
            with tracer.trace_span(tid, "fail_span", "tool"):
                raise ValueError("boom")
        t = tracer.get_trace(tid)
        assert t["spans"][0]["status"] == "error"
        assert "boom" in t["spans"][0]["error"]

    def test_end_trace_aggregates(self, tmp_path):
        tracer = _make_tracer(tmp_path)
        tid = tracer.start_trace(query="agg")
        sid = tracer.start_span(tid, "s1", "llm")
        tracer.end_span(tid, sid, tokens_in=100, tokens_out=200, cost_usd=0.001)
        tracer.end_trace(tid, status="ok")
        t = tracer._traces[-1]
        assert t.total_tokens_in == 100
        assert t.total_tokens_out == 200
        assert t.total_cost_usd == 0.001
        assert t.span_count == 1

    def test_unknown_trace_no_crash(self, tmp_path):
        tracer = _make_tracer(tmp_path)
        tracer.end_trace("nonexistent", status="ok")  # no crash
        tracer.end_span("nonexistent", "span1", status="ok")  # no crash
        assert tracer.get_trace("nonexistent") is None

    def test_max_traces_eviction(self, tmp_path):
        tracer = ExecutionTracer(storage_dir=str(tmp_path / "t"), max_traces=5)
        for i in range(10):
            tid = tracer.start_trace(query=f"q{i}")
            tracer.end_trace(tid, status="ok")
        assert len(tracer._traces) == 5

    def test_persistence(self, tmp_path):
        d = tmp_path / "traces"
        tracer1 = ExecutionTracer(storage_dir=str(d), max_traces=50)
        tid = tracer1.start_trace(query="persist me")
        tracer1.end_trace(tid, status="ok", result="saved")

        # end_trace persists on a background daemon thread; wait for the file
        deadline = time.time() + 5.0
        while not (d / "traces.json").exists() and time.time() < deadline:
            time.sleep(0.01)
        assert (d / "traces.json").exists(), "async trace save never landed"

        tracer2 = ExecutionTracer(storage_dir=str(d), max_traces=50)
        assert len(tracer2._traces) == 1
        assert tracer2._traces[0].query == "persist me"


# ── Query / Search / Stats ───────────────────────────────────────────────────


class TestTraceQueries:
    def _populate(self, tmp_path):
        tracer = _make_tracer(tmp_path)
        for i in range(5):
            tid = tracer.start_trace(query=f"query {i}", agent_id="TAS")
            tracer.end_trace(tid, status="ok" if i < 3 else "error")
        return tracer

    def test_list_traces(self, tmp_path):
        tracer = self._populate(tmp_path)
        traces = tracer.list_traces(limit=3)
        assert len(traces) == 3
        # Most recent first
        assert traces[0]["query"] == "query 4"

    def test_list_by_status(self, tmp_path):
        tracer = self._populate(tmp_path)
        errors = tracer.list_traces(status="error")
        assert len(errors) == 2

    def test_list_by_agent(self, tmp_path):
        tracer = self._populate(tmp_path)
        tas = tracer.list_traces(agent_id="TAS")
        assert len(tas) == 5

    def test_list_by_query(self, tmp_path):
        tracer = self._populate(tmp_path)
        q3 = tracer.list_traces(query="query 3")
        assert len(q3) == 1

    def test_slowest(self, tmp_path):
        tracer = _make_tracer(tmp_path)
        for i in range(3):
            tid = tracer.start_trace(query=f"slow {i}")
            time.sleep(0.005)
            tracer.end_trace(tid)
        slow = tracer.get_slowest(limit=2)
        assert len(slow) == 2
        assert slow[0]["total_duration_ms"] >= slow[1]["total_duration_ms"]

    def test_errors(self, tmp_path):
        tracer = self._populate(tmp_path)
        errs = tracer.get_errors()
        assert len(errs) == 2

    def test_stats(self, tmp_path):
        tracer = self._populate(tmp_path)
        stats = tracer.get_stats()
        assert stats["total_traces"] == 5
        assert stats["error_traces"] == 2
        assert stats["error_rate"] == 40.0
        assert "TAS" in stats["by_agent"]
        assert stats["total_spans"] >= 0

    def test_stats_empty(self, tmp_path):
        tracer = _make_tracer(tmp_path)
        stats = tracer.get_stats()
        assert stats["total_traces"] == 0

    def test_clear(self, tmp_path):
        tracer = self._populate(tmp_path)
        tracer.clear()
        assert len(tracer._traces) == 0
        assert len(tracer._active) == 0
        stats = tracer.get_stats()
        assert stats["total_traces"] == 0


# ── Singleton ────────────────────────────────────────────────────────────────


class TestSingleton:
    def test_get_execution_tracer(self):
        t1 = get_execution_tracer()
        t2 = get_execution_tracer()
        assert t1 is t2


# ── Context variable ─────────────────────────────────────────────────────────


class TestContextVar:
    def test_parent_tracking(self, tmp_path):
        from orbit.orbit.core.execution_trace import _current_span_id

        tracer = _make_tracer(tmp_path)
        tid = tracer.start_trace(query="ctx")
        s1 = tracer.start_span(tid, "parent", "agent")
        assert _current_span_id.get() == s1

        s2 = tracer.start_span(tid, "child", "tool", parent_id=s1)
        assert _current_span_id.get() == s2

        tracer.end_span(tid, s2)
        # Stack semantics: ending the child restores the parent span
        # (the old single-slot clear dropped parents — the bug).
        assert _current_span_id.get() == s1

        tracer.end_span(tid, s1)
        assert _current_span_id.get() is None
