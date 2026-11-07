"""Unit tests for orbit/orbit/core/long_horizon_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.long_horizon_bp import horizon_bp


class TestLongHorizonBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(horizon_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(horizon_bp.name, "horizon")

    def test_url_prefix(self):
        self.assertEqual(horizon_bp.url_prefix, "/api/horizon")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/horizon/start", "/api/horizon/status", "/api/horizon/advance", "/api/horizon/stop"]:
            self.assertIn(p, rules)

    def test_start_missing_goal_400(self):
        r = self.client.post("/api/horizon/start", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_start_success(self):
        with patch("orbit.core.long_horizon_bp.get_long_horizon") as gh:
            gh.return_value.start_goal.return_value = {"id": "g1", "goal": "do x"}
            r = self.client.post("/api/horizon/start", json={"goal": "do x"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        self.assertEqual(r.get_json()["goal"]["id"], "g1")
        gh.return_value.start_goal.assert_called_once_with("do x")

    def test_start_value_error_400(self):
        with patch("orbit.core.long_horizon_bp.get_long_horizon") as gh:
            gh.return_value.start_goal.side_effect = ValueError("bad goal")
            r = self.client.post("/api/horizon/start", json={"goal": "x"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_start_no_body(self):
        r = self.client.post("/api/horizon/start")
        self.assertEqual(r.status_code, 400)

    def test_status(self):
        with patch("orbit.core.long_horizon_bp.get_long_horizon") as gh:
            gh.return_value.status.return_value = {"running": True}
            r = self.client.get("/api/horizon/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["running"], True)

    def test_advance(self):
        with patch("orbit.core.long_horizon_bp.get_long_horizon") as gh:
            gh.return_value.advance.return_value = {"id": "g1"}
            r = self.client.post("/api/horizon/advance", json={"id": "g1"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        self.assertEqual(r.get_json()["goal"]["id"], "g1")
        gh.return_value.advance.assert_called_once_with(goal_id="g1")

    def test_advance_none(self):
        with patch("orbit.core.long_horizon_bp.get_long_horizon") as gh:
            gh.return_value.advance.return_value = None
            r = self.client.post("/api/horizon/advance", json={})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()["ok"])
        self.assertIsNone(r.get_json()["goal"])

    def test_stop(self):
        with patch("orbit.core.long_horizon_bp.get_long_horizon") as gh:
            r = self.client.post("/api/horizon/stop")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        gh.return_value.stop_daemon.assert_called_once()


if __name__ == "__main__":
    unittest.main()
