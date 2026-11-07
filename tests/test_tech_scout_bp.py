"""Unit tests for orbit/orbit/core/tech_scout_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.tech_scout_bp import tech_scout_bp


class TestTechScoutBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(tech_scout_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(tech_scout_bp.name, "tech_scout")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/scout/latest", "/api/scout/history", "/api/scout/run"]:
            self.assertIn(p, rules)

    def test_latest_empty(self):
        with patch("orbit.core.tech_scout_bp.get_scout") as gs:
            gs.return_value.get_latest.return_value = None
            r = self.client.get("/api/scout/latest")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "empty")

    def test_latest_ok(self):
        with patch("orbit.core.tech_scout_bp.get_scout") as gs:
            gs.return_value.get_latest.return_value = {"findings": 3}
            r = self.client.get("/api/scout/latest")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["report"]["findings"], 3)

    def test_history(self):
        with patch("orbit.core.tech_scout_bp.get_scout") as gs:
            gs.return_value.get_history.return_value = [{"d": 1}, {"d": 2}]
            r = self.client.get("/api/scout/history?days=3")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["count"], 2)
        self.assertEqual(len(body["reports"]), 2)
        gs.return_value.get_history.assert_called_once_with(3)

    def test_history_default(self):
        with patch("orbit.core.tech_scout_bp.get_scout") as gs:
            gs.return_value.get_history.return_value = []
            r = self.client.get("/api/scout/history")
        gs.return_value.get_history.assert_called_once_with(7)

    def test_run(self):
        with patch("orbit.core.tech_scout_bp.get_scout") as gs:
            gs.return_value.scan_all.return_value = {"scanned": True}
            r = self.client.post("/api/scout/run")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertEqual(r.get_json()["report"], {"scanned": True})


if __name__ == "__main__":
    unittest.main()
