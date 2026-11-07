"""Unit tests for orbit/orbit/core/society_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.society_bp import society_bp


class TestSocietyBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(society_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(society_bp.name, "society")

    def test_url_prefix(self):
        self.assertEqual(society_bp.url_prefix, "/api/society")

    def test_route_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/society/debate", rules)

    def test_debate_success(self):
        with patch("orbit.core.society_bp.debate", return_value={"ok": True, "result": "consensus"}) as m:
            r = self.client.post("/api/society/debate", json={"question": "q"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        m.assert_called_once_with("q")

    def test_debate_failure(self):
        with patch("orbit.core.society_bp.debate", return_value={"ok": False, "error": "bad"}):
            r = self.client.post("/api/society/debate", json={"question": "q"})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.get_json()["ok"])

    def test_no_body(self):
        with patch("orbit.core.society_bp.debate", return_value={"ok": False, "error": "no question"}):
            r = self.client.post("/api/society/debate")
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
