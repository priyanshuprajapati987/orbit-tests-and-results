"""Unit tests for orbit/orbit/core/wellness_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.wellness_bp import wellness_bp


class TestWellnessBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(wellness_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(wellness_bp.name, "wellness")

    def test_url_prefix(self):
        self.assertEqual(wellness_bp.url_prefix, "/api/wellness")

    def test_route_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/wellness/status", rules)

    def test_status_endpoint(self):
        with patch("orbit.core.wellness_bp.status", return_value={"session_minutes": 5, "suggestion": "Keep going."}):
            r = self.client.get("/api/wellness/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["suggestion"], "Keep going.")


if __name__ == "__main__":
    unittest.main()
