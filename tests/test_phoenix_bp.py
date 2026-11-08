"""Unit tests for orbit/orbit/core/phoenix_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.phoenix_bp import phoenix_bp


class TestPhoenixBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(phoenix_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(phoenix_bp.name, "phoenix")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/phoenix/health", "/api/phoenix/checkpoint", "/api/phoenix/backup",
                  "/api/phoenix/restore", "/api/phoenix/backups", "/api/phoenix/history",
                  "/api/phoenix/stats"]:
            self.assertIn(p, rules)

    def test_health(self):
        with patch("orbit.core.phoenix_bp.check_health", return_value={"ok": True}):
            r = self.client.get("/api/phoenix/health")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])

    def test_checkpoint(self):
        with patch("orbit.core.phoenix_bp.take_checkpoint", return_value={"id": "c1"}) as tc:
            r = self.client.post("/api/phoenix/checkpoint", json={"label": "manual"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], "c1")
        tc.assert_called_once_with("manual")

    def test_checkpoint_default(self):
        with patch("orbit.core.phoenix_bp.take_checkpoint", return_value={"id": "c2"}) as tc:
            r = self.client.post("/api/phoenix/checkpoint", json={})
        tc.assert_called_once_with("api")

    def test_checkpoint_no_body(self):
        with patch("orbit.core.phoenix_bp.take_checkpoint", return_value={"id": "c3"}) as tc:
            r = self.client.post("/api/phoenix/checkpoint")
        tc.assert_called_once_with("api")

    def test_backup(self):
        with patch("orbit.core.phoenix_bp.create_backup", return_value={"id": "b1"}) as cb:
            r = self.client.post("/api/phoenix/backup", json={"label": "nightly"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], "b1")
        cb.assert_called_once_with("nightly")

    def test_backup_default(self):
        with patch("orbit.core.phoenix_bp.create_backup", return_value={"id": "b2"}) as cb:
            r = self.client.post("/api/phoenix/backup", json={})
        cb.assert_called_once_with("")

    def test_backup_no_body(self):
        with patch("orbit.core.phoenix_bp.create_backup", return_value={"id": "b3"}) as cb:
            r = self.client.post("/api/phoenix/backup")
        cb.assert_called_once_with("")

    def test_restore(self):
        with patch("orbit.core.phoenix_bp.restore_backup", return_value={"restored": True}) as rb:
            r = self.client.post("/api/phoenix/restore", json={"backup_id": "b1"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["restored"])
        rb.assert_called_once_with("b1")

    def test_restore_default(self):
        with patch("orbit.core.phoenix_bp.restore_backup", return_value={"restored": True}) as rb:
            r = self.client.post("/api/phoenix/restore", json={})
        rb.assert_called_once_with("")

    def test_restore_no_body(self):
        with patch("orbit.core.phoenix_bp.restore_backup", return_value={"restored": True}) as rb:
            r = self.client.post("/api/phoenix/restore")
        rb.assert_called_once_with("")

    def test_list_backups(self):
        with patch("orbit.core.phoenix_bp.get_phoenix") as gp:
            phoenix = gp.return_value
            phoenix.list_backups.return_value = ["b1"]
            phoenix.list_checkpoints.return_value = ["c1"]
            r = self.client.get("/api/phoenix/backups")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["backups"], ["b1"])
        self.assertEqual(body["checkpoints"], ["c1"])

    def test_history(self):
        with patch("orbit.core.phoenix_bp.get_phoenix_history", return_value=[{"e": 1}]) as gh:
            r = self.client.get("/api/phoenix/history?limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["events"], [{"e": 1}])
        gh.assert_called_once_with(5)

    def test_history_default(self):
        with patch("orbit.core.phoenix_bp.get_phoenix_history", return_value=[]) as gh:
            r = self.client.get("/api/phoenix/history")
        gh.assert_called_once_with(50)

    def test_stats(self):
        with patch("orbit.core.phoenix_bp.get_phoenix_stats", return_value={"total": 2}):
            r = self.client.get("/api/phoenix/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 2)


if __name__ == "__main__":
    unittest.main()
