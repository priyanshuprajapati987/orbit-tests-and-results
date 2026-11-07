"""Unit tests for orbit/orbit/core/json_formatter_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.json_formatter_bp import json_formatter_bp


class TestJsonFormatterBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(json_formatter_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(json_formatter_bp.name, "json_formatter_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/json/format", "/api/json/minify", "/api/json/validate"]:
            self.assertIn(p, rules)

    def test_format(self):
        with patch("orbit.core.json_formatter_bp.get_json_formatter") as gj:
            gj.return_value.format_json.return_value = {"formatted": "{ }"}
            r = self.client.post("/api/json/format", json={"json": "{}", "indent": 4})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["formatted"], "{ }")
        gj.return_value.format_json.assert_called_once_with("{}", 4)

    def test_format_default_indent(self):
        with patch("orbit.core.json_formatter_bp.get_json_formatter") as gj:
            gj.return_value.format_json.return_value = {}
            r = self.client.post("/api/json/format", json={"json": "{}"})
        gj.return_value.format_json.assert_called_once_with("{}", 2)

    def test_format_no_body(self):
        with patch("orbit.core.json_formatter_bp.get_json_formatter") as gj:
            gj.return_value.format_json.return_value = {}
            r = self.client.post("/api/json/format")
        gj.return_value.format_json.assert_called_once_with("", 2)

    def test_minify(self):
        with patch("orbit.core.json_formatter_bp.get_json_formatter") as gj:
            gj.return_value.minify.return_value = {"minified": "{}"}
            r = self.client.post("/api/json/minify", json={"json": "{ }"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["minified"], "{}")
        gj.return_value.minify.assert_called_once_with("{ }")

    def test_minify_no_body(self):
        with patch("orbit.core.json_formatter_bp.get_json_formatter") as gj:
            gj.return_value.minify.return_value = {}
            r = self.client.post("/api/json/minify")
        gj.return_value.minify.assert_called_once_with("")

    def test_validate(self):
        with patch("orbit.core.json_formatter_bp.get_json_formatter") as gj:
            gj.return_value.validate.return_value = {"valid": True}
            r = self.client.post("/api/json/validate", json={"json": "{}"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["valid"])
        gj.return_value.validate.assert_called_once_with("{}")

    def test_validate_no_body(self):
        with patch("orbit.core.json_formatter_bp.get_json_formatter") as gj:
            gj.return_value.validate.return_value = {"valid": False}
            r = self.client.post("/api/json/validate")
        gj.return_value.validate.assert_called_once_with("")


if __name__ == "__main__":
    unittest.main()
