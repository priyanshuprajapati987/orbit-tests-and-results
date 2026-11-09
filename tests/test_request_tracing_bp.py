"""Unit tests for orbit/orbit/core/request_tracing_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.request_tracing_bp import request_tracing_bp


class TestRequestTracingBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(request_tracing_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(request_tracing_bp.name, "request_tracing")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/tracing/start", "/api/tracing/<trace_id>/span",
                  "/api/tracing/<trace_id>/span/<span_id>/end", "/api/tracing/<trace_id>/end",
                  "/api/tracing/<trace_id>", "/api/tracing/search", "/api/tracing/slowest",
                  "/api/tracing/errors", "/api/tracing/stats"]:
            self.assertIn(p, rules)

    def test_start_trace(self):
        with patch("orbit.core.request_tracing_bp.get_tracer") as gt:
            gt.return_value.start_trace.return_value = "tid1"
            r = self.client.post("/api/tracing/start", json={"request_text": "q", "agent_id": "a1"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["trace_id"], "tid1")
        gt.return_value.start_trace.assert_called_once_with(request_text="q", agent_id="a1")

    def test_start_trace_defaults(self):
        with patch("orbit.core.request_tracing_bp.get_tracer") as gt:
            gt.return_value.start_trace.return_value = "tid2"
            r = self.client.post("/api/tracing/start", json={})
        gt.return_value.start_trace.assert_called_once_with(request_text="", agent_id="")

    def test_start_trace_no_body(self):
        with patch("orbit.core.request_tracing_bp.get_tracer") as gt:
            gt.return_value.start_trace.return_value = "tid3"
            r = self.client.post("/api/tracing/start")
        gt.return_value.start_trace.assert_called_once_with(request_text="", agent_id="")

    def test_start_span_missing_name_400(self):
        r = self.client.post("/api/tracing/t1/span", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_start_span_success(self):
        with patch("orbit.core.request_tracing_bp.get_tracer") as gt:
            gt.return_value.start_span.return_value = "sid1"
            r = self.client.post("/api/tracing/t1/span", json={"name": "n", "service": "s", "parent_id": "p", "attributes": {"k": "v"}})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["span_id"], "sid1")
        gt.return_value.start_span.assert_called_once_with("t1", "n", service="s", parent_id="p", attributes={"k": "v"})

    def test_start_span_defaults(self):
        with patch("orbit.core.request_tracing_bp.get_tracer") as gt:
            gt.return_value.start_span.return_value = "sid2"
            r = self.client.post("/api/tracing/t1/span", json={"name": "n"})
        gt.return_value.start_span.assert_called_once_with("t1", "n", service="", parent_id="", attributes={})

    def test_start_span_no_body(self):
        r = self.client.post("/api/tracing/t1/span")
        self.assertEqual(r.status_code, 400)

    def test_end_span(self):
        with patch("orbit.core.request_tracing_bp.get_tracer") as gt:
            r = self.client.post("/api/tracing/t1/span/s1/end", json={"status": "ok", "error": ""})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        gt.return_value.end_span.assert_called_once_with("t1", "s1", status="ok", error="")

    def test_end_span_defaults(self):
        with patch("orbit.core.request_tracing_bp.get_tracer") as gt:
            r = self.client.post("/api/tracing/t1/span/s1/end", json={})
        gt.return_value.end_span.assert_called_once_with("t1", "s1", status="ok", error="")

    def test_end_span_no_body(self):
        with patch("orbit.core.request_tracing_bp.get_tracer") as gt:
            r = self.client.post("/api/tracing/t1/span/s1/end")
        gt.return_value.end_span.assert_called_once_with("t1", "s1", status="ok", error="")

    def test_end_trace(self):
        with patch("orbit.core.request_tracing_bp.get_tracer") as gt:
            r = self.client.post("/api/tracing/t1/end", json={"status": "ok", "result": "r", "error": ""})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        gt.return_value.end_trace.assert_called_once_with("t1", status="ok", result="r", error="")

    def test_end_trace_defaults(self):
        with patch("orbit.core.request_tracing_bp.get_tracer") as gt:
            r = self.client.post("/api/tracing/t1/end", json={})
        gt.return_value.end_trace.assert_called_once_with("t1", status="ok", result="", error="")

    def test_end_trace_no_body(self):
        with patch("orbit.core.request_tracing_bp.get_tracer") as gt:
            r = self.client.post("/api/tracing/t1/end")
        gt.return_value.end_trace.assert_called_once_with("t1", status="ok", result="", error="")

    def test_get_trace_found(self):
        with patch("orbit.core.request_tracing_bp.get_tracer") as gt:
            gt.return_value.get_trace.return_value = {"id": "t1"}
            r = self.client.get("/api/tracing/t1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], "t1")
        gt.return_value.get_trace.assert_called_once_with("t1")

    def test_get_trace_not_found_404(self):
        with patch("orbit.core.request_tracing_bp.get_tracer") as gt:
            gt.return_value.get_trace.return_value = None
            r = self.client.get("/api/tracing/t1")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_search(self):
        with patch("orbit.core.request_tracing_bp.get_tracer") as gt:
            gt.return_value.search_traces.return_value = [{"id": "t1"}]
            r = self.client.get("/api/tracing/search?q=hi&agent_id=a&status=ok&limit=5")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["traces"], [{"id": "t1"}])
        self.assertEqual(body["count"], 1)
        gt.return_value.search_traces.assert_called_once_with("hi", "a", "ok", 5)

    def test_search_defaults(self):
        with patch("orbit.core.request_tracing_bp.get_tracer") as gt:
            gt.return_value.search_traces.return_value = []
            r = self.client.get("/api/tracing/search")
        gt.return_value.search_traces.assert_called_once_with("", "", "", 20)

    def test_slowest(self):
        with patch("orbit.core.request_tracing_bp.get_tracer") as gt:
            gt.return_value.get_slowest.return_value = [{"id": "t1"}]
            r = self.client.get("/api/tracing/slowest?limit=3")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["traces"], [{"id": "t1"}])
        gt.return_value.get_slowest.assert_called_once_with(3)

    def test_slowest_default(self):
        with patch("orbit.core.request_tracing_bp.get_tracer") as gt:
            gt.return_value.get_slowest.return_value = []
            r = self.client.get("/api/tracing/slowest")
        gt.return_value.get_slowest.assert_called_once_with(10)

    def test_errors(self):
        with patch("orbit.core.request_tracing_bp.get_tracer") as gt:
            gt.return_value.get_error_traces.return_value = [{"id": "t2"}]
            r = self.client.get("/api/tracing/errors?limit=7")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["traces"], [{"id": "t2"}])
        gt.return_value.get_error_traces.assert_called_once_with(7)

    def test_errors_default(self):
        with patch("orbit.core.request_tracing_bp.get_tracer") as gt:
            gt.return_value.get_error_traces.return_value = []
            r = self.client.get("/api/tracing/errors")
        gt.return_value.get_error_traces.assert_called_once_with(20)

    def test_stats(self):
        with patch("orbit.core.request_tracing_bp.get_trace_stats", return_value={"total": 5}):
            r = self.client.get("/api/tracing/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)


if __name__ == "__main__":
    unittest.main()
