"""Unit tests for orbit/orbit/core/mode_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.mode_bp import mode_bp


class TestModeBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(mode_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(mode_bp.name, "mode")

    def test_url_prefix(self):
        self.assertEqual(mode_bp.url_prefix, "/api/mode")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/mode", rules)

    def test_get_mode(self):
        rm = MagicMock()
        rm.get.return_value = "local"
        rm.force_offline.return_value = True
        with patch("orbit.core.mode_bp.get_runtime_mode", return_value=rm):
            r = self.client.get("/api/mode")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["mode"], "local")
        self.assertTrue(r.get_json()["force_offline"])

    def test_set_mode_success(self):
        rm = MagicMock()
        rm.set.return_value = "auto"
        rm.force_offline.return_value = False
        with patch("orbit.core.mode_bp.get_runtime_mode", return_value=rm):
            r = self.client.post("/api/mode", json={"mode": "auto"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["mode"], "auto")
        rm.set.assert_called_once_with("auto")

    def test_set_mode_invalid_400(self):
        rm = MagicMock()
        rm.set.side_effect = ValueError("mode must be 'local' or 'auto'")
        with patch("orbit.core.mode_bp.get_runtime_mode", return_value=rm):
            r = self.client.post("/api/mode", json={"mode": "cloud"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_set_mode_no_body(self):
        rm = MagicMock()
        rm.set.return_value = "local"
        rm.force_offline.return_value = True
        with patch("orbit.core.mode_bp.get_runtime_mode", return_value=rm):
            r = self.client.post("/api/mode")
        rm.set.assert_called_once_with("")


if __name__ == "__main__":
    unittest.main()
