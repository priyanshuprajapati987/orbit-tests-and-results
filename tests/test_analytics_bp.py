"""Unit tests for orbit/orbit/core/analytics_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.analytics_bp import analytics_bp


class TestAnalyticsBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(analytics_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(analytics_bp.name, "analytics")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/analytics/summary", "/api/analytics/weekly", "/api/analytics/agents",
                  "/api/analytics/peak-hours", "/api/analytics/track"]:
            self.assertIn(p, rules)

    def test_summary(self):
        with patch("orbit.core.analytics_bp.get_analytics") as ga:
            ga.return_value.get_summary.return_value = {"total": 5}
            r = self.client.get("/api/analytics/summary")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)

    def test_summary_error(self):
        with patch("orbit.core.analytics_bp.get_analytics") as ga:
            ga.return_value.get_summary.side_effect = RuntimeError("boom")
            r = self.client.get("/api/analytics/summary")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_weekly(self):
        with patch("orbit.core.analytics_bp.get_analytics") as ga:
            ga.return_value.get_weekly.return_value = {"week": 1}
            r = self.client.get("/api/analytics/weekly")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["week"], 1)

    def test_weekly_error(self):
        with patch("orbit.core.analytics_bp.get_analytics") as ga:
            ga.return_value.get_weekly.side_effect = RuntimeError("boom")
            r = self.client.get("/api/analytics/weekly")
        self.assertEqual(r.status_code, 500)

    def test_agents(self):
        with patch("orbit.core.analytics_bp.get_analytics") as ga:
            ga.return_value.get_agent_stats.return_value = {"agents": 3}
            r = self.client.get("/api/analytics/agents")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["agents"], 3)

    def test_agents_error(self):
        with patch("orbit.core.analytics_bp.get_analytics") as ga:
            ga.return_value.get_agent_stats.side_effect = RuntimeError("boom")
            r = self.client.get("/api/analytics/agents")
        self.assertEqual(r.status_code, 500)

    def test_peak_hours(self):
        with patch("orbit.core.analytics_bp.get_analytics") as ga:
            ga.return_value.get_peak_hours.return_value = {"peak": 14}
            r = self.client.get("/api/analytics/peak-hours")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["peak"], 14)

    def test_peak_hours_error(self):
        with patch("orbit.core.analytics_bp.get_analytics") as ga:
            ga.return_value.get_peak_hours.side_effect = RuntimeError("boom")
            r = self.client.get("/api/analytics/peak-hours")
        self.assertEqual(r.status_code, 500)

    def test_track(self):
        with patch("orbit.core.analytics_bp.get_analytics") as ga:
            r = self.client.post("/api/analytics/track", json={"type": "click", "details": {"x": 1}})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        ga.return_value.track.assert_called_once_with("click", {"x": 1})

    def test_track_defaults(self):
        with patch("orbit.core.analytics_bp.get_analytics") as ga:
            r = self.client.post("/api/analytics/track", json={})
        ga.return_value.track.assert_called_once_with("unknown", {})

    def test_track_no_body(self):
        with patch("orbit.core.analytics_bp.get_analytics") as ga:
            r = self.client.post("/api/analytics/track")
        ga.return_value.track.assert_called_once_with("unknown", {})

    def test_track_error(self):
        with patch("orbit.core.analytics_bp.get_analytics") as ga:
            ga.return_value.track.side_effect = RuntimeError("boom")
            r = self.client.post("/api/analytics/track", json={"type": "x"})
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())


if __name__ == "__main__":
    unittest.main()
