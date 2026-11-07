"""Unit tests for orbit/orbit/core/continuity_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.continuity_bp import continuity_bp


class TestContinuityBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(continuity_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(continuity_bp.name, "continuity")

    def test_url_prefix(self):
        self.assertEqual(continuity_bp.url_prefix, "/api/continuity")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/continuity/export", rules)
        self.assertIn("/api/continuity/import", rules)

    def test_export_success(self):
        with patch("orbit.core.continuity_bp.export_package", return_value="PKGDATA") as m:
            r = self.client.post("/api/continuity/export", json={"passphrase": "secret"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        self.assertEqual(r.get_json()["package"], "PKGDATA")
        m.assert_called_once_with("secret")

    def test_export_missing_passphrase(self):
        with patch("orbit.core.continuity_bp.export_package", return_value=None):
            r = self.client.post("/api/continuity/export", json={})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.get_json()["ok"])

    def test_export_no_body(self):
        with patch("orbit.core.continuity_bp.export_package", return_value=None):
            r = self.client.post("/api/continuity/export")
        self.assertEqual(r.status_code, 400)

    def test_import_success(self):
        with patch("orbit.core.continuity_bp.import_package", return_value={"ok": True, "imported": 3}) as m:
            r = self.client.post("/api/continuity/import", json={"package": "PKG", "passphrase": "secret"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        m.assert_called_once_with("PKG", "secret")

    def test_import_failure(self):
        with patch("orbit.core.continuity_bp.import_package", return_value={"ok": False, "error": "bad"}):
            r = self.client.post("/api/continuity/import", json={"package": "PKG", "passphrase": "x"})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.get_json()["ok"])

    def test_import_no_body(self):
        with patch("orbit.core.continuity_bp.import_package", return_value={"ok": False, "error": "no data"}):
            r = self.client.post("/api/continuity/import")
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
