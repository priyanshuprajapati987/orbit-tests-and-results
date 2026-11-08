"""Unit tests for orbit/orbit/core/time_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.time_bp import time_bp


class TestTimeBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(time_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(time_bp.name, "time")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/time/start", "/api/time/stop", "/api/time/active", "/api/time/pomodoro",
                  "/api/time/report", "/api/time/streak", "/api/time/stats"]:
            self.assertIn(p, rules)

    def test_start_success(self):
        with patch("orbit.core.time_bp.get_time_tracker") as gt:
            gt.return_value.start_session.return_value = {"started": True}
            r = self.client.post("/api/time/start", json={"label": "coding", "goal_id": "g1"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["started"])
        gt.return_value.start_session.assert_called_once_with("coding", "g1")

    def test_start_error_in_result_409(self):
        with patch("orbit.core.time_bp.get_time_tracker") as gt:
            gt.return_value.start_session.return_value = {"error": "already running"}
            r = self.client.post("/api/time/start", json={"label": "coding"})
        self.assertEqual(r.status_code, 409)
        self.assertIn("error", r.get_json())

    def test_start_defaults(self):
        with patch("orbit.core.time_bp.get_time_tracker") as gt:
            gt.return_value.start_session.return_value = {"started": True}
            r = self.client.post("/api/time/start", json={})
        gt.return_value.start_session.assert_called_once_with("coding", "")

    def test_start_no_body(self):
        with patch("orbit.core.time_bp.get_time_tracker") as gt:
            gt.return_value.start_session.return_value = {"started": True}
            r = self.client.post("/api/time/start")
        gt.return_value.start_session.assert_called_once_with("coding", "")

    def test_start_exception_500(self):
        with patch("orbit.core.time_bp.get_time_tracker") as gt:
            gt.return_value.start_session.side_effect = RuntimeError("boom")
            r = self.client.post("/api/time/start", json={"label": "x"})
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_stop_success(self):
        with patch("orbit.core.time_bp.get_time_tracker") as gt:
            gt.return_value.stop_session.return_value = {"stopped": True}
            r = self.client.post("/api/time/stop")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["stopped"])

    def test_stop_no_active_404(self):
        with patch("orbit.core.time_bp.get_time_tracker") as gt:
            gt.return_value.stop_session.return_value = None
            r = self.client.post("/api/time/stop")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_stop_exception_500(self):
        with patch("orbit.core.time_bp.get_time_tracker") as gt:
            gt.return_value.stop_session.side_effect = RuntimeError("boom")
            r = self.client.post("/api/time/stop")
        self.assertEqual(r.status_code, 500)

    def test_active(self):
        with patch("orbit.core.time_bp.get_time_tracker") as gt:
            gt.return_value.get_active.return_value = {"label": "coding"}
            r = self.client.get("/api/time/active")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["active"], {"label": "coding"})

    def test_active_exception_500(self):
        with patch("orbit.core.time_bp.get_time_tracker") as gt:
            gt.return_value.get_active.side_effect = RuntimeError("boom")
            r = self.client.get("/api/time/active")
        self.assertEqual(r.status_code, 500)

    def test_pomodoro(self):
        with patch("orbit.core.time_bp.get_time_tracker") as gt:
            gt.return_value.start_pomodoro.return_value = {"started": True}
            r = self.client.post("/api/time/pomodoro")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["started"])

    def test_pomodoro_exception_500(self):
        with patch("orbit.core.time_bp.get_time_tracker") as gt:
            gt.return_value.start_pomodoro.side_effect = RuntimeError("boom")
            r = self.client.post("/api/time/pomodoro")
        self.assertEqual(r.status_code, 500)

    def test_report(self):
        with patch("orbit.core.time_bp.get_time_tracker") as gt:
            gt.return_value.get_report.return_value = {"total": 10}
            r = self.client.get("/api/time/report?period=week")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 10)
        gt.return_value.get_report.assert_called_once_with("week")

    def test_report_default(self):
        with patch("orbit.core.time_bp.get_time_tracker") as gt:
            gt.return_value.get_report.return_value = {}
            r = self.client.get("/api/time/report")
        gt.return_value.get_report.assert_called_once_with("today")

    def test_report_exception_500(self):
        with patch("orbit.core.time_bp.get_time_tracker") as gt:
            gt.return_value.get_report.side_effect = RuntimeError("boom")
            r = self.client.get("/api/time/report")
        self.assertEqual(r.status_code, 500)

    def test_streak(self):
        with patch("orbit.core.time_bp.get_time_tracker") as gt:
            gt.return_value.get_streak.return_value = {"streak": 5}
            r = self.client.get("/api/time/streak")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["streak"], 5)

    def test_streak_exception_500(self):
        with patch("orbit.core.time_bp.get_time_tracker") as gt:
            gt.return_value.get_streak.side_effect = RuntimeError("boom")
            r = self.client.get("/api/time/streak")
        self.assertEqual(r.status_code, 500)

    def test_stats(self):
        with patch("orbit.core.time_bp.get_time_tracker") as gt:
            gt.return_value.get_stats.return_value = {"sessions": 3}
            r = self.client.get("/api/time/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["sessions"], 3)

    def test_stats_exception_500(self):
        with patch("orbit.core.time_bp.get_time_tracker") as gt:
            gt.return_value.get_stats.side_effect = RuntimeError("boom")
            r = self.client.get("/api/time/stats")
        self.assertEqual(r.status_code, 500)


if __name__ == "__main__":
    unittest.main()
