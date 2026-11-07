"""Unit tests for orbit/orbit/core/redteam_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.redteam_bp import redteam_bp


class TestRedteamBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(redteam_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(redteam_bp.name, "redteam")

    def test_url_prefix(self):
        self.assertEqual(redteam_bp.url_prefix, "/api/redteam")

    def test_route_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/redteam/scan", rules)

    def test_scan_post(self):
        with patch("orbit.core.redteam_bp.run_red_team", return_value={"ok": True, "verdict": "resilient"}):
            r = self.client.post("/api/redteam/scan")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["verdict"], "resilient")


if __name__ == "__main__":
    unittest.main()
