"""Unit tests for orbit/orbit/core/clipboard_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.clipboard_bp import clipboard_bp


class TestClipboardBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(clipboard_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(clipboard_bp.name, "clipboard_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/clipboard/current", "/api/clipboard/copy", "/api/clipboard/history", "/api/clipboard/clear"]:
            self.assertIn(p, rules)

    def test_current(self):
        with patch("orbit.core.clipboard_bp.get_clipboard_manager") as gc:
            gc.return_value.get_current.return_value = "hello"
            r = self.client.get("/api/clipboard/current")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), "hello")

    def test_copy_missing_text(self):
        r = self.client.post("/api/clipboard/copy", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_copy_success(self):
        with patch("orbit.core.clipboard_bp.get_clipboard_manager") as gc:
            gc.return_value.copy.return_value = {"copied": True}
            r = self.client.post("/api/clipboard/copy", json={"text": "hi"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["copied"])
        gc.return_value.copy.assert_called_once_with("hi")

    def test_copy_no_body(self):
        r = self.client.post("/api/clipboard/copy")
        self.assertEqual(r.status_code, 400)

    def test_history(self):
        with patch("orbit.core.clipboard_bp.get_clipboard_manager") as gc:
            gc.return_value.get_history.return_value = ["a", "b"]
            r = self.client.get("/api/clipboard/history")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["history"], ["a", "b"])

    def test_clear(self):
        with patch("orbit.core.clipboard_bp.get_clipboard_manager") as gc:
            r = self.client.post("/api/clipboard/clear")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "cleared")
        gc.return_value.clear_history.assert_called_once()


if __name__ == "__main__":
    unittest.main()
