"""Unit tests for orbit/orbit/core/universal_search_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.universal_search_bp import universal_search_bp


class TestUniversalSearchBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(universal_search_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(universal_search_bp.name, "universal_search")

    def test_route_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/search", rules)

    def test_empty_query(self):
        r = self.client.get("/api/search")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["results"], [])
        self.assertEqual(r.get_json()["query"], "")

    def test_search_with_results(self):
        with patch("orbit.core.universal_search_bp.get_universal_search") as gs:
            gs.return_value.search.return_value = ["r1", "r2"]
            r = self.client.get("/api/search?q=hello&category=docs")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["results"], ["r1", "r2"])
        self.assertEqual(body["count"], 2)
        self.assertEqual(body["query"], "hello")
        gs.return_value.search.assert_called_once_with("hello", category="docs")

    def test_search_no_category(self):
        with patch("orbit.core.universal_search_bp.get_universal_search") as gs:
            gs.return_value.search.return_value = []
            r = self.client.get("/api/search?q=hello")
        gs.return_value.search.assert_called_once_with("hello", category=None)

    def test_search_exception_500(self):
        with patch("orbit.core.universal_search_bp.get_universal_search") as gs:
            gs.return_value.search.side_effect = RuntimeError("boom")
            r = self.client.get("/api/search?q=hello")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())


if __name__ == "__main__":
    unittest.main()
