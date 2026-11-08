"""Unit tests for orbit/orbit/core/knowledge_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.knowledge_bp import knowledge_bp


class TestKnowledgeBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(knowledge_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(knowledge_bp.name, "knowledge")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/knowledge/add", "/api/knowledge/search", "/api/knowledge/<card_id>",
                  "/api/knowledge/list", "/api/knowledge/stats"]:
            self.assertIn(p, rules)

    def test_add_missing_fields_400(self):
        r = self.client.post("/api/knowledge/add", json={"title": "t"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_add_success(self):
        with patch("orbit.core.knowledge_base.get_knowledge_base") as gkb:
            gkb.return_value.add.return_value = "card1"
            r = self.client.post("/api/knowledge/add", json={"title": "t", "content": "c", "category": "coding", "confidence": 0.9, "tags": ["x"]})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        self.assertEqual(r.get_json()["card_id"], "card1")
        from orbit.core.knowledge_base import KnowledgeCategory
        gkb.return_value.add.assert_called_once_with("t", "c", KnowledgeCategory.CODING, confidence=0.9, tags=["x"])

    def test_add_invalid_category_fallback(self):
        with patch("orbit.core.knowledge_base.get_knowledge_base") as gkb:
            gkb.return_value.add.return_value = "card2"
            r = self.client.post("/api/knowledge/add", json={"title": "t", "content": "c", "category": "nope"})
        from orbit.core.knowledge_base import KnowledgeCategory
        gkb.return_value.add.assert_called_once_with("t", "c", KnowledgeCategory.GENERAL, confidence=0.5, tags=None)

    def test_add_no_body(self):
        r = self.client.post("/api/knowledge/add")
        self.assertEqual(r.status_code, 400)

    def test_search(self):
        with patch("orbit.core.knowledge_base.get_knowledge_base") as gkb:
            gkb.return_value.search.return_value = [{"id": "c1"}]
            r = self.client.get("/api/knowledge/search?q=hi&category=coding&limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["results"], [{"id": "c1"}])
        from orbit.core.knowledge_base import KnowledgeCategory
        gkb.return_value.search.assert_called_once_with("hi", KnowledgeCategory.CODING, 5)

    def test_search_no_category(self):
        with patch("orbit.core.knowledge_base.get_knowledge_base") as gkb:
            gkb.return_value.search.return_value = []
            r = self.client.get("/api/knowledge/search?q=hi")
        from orbit.core.knowledge_base import KnowledgeCategory
        gkb.return_value.search.assert_called_once_with("hi", None, 10)

    def test_search_invalid_category(self):
        with patch("orbit.core.knowledge_base.get_knowledge_base") as gkb:
            gkb.return_value.search.return_value = []
            r = self.client.get("/api/knowledge/search?q=hi&category=nope")
        gkb.return_value.search.assert_called_once_with("hi", None, 10)

    def test_get_card_found(self):
        with patch("orbit.core.knowledge_base.get_knowledge_base") as gkb:
            gkb.return_value.get.return_value = {"id": "c1"}
            r = self.client.get("/api/knowledge/c1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], "c1")
        gkb.return_value.get.assert_called_once_with("c1")

    def test_get_card_not_found_404(self):
        with patch("orbit.core.knowledge_base.get_knowledge_base") as gkb:
            gkb.return_value.get.return_value = None
            r = self.client.get("/api/knowledge/c1")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_list_cards(self):
        with patch("orbit.core.knowledge_base.get_knowledge_base") as gkb:
            gkb.return_value.get_all.return_value = [{"id": "c1"}, {"id": "c2"}]
            r = self.client.get("/api/knowledge/list")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["cards"], [{"id": "c1"}, {"id": "c2"}])

    def test_stats(self):
        with patch("orbit.core.knowledge_base.get_knowledge_base") as gkb:
            gkb.return_value.get_stats.return_value = {"total": 5}
            r = self.client.get("/api/knowledge/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)


if __name__ == "__main__":
    unittest.main()
