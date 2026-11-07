"""Unit tests for orbit/orbit/core/code_debugger_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.code_debugger_bp import code_debugger_bp


class TestCodeDebuggerBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(code_debugger_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(code_debugger_bp.name, "code_debugger_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/code-debugger/analyze", "/api/code-debugger/explain", "/api/code-debugger/stats"]:
            self.assertIn(p, rules)

    def test_analyze_missing_error_400(self):
        r = self.client.post("/api/code-debugger/analyze", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_analyze_success(self):
        with patch("orbit.core.code_debugger_bp.get_debugger") as gd:
            gd.return_value.analyze_error.return_value = {"diagnosis": "x"}
            r = self.client.post("/api/code-debugger/analyze", json={"error": "boom", "code": "print(1)"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["diagnosis"], "x")
        gd.return_value.analyze_error.assert_called_once_with("boom", "print(1)")

    def test_analyze_no_code(self):
        with patch("orbit.core.code_debugger_bp.get_debugger") as gd:
            gd.return_value.analyze_error.return_value = {"diagnosis": "y"}
            r = self.client.post("/api/code-debugger/analyze", json={"error": "boom"})
        gd.return_value.analyze_error.assert_called_once_with("boom", None)

    def test_explain_missing_code_400(self):
        r = self.client.post("/api/code-debugger/explain", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_explain_success(self):
        with patch("orbit.core.code_debugger_bp.get_debugger") as gd:
            gd.return_value.explain_code.return_value = {"explanation": "ok"}
            r = self.client.post("/api/code-debugger/explain", json={"code": "x=1"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["explanation"], "ok")
        gd.return_value.explain_code.assert_called_once_with("x=1")

    def test_stats(self):
        with patch("orbit.core.code_debugger_bp.get_debugger") as gd:
            gd.return_value.get_stats.return_value = {"count": 3}
            r = self.client.get("/api/code-debugger/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["count"], 3)

    def test_analyze_no_body(self):
        r = self.client.post("/api/code-debugger/analyze")
        self.assertEqual(r.status_code, 400)

    def test_explain_no_body(self):
        r = self.client.post("/api/code-debugger/explain")
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
