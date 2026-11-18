"""Unit tests for orbit/orbit/core/idea_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.idea_bp import idea_bp


class IdeaBpBase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(idea_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(idea_bp.name, "idea_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/ideas/add", "/api/ideas/list", "/api/ideas/top",
                  "/api/ideas/search", "/api/ideas/<idea_id>",
                  "/api/ideas/update/<idea_id>", "/api/ideas/delete/<idea_id>",
                  "/api/ideas/<idea_id>/convert", "/api/ideas/<idea_id>/score",
                  "/api/ideas/<idea_id>/related"]:
            self.assertIn(p, rules)


class TestAddIdea(IdeaBpBase):
    def test_add_success(self):
        with patch("orbit.core.idea_bp.get_idea_vault") as gv:
            gv.return_value.add_idea.return_value = {"id": "i1", "title": "T"}
            r = self.client.post("/api/ideas/add", json={"title": "T"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["id"], "i1")
        gv.return_value.add_idea.assert_called_once_with(
            title="T", description="", category="personal",
            feasibility=5, impact=5, tags=None,
        )

    def test_add_all_fields(self):
        with patch("orbit.core.idea_bp.get_idea_vault") as gv:
            gv.return_value.add_idea.return_value = {"id": "i2"}
            r = self.client.post("/api/ideas/add", json={
                "title": "T", "description": "D", "category": "tech",
                "feasibility": 8, "impact": 9, "tags": ["a"],
            })
        self.assertEqual(r.status_code, 200)
        gv.return_value.add_idea.assert_called_once_with(
            title="T", description="D", category="tech",
            feasibility=8, impact=9, tags=["a"],
        )

    def test_add_missing_title_400(self):
        r = self.client.post("/api/ideas/add", json={"description": "x"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_add_no_body_400(self):
        r = self.client.post("/api/ideas/add")
        self.assertEqual(r.status_code, 400)

    def test_add_exception_500_json(self):
        with patch("orbit.core.idea_bp.get_idea_vault", side_effect=RuntimeError("boom")):
            r = self.client.post("/api/ideas/add", json={"title": "T"})
        self.assertEqual(r.status_code, 500)
        body = r.get_json()
        self.assertEqual(body["error"], "boom")
        self.assertEqual(body["route"], "add_idea")
        self.assertEqual(body["type"], "RuntimeError")


class TestListIdeas(IdeaBpBase):
    def test_list_default(self):
        with patch("orbit.core.idea_bp.get_idea_vault") as gv:
            gv.return_value.list_ideas.return_value = [{"id": "i1"}]
            r = self.client.get("/api/ideas/list")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["ideas"], [{"id": "i1"}])
        gv.return_value.list_ideas.assert_called_once_with(category=None, sort_by="score")

    def test_list_with_filters(self):
        with patch("orbit.core.idea_bp.get_idea_vault") as gv:
            gv.return_value.list_ideas.return_value = []
            r = self.client.get("/api/ideas/list?category=tech&sort=newest")
        gv.return_value.list_ideas.assert_called_once_with(category="tech", sort_by="newest")

    def test_list_exception_500(self):
        with patch("orbit.core.idea_bp.get_idea_vault", side_effect=RuntimeError("x")):
            r = self.client.get("/api/ideas/list")
        self.assertEqual(r.status_code, 500)


class TestGetIdea(IdeaBpBase):
    def test_get_found(self):
        with patch("orbit.core.idea_bp.get_idea_vault") as gv:
            gv.return_value.get_idea.return_value = {"id": "i1"}
            r = self.client.get("/api/ideas/i1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], "i1")

    def test_get_not_found_404(self):
        with patch("orbit.core.idea_bp.get_idea_vault") as gv:
            gv.return_value.get_idea.return_value = None
            r = self.client.get("/api/ideas/nope")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"], "idea not found")


class TestUpdateIdea(IdeaBpBase):
    def test_update_success(self):
        with patch("orbit.core.idea_bp.get_idea_vault") as gv:
            gv.return_value.update_idea.return_value = {"id": "i1", "title": "New"}
            r = self.client.post("/api/ideas/update/i1", json={"title": "New"})
        self.assertEqual(r.status_code, 200)
        gv.return_value.update_idea.assert_called_once_with("i1", title="New")

    def test_update_not_found_404(self):
        with patch("orbit.core.idea_bp.get_idea_vault") as gv:
            gv.return_value.update_idea.return_value = None
            r = self.client.post("/api/ideas/update/nope", json={"title": "x"})
        self.assertEqual(r.status_code, 404)

    def test_update_no_body(self):
        with patch("orbit.core.idea_bp.get_idea_vault") as gv:
            gv.return_value.update_idea.return_value = {"id": "i1"}
            r = self.client.post("/api/ideas/update/i1")
        self.assertEqual(r.status_code, 200)
        gv.return_value.update_idea.assert_called_once_with("i1")


class TestDeleteIdea(IdeaBpBase):
    def test_delete_post_ok(self):
        with patch("orbit.core.idea_bp.get_idea_vault") as gv:
            gv.return_value.delete_idea.return_value = True
            r = self.client.post("/api/ideas/delete/i1")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["deleted"])

    def test_delete_method_ok(self):
        with patch("orbit.core.idea_bp.get_idea_vault") as gv:
            gv.return_value.delete_idea.return_value = True
            r = self.client.delete("/api/ideas/i1")
        self.assertEqual(r.status_code, 200)

    def test_delete_not_found_404(self):
        with patch("orbit.core.idea_bp.get_idea_vault") as gv:
            gv.return_value.delete_idea.return_value = False
            r = self.client.delete("/api/ideas/nope")
        self.assertEqual(r.status_code, 404)


class TestTopIdeas(IdeaBpBase):
    def test_top_default(self):
        with patch("orbit.core.idea_bp.get_idea_vault") as gv:
            gv.return_value.get_top_ideas.return_value = [{"id": "i1"}]
            r = self.client.get("/api/ideas/top")
        self.assertEqual(r.status_code, 200)
        gv.return_value.get_top_ideas.assert_called_once_with(limit=5)

    def test_top_limit(self):
        with patch("orbit.core.idea_bp.get_idea_vault") as gv:
            gv.return_value.get_top_ideas.return_value = []
            r = self.client.get("/api/ideas/top?limit=10")
        gv.return_value.get_top_ideas.assert_called_once_with(limit=10)


class TestConvertToGoal(IdeaBpBase):
    def test_convert_alias(self):
        with patch("orbit.core.idea_bp.get_idea_vault") as gv:
            gv.return_value.convert_to_goal.return_value = {"id": "i1", "goal": "G"}
            r = self.client.post("/api/ideas/i1/convert")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["goal"], "G")

    def test_convert_long_alias(self):
        with patch("orbit.core.idea_bp.get_idea_vault") as gv:
            gv.return_value.convert_to_goal.return_value = {"id": "i1"}
            r = self.client.post("/api/ideas/i1/convert-to-goal")
        self.assertEqual(r.status_code, 200)

    def test_convert_not_found_404(self):
        with patch("orbit.core.idea_bp.get_idea_vault") as gv:
            gv.return_value.convert_to_goal.return_value = None
            r = self.client.post("/api/ideas/nope/convert")
        self.assertEqual(r.status_code, 404)


class TestScoreIdea(IdeaBpBase):
    def test_score_defaults(self):
        with patch("orbit.core.idea_bp.get_idea_vault") as gv:
            gv.return_value.score_idea.return_value = {"id": "i1", "score": 25}
            r = self.client.post("/api/ideas/i1/score", json={})
        self.assertEqual(r.status_code, 200)
        gv.return_value.score_idea.assert_called_once_with("i1", 5, 5)

    def test_score_explicit(self):
        with patch("orbit.core.idea_bp.get_idea_vault") as gv:
            gv.return_value.score_idea.return_value = {"id": "i1"}
            r = self.client.post("/api/ideas/i1/score", json={"feasibility": 9, "impact": 8})
        gv.return_value.score_idea.assert_called_once_with("i1", 9, 8)

    def test_score_no_body(self):
        with patch("orbit.core.idea_bp.get_idea_vault") as gv:
            gv.return_value.score_idea.return_value = {"id": "i1"}
            r = self.client.post("/api/ideas/i1/score")
        self.assertEqual(r.status_code, 200)

    def test_score_not_found_404(self):
        with patch("orbit.core.idea_bp.get_idea_vault") as gv:
            gv.return_value.score_idea.return_value = None
            r = self.client.post("/api/ideas/nope/score", json={})
        self.assertEqual(r.status_code, 404)


class TestSearchIdeas(IdeaBpBase):
    def test_search_with_q(self):
        with patch("orbit.core.idea_bp.get_idea_vault") as gv:
            gv.return_value.search_ideas.return_value = [{"id": "i1"}]
            r = self.client.get("/api/ideas/search?q=rocket")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["ideas"], [{"id": "i1"}])
        gv.return_value.search_ideas.assert_called_once_with("rocket")

    def test_search_no_q(self):
        with patch("orbit.core.idea_bp.get_idea_vault") as gv:
            r = self.client.get("/api/ideas/search")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["ideas"], [])
        gv.return_value.search_ideas.assert_not_called()


class TestRelatedIdeas(IdeaBpBase):
    def test_related(self):
        with patch("orbit.core.idea_bp.get_idea_vault") as gv:
            gv.return_value.get_related_ideas.return_value = [{"id": "i2"}]
            r = self.client.get("/api/ideas/i1/related")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["ideas"], [{"id": "i2"}])
        gv.return_value.get_related_ideas.assert_called_once_with("i1")

    def test_related_exception_500(self):
        with patch("orbit.core.idea_bp.get_idea_vault", side_effect=RuntimeError("x")):
            r = self.client.get("/api/ideas/i1/related")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["route"], "related_ideas")


if __name__ == "__main__":
    unittest.main()
