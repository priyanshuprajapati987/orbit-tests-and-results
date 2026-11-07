"""Unit tests for orbit/orbit/core/selfextend_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.selfextend_bp import selfextend_bp


class TestSelfextendBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(selfextend_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(selfextend_bp.name, "selfextend")

    def test_url_prefix(self):
        self.assertEqual(selfextend_bp.url_prefix, "/api/selfextend")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/selfextend/propose", rules)
        self.assertIn("/api/selfextend/proposed", rules)

    def test_propose_success(self):
        with patch("orbit.core.selfextend_bp.propose") as p:
            p.return_value = {"ok": True, "name": "tool1"}
            r = self.client.post("/api/selfextend/propose", json={"description": "desc", "name": "tool1"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        p.assert_called_once_with("desc", "tool1")

    def test_propose_failure(self):
        with patch("orbit.core.selfextend_bp.propose") as p:
            p.return_value = {"ok": False, "error": "dup"}
            r = self.client.post("/api/selfextend/propose", json={"description": "desc"})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.get_json()["ok"])
        p.assert_called_once_with("desc", None)

    def test_propose_no_body(self):
        with patch("orbit.core.selfextend_bp.propose") as p:
            p.return_value = {"ok": False, "error": "no desc"}
            r = self.client.post("/api/selfextend/propose")
        self.assertEqual(r.status_code, 400)

    def test_proposed(self):
        with patch("orbit.core.selfextend_bp.list_proposed", return_value=["t1", "t2"]):
            r = self.client.get("/api/selfextend/proposed")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), ["t1", "t2"])


if __name__ == "__main__":
    unittest.main()
