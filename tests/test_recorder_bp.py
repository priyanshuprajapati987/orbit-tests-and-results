"""Unit tests for orbit/orbit/core/recorder_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.recorder_bp import recorder_bp


class TestRecorderBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(recorder_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(recorder_bp.name, "recorder_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/recorder/start", "/api/recorder/stop", "/api/recorder/status"]:
            self.assertIn(p, rules)

    def test_start(self):
        with patch("orbit.core.recorder_bp.get_recorder") as gr:
            gr.return_value.start.return_value = {"recording": True}
            r = self.client.post("/api/recorder/start", json={"fps": 10})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["recording"])
        gr.return_value.start.assert_called_once_with(10)

    def test_start_default(self):
        with patch("orbit.core.recorder_bp.get_recorder") as gr:
            gr.return_value.start.return_value = {"recording": True}
            r = self.client.post("/api/recorder/start", json={})
        gr.return_value.start.assert_called_once_with(5)

    def test_start_no_body(self):
        with patch("orbit.core.recorder_bp.get_recorder") as gr:
            gr.return_value.start.return_value = {"recording": True}
            r = self.client.post("/api/recorder/start")
        gr.return_value.start.assert_called_once_with(5)

    def test_stop(self):
        with patch("orbit.core.recorder_bp.get_recorder") as gr:
            gr.return_value.stop.return_value = {"stopped": True}
            r = self.client.post("/api/recorder/stop")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["stopped"])

    def test_status(self):
        with patch("orbit.core.recorder_bp.get_recorder") as gr:
            gr.return_value.get_status.return_value = {"recording": False}
            r = self.client.get("/api/recorder/status")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()["recording"])


if __name__ == "__main__":
    unittest.main()
