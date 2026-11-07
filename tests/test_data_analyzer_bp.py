"""Unit tests for orbit/orbit/core/data_analyzer_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.data_analyzer_bp import data_analyzer_bp


class TestDataAnalyzerBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(data_analyzer_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(data_analyzer_bp.name, "data_analyzer_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/data-analyzer/analyze", rules)
        self.assertIn("/api/data-analyzer/summary", rules)

    def test_analyze_missing_file_400(self):
        r = self.client.post("/api/data-analyzer/analyze", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_analyze_csv(self):
        with patch("orbit.core.data_analyzer_bp.get_analyzer") as ga:
            ga.return_value.load_csv.return_value = {"rows": 10}
            r = self.client.post("/api/data-analyzer/analyze", json={"file": "data.csv"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["rows"], 10)
        ga.return_value.load_csv.assert_called_once_with("data.csv")

    def test_analyze_excel(self):
        with patch("orbit.core.data_analyzer_bp.get_analyzer") as ga:
            ga.return_value.load_excel.return_value = {"sheets": 2}
            r = self.client.post("/api/data-analyzer/analyze", json={"file": "data.xlsx"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["sheets"], 2)
        ga.return_value.load_excel.assert_called_once_with("data.xlsx")

    def test_analyze_xls(self):
        with patch("orbit.core.data_analyzer_bp.get_analyzer") as ga:
            ga.return_value.load_excel.return_value = {"sheets": 1}
            r = self.client.post("/api/data-analyzer/analyze", json={"file": "data.xls"})
        self.assertEqual(r.status_code, 200)
        ga.return_value.load_excel.assert_called_once_with("data.xls")

    def test_analyze_unsupported_400(self):
        r = self.client.post("/api/data-analyzer/analyze", json={"file": "data.txt"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Unsupported", r.get_json()["error"])

    def test_analyze_no_body(self):
        r = self.client.post("/api/data-analyzer/analyze")
        self.assertEqual(r.status_code, 400)

    def test_summary_missing_file_400(self):
        r = self.client.post("/api/data-analyzer/summary", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_summary_success(self):
        with patch("orbit.core.data_analyzer_bp.get_analyzer") as ga:
            ga.return_value.export_summary.return_value = "summary text"
            r = self.client.post("/api/data-analyzer/summary", json={"file": "data.csv"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["summary"], "summary text")
        ga.return_value.export_summary.assert_called_once_with("data.csv")

    def test_summary_no_body(self):
        r = self.client.post("/api/data-analyzer/summary")
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
