"""Unit tests for orbit/orbit/core/self_test_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.self_test_bp import self_test_bp


class TestSelfTestBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(self_test_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(self_test_bp.name, "self_test")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/selftest/run", "/api/selftest/latest", "/api/selftest/history"]:
            self.assertIn(p, rules)

    def test_run(self):
        with patch("orbit.core.self_test_bp.get_self_test") as gst:
            gst.return_value.run_all.return_value = {"passed": 5}
            r = self.client.post("/api/selftest/run")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertEqual(r.get_json()["report"], {"passed": 5})

    def test_run_error(self):
        with patch("orbit.core.self_test_bp.get_self_test") as gst:
            gst.return_value.run_all.side_effect = RuntimeError("boom")
            r = self.client.post("/api/selftest/run")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_latest_empty(self):
        with patch("orbit.core.self_test_bp.get_self_test") as gst:
            gst.return_value.get_latest.return_value = None
            r = self.client.get("/api/selftest/latest")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "empty")

    def test_latest_ok(self):
        with patch("orbit.core.self_test_bp.get_self_test") as gst:
            gst.return_value.get_latest.return_value = {"passed": 3}
            r = self.client.get("/api/selftest/latest")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertEqual(r.get_json()["report"], {"passed": 3})

    def test_latest_error(self):
        with patch("orbit.core.self_test_bp.get_self_test") as gst:
            gst.return_value.get_latest.side_effect = RuntimeError("boom")
            r = self.client.get("/api/selftest/latest")
        self.assertEqual(r.status_code, 500)

    def test_history(self):
        with patch("orbit.core.self_test_bp.get_self_test") as gst:
            gst.return_value.get_history.return_value = [{"r": 1}, {"r": 2}]
            r = self.client.get("/api/selftest/history?days=3")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["count"], 2)
        self.assertEqual(len(body["reports"]), 2)
        gst.return_value.get_history.assert_called_once_with(3)

    def test_history_default(self):
        with patch("orbit.core.self_test_bp.get_self_test") as gst:
            gst.return_value.get_history.return_value = []
            r = self.client.get("/api/selftest/history")
        gst.return_value.get_history.assert_called_once_with(7)

    def test_history_error(self):
        with patch("orbit.core.self_test_bp.get_self_test") as gst:
            gst.return_value.get_history.side_effect = RuntimeError("boom")
            r = self.client.get("/api/selftest/history")
        self.assertEqual(r.status_code, 500)


if __name__ == "__main__":
    unittest.main()
