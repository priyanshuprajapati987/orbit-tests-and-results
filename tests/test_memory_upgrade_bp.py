"""Unit tests for orbit/orbit/core/memory_upgrade_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.memory_upgrade_bp import memory_upgrade_bp


class TestMemoryUpgradeBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(memory_upgrade_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(memory_upgrade_bp.name, "memory_upgrade")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/memory/profile", "/api/memory/profile/summary", "/api/memory/profile/update",
                  "/api/memory/categories", "/api/memory/categories/search", "/api/memory/categories/add",
                  "/api/memory/categories/cleanup"]:
            self.assertIn(p, rules)

    def test_profile(self):
        with patch("orbit.core.memory_upgrade_bp.get_profile") as gp:
            gp.return_value.get_all.return_value = {"name": "x"}
            r = self.client.get("/api/memory/profile")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["name"], "x")

    def test_profile_summary(self):
        with patch("orbit.core.memory_upgrade_bp.get_profile") as gp:
            gp.return_value.get_summary.return_value = "summary"
            r = self.client.get("/api/memory/profile/summary")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), "summary")

    def test_profile_update_missing_400(self):
        r = self.client.post("/api/memory/profile/update", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_profile_update_success(self):
        with patch("orbit.core.memory_upgrade_bp.get_profile") as gp:
            r = self.client.post("/api/memory/profile/update", json={"key": "k", "value": "v", "category": "personal"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertEqual(r.get_json()["key"], "k")
        gp.return_value.update.assert_called_once_with("k", "v", "personal")

    def test_profile_update_defaults(self):
        with patch("orbit.core.memory_upgrade_bp.get_profile") as gp:
            r = self.client.post("/api/memory/profile/update", json={"key": "k", "value": "v"})
        gp.return_value.update.assert_called_once_with("k", "v", "personal")

    def test_profile_update_no_body(self):
        r = self.client.post("/api/memory/profile/update")
        self.assertEqual(r.status_code, 400)

    def test_categories(self):
        with patch("orbit.core.memory_upgrade_bp.get_categorized_memory") as gc:
            gc.return_value.stats.return_value = {"total": 5}
            r = self.client.get("/api/memory/categories")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)

    def test_cat_search_missing_q_400(self):
        r = self.client.get("/api/memory/categories/search")
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_cat_search_success(self):
        with patch("orbit.core.memory_upgrade_bp.get_categorized_memory") as gc:
            gc.return_value.search.return_value = [{"id": 1}]
            r = self.client.get("/api/memory/categories/search?q=hi&category=personal")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["results"], [{"id": 1}])
        self.assertEqual(r.get_json()["count"], 1)
        gc.return_value.search.assert_called_once_with("hi", category="personal")

    def test_cat_search_no_category(self):
        with patch("orbit.core.memory_upgrade_bp.get_categorized_memory") as gc:
            gc.return_value.search.return_value = []
            r = self.client.get("/api/memory/categories/search?q=hi")
        gc.return_value.search.assert_called_once_with("hi", category=None)

    def test_cat_add_missing_content_400(self):
        r = self.client.post("/api/memory/categories/add", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_cat_add_success(self):
        with patch("orbit.core.memory_upgrade_bp.get_categorized_memory") as gc:
            r = self.client.post("/api/memory/categories/add", json={"content": "hi", "category": "work", "importance": 0.8, "agent": "TAS"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        gc.return_value.add.assert_called_once_with("hi", "work", 0.8, "TAS")

    def test_cat_add_defaults(self):
        with patch("orbit.core.memory_upgrade_bp.get_categorized_memory") as gc:
            r = self.client.post("/api/memory/categories/add", json={"content": "hi"})
        gc.return_value.add.assert_called_once_with("hi", "personal", None, "user")

    def test_cat_add_no_body(self):
        r = self.client.post("/api/memory/categories/add")
        self.assertEqual(r.status_code, 400)

    def test_cat_cleanup(self):
        with patch("orbit.core.memory_upgrade_bp.get_categorized_memory") as gc:
            gc.return_value.cleanup.return_value = 3
            r = self.client.post("/api/memory/categories/cleanup")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertEqual(r.get_json()["removed"], 3)


if __name__ == "__main__":
    unittest.main()
