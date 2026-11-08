"""Unit tests for orbit/orbit/core/auto_healer_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.auto_healer_bp import auto_healer_bp


class TestAutoHealerBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(auto_healer_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(auto_healer_bp.name, "auto_healer_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/auto-heal/status", "/api/auto-heal/probes", "/api/auto-heal/probe/<name>",
                  "/api/auto-heal/trigger", "/api/auto-heal/enable",
                  "/api/auto-heal/start-monitor", "/api/auto-heal/stop-monitor"]:
            self.assertIn(p, rules)

    def test_status(self):
        with patch("orbit.core.auto_healer_bp.get_auto_healer") as gh:
            gh.return_value.get_status.return_value = {"healthy": True}
            r = self.client.get("/api/auto-heal/status")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["healthy"])

    def test_probes(self):
        with patch("orbit.core.auto_healer_bp.get_auto_healer") as gh:
            gh.return_value.run_all_probes.return_value = [{"name": "p1"}]
            r = self.client.get("/api/auto-heal/probes")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), [{"name": "p1"}])

    def test_probe(self):
        with patch("orbit.core.auto_healer_bp.get_auto_healer") as gh:
            gh.return_value.run_probe.return_value = {"name": "p1", "ok": True}
            r = self.client.get("/api/auto-heal/probe/p1")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        gh.return_value.run_probe.assert_called_once_with("p1")

    def test_trigger_missing_component_400(self):
        r = self.client.post("/api/auto-heal/trigger", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_trigger_success(self):
        with patch("orbit.core.auto_healer_bp.get_auto_healer") as gh:
            healer = gh.return_value
            action = MagicMock()
            action.action_id = "a1"
            action.status = MagicMock(value="healed")
            action.result = "ok"
            action.duration_ms = 12.5
            healer.trigger_heal.return_value = action
            r = self.client.post("/api/auto-heal/trigger", json={"component": "db", "issue": "down"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["action_id"], "a1")
        self.assertEqual(body["status"], "healed")
        self.assertEqual(body["result"], "ok")
        self.assertEqual(body["duration_ms"], 12.5)
        healer.trigger_heal.assert_called_once_with("db", "down")

    def test_trigger_default_issue(self):
        with patch("orbit.core.auto_healer_bp.get_auto_healer") as gh:
            healer = gh.return_value
            action = MagicMock()
            action.action_id = "a2"
            action.status = MagicMock(value="healed")
            action.result = "ok"
            action.duration_ms = 1.0
            healer.trigger_heal.return_value = action
            r = self.client.post("/api/auto-heal/trigger", json={"component": "db"})
        healer.trigger_heal.assert_called_once_with("db", "manual")

    def test_trigger_no_body(self):
        r = self.client.post("/api/auto-heal/trigger")
        self.assertEqual(r.status_code, 400)

    def test_enable(self):
        with patch("orbit.core.auto_healer_bp.get_auto_healer") as gh:
            r = self.client.post("/api/auto-heal/enable", json={"enabled": False})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()["enabled"])
        gh.return_value.set_enabled.assert_called_once_with(False)

    def test_enable_default(self):
        with patch("orbit.core.auto_healer_bp.get_auto_healer") as gh:
            r = self.client.post("/api/auto-heal/enable", json={})
        gh.return_value.set_enabled.assert_called_once_with(True)

    def test_enable_no_body(self):
        with patch("orbit.core.auto_healer_bp.get_auto_healer") as gh:
            r = self.client.post("/api/auto-heal/enable")
        gh.return_value.set_enabled.assert_called_once_with(True)

    def test_start_monitor(self):
        with patch("orbit.core.auto_healer_bp.get_auto_healer") as gh:
            r = self.client.post("/api/auto-heal/start-monitor", json={"interval": 10})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "started")
        self.assertEqual(r.get_json()["interval"], 10)
        gh.return_value.start_monitor.assert_called_once_with(10)

    def test_start_monitor_clamp_low(self):
        with patch("orbit.core.auto_healer_bp.get_auto_healer") as gh:
            r = self.client.post("/api/auto-heal/start-monitor", json={"interval": 1})
        self.assertEqual(r.get_json()["interval"], 5)

    def test_start_monitor_clamp_high(self):
        with patch("orbit.core.auto_healer_bp.get_auto_healer") as gh:
            r = self.client.post("/api/auto-heal/start-monitor", json={"interval": 9999})
        self.assertEqual(r.get_json()["interval"], 3600)

    def test_start_monitor_bad_interval(self):
        with patch("orbit.core.auto_healer_bp.get_auto_healer") as gh:
            r = self.client.post("/api/auto-heal/start-monitor", json={"interval": "abc"})
        self.assertEqual(r.get_json()["interval"], 30)

    def test_start_monitor_no_body(self):
        with patch("orbit.core.auto_healer_bp.get_auto_healer") as gh:
            r = self.client.post("/api/auto-heal/start-monitor")
        self.assertEqual(r.get_json()["interval"], 30)

    def test_stop_monitor(self):
        with patch("orbit.core.auto_healer_bp.get_auto_healer") as gh:
            r = self.client.post("/api/auto-heal/stop-monitor")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "stopped")
        gh.return_value.stop_monitor.assert_called_once()


if __name__ == "__main__":
    unittest.main()
