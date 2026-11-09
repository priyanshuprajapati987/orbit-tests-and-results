"""Unit tests for orbit/orbit/core/marketplace_v2_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.marketplace_v2_bp import marketplace_v2_bp


class TestMarketplaceV2Bp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(marketplace_v2_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(marketplace_v2_bp.name, "marketplace_v2")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/marketplace-v2/skills", "/api/marketplace-v2/skills/<skill_id>",
                  "/api/marketplace-v2/install", "/api/marketplace-v2/rate",
                  "/api/marketplace-v2/hubs", "/api/marketplace-v2/featured",
                  "/api/marketplace-v2/stats"]:
            self.assertIn(p, rules)

    def test_list_skills(self):
        with patch("orbit.core.marketplace_v2_bp.get_marketplace") as gm:
            gm.return_value.search.return_value = [{"id": "s1"}]
            r = self.client.get("/api/marketplace-v2/skills?q=q&category=cat")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["skills"], [{"id": "s1"}])
        self.assertEqual(r.get_json()["count"], 1)
        gm.return_value.search.assert_called_once_with("q", category="cat")

    def test_list_skills_defaults(self):
        with patch("orbit.core.marketplace_v2_bp.get_marketplace") as gm:
            gm.return_value.search.return_value = []
            r = self.client.get("/api/marketplace-v2/skills")
        gm.return_value.search.assert_called_once_with("", category=None)

    def test_get_skill_found(self):
        with patch("orbit.core.marketplace_v2_bp.get_marketplace") as gm:
            gm.return_value.get.return_value = {"id": "s1"}
            r = self.client.get("/api/marketplace-v2/skills/s1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], "s1")
        gm.return_value.get.assert_called_once_with("s1")

    def test_get_skill_not_found_404(self):
        with patch("orbit.core.marketplace_v2_bp.get_marketplace") as gm:
            gm.return_value.get.return_value = None
            r = self.client.get("/api/marketplace-v2/skills/s1")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_publish_missing_name_400(self):
        r = self.client.post("/api/marketplace-v2/skills", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_publish_success(self):
        with patch("orbit.core.marketplace_v2_bp.get_marketplace") as gm:
            gm.return_value.publish.return_value = "skill_id_1"
            r = self.client.post("/api/marketplace-v2/skills", json={
                "name": "n", "description": "d", "code": "c", "tags": ["t"], "category": "cat", "author": "me"
            })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertEqual(r.get_json()["skill_id"], "skill_id_1")
        gm.return_value.publish.assert_called_once_with("n", description="d", skill_data={"code": "c", "tags": ["t"]}, category="cat", author="me")

    def test_publish_no_body(self):
        r = self.client.post("/api/marketplace-v2/skills")
        self.assertEqual(r.status_code, 400)

    def test_install_missing_skill_id_400(self):
        r = self.client.post("/api/marketplace-v2/install", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_install_success(self):
        with patch("orbit.core.marketplace_v2_bp.get_marketplace") as gm:
            gm.return_value.install.return_value = {"installed": True}
            r = self.client.post("/api/marketplace-v2/install", json={"skill_id": "s1"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["installed"])
        gm.return_value.install.assert_called_once_with("s1")

    def test_install_no_body(self):
        r = self.client.post("/api/marketplace-v2/install")
        self.assertEqual(r.status_code, 400)

    def test_rate_missing_fields_400(self):
        r = self.client.post("/api/marketplace-v2/rate", json={"skill_id": "s1"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_rate_bad_rating_400(self):
        r = self.client.post("/api/marketplace-v2/rate", json={"skill_id": "s1", "rating": 10})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_rate_success(self):
        with patch("orbit.core.marketplace_v2_bp.get_marketplace") as gm:
            gm.return_value.rate.return_value = True
            r = self.client.post("/api/marketplace-v2/rate", json={"skill_id": "s1", "rating": 4})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertTrue(r.get_json()["rated"])
        gm.return_value.rate.assert_called_once_with("s1", 4)

    def test_rate_no_body(self):
        r = self.client.post("/api/marketplace-v2/rate")
        self.assertEqual(r.status_code, 400)

    def test_hubs(self):
        with patch("orbit.core.marketplace_v2_bp.get_marketplace") as gm:
            gm.return_value.get_hubs.return_value = ["h1"]
            r = self.client.get("/api/marketplace-v2/hubs")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["hubs"], ["h1"])

    def test_featured(self):
        with patch("orbit.core.marketplace_v2_bp.get_marketplace") as gm:
            gm.return_value.get_featured.return_value = [{"id": "f1"}]
            r = self.client.get("/api/marketplace-v2/featured")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["skills"], [{"id": "f1"}])

    def test_stats(self):
        with patch("orbit.core.marketplace_v2_bp.get_marketplace") as gm:
            gm.return_value.get_stats.return_value = {"total": 5}
            r = self.client.get("/api/marketplace-v2/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)


if __name__ == "__main__":
    unittest.main()
