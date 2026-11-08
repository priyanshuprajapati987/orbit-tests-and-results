"""Unit tests for orbit/orbit/core/tool_analytics_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.tool_analytics_bp import tool_analytics_bp


class TestToolAnalyticsBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(tool_analytics_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(tool_analytics_bp.name, "tool_analytics")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/tool-analytics/record", "/api/tool-analytics/stats",
                  "/api/tool-analytics/tool/<tool_name>", "/api/tool-analytics/recent",
                  "/api/tool-analytics/trend/<tool_name>"]:
            self.assertIn(p, rules)

    def test_record_missing_tool_name_400(self):
        r = self.client.post("/api/tool-analytics/record", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_record_success(self):
        with patch("orbit.core.tool_analytics_bp.get_tool_analytics") as gta:
            ta = gta.return_value
            inv = MagicMock()
            inv.timestamp = "ts1"
            ta.record.return_value = inv
            r = self.client.post("/api/tool-analytics/record", json={
                "tool_name": "t1", "action": "a", "success": False, "latency_ms": 10.5,
                "error": "e", "input_size": 2, "output_size": 3, "agent_id": "TAS"
            })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertEqual(r.get_json()["invocation_id"], "ts1")
        ta.record.assert_called_once_with(
            "t1", action="a", success=False, latency_ms=10.5, error="e",
            input_size=2.0, output_size=3.0, agent_id="TAS"
        )

    def test_record_defaults(self):
        with patch("orbit.core.tool_analytics_bp.get_tool_analytics") as gta:
            ta = gta.return_value
            inv = MagicMock()
            inv.timestamp = "ts2"
            ta.record.return_value = inv
            r = self.client.post("/api/tool-analytics/record", json={"tool_name": "t1"})
        ta.record.assert_called_once_with(
            "t1", action="", success=True, latency_ms=0.0, error="",
            input_size=0.0, output_size=0.0, agent_id=""
        )

    def test_record_no_body(self):
        r = self.client.post("/api/tool-analytics/record")
        self.assertEqual(r.status_code, 400)

    def test_record_invalid_payload_400(self):
        with patch("orbit.core.tool_analytics_bp.get_tool_analytics") as gta:
            ta = gta.return_value
            ta.record.side_effect = ValueError("bad")
            r = self.client.post("/api/tool-analytics/record", json={"tool_name": "t1"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_stats(self):
        with patch("orbit.core.tool_analytics_bp.get_all_tool_stats", return_value={"total": 5}):
            r = self.client.get("/api/tool-analytics/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)

    def test_tool_stats(self):
        with patch("orbit.core.tool_analytics_bp.get_tool_analytics") as ga:
            ga.return_value.get_tool_stats.return_value = {"calls": 3}
            r = self.client.get("/api/tool-analytics/tool/mytool")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["calls"], 3)
        ga.return_value.get_tool_stats.assert_called_once_with("mytool")

    def test_recent(self):
        with patch("orbit.core.tool_analytics_bp.get_tool_analytics") as ga:
            ga.return_value.get_recent.return_value = [{"id": 1}]
            r = self.client.get("/api/tool-analytics/recent?tool=t1&limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["invocations"], [{"id": 1}])
        ga.return_value.get_recent.assert_called_once_with("t1", 5)

    def test_recent_defaults(self):
        with patch("orbit.core.tool_analytics_bp.get_tool_analytics") as ga:
            ga.return_value.get_recent.return_value = []
            r = self.client.get("/api/tool-analytics/recent")
        ga.return_value.get_recent.assert_called_once_with("", 20)

    def test_recent_limit_clamped(self):
        with patch("orbit.core.tool_analytics_bp.get_tool_analytics") as ga:
            ga.return_value.get_recent.return_value = []
            r = self.client.get("/api/tool-analytics/recent?limit=500")
        ga.return_value.get_recent.assert_called_once_with("", 200)

    def test_trend(self):
        with patch("orbit.core.tool_analytics_bp.get_tool_analytics") as ga:
            ga.return_value.get_trend.return_value = {"trend": "up"}
            r = self.client.get("/api/tool-analytics/trend/mytool?hours=12")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["trend"], "up")
        ga.return_value.get_trend.assert_called_once_with("mytool", 12)

    def test_trend_defaults(self):
        with patch("orbit.core.tool_analytics_bp.get_tool_analytics") as ga:
            ga.return_value.get_trend.return_value = {}
            r = self.client.get("/api/tool-analytics/trend/mytool")
        ga.return_value.get_trend.assert_called_once_with("mytool", 24)

    def test_trend_clamped(self):
        with patch("orbit.core.tool_analytics_bp.get_tool_analytics") as ga:
            ga.return_value.get_trend.return_value = {}
            r = self.client.get("/api/tool-analytics/trend/mytool?hours=10000")
        ga.return_value.get_trend.assert_called_once_with("mytool", 720)


if __name__ == "__main__":
    unittest.main()
