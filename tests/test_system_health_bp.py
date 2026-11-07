"""Unit tests for orbit/orbit/core/system_health_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.system_health_bp import system_health_bp


class TestSystemHealthBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(system_health_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(system_health_bp.name, "system_health_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/system-health/snapshot", "/api/system-health/processes",
                  "/api/system-health/alerts", "/api/system-health/history",
                  "/api/system-health/stats"]:
            self.assertIn(p, rules)

    def test_snapshot(self):
        with patch("orbit.core.system_health_bp.get_system_health") as gs:
            gs.return_value.get_snapshot.return_value = {"cpu": 10}
            r = self.client.get("/api/system-health/snapshot")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["cpu"], 10)

    def test_processes(self):
        with patch("orbit.core.system_health_bp.get_system_health") as gs:
            gs.return_value.get_top_processes.return_value = [{"pid": 1}]
            r = self.client.get("/api/system-health/processes?n=3")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["processes"], [{"pid": 1}])
        gs.return_value.get_top_processes.assert_called_once_with(3)

    def test_processes_default(self):
        with patch("orbit.core.system_health_bp.get_system_health") as gs:
            gs.return_value.get_top_processes.return_value = []
            r = self.client.get("/api/system-health/processes")
        gs.return_value.get_top_processes.assert_called_once_with(5)

    def test_alerts(self):
        with patch("orbit.core.system_health_bp.get_system_health") as gs:
            gs.return_value.get_alerts.return_value = [{"msg": "x"}]
            r = self.client.get("/api/system-health/alerts?limit=2")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["alerts"], [{"msg": "x"}])
        gs.return_value.get_alerts.assert_called_once_with(2)

    def test_alerts_default(self):
        with patch("orbit.core.system_health_bp.get_system_health") as gs:
            gs.return_value.get_alerts.return_value = []
            r = self.client.get("/api/system-health/alerts")
        gs.return_value.get_alerts.assert_called_once_with(10)

    def test_history(self):
        with patch("orbit.core.system_health_bp.get_system_health") as gs:
            gs.return_value.get_history.return_value = [{"h": 1}]
            r = self.client.get("/api/system-health/history?limit=4")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["history"], [{"h": 1}])
        gs.return_value.get_history.assert_called_once_with(4)

    def test_history_default(self):
        with patch("orbit.core.system_health_bp.get_system_health") as gs:
            gs.return_value.get_history.return_value = []
            r = self.client.get("/api/system-health/history")
        gs.return_value.get_history.assert_called_once_with(20)

    def test_stats(self):
        with patch("orbit.core.system_health_bp.get_system_health") as gs:
            gs.return_value.get_stats.return_value = {"uptime": 100}
            r = self.client.get("/api/system-health/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["uptime"], 100)


if __name__ == "__main__":
    unittest.main()
