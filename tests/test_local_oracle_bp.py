"""Unit tests for orbit/orbit/core/local_oracle_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.local_oracle_bp import local_oracle_bp


class TestLocalOracleBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(local_oracle_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(local_oracle_bp.name, "local_oracle")

    def test_url_prefix(self):
        self.assertEqual(local_oracle_bp.url_prefix, "/api/oracle")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/oracle/ask", rules)
        self.assertIn("/api/oracle/status", rules)

    def test_ask_missing_q_400(self):
        r = self.client.post("/api/oracle/ask", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_ask_success(self):
        with patch("orbit.core.local_oracle_bp.get_local_oracle") as gl:
            gl.return_value.ask.return_value = {"answer": "found"}
            r = self.client.post("/api/oracle/ask", json={"q": "where is x", "root": "/tmp"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["answer"], "found")
        gl.return_value.ask.assert_called_once_with("where is x", root="/tmp")

    def test_ask_no_body(self):
        r = self.client.post("/api/oracle/ask")
        self.assertEqual(r.status_code, 400)

    def test_status(self):
        with patch("orbit.core.local_oracle_bp.get_local_oracle") as gl:
            gl.return_value.status.return_value = {"indexed": 5}
            r = self.client.get("/api/oracle/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["indexed"], 5)


if __name__ == "__main__":
    unittest.main()
