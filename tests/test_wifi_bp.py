"""Unit tests for orbit/orbit/core/wifi_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.wifi_bp import wifi_bp


class TestWifiBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(wifi_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(wifi_bp.name, "wifi_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for path in ["/api/wifi/networks", "/api/wifi/status", "/api/wifi/connect", "/api/wifi/disconnect"]:
            self.assertIn(path, rules)

    def test_networks(self):
        mgr = MagicMock()
        mgr.list_networks.return_value = ["net1", "net2"]
        with patch("orbit.core.wifi_bp.get_wifi_manager", return_value=mgr):
            r = self.client.get("/api/wifi/networks")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["networks"], ["net1", "net2"])

    def test_status(self):
        mgr = MagicMock()
        mgr.get_status.return_value = {"connected": True}
        with patch("orbit.core.wifi_bp.get_wifi_manager", return_value=mgr):
            r = self.client.get("/api/wifi/status")
        self.assertEqual(r.get_json()["connected"], True)

    def test_connect_missing_ssid(self):
        r = self.client.post("/api/wifi/connect", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_connect_success(self):
        mgr = MagicMock()
        mgr.connect.return_value = {"connected": True}
        with patch("orbit.core.wifi_bp.get_wifi_manager", return_value=mgr):
            r = self.client.post("/api/wifi/connect", json={"ssid": "Home", "password": "secret"})
        self.assertEqual(r.status_code, 200)
        mgr.connect.assert_called_once_with("Home", "secret")

    def test_disconnect(self):
        mgr = MagicMock()
        mgr.disconnect.return_value = {"disconnected": True}
        with patch("orbit.core.wifi_bp.get_wifi_manager", return_value=mgr):
            r = self.client.post("/api/wifi/disconnect")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["disconnected"])


if __name__ == "__main__":
    unittest.main()
