"""Unit tests for orbit/orbit/core/companion_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.companion_bp import companion_bp


class TestCompanionBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(companion_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(companion_bp.name, "companion")

    def test_url_prefix(self):
        self.assertEqual(companion_bp.url_prefix, "/api/companion")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/companion/add", "/api/companion/timeline", "/api/companion/summarize"]:
            self.assertIn(p, rules)

    def test_add_success(self):
        with patch("orbit.core.companion_bp.get_companion_memory") as gc:
            gc.return_value.add_event.return_value = {"id": 1, "text": "hi"}
            r = self.client.post("/api/companion/add", json={"text": "hi", "kind": "note"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], 1)
        gc.return_value.add_event.assert_called_once_with("hi", "note")

    def test_add_empty_400(self):
        with patch("orbit.core.companion_bp.get_companion_memory") as gc:
            gc.return_value.add_event.return_value = None
            r = self.client.post("/api/companion/add", json={"text": ""})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_add_default_kind(self):
        with patch("orbit.core.companion_bp.get_companion_memory") as gc:
            gc.return_value.add_event.return_value = {"id": 2}
            r = self.client.post("/api/companion/add", json={"text": "hi"})
        gc.return_value.add_event.assert_called_once_with("hi", "moment")

    def test_add_no_body(self):
        with patch("orbit.core.companion_bp.get_companion_memory") as gc:
            gc.return_value.add_event.return_value = None
            r = self.client.post("/api/companion/add")
        self.assertEqual(r.status_code, 400)

    def test_timeline(self):
        with patch("orbit.core.companion_bp.get_companion_memory") as gc:
            gc.return_value.timeline.return_value = [{"id": 1}]
            r = self.client.get("/api/companion/timeline?n=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), [{"id": 1}])
        gc.return_value.timeline.assert_called_once_with(5)

    def test_timeline_default(self):
        with patch("orbit.core.companion_bp.get_companion_memory") as gc:
            gc.return_value.timeline.return_value = []
            r = self.client.get("/api/companion/timeline")
        gc.return_value.timeline.assert_called_once_with(30)

    def test_timeline_invalid_n(self):
        with patch("orbit.core.companion_bp.get_companion_memory") as gc:
            gc.return_value.timeline.return_value = []
            r = self.client.get("/api/companion/timeline?n=abc")
        gc.return_value.timeline.assert_called_once_with(30)

    def test_summarize(self):
        with patch("orbit.core.companion_bp.get_companion_memory") as gc:
            gc.return_value.summarize.return_value = "a summary"
            r = self.client.get("/api/companion/summarize")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["summary"], "a summary")


if __name__ == "__main__":
    unittest.main()
