"""Unit tests for orbit/orbit/core/similarity_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.similarity_bp import similarity_bp


class TestSimilarityBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(similarity_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(similarity_bp.name, "similarity_bp")

    def test_route_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/similarity/compare", rules)

    def test_missing_fields_400(self):
        r = self.client.post("/api/similarity/compare", json={"text1": "hi"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_compare_success(self):
        with patch("orbit.core.similarity_bp.get_similarity") as gs:
            gs.return_value.compare.return_value = {"similarity": 0.9}
            r = self.client.post("/api/similarity/compare", json={"text1": "a", "text2": "b"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["similarity"], 0.9)

    def test_no_body(self):
        r = self.client.post("/api/similarity/compare")
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
