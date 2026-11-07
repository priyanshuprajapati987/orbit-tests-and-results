"""Unit tests for orbit/orbit/core/multi_language_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.multi_language_bp import multi_language_bp


class TestMultiLanguageBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(multi_language_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(multi_language_bp.name, "multi_language_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/language/status", "/api/language/list", "/api/language/switch", "/api/language/stats"]:
            self.assertIn(p, rules)

    def test_status(self):
        with patch("orbit.core.multi_language_bp.get_multi_language") as gm:
            gm.return_value.get_language.return_value = "en"
            r = self.client.get("/api/language/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), "en")

    def test_list(self):
        with patch("orbit.core.multi_language_bp.get_multi_language") as gm:
            gm.return_value.get_available.return_value = ["en", "es"]
            r = self.client.get("/api/language/list")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["languages"], ["en", "es"])

    def test_switch_missing_lang_400(self):
        r = self.client.post("/api/language/switch", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_switch_success(self):
        with patch("orbit.core.multi_language_bp.get_multi_language") as gm:
            gm.return_value.set_language.return_value = {"language": "es"}
            r = self.client.post("/api/language/switch", json={"language": "es"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["language"], "es")
        gm.return_value.set_language.assert_called_once_with("es")

    def test_switch_error_400(self):
        with patch("orbit.core.multi_language_bp.get_multi_language") as gm:
            gm.return_value.set_language.return_value = {"error": "unsupported"}
            r = self.client.post("/api/language/switch", json={"language": "xx"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_switch_no_body(self):
        r = self.client.post("/api/language/switch")
        self.assertEqual(r.status_code, 400)

    def test_stats(self):
        with patch("orbit.core.multi_language_bp.get_multi_language") as gm:
            gm.return_value.get_stats.return_value = {"total": 5}
            r = self.client.get("/api/language/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)


if __name__ == "__main__":
    unittest.main()
