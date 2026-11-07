"""Unit tests for orbit/orbit/core/thoughtatorium_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.thoughtatorium_bp import thoughtatorium_bp


class TestThoughtatoriumBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(thoughtatorium_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(thoughtatorium_bp.name, "thoughtatorium")

    def test_url_prefix(self):
        self.assertEqual(thoughtatorium_bp.url_prefix, "/api/thoughtatorium")

    def test_route_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/thoughtatorium/spark", rules)

    def test_spark_success(self):
        with patch("orbit.core.thoughtatorium_bp.spark", return_value={"ok": True, "idea": "x"}):
            r = self.client.post("/api/thoughtatorium/spark")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])

    def test_spark_failure(self):
        with patch("orbit.core.thoughtatorium_bp.spark", return_value={"ok": False, "error": "bad"}):
            r = self.client.post("/api/thoughtatorium/spark")
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.get_json()["ok"])


if __name__ == "__main__":
    unittest.main()
