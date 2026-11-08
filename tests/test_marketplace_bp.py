"""Unit tests for orbit/orbit/core/marketplace_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.marketplace_bp import marketplace_bp


class TestMarketplaceBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(marketplace_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(marketplace_bp.name, "marketplace_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/marketplace/status", "/api/marketplace/browse", "/api/marketplace/skill/<skill_id>",
                  "/api/marketplace/install", "/api/marketplace/uninstall", "/api/marketplace/installed",
                  "/api/marketplace/categories"]:
            self.assertIn(p, rules)

    def test_status(self):
        with patch("orbit.core.marketplace_bp._get_mp") as gm:
            gm.return_value.get_status.return_value = {"ok": True}
            r = self.client.get("/api/marketplace/status")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])

    def test_browse(self):
        with patch("orbit.core.marketplace_bp._get_mp") as gm:
            gm.return_value.browse.return_value = [{"id": "s1"}]
            r = self.client.get("/api/marketplace/browse?category=cat&search=q&limit=10")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["skills"], [{"id": "s1"}])
        gm.return_value.browse.assert_called_once_with("cat", "q", 10)

    def test_browse_defaults(self):
        with patch("orbit.core.marketplace_bp._get_mp") as gm:
            gm.return_value.browse.return_value = []
            r = self.client.get("/api/marketplace/browse")
        gm.return_value.browse.assert_called_once_with("", "", 50)

    def test_skill_found(self):
        with patch("orbit.core.marketplace_bp._get_mp") as gm:
            gm.return_value.get_skill.return_value = {"id": "s1"}
            r = self.client.get("/api/marketplace/skill/s1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], "s1")
        gm.return_value.get_skill.assert_called_once_with("s1")
        gm.return_value._get_builtin_skill.assert_not_called()

    def test_skill_builtin_fallback(self):
        with patch("orbit.core.marketplace_bp._get_mp") as gm:
            gm.return_value.get_skill.return_value = None
            gm.return_value._get_builtin_skill.return_value = {"id": "b1"}
            r = self.client.get("/api/marketplace/skill/b1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], "b1")

    def test_skill_not_found_404(self):
        with patch("orbit.core.marketplace_bp._get_mp") as gm:
            gm.return_value.get_skill.return_value = None
            gm.return_value._get_builtin_skill.return_value = None
            r = self.client.get("/api/marketplace/skill/x")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_install_missing_skill_id_400(self):
        r = self.client.post("/api/marketplace/install", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_install_success(self):
        with patch("orbit.core.marketplace_bp._get_mp") as gm:
            gm.return_value.install.return_value = {"installed": True}
            r = self.client.post("/api/marketplace/install", json={"skill_id": "s1"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["installed"])
        gm.return_value.install.assert_called_once_with("s1")

    def test_install_no_body(self):
        r = self.client.post("/api/marketplace/install")
        self.assertEqual(r.status_code, 400)

    def test_uninstall_missing_skill_id_400(self):
        r = self.client.post("/api/marketplace/uninstall", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_uninstall_success(self):
        with patch("orbit.core.marketplace_bp._get_mp") as gm:
            gm.return_value.uninstall.return_value = {"uninstalled": True}
            r = self.client.post("/api/marketplace/uninstall", json={"skill_id": "s1"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["uninstalled"])
        gm.return_value.uninstall.assert_called_once_with("s1")

    def test_uninstall_no_body(self):
        r = self.client.post("/api/marketplace/uninstall")
        self.assertEqual(r.status_code, 400)

    def test_installed(self):
        with patch("orbit.core.marketplace_bp._get_mp") as gm:
            gm.return_value.get_installed.return_value = [{"id": "s1"}]
            r = self.client.get("/api/marketplace/installed")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["skills"], [{"id": "s1"}])

    def test_categories(self):
        with patch("orbit.core.marketplace_bp._get_mp") as gm:
            gm.return_value.get_categories.return_value = ["cat1"]
            r = self.client.get("/api/marketplace/categories")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["categories"], ["cat1"])

    def test_register(self):
        from orbit.core.marketplace_bp import register
        server = MagicMock()
        self.assertTrue(register(server))
        server.register_blueprint.assert_called_once_with(marketplace_bp)


if __name__ == "__main__":
    unittest.main()
