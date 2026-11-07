"""Unit tests for orbit/orbit/core/updater_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.updater_bp import updater_bp


class TestUpdaterBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(updater_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(updater_bp.name, "updater")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/updater/check", "/api/updater/apply", "/api/updater/rollback", "/api/updater/backups"]:
            self.assertIn(p, rules)

    def test_check(self):
        with patch("orbit.core.updater_bp.get_updater") as gu:
            gu.return_value.check_for_updates.return_value = {"available": True}
            r = self.client.get("/api/updater/check")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["available"])

    def test_apply_missing_confirm(self):
        r = self.client.post("/api/updater/apply", json={})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "missing_confirm")

    def test_apply_success(self):
        with patch("orbit.core.updater_bp.get_updater") as gu:
            gu.return_value.apply_update.return_value = {"applied": True}
            r = self.client.post("/api/updater/apply", json={"confirm": True})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["applied"])

    def test_rollback_missing_confirm(self):
        r = self.client.post("/api/updater/rollback", json={})
        self.assertEqual(r.status_code, 400)

    def test_rollback_success(self):
        with patch("orbit.core.updater_bp.get_updater") as gu:
            gu.return_value.rollback.return_value = {"rolled_back": True}
            r = self.client.post("/api/updater/rollback", json={"confirm": True})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["rolled_back"])

    def test_backups(self):
        with patch("orbit.core.updater_bp.get_updater") as gu:
            gu.return_value.get_backups.return_value = ["b1"]
            r = self.client.get("/api/updater/backups")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["backups"], ["b1"])


if __name__ == "__main__":
    unittest.main()
