"""Unit tests for orbit/orbit/core/plugin_bridge_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.plugin_bridge_bp import plugin_bridge_bp


class TestPluginBridgeBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(plugin_bridge_bp)
        self.client = self.app.test_client()
        self.fake_pb = patch("orbit.orbit.core.plugin_bridge.get_plugin_bridge").start() if False else None
        # register fake module
        self.fake = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
        sys.modules["orbit.orbit.core.plugin_bridge"] = self.fake

    def tearDown(self):
        sys.modules.pop("orbit.orbit.core.plugin_bridge", None)

    def test_blueprint_name(self):
        self.assertEqual(plugin_bridge_bp.name, "plugin_bridge")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/plugin-bridge/scan", "/api/plugin-bridge/scan-all", "/api/plugin-bridge/watch",
                  "/api/plugin-bridge/start", "/api/plugin-bridge/stop", "/api/plugin-bridge/events",
                  "/api/plugin-bridge/watchers", "/api/plugin-bridge/stats"]:
            self.assertIn(p, rules)

    def test_scan(self):
        self.fake.get_plugin_bridge.return_value.scan_directory.return_value = {"scanned": 2}
        r = self.client.post("/api/plugin-bridge/scan", json={"directory": "plugins"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["scanned"], 2)
        self.fake.get_plugin_bridge.return_value.scan_directory.assert_called_once_with("plugins")

    def test_scan_default(self):
        self.fake.get_plugin_bridge.return_value.scan_directory.return_value = {}
        r = self.client.post("/api/plugin-bridge/scan", json={})
        self.fake.get_plugin_bridge.return_value.scan_directory.assert_called_once_with("plugins")

    def test_scan_no_body(self):
        self.fake.get_plugin_bridge.return_value.scan_directory.return_value = {}
        r = self.client.post("/api/plugin-bridge/scan")
        self.fake.get_plugin_bridge.return_value.scan_directory.assert_called_once_with("plugins")

    def test_scan_all(self):
        self.fake.get_plugin_bridge.return_value.scan_all.return_value = {"all": True}
        r = self.client.post("/api/plugin-bridge/scan-all")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["all"])

    def test_watch_missing_fields_400(self):
        r = self.client.post("/api/plugin-bridge/watch", json={"name": "n"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_watch_success(self):
        r = self.client.post("/api/plugin-bridge/watch", json={"name": "n", "path": "/p"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "watching")
        self.assertEqual(r.get_json()["name"], "n")
        self.fake.get_plugin_bridge.return_value.register_watcher.assert_called_once_with("n", "/p")

    def test_watch_no_body(self):
        r = self.client.post("/api/plugin-bridge/watch")
        self.assertEqual(r.status_code, 400)

    def test_start(self):
        r = self.client.post("/api/plugin-bridge/start")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "started")
        self.fake.get_plugin_bridge.return_value.start_watching.assert_called_once()

    def test_stop(self):
        r = self.client.post("/api/plugin-bridge/stop")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "stopped")
        self.fake.get_plugin_bridge.return_value.stop_watching.assert_called_once()

    def test_events(self):
        self.fake.get_plugin_bridge.return_value.get_events.return_value = [{"e": 1}]
        r = self.client.get("/api/plugin-bridge/events?limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["events"], [{"e": 1}])
        self.fake.get_plugin_bridge.return_value.get_events.assert_called_once_with(5)

    def test_events_default(self):
        self.fake.get_plugin_bridge.return_value.get_events.return_value = []
        r = self.client.get("/api/plugin-bridge/events")
        self.fake.get_plugin_bridge.return_value.get_events.assert_called_once_with(50)

    def test_watchers(self):
        self.fake.get_plugin_bridge.return_value.get_watchers.return_value = ["w1"]
        r = self.client.get("/api/plugin-bridge/watchers")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["watchers"], ["w1"])

    def test_stats(self):
        self.fake.get_plugin_bridge.return_value.get_stats.return_value = {"count": 2}
        r = self.client.get("/api/plugin-bridge/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["count"], 2)


if __name__ == "__main__":
    unittest.main()
