"""Unit tests for orbit/orbit/core/cleanup_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.cleanup_bp import cleanup_bp


class TestCleanupBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(cleanup_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(cleanup_bp.name, "cleanup_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/cleanup/scan", rules)
        self.assertIn("/api/cleanup/run", rules)

    def test_scan(self):
        with patch("orbit.core.cleanup_bp.get_cleanup") as gc:
            gc.return_value.scan.return_value = {"files": 3}
            r = self.client.get("/api/cleanup/scan")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["files"], 3)

    def test_run_dry_run_default(self):
        with patch("orbit.core.cleanup_bp.get_cleanup") as gc:
            gc.return_value.clean.return_value = {"deleted": 0}
            r = self.client.post("/api/cleanup/run", json={})
        self.assertEqual(r.status_code, 200)
        gc.return_value.clean.assert_called_once_with(7, dry_run=True)

    def test_run_dry_run_false(self):
        with patch("orbit.core.cleanup_bp.get_cleanup") as gc:
            gc.return_value.clean.return_value = {"deleted": 2}
            r = self.client.post("/api/cleanup/run", json={"older_than_days": 14, "dry_run": False})
        self.assertEqual(r.status_code, 200)
        gc.return_value.clean.assert_called_once_with(14, dry_run=False)

    def test_run_dry_run_string_false(self):
        with patch("orbit.core.cleanup_bp.get_cleanup") as gc:
            gc.return_value.clean.return_value = {"deleted": 1}
            r = self.client.post("/api/cleanup/run", json={"dry_run": "false"})
        gc.return_value.clean.assert_called_once_with(7, dry_run=False)

    def test_run_no_body(self):
        with patch("orbit.core.cleanup_bp.get_cleanup") as gc:
            gc.return_value.clean.return_value = {"deleted": 0}
            r = self.client.post("/api/cleanup/run")
        self.assertEqual(r.status_code, 200)
        gc.return_value.clean.assert_called_once_with(7, dry_run=True)


if __name__ == "__main__":
    unittest.main()
