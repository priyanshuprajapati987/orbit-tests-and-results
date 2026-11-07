"""Unit tests for orbit/orbit/core/timer_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.timer_bp import timer_bp


class TestTimerBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(timer_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(timer_bp.name, "timer_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/timer/countdown", "/api/timer/cancel/<timer_id>", "/api/timer/list",
                  "/api/timer/stopwatch/start", "/api/timer/stopwatch/stop", "/api/timer/stopwatch/lap"]:
            self.assertIn(p, rules)

    def test_countdown(self):
        with patch("orbit.core.timer_bp.get_timer") as gt:
            gt.return_value.countdown.return_value = {"id": "t1"}
            r = self.client.post("/api/timer/countdown", json={"seconds": 30, "label": "x"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], "t1")
        gt.return_value.countdown.assert_called_once_with(30, "x")

    def test_countdown_defaults(self):
        with patch("orbit.core.timer_bp.get_timer") as gt:
            gt.return_value.countdown.return_value = {"id": "t2"}
            r = self.client.post("/api/timer/countdown", json={})
        gt.return_value.countdown.assert_called_once_with(60, "")

    def test_countdown_no_body(self):
        with patch("orbit.core.timer_bp.get_timer") as gt:
            gt.return_value.countdown.return_value = {"id": "t3"}
            r = self.client.post("/api/timer/countdown")
        gt.return_value.countdown.assert_called_once_with(60, "")

    def test_cancel(self):
        with patch("orbit.core.timer_bp.get_timer") as gt:
            gt.return_value.cancel.return_value = {"cancelled": True}
            r = self.client.post("/api/timer/cancel/abc")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["cancelled"])
        gt.return_value.cancel.assert_called_once_with("abc")

    def test_list(self):
        with patch("orbit.core.timer_bp.get_timer") as gt:
            gt.return_value.get_timers.return_value = ["t1"]
            r = self.client.get("/api/timer/list")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["timers"], ["t1"])

    def test_stopwatch_start(self):
        with patch("orbit.core.timer_bp.get_timer") as gt:
            gt.return_value.stopwatch_start.return_value = {"started": True}
            r = self.client.post("/api/timer/stopwatch/start")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["started"])

    def test_stopwatch_stop(self):
        with patch("orbit.core.timer_bp.get_timer") as gt:
            gt.return_value.stopwatch_stop.return_value = {"elapsed": 5.0}
            r = self.client.post("/api/timer/stopwatch/stop")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["elapsed"], 5.0)

    def test_stopwatch_lap(self):
        with patch("orbit.core.timer_bp.get_timer") as gt:
            gt.return_value.stopwatch_lap.return_value = {"lap": 1}
            r = self.client.post("/api/timer/stopwatch/lap")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["lap"], 1)


if __name__ == "__main__":
    unittest.main()
