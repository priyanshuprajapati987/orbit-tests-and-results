"""Unit tests for orbit/orbit/core/commander_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.commander_bp import commander_bp


class TestCommanderBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(commander_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(commander_bp.name, "commander")

    def test_url_prefix(self):
        self.assertEqual(commander_bp.url_prefix, "/api/commander")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/commander/execute", "/api/commander/parse", "/api/commander/status", "/api/commander/history"]:
            self.assertIn(p, rules)

    def test_execute_missing_command_400(self):
        r = self.client.post("/api/commander/execute", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_execute_success(self):
        result = MagicMock()
        result.success = True
        result.message = "ok"
        result.action = "open"
        result.latency_ms = 12.34
        result.data = {"x": 1}
        with patch("orbit.core.commander_bp.get_commander") as gc:
            gc.return_value.execute.return_value = result
            r = self.client.post("/api/commander/execute", json={"command": "open chrome"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["success"])
        self.assertEqual(body["message"], "ok")
        self.assertEqual(body["action"], "open")
        self.assertEqual(body["latency_ms"], 12.3)
        self.assertEqual(body["data"], {"x": 1})
        gc.return_value.execute.assert_called_once_with("open chrome")

    def test_execute_no_body(self):
        r = self.client.post("/api/commander/execute")
        self.assertEqual(r.status_code, 400)

    def test_execute_error(self):
        with patch("orbit.core.commander_bp.get_commander") as gc:
            gc.return_value.execute.side_effect = RuntimeError("boom")
            r = self.client.post("/api/commander/execute", json={"command": "x"})
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_parse_missing_command_400(self):
        r = self.client.post("/api/commander/parse", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_parse_success(self):
        intent = MagicMock()
        intent.action = "open"
        intent.target = "chrome"
        intent.params = {"x": 1}
        intent.confidence = 0.9
        intent.category = "app"
        intent.raw_input = "open chrome"
        with patch("orbit.core.commander.parse_command", return_value=intent):
            r = self.client.post("/api/commander/parse", json={"command": "open chrome"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["action"], "open")
        self.assertEqual(body["target"], "chrome")
        self.assertEqual(body["params"], {"x": 1})
        self.assertEqual(body["confidence"], 0.9)
        self.assertEqual(body["category"], "app")
        self.assertEqual(body["raw_input"], "open chrome")

    def test_parse_no_body(self):
        r = self.client.post("/api/commander/parse")
        self.assertEqual(r.status_code, 400)

    def test_parse_error(self):
        with patch("orbit.core.commander.parse_command", side_effect=RuntimeError("boom")):
            r = self.client.post("/api/commander/parse", json={"command": "x"})
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_status(self):
        with patch("orbit.core.commander_bp.get_commander") as gc:
            gc.return_value.get_status.return_value = {"running": True}
            r = self.client.get("/api/commander/status")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["running"])

    def test_status_error(self):
        with patch("orbit.core.commander_bp.get_commander") as gc:
            gc.return_value.get_status.side_effect = RuntimeError("boom")
            r = self.client.get("/api/commander/status")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_history(self):
        with patch("orbit.core.commander_bp.get_commander") as gc:
            gc.return_value.get_history.return_value = [{"id": 1}]
            r = self.client.get("/api/commander/history?limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["history"], [{"id": 1}])
        gc.return_value.get_history.assert_called_once_with(5)

    def test_history_default(self):
        with patch("orbit.core.commander_bp.get_commander") as gc:
            gc.return_value.get_history.return_value = []
            r = self.client.get("/api/commander/history")
        gc.return_value.get_history.assert_called_once_with(20)


if __name__ == "__main__":
    unittest.main()
