"""Unit tests for orbit/orbit/core/code_interpreter_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.code_interpreter_bp import code_interpreter_bp


class TestCodeInterpreterBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(code_interpreter_bp)
        self.client = self.app.test_client()
        self.fake_ci = MagicMock()
        sys.modules["orbit.orbit.core.code_interpreter"] = self.fake_ci

    def tearDown(self):
        sys.modules.pop("orbit.orbit.core.code_interpreter", None)

    def test_blueprint_name(self):
        self.assertEqual(code_interpreter_bp.name, "code_interpreter")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/code-interpreter/execute", "/api/code-interpreter/history",
                  "/api/code-interpreter/clear", "/api/code-interpreter/stats"]:
            self.assertIn(p, rules)

    def test_execute_missing_code_400(self):
        r = self.client.post("/api/code-interpreter/execute", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_execute_success(self):
        result = MagicMock()
        result.exec_id = "e1"
        result.output = "out"
        result.error = None
        result.status = "ok"
        result.execution_time_ms = 12.5
        self.fake_ci.get_code_interpreter.return_value.execute.return_value = result
        r = self.client.post("/api/code-interpreter/execute", json={"code": "print(1)", "session_id": "s1", "variables": {"x": 1}})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["exec_id"], "e1")
        self.assertEqual(body["output"], "out")
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["time_ms"], 12.5)
        self.fake_ci.get_code_interpreter.return_value.execute.assert_called_once_with("print(1)", session_id="s1", variables={"x": 1})

    def test_execute_defaults(self):
        result = MagicMock()
        result.exec_id = "e2"
        result.output = ""
        result.error = None
        result.status = "ok"
        result.execution_time_ms = 1.0
        self.fake_ci.get_code_interpreter.return_value.execute.return_value = result
        r = self.client.post("/api/code-interpreter/execute", json={"code": "x=1"})
        self.fake_ci.get_code_interpreter.return_value.execute.assert_called_once_with("x=1", session_id="default", variables=None)

    def test_execute_no_body(self):
        r = self.client.post("/api/code-interpreter/execute")
        self.assertEqual(r.status_code, 400)

    def test_history(self):
        self.fake_ci.get_code_interpreter.return_value.get_history.return_value = [{"id": "e1"}]
        r = self.client.get("/api/code-interpreter/history?limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["history"], [{"id": "e1"}])
        self.fake_ci.get_code_interpreter.return_value.get_history.assert_called_once_with(5)

    def test_history_default(self):
        self.fake_ci.get_code_interpreter.return_value.get_history.return_value = []
        r = self.client.get("/api/code-interpreter/history")
        self.fake_ci.get_code_interpreter.return_value.get_history.assert_called_once_with(20)

    def test_clear(self):
        r = self.client.post("/api/code-interpreter/clear", json={"session_id": "s1"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["cleared"], "s1")
        self.fake_ci.get_code_interpreter.return_value.clear_session.assert_called_once_with("s1")

    def test_clear_default(self):
        r = self.client.post("/api/code-interpreter/clear", json={})
        self.fake_ci.get_code_interpreter.return_value.clear_session.assert_called_once_with("default")

    def test_clear_no_body(self):
        r = self.client.post("/api/code-interpreter/clear")
        self.fake_ci.get_code_interpreter.return_value.clear_session.assert_called_once_with("default")

    def test_stats(self):
        self.fake_ci.get_code_interpreter.return_value.get_stats.return_value = {"count": 3}
        r = self.client.get("/api/code-interpreter/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["count"], 3)


if __name__ == "__main__":
    unittest.main()
