"""Unit tests for orbit/orbit/core/persona_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.persona_bp import persona_bp


class TestPersonaBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(persona_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(persona_bp.name, "persona")

    def test_url_prefix(self):
        self.assertEqual(persona_bp.url_prefix, "/api/persona")

    def test_route_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/persona/rewrite", rules)

    def test_missing_text_400(self):
        r = self.client.post("/api/persona/rewrite", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_rewrite_by_recipient(self):
        with patch("orbit.core.persona_bp.rewrite", return_value={"rewritten": "hi"}) as m:
            r = self.client.post("/api/persona/rewrite", json={"text": "hello", "recipient": "manager"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["rewritten"], "hi")
        m.assert_called_once_with("hello", "manager")

    def test_rewrite_by_name(self):
        with patch("orbit.core.persona_bp.rewrite_for_name", return_value={"rewritten": "hi2"}) as m:
            r = self.client.post("/api/persona/rewrite", json={"text": "hello", "name": "Alice"})
        self.assertEqual(r.status_code, 200)
        m.assert_called_once_with("hello", "Alice")

    def test_no_body(self):
        r = self.client.post("/api/persona/rewrite")
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
