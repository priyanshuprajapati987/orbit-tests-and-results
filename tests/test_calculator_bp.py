"""Unit tests for orbit/orbit/core/calculator_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.calculator_bp import calculator_bp


class TestCalculatorBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(calculator_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(calculator_bp.name, "calculator_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/calc", rules)
        self.assertIn("/api/calc/percentage", rules)

    def test_calc_missing_expr_400(self):
        r = self.client.post("/api/calc", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_calc_success(self):
        with patch("orbit.core.calculator_bp.get_calculator") as gc:
            gc.return_value.calculate.return_value = {"result": 4.0}
            r = self.client.post("/api/calc", json={"expression": "2+2"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["result"], 4.0)
        gc.return_value.calculate.assert_called_once_with("2+2")

    def test_calc_no_body(self):
        r = self.client.post("/api/calc")
        self.assertEqual(r.status_code, 400)

    def test_percentage(self):
        with patch("orbit.core.calculator_bp.get_calculator") as gc:
            gc.return_value.percentage.return_value = {"result": 10.0}
            r = self.client.post("/api/calc/percentage", json={"value": 100, "percent": 10})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["result"], 10.0)
        gc.return_value.percentage.assert_called_once_with(100, 10)

    def test_percentage_defaults(self):
        with patch("orbit.core.calculator_bp.get_calculator") as gc:
            gc.return_value.percentage.return_value = {"result": 0.0}
            r = self.client.post("/api/calc/percentage", json={})
        gc.return_value.percentage.assert_called_once_with(0, 0)

    def test_percentage_no_body(self):
        with patch("orbit.core.calculator_bp.get_calculator") as gc:
            gc.return_value.percentage.return_value = {"result": 0.0}
            r = self.client.post("/api/calc/percentage")
        self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()
