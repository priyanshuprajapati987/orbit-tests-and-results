"""Unit tests for orbit/orbit/core/twin_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.twin_bp import twin_bp


class TestTwinBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(twin_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(twin_bp.name, "twin")

    def test_url_prefix(self):
        self.assertEqual(twin_bp.url_prefix, "/api/twin")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/twin", rules)
        self.assertIn("/api/twin/summary", rules)

    def test_twin(self):
        with patch("orbit.core.twin_bp.build_twin", return_value={"persona": "x"}) as m:
            r = self.client.get("/api/twin")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["persona"], "x")
        m.assert_called_once()

    def test_summary(self):
        with patch("orbit.core.twin_bp.twin_summary", return_value="a summary"):
            r = self.client.get("/api/twin/summary")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["summary"], "a summary")


if __name__ == "__main__":
    unittest.main()
