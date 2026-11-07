"""Unit tests for orbit/orbit/core/transparency_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.transparency_bp import transparency_bp


class TestTransparencyBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(transparency_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(transparency_bp.name, "transparency")

    def test_url_prefix(self):
        self.assertEqual(transparency_bp.url_prefix, "/api/transparency")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/transparency/latest", rules)
        self.assertIn("/api/transparency/history", rules)

    def test_latest(self):
        with patch("orbit.core.transparency_bp.get_transparency_store") as gs:
            gs.return_value.latest.return_value = {"provider": "groq"}
            r = self.client.get("/api/transparency/latest")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["provider"], "groq")

    def test_latest_none(self):
        with patch("orbit.core.transparency_bp.get_transparency_store") as gs:
            gs.return_value.latest.return_value = None
            r = self.client.get("/api/transparency/latest")
        self.assertEqual(r.get_json(), {})

    def test_history(self):
        with patch("orbit.core.transparency_bp.get_transparency_store") as gs:
            gs.return_value.history.return_value = [{"a": 1}]
            r = self.client.get("/api/transparency/history?n=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), [{"a": 1}])
        gs.return_value.history.assert_called_once_with(5)

    def test_history_default(self):
        with patch("orbit.core.transparency_bp.get_transparency_store") as gs:
            gs.return_value.history.return_value = []
            r = self.client.get("/api/transparency/history")
        gs.return_value.history.assert_called_once_with(10)

    def test_history_invalid_n(self):
        r = self.client.get("/api/transparency/history?n=abc")
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_history_clamped(self):
        with patch("orbit.core.transparency_bp.get_transparency_store") as gs:
            gs.return_value.history.return_value = []
            r = self.client.get("/api/transparency/history?n=1000")
        gs.return_value.history.assert_called_once_with(500)


if __name__ == "__main__":
    unittest.main()
