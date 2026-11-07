"""Unit tests for orbit/orbit/core/dreams_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.dreams_bp import dreams_bp


class TestDreamsBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(dreams_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(dreams_bp.name, "dreams")

    def test_url_prefix(self):
        self.assertEqual(dreams_bp.url_prefix, "/api/dreams")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/dreams/synthesize", rules)
        self.assertIn("/api/dreams/latest", rules)

    def test_synthesize(self):
        with patch("orbit.core.dreams_bp.get_dream_synthesizer") as gd:
            gd.return_value.synthesize.return_value = {"dream": "idea"}
            r = self.client.post("/api/dreams/synthesize")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["dream"], "idea")

    def test_latest(self):
        with patch("orbit.core.dreams_bp.get_dream_synthesizer") as gd:
            gd.return_value.latest.return_value = {"dream": "latest"}
            r = self.client.get("/api/dreams/latest")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["dream"], "latest")

    def test_latest_none(self):
        with patch("orbit.core.dreams_bp.get_dream_synthesizer") as gd:
            gd.return_value.latest.return_value = None
            r = self.client.get("/api/dreams/latest")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {})


if __name__ == "__main__":
    unittest.main()
