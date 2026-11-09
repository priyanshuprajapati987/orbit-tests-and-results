"""Unit tests for orbit/orbit/core/file_watcher_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.file_watcher_bp import file_watcher_bp


class TestFileWatcherBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(file_watcher_bp)
        self.client = self.app.test_client()
        self.fake_fw = MagicMock()
        sys.modules["orbit.orbit.core.smart_file_watcher"] = self.fake_fw

    def tearDown(self):
        sys.modules.pop("orbit.orbit.core.smart_file_watcher", None)

    def test_blueprint_name(self):
        self.assertEqual(file_watcher_bp.name, "file_watcher")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/file-watcher/watch", "/api/file-watcher/<watch_id>", "/api/file-watcher/scan",
                  "/api/file-watcher/start", "/api/file-watcher/stop", "/api/file-watcher/watches",
                  "/api/file-watcher/events", "/api/file-watcher/stats"]:
            self.assertIn(p, rules)

    def test_add_watch_missing_path_400(self):
        r = self.client.post("/api/file-watcher/watch", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_add_watch_blocked_403(self):
        with patch("orbit.core._security_utils.validate_path", return_value=(False, "nope")):
            r = self.client.post("/api/file-watcher/watch", json={"path": "/etc"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("path not allowed", r.get_json()["error"])

    def test_add_watch_success(self):
        w = MagicMock()
        w.watch_id = "w1"
        w.path = "/tmp"
        self.fake_fw.get_file_watcher.return_value.add_watch.return_value = w
        with patch("orbit.core._security_utils.validate_path", return_value=(True, "ok")):
            r = self.client.post("/api/file-watcher/watch", json={"path": "/tmp", "recursive": False, "patterns": ["*.py"], "ignore_patterns": ["*.log"]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["watch_id"], "w1")
        self.assertEqual(r.get_json()["path"], "/tmp")
        self.fake_fw.get_file_watcher.return_value.add_watch.assert_called_once_with("/tmp", recursive=False, patterns=["*.py"], ignore_patterns=["*.log"])

    def test_add_watch_defaults(self):
        w = MagicMock()
        w.watch_id = "w2"
        w.path = "/tmp"
        self.fake_fw.get_file_watcher.return_value.add_watch.return_value = w
        with patch("orbit.core._security_utils.validate_path", return_value=(True, "ok")):
            r = self.client.post("/api/file-watcher/watch", json={"path": "/tmp"})
        self.fake_fw.get_file_watcher.return_value.add_watch.assert_called_once_with("/tmp", recursive=True, patterns=None, ignore_patterns=None)

    def test_add_watch_no_body(self):
        r = self.client.post("/api/file-watcher/watch")
        self.assertEqual(r.status_code, 400)

    def test_remove_watch(self):
        self.fake_fw.get_file_watcher.return_value.remove_watch.return_value = True
        r = self.client.delete("/api/file-watcher/w1")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["removed"])
        self.fake_fw.get_file_watcher.return_value.remove_watch.assert_called_once_with("w1")

    def test_scan(self):
        self.fake_fw.get_file_watcher.return_value.scan_all.return_value = {"scanned": 3}
        r = self.client.post("/api/file-watcher/scan")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["scanned"], 3)

    def test_start(self):
        r = self.client.post("/api/file-watcher/start")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "started")
        self.fake_fw.get_file_watcher.return_value.start.assert_called_once()

    def test_stop(self):
        r = self.client.post("/api/file-watcher/stop")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "stopped")
        self.fake_fw.get_file_watcher.return_value.stop.assert_called_once()

    def test_watches(self):
        self.fake_fw.get_file_watcher.return_value.list_watches.return_value = [{"id": "w1"}]
        r = self.client.get("/api/file-watcher/watches")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["watches"], [{"id": "w1"}])

    def test_events(self):
        self.fake_fw.get_file_watcher.return_value.get_events.return_value = [{"e": 1}]
        r = self.client.get("/api/file-watcher/events?limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["events"], [{"e": 1}])
        self.fake_fw.get_file_watcher.return_value.get_events.assert_called_once_with(5)

    def test_events_default(self):
        self.fake_fw.get_file_watcher.return_value.get_events.return_value = []
        r = self.client.get("/api/file-watcher/events")
        self.fake_fw.get_file_watcher.return_value.get_events.assert_called_once_with(50)

    def test_stats(self):
        self.fake_fw.get_file_watcher.return_value.get_stats.return_value = {"total": 2}
        r = self.client.get("/api/file-watcher/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 2)


if __name__ == "__main__":
    unittest.main()
