"""Unit tests for orbit/orbit/core/perf_profiler_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.perf_profiler_bp import perf_profiler_bp


class TestPerfProfilerBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(perf_profiler_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(perf_profiler_bp.name, "perf_profiler_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/perf/dashboard", "/api/perf/agents", "/api/perf/tools", "/api/perf/queries",
                  "/api/perf/timeseries", "/api/perf/bottlenecks", "/api/perf/regressions",
                  "/api/perf/record"]:
            self.assertIn(p, rules)

    def test_dashboard(self):
        with patch("orbit.core.perf_profiler_bp.get_profiler") as gp:
            gp.return_value.get_dashboard.return_value = {"ok": True}
            r = self.client.get("/api/perf/dashboard")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])

    def test_agents(self):
        with patch("orbit.core.perf_profiler_bp.get_profiler") as gp:
            gp.return_value.get_agent_stats.return_value = {"agents": 2}
            r = self.client.get("/api/perf/agents")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["agents"], 2)

    def test_tools(self):
        with patch("orbit.core.perf_profiler_bp.get_profiler") as gp:
            gp.return_value.get_tool_stats.return_value = {"tools": 3}
            r = self.client.get("/api/perf/tools")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["tools"], 3)

    def test_queries(self):
        with patch("orbit.core.perf_profiler_bp.get_profiler") as gp:
            gp.return_value.get_query_stats.return_value = {"q": 1}
            r = self.client.get("/api/perf/queries")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["q"], 1)

    def test_timeseries(self):
        with patch("orbit.core.perf_profiler_bp.get_profiler") as gp:
            gp.return_value.get_time_series.return_value = [1, 2]
            r = self.client.get("/api/perf/timeseries?minutes=30")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), [1, 2])
        gp.return_value.get_time_series.assert_called_once_with(30)

    def test_timeseries_default(self):
        with patch("orbit.core.perf_profiler_bp.get_profiler") as gp:
            gp.return_value.get_time_series.return_value = []
            r = self.client.get("/api/perf/timeseries")
        gp.return_value.get_time_series.assert_called_once_with(60)

    def test_bottlenecks(self):
        with patch("orbit.core.perf_profiler_bp.get_profiler") as gp:
            gp.return_value.detect_bottlenecks.return_value = [{"b": 1}]
            r = self.client.get("/api/perf/bottlenecks?threshold=1000")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), [{"b": 1}])
        gp.return_value.detect_bottlenecks.assert_called_once_with(1000.0)

    def test_bottlenecks_default(self):
        with patch("orbit.core.perf_profiler_bp.get_profiler") as gp:
            gp.return_value.detect_bottlenecks.return_value = []
            r = self.client.get("/api/perf/bottlenecks")
        gp.return_value.detect_bottlenecks.assert_called_once_with(2000.0)

    def test_regressions(self):
        with patch("orbit.core.perf_profiler_bp.get_profiler") as gp:
            gp.return_value.detect_regressions.return_value = [{"r": 1}]
            r = self.client.get("/api/perf/regressions?window=30")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), [{"r": 1}])
        gp.return_value.detect_regressions.assert_called_once_with(30)

    def test_regressions_default(self):
        with patch("orbit.core.perf_profiler_bp.get_profiler") as gp:
            gp.return_value.detect_regressions.return_value = []
            r = self.client.get("/api/perf/regressions")
        gp.return_value.detect_regressions.assert_called_once_with(60)

    def test_record_missing_component_400(self):
        r = self.client.post("/api/perf/record", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_record_success(self):
        with patch("orbit.core.perf_profiler_bp.get_profiler") as gp:
            r = self.client.post("/api/perf/record", json={
                "component": "TAS", "type": "agent", "operation": "exec",
                "latency_ms": 12.5, "success": False, "error": "boom"
            })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "recorded")
        gp.return_value.record.assert_called_once_with("TAS", "agent", "exec", 12.5, False, error="boom")

    def test_record_defaults(self):
        with patch("orbit.core.perf_profiler_bp.get_profiler") as gp:
            r = self.client.post("/api/perf/record", json={"component": "TAS"})
        gp.return_value.record.assert_called_once_with("TAS", "system", "unknown", 0, True, error=None)

    def test_record_no_body(self):
        r = self.client.post("/api/perf/record")
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
