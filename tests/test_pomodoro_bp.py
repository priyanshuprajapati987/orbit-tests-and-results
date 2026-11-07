"""Unit tests for orbit/orbit/core/pomodoro_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.pomodoro_bp import pomodoro_bp


class TestPomodoroBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(pomodoro_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(pomodoro_bp.name, "pomodoro_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/pomodoro/start", "/api/pomodoro/stop", "/api/pomodoro/status"]:
            self.assertIn(p, rules)

    def test_start(self):
        with patch("orbit.core.pomodoro_bp.get_pomodoro") as gp:
            gp.return_value.start.return_value = {"started": True}
            r = self.client.post("/api/pomodoro/start", json={"focus": 30, "break": 10})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["started"])
        gp.return_value.start.assert_called_once_with(30, 10)

    def test_start_defaults(self):
        with patch("orbit.core.pomodoro_bp.get_pomodoro") as gp:
            gp.return_value.start.return_value = {"started": True}
            r = self.client.post("/api/pomodoro/start", json={})
        gp.return_value.start.assert_called_once_with(25, 5)

    def test_start_no_body(self):
        with patch("orbit.core.pomodoro_bp.get_pomodoro") as gp:
            gp.return_value.start.return_value = {"started": True}
            r = self.client.post("/api/pomodoro/start")
        gp.return_value.start.assert_called_once_with(25, 5)

    def test_stop(self):
        with patch("orbit.core.pomodoro_bp.get_pomodoro") as gp:
            gp.return_value.stop.return_value = {"stopped": True}
            r = self.client.post("/api/pomodoro/stop")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["stopped"])

    def test_status(self):
        with patch("orbit.core.pomodoro_bp.get_pomodoro") as gp:
            gp.return_value.status.return_value = {"running": False}
            r = self.client.get("/api/pomodoro/status")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()["running"])


if __name__ == "__main__":
    unittest.main()
