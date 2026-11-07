"""Unit tests for orbit/orbit/core/overnight_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.overnight_bp import overnight_bp


class TestOvernightBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(overnight_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(overnight_bp.name, "overnight")

    def test_url_prefix(self):
        self.assertEqual(overnight_bp.url_prefix, "/api/overnight")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/overnight/start", rules)
        self.assertIn("/api/overnight/status", rules)

    def test_start_success(self):
        with patch("orbit.core.overnight_bp.start_overnight", return_value={"ok": True, "started": True}) as m:
            r = self.client.post("/api/overnight/start", json={"goal": "g", "iterations": 3})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        m.assert_called_once_with("g", 3)

    def test_start_failure(self):
        with patch("orbit.core.overnight_bp.start_overnight", return_value={"ok": False, "error": "bad"}):
            r = self.client.post("/api/overnight/start", json={"goal": "g"})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.get_json()["ok"])

    def test_start_invalid_iterations(self):
        with patch("orbit.core.overnight_bp.start_overnight", return_value={"ok": True}) as m:
            r = self.client.post("/api/overnight/start", json={"goal": "g", "iterations": "abc"})
        m.assert_called_once_with("g", 5)

    def test_start_defaults(self):
        with patch("orbit.core.overnight_bp.start_overnight", return_value={"ok": True}) as m:
            r = self.client.post("/api/overnight/start", json={})
        m.assert_called_once_with("", 5)

    def test_start_no_body(self):
        with patch("orbit.core.overnight_bp.start_overnight", return_value={"ok": False, "error": "no goal"}):
            r = self.client.post("/api/overnight/start")
        self.assertEqual(r.status_code, 400)

    def test_status(self):
        with patch("orbit.core.overnight_bp.status", return_value={"running": False}):
            r = self.client.get("/api/overnight/status")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()["running"])


if __name__ == "__main__":
    unittest.main()
