"""Unit tests for orbit/orbit/core/whatif_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.whatif_bp import whatif_bp


class TestWhatifBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(whatif_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(whatif_bp.name, "whatif")

    def test_url_prefix(self):
        self.assertEqual(whatif_bp.url_prefix, "/api/whatif")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/whatif/simulate", rules)
        self.assertIn("/api/whatif/stats", rules)

    def test_simulate_success(self):
        with patch("orbit.core.whatif_bp.simulate", return_value={"ok": True, "predicted": "fine"}):
            r = self.client.post("/api/whatif/simulate", json={"action": "delete file"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])

    def test_simulate_failure_400(self):
        with patch("orbit.core.whatif_bp.simulate", return_value={"ok": False, "error": "empty action"}):
            r = self.client.post("/api/whatif/simulate", json={"action": ""})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.get_json()["ok"])

    def test_simulate_no_body(self):
        with patch("orbit.core.whatif_bp.simulate", return_value={"ok": False, "error": "empty action"}):
            r = self.client.post("/api/whatif/simulate")
        self.assertEqual(r.status_code, 400)

    def test_stats(self):
        r = self.client.get("/api/whatif/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "idle")


if __name__ == "__main__":
    unittest.main()
