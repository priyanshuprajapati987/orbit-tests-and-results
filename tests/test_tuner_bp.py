"""Unit tests for orbit/orbit/core/tuner_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.tuner_bp import tuner_bp


class TestTunerBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(tuner_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(tuner_bp.name, "tuner")

    def test_url_prefix(self):
        self.assertEqual(tuner_bp.url_prefix, "/api/tuner")

    def test_route_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/tuner/stats", rules)

    def test_stats(self):
        with patch("orbit.core.tuner_bp.get_router_tuner") as gt:
            gt.return_value.stats.return_value = {"tuned": 5}
            r = self.client.get("/api/tuner/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["tuned"], 5)


if __name__ == "__main__":
    unittest.main()
