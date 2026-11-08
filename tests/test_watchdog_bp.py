"""Unit tests for orbit/orbit/core/watchdog_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.watchdog_bp import watchdog_bp


class TestWatchdogBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(watchdog_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(watchdog_bp.name, "watchdog")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/watchdog/status", "/api/watchdog/start", "/api/watchdog/stop",
                  "/api/watchdog/incidents", "/api/watchdog/locks", "/api/watchdog/locks/<name>",
                  "/api/watchdog/locks/acquire", "/api/watchdog/locks/<name>/release",
                  "/api/watchdog/locks/reclaim"]:
            self.assertIn(p, rules)

    def test_status(self):
        with patch("orbit.core.watchdog_bp.get_watchdog") as gw:
            gw.return_value.get_status.return_value = {"healthy": True}
            r = self.client.get("/api/watchdog/status")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["healthy"])

    def test_start(self):
        with patch("orbit.core.watchdog_bp.get_watchdog") as gw:
            r = self.client.post("/api/watchdog/start")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertEqual(r.get_json()["message"], "Watchdog started")
        gw.return_value.start.assert_called_once()

    def test_stop(self):
        with patch("orbit.core.watchdog_bp.get_watchdog") as gw:
            r = self.client.post("/api/watchdog/stop")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertEqual(r.get_json()["message"], "Watchdog stopped")
        gw.return_value.stop.assert_called_once()

    def test_incidents(self):
        with patch("orbit.core.watchdog_bp.get_watchdog") as gw:
            gw.return_value.get_incidents.return_value = [{"id": 1}, {"id": 2}]
            r = self.client.get("/api/watchdog/incidents")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["count"], 2)
        self.assertEqual(body["incidents"], [{"id": 1}, {"id": 2}])

    def test_locks(self):
        with patch("orbit.core.watchdog_bp.get_watchdog") as gw:
            gw.return_value.get_all_locks.return_value = [{"name": "l1"}]
            r = self.client.get("/api/watchdog/locks")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["locks"], [{"name": "l1"}])

    def test_lock_detail_found(self):
        with patch("orbit.core.watchdog_bp.get_watchdog") as gw:
            gw.return_value.get_lock_status.return_value = {"name": "l1", "held": True}
            r = self.client.get("/api/watchdog/locks/l1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertEqual(r.get_json()["lock"]["name"], "l1")
        gw.return_value.get_lock_status.assert_called_once_with("l1")

    def test_lock_detail_not_found_404(self):
        with patch("orbit.core.watchdog_bp.get_watchdog") as gw:
            gw.return_value.get_lock_status.return_value = None
            r = self.client.get("/api/watchdog/locks/missing")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["status"], "not_found")

    def test_lock_acquire_missing_name_400(self):
        r = self.client.post("/api/watchdog/locks/acquire", json={})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["status"], "error")

    def test_lock_acquire_success(self):
        with patch("orbit.core.watchdog_bp.get_watchdog") as gw:
            gw.return_value.acquire_lock.return_value = True
            r = self.client.post("/api/watchdog/locks/acquire", json={"name": "l1", "component": "c1"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertTrue(r.get_json()["acquired"])
        gw.return_value.acquire_lock.assert_called_once_with("l1", "c1")

    def test_lock_acquire_defaults(self):
        with patch("orbit.core.watchdog_bp.get_watchdog") as gw:
            gw.return_value.acquire_lock.return_value = False
            r = self.client.post("/api/watchdog/locks/acquire", json={"name": "l1"})
        gw.return_value.acquire_lock.assert_called_once_with("l1", "")

    def test_lock_acquire_no_body(self):
        r = self.client.post("/api/watchdog/locks/acquire")
        self.assertEqual(r.status_code, 400)

    def test_lock_release(self):
        with patch("orbit.core.watchdog_bp.get_watchdog") as gw:
            gw.return_value.release_lock.return_value = True
            r = self.client.post("/api/watchdog/locks/l1/release")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertTrue(r.get_json()["released"])
        gw.return_value.release_lock.assert_called_once_with("l1")

    def test_lock_reclaim(self):
        with patch("orbit.core.watchdog_bp.get_watchdog") as gw:
            gw.return_value._lock_manager.reclaim_dead_locks.return_value = ["l1", "l2"]
            r = self.client.post("/api/watchdog/locks/reclaim")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["reclaimed"], ["l1", "l2"])
        self.assertEqual(body["count"], 2)


if __name__ == "__main__":
    unittest.main()
