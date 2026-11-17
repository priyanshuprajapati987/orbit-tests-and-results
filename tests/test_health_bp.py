"""Unit tests for orbit/orbit/core/health_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.health_bp import health_bp


class TestHealthBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(health_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(health_bp.name, "health_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/health/dashboard", "/api/health/components", "/api/health/reliability"]:
            self.assertIn(p, rules)

    def test_dashboard_success(self):
        with patch("orbit.core.monitoring.get_health_dashboard") as mghd, \
             patch("orbit.core.health_check.get_health_system") as ghs:
            mghd.return_value = {"uptime": 100}
            ghs.return_value.get_agent_dashboard.return_value = {"agents": 5}
            r = self.client.get("/api/health/dashboard")
            self.assertEqual(r.status_code, 200)
            body = r.get_json()
            self.assertEqual(body["uptime"], 100)
            self.assertEqual(body["agent_dashboard"], {"agents": 5})

    def test_dashboard_health_check_failure(self):
        with patch("orbit.core.monitoring.get_health_dashboard") as mghd, \
             patch("orbit.core.health_check.get_health_system", side_effect=RuntimeError("boom")):
            mghd.return_value = {"uptime": 100}
            r = self.client.get("/api/health/dashboard")
            self.assertEqual(r.status_code, 200)
            body = r.get_json()
            self.assertEqual(body["uptime"], 100)
            self.assertIsNone(body["agent_dashboard"])

    def test_components(self):
        with patch("orbit.core.monitoring.get_monitoring") as gm:
            gm.return_value.uptime.get_all_components.return_value = ["c1", "c2"]
            r = self.client.get("/api/health/components")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.get_json()["components"], ["c1", "c2"])

    def test_reliability(self):
        with patch("orbit.core.reliability.get_reliability_status") as grs, \
             patch("orbit.core.fallback_chain.get_death_detector") as gdd, \
             patch("orbit.core.fallback_chain.get_switch_metrics") as gsm:
            grs.return_value = {"ok": True}
            gdd.return_value.get_status.return_value = {"dead": False}
            gsm.return_value = {"switches": 3}
            r = self.client.get("/api/health/reliability")
            self.assertEqual(r.status_code, 200)
            body = r.get_json()
            self.assertTrue(body["ok"])
            self.assertEqual(body["death_detection"], {"dead": False})
            self.assertEqual(body["fallback_chain"], {"switches": 3})


if __name__ == "__main__":
    unittest.main()
