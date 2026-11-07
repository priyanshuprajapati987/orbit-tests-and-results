"""Unit tests for orbit/orbit/core/mesh_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.mesh_bp import mesh_bp


class TestMeshBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(mesh_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(mesh_bp.name, "mesh")

    def test_url_prefix(self):
        self.assertEqual(mesh_bp.url_prefix, "/api/mesh")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/mesh/export", rules)
        self.assertIn("/api/mesh/import", rules)

    def test_export_success(self):
        with patch("orbit.core.mesh_bp.export_capsule", return_value="CAPDATA") as m:
            r = self.client.post("/api/mesh/export", json={"name": "n", "code": "c", "passphrase": "p"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        self.assertEqual(r.get_json()["capsule"], "CAPDATA")
        m.assert_called_once_with("n", "c", "p")

    def test_export_missing(self):
        with patch("orbit.core.mesh_bp.export_capsule", return_value=None):
            r = self.client.post("/api/mesh/export", json={})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.get_json()["ok"])

    def test_export_no_body(self):
        with patch("orbit.core.mesh_bp.export_capsule", return_value=None):
            r = self.client.post("/api/mesh/export")
        self.assertEqual(r.status_code, 400)

    def test_import_success(self):
        with patch("orbit.core.mesh_bp.import_capsule", return_value={"ok": True, "imported": 1}) as m:
            r = self.client.post("/api/mesh/import", json={"capsule": "CAP", "passphrase": "p"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        m.assert_called_once_with("CAP", "p")

    def test_import_failure(self):
        with patch("orbit.core.mesh_bp.import_capsule", return_value={"ok": False, "error": "bad"}):
            r = self.client.post("/api/mesh/import", json={"capsule": "CAP", "passphrase": "x"})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.get_json()["ok"])

    def test_import_no_body(self):
        with patch("orbit.core.mesh_bp.import_capsule", return_value={"ok": False, "error": "no data"}):
            r = self.client.post("/api/mesh/import")
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
