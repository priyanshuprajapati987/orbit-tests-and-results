"""Unit tests for orbit/orbit/core/sysinfo_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.sysinfo_bp import sysinfo_bp


class TestSysinfoBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(sysinfo_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(sysinfo_bp.name, "sysinfo_bp")

    def test_route_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/system-info", rules)

    def test_info(self):
        with patch("orbit.core.sysinfo_bp.get_system_info") as gs:
            gs.return_value.get_info.return_value = {"platform": "win32"}
            r = self.client.get("/api/system-info")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["platform"], "win32")


if __name__ == "__main__":
    unittest.main()
