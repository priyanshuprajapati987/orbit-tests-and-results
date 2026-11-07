"""Unit tests for orbit/orbit/core/unit_converter_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.unit_converter_bp import unit_converter_bp


class TestUnitConverterBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(unit_converter_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(unit_converter_bp.name, "unit_converter_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/converter/convert", rules)
        self.assertIn("/api/converter/categories", rules)

    def test_missing_fields_400(self):
        r = self.client.post("/api/converter/convert", json={"value": 1})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_non_numeric_value_400(self):
        r = self.client.post("/api/converter/convert", json={"value": "abc", "from": "m", "to": "km"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("numeric", r.get_json()["error"])

    def test_convert_success(self):
        with patch("orbit.core.unit_converter_bp.get_converter") as gc:
            gc.return_value.convert.return_value = {"result": 1000.0}
            r = self.client.post("/api/converter/convert", json={"value": 1, "from": "km", "to": "m", "category": "length"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["result"], 1000.0)
        gc.return_value.convert.assert_called_once_with(1.0, "km", "m", "length")

    def test_categories(self):
        with patch("orbit.core.unit_converter_bp.get_converter") as gc:
            gc.return_value.list_categories.return_value = ["length", "weight"]
            r = self.client.get("/api/converter/categories")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), ["length", "weight"])

    def test_no_body(self):
        r = self.client.post("/api/converter/convert")
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
