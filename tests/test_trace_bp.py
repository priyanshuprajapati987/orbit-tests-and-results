"""Unit tests for orbit/orbit/core/trace_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.trace_bp import trace_bp


class TraceBpBase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(trace_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(trace_bp.name, "execution_trace")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/traces", "/api/traces/<trace_id>", "/api/traces/stats",
                  "/api/traces/slowest", "/api/traces/errors", "/api/traces/clear",
                  "/api/traces/manual/start", "/api/traces/manual/<trace_id>/span",
                  "/api/traces/manual/<trace_id>/span/<span_id>/end",
                  "/api/traces/manual/<trace_id>/end"]:
            self.assertIn(p, rules)


class TestListTraces(TraceBpBase):
    def test_list_default(self):
        with patch("orbit.core.trace_bp.get_execution_tracer") as gt:
            gt.return_value.list_traces.return_value = [{"id": "t1"}]
            r = self.client.get("/api/traces")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["traces"], [{"id": "t1"}])
        gt.return_value.list_traces.assert_called_once_with(
            limit=50, status="", agent_id="", query="")

    def test_list_filters(self):
        with patch("orbit.core.trace_bp.get_execution_tracer") as gt:
            gt.return_value.list_traces.return_value = []
            r = self.client.get("/api/traces?limit=5&status=error&agent_id=planner&q=weather")
        gt.return_value.list_traces.assert_called_once_with(
            limit=5, status="error", agent_id="planner", query="weather")

    def test_list_bad_limit_type(self):
        # Flask type=int falls back to default 50 on parse failure
        with patch("orbit.core.trace_bp.get_execution_tracer") as gt:
            gt.return_value.list_traces.return_value = []
            r = self.client.get("/api/traces?limit=abc")
        gt.return_value.list_traces.assert_called_once_with(
            limit=50, status="", agent_id="", query="")


class TestGetTrace(TraceBpBase):
    def test_found(self):
        with patch("orbit.core.trace_bp.get_execution_tracer") as gt:
            gt.return_value.get_trace.return_value = {"id": "t1", "spans": []}
            r = self.client.get("/api/traces/t1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], "t1")

    def test_not_found_404(self):
        with patch("orbit.core.trace_bp.get_execution_tracer") as gt:
            gt.return_value.get_trace.return_value = None
            r = self.client.get("/api/traces/nope")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"], "Not found")


class TestStats(TraceBpBase):
    def test_stats(self):
        with patch("orbit.core.trace_bp.get_execution_tracer") as gt:
            gt.return_value.get_stats.return_value = {"total": 10, "errors": 2}
            r = self.client.get("/api/traces/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 10)


class TestSlowest(TraceBpBase):
    def test_slowest_default(self):
        with patch("orbit.core.trace_bp.get_execution_tracer") as gt:
            gt.return_value.get_slowest.return_value = []
            r = self.client.get("/api/traces/slowest")
        gt.return_value.get_slowest.assert_called_once_with(10)

    def test_slowest_limit(self):
        with patch("orbit.core.trace_bp.get_execution_tracer") as gt:
            gt.return_value.get_slowest.return_value = [{"id": "t"}]
            r = self.client.get("/api/traces/slowest?limit=3")
        gt.return_value.get_slowest.assert_called_once_with(3)


class TestErrors(TraceBpBase):
    def test_errors_default(self):
        with patch("orbit.core.trace_bp.get_execution_tracer") as gt:
            gt.return_value.get_errors.return_value = []
            r = self.client.get("/api/traces/errors")
        gt.return_value.get_errors.assert_called_once_with(20)

    def test_errors_limit(self):
        with patch("orbit.core.trace_bp.get_execution_tracer") as gt:
            gt.return_value.get_errors.return_value = []
            r = self.client.get("/api/traces/errors?limit=7")
        gt.return_value.get_errors.assert_called_once_with(7)


class TestClear(TraceBpBase):
    def test_clear(self):
        with patch("orbit.core.trace_bp.get_execution_tracer") as gt:
            r = self.client.post("/api/traces/clear")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "cleared")
        gt.return_value.clear.assert_called_once()


class TestManualStart(TraceBpBase):
    def test_start_defaults(self):
        with patch("orbit.core.trace_bp.get_execution_tracer") as gt:
            gt.return_value.start_trace.return_value = "tr1"
            r = self.client.post("/api/traces/manual/start", json={})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["trace_id"], "tr1")
        gt.return_value.start_trace.assert_called_once_with(query="", agent_id="")

    def test_start_with_fields(self):
        with patch("orbit.core.trace_bp.get_execution_tracer") as gt:
            gt.return_value.start_trace.return_value = "tr2"
            r = self.client.post("/api/traces/manual/start", json={"query": "q", "agent_id": "a"})
        gt.return_value.start_trace.assert_called_once_with(query="q", agent_id="a")

    def test_start_no_body(self):
        with patch("orbit.core.trace_bp.get_execution_tracer") as gt:
            gt.return_value.start_trace.return_value = "tr3"
            r = self.client.post("/api/traces/manual/start")
        self.assertEqual(r.status_code, 200)


class TestManualSpan(TraceBpBase):
    def test_span_defaults(self):
        with patch("orbit.core.trace_bp.get_execution_tracer") as gt:
            gt.return_value.start_span.return_value = "sp1"
            r = self.client.post("/api/traces/manual/t1/span", json={"name": "myspan"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["span_id"], "sp1")
        gt.return_value.start_span.assert_called_once_with(
            "t1", "myspan", span_type="custom", parent_id="",
            agent_id="", tool_name="", input_preview="")

    def test_span_all_fields(self):
        with patch("orbit.core.trace_bp.get_execution_tracer") as gt:
            gt.return_value.start_span.return_value = "sp2"
            r = self.client.post("/api/traces/manual/t1/span", json={
                "name": "n", "span_type": "llm", "parent_id": "p",
                "agent_id": "ag", "tool_name": "calc", "input_preview": "in",
            })
        gt.return_value.start_span.assert_called_once_with(
            "t1", "n", span_type="llm", parent_id="p",
            agent_id="ag", tool_name="calc", input_preview="in")

    def test_span_missing_name_400(self):
        r = self.client.post("/api/traces/manual/t1/span", json={"span_type": "x"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("name required", r.get_json()["error"])

    def test_span_no_body_400(self):
        r = self.client.post("/api/traces/manual/t1/span")
        self.assertEqual(r.status_code, 400)


class TestManualEndSpan(TraceBpBase):
    def test_end_span_defaults(self):
        with patch("orbit.core.trace_bp.get_execution_tracer") as gt:
            r = self.client.post("/api/traces/manual/t1/span/sp1/end", json={})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        gt.return_value.end_span.assert_called_once_with(
            "t1", "sp1", status="ok", error="", output_preview="",
            tokens_in=0, tokens_out=0, cost_usd=0.0)

    def test_end_span_full(self):
        with patch("orbit.core.trace_bp.get_execution_tracer") as gt:
            r = self.client.post("/api/traces/manual/t1/span/sp1/end", json={
                "status": "error", "error": "boom", "output_preview": "out",
                "tokens_in": 10, "tokens_out": 20, "cost_usd": 0.005,
            })
        gt.return_value.end_span.assert_called_once_with(
            "t1", "sp1", status="error", error="boom", output_preview="out",
            tokens_in=10, tokens_out=20, cost_usd=0.005)

    def test_end_span_no_body(self):
        with patch("orbit.core.trace_bp.get_execution_tracer") as gt:
            r = self.client.post("/api/traces/manual/t1/span/sp1/end")
        self.assertEqual(r.status_code, 200)


class TestManualEndTrace(TraceBpBase):
    def test_end_trace_defaults(self):
        with patch("orbit.core.trace_bp.get_execution_tracer") as gt:
            r = self.client.post("/api/traces/manual/t1/end", json={})
        self.assertEqual(r.status_code, 200)
        gt.return_value.end_trace.assert_called_once_with(
            "t1", status="ok", result="", error="")

    def test_end_trace_full(self):
        with patch("orbit.core.trace_bp.get_execution_tracer") as gt:
            r = self.client.post("/api/traces/manual/t1/end", json={
                "status": "error", "result": "partial", "error": "failed",
            })
        gt.return_value.end_trace.assert_called_once_with(
            "t1", status="error", result="partial", error="failed")

    def test_end_trace_no_body(self):
        with patch("orbit.core.trace_bp.get_execution_tracer") as gt:
            r = self.client.post("/api/traces/manual/t1/end")
        self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()
