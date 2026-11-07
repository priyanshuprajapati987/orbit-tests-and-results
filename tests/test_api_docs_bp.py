"""Unit tests for orbit/orbit/core/api_docs_bp.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.api_docs_bp import api_docs_bp


class TestApiDocsBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(api_docs_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(api_docs_bp.name, "api_docs_bp")

    def test_route_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/docs", rules)

    def test_docs_payload(self):
        r = self.client.get("/api/docs")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["title"], "ORBIT AI OS API")
        self.assertEqual(body["version"], "3.7.0")
        self.assertIn("/api/health", body["endpoints"])
        self.assertIn("docs_url", body)


if __name__ == "__main__":
    unittest.main()
