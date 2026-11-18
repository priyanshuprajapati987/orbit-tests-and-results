"""Unit tests for orbit/orbit/core/goal_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.goal_bp import goal_bp


class GoalBpBase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(goal_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(goal_bp.name, "goals")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/goals", "/api/goals/<goal_id>", "/api/goals/add",
                  "/api/goals/<goal_id>/progress",
                  "/api/goals/<goal_id>/milestone",
                  "/api/goals/<goal_id>/milestone/<int:idx>/complete",
                  "/api/goals/<goal_id>/subgoal",
                  "/api/goals/suggestions", "/api/goals/stats"]:
            self.assertIn(p, rules)


class TestGoalsList(GoalBpBase):
    def test_list(self):
        with patch("orbit.core.goal_bp.get_goal_tracker") as gt:
            gt.return_value.get_all.return_value = [{"id": "g1"}]
            r = self.client.get("/api/goals")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["goals"], [{"id": "g1"}])

    def test_list_empty(self):
        with patch("orbit.core.goal_bp.get_goal_tracker") as gt:
            gt.return_value.get_all.return_value = []
            r = self.client.get("/api/goals")
        self.assertEqual(r.get_json()["goals"], [])

    def test_list_exception_500(self):
        with patch("orbit.core.goal_bp.get_goal_tracker", side_effect=RuntimeError("x")):
            r = self.client.get("/api/goals")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "internal error")


class TestGoalDetail(GoalBpBase):
    def test_found(self):
        with patch("orbit.core.goal_bp.get_goal_tracker") as gt:
            gt.return_value.get_goal.return_value = {"id": "g1", "title": "T"}
            r = self.client.get("/api/goals/g1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], "g1")

    def test_not_found_404(self):
        with patch("orbit.core.goal_bp.get_goal_tracker") as gt:
            gt.return_value.get_goal.return_value = None
            r = self.client.get("/api/goals/nope")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"], "goal not found")

    def test_exception_500(self):
        with patch("orbit.core.goal_bp.get_goal_tracker", side_effect=RuntimeError("x")):
            r = self.client.get("/api/goals/g1")
        self.assertEqual(r.status_code, 500)


class TestGoalAdd(GoalBpBase):
    def test_add_defaults(self):
        with patch("orbit.core.goal_bp.get_goal_tracker") as gt:
            gt.return_value.add_goal.return_value = {"id": "g1", "title": "T"}
            r = self.client.post("/api/goals/add", json={"title": "T"})
        self.assertEqual(r.status_code, 200)
        gt.return_value.add_goal.assert_called_once_with(
            title="T", category="personal", description="",
            deadline="", priority="medium")

    def test_add_all_fields(self):
        with patch("orbit.core.goal_bp.get_goal_tracker") as gt:
            gt.return_value.add_goal.return_value = {"id": "g1"}
            r = self.client.post("/api/goals/add", json={
                "title": "T", "category": "tech", "description": "D",
                "deadline": "2026-12-31", "priority": "high"})
        gt.return_value.add_goal.assert_called_once_with(
            title="T", category="tech", description="D",
            deadline="2026-12-31", priority="high")

    def test_add_missing_title_400(self):
        with patch("orbit.core.goal_bp.get_goal_tracker") as gt:
            r = self.client.post("/api/goals/add", json={"description": "x"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("title required", r.get_json()["error"])
        gt.return_value.add_goal.assert_not_called()

    def test_add_no_body_400(self):
        r = self.client.post("/api/goals/add")
        self.assertEqual(r.status_code, 400)

    def test_add_exception_500(self):
        with patch("orbit.core.goal_bp.get_goal_tracker", side_effect=RuntimeError("x")):
            r = self.client.post("/api/goals/add", json={"title": "T"})
        self.assertEqual(r.status_code, 500)


class TestGoalProgress(GoalBpBase):
    def test_put_success(self):
        with patch("orbit.core.goal_bp.get_goal_tracker") as gt:
            gt.return_value.update_progress.return_value = {"id": "g1", "progress": 50}
            r = self.client.put("/api/goals/g1/progress", json={"progress": 50})
        self.assertEqual(r.status_code, 200)
        gt.return_value.update_progress.assert_called_once_with("g1", 50)

    def test_post_success(self):
        with patch("orbit.core.goal_bp.get_goal_tracker") as gt:
            gt.return_value.update_progress.return_value = {"id": "g1"}
            r = self.client.post("/api/goals/g1/progress", json={"progress": 10})
        self.assertEqual(r.status_code, 200)
        gt.return_value.update_progress.assert_called_once_with("g1", 10)

    def test_string_number_coerced(self):
        with patch("orbit.core.goal_bp.get_goal_tracker") as gt:
            gt.return_value.update_progress.return_value = {"id": "g1"}
            r = self.client.post("/api/goals/g1/progress", json={"progress": "75"})
        gt.return_value.update_progress.assert_called_once_with("g1", 75)

    def test_bad_progress_400(self):
        with patch("orbit.core.goal_bp.get_goal_tracker") as gt:
            r = self.client.post("/api/goals/g1/progress", json={"progress": "abc"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("must be a number", r.get_json()["error"])
        gt.return_value.update_progress.assert_not_called()

    def test_none_progress_400(self):
        r = self.client.post("/api/goals/g1/progress", json={"progress": None})
        self.assertEqual(r.status_code, 400)

    def test_default_progress_zero(self):
        with patch("orbit.core.goal_bp.get_goal_tracker") as gt:
            gt.return_value.update_progress.return_value = {"id": "g1"}
            r = self.client.post("/api/goals/g1/progress", json={})
        gt.return_value.update_progress.assert_called_once_with("g1", 0)

    def test_goal_not_found_404(self):
        with patch("orbit.core.goal_bp.get_goal_tracker") as gt:
            gt.return_value.update_progress.return_value = None
            r = self.client.post("/api/goals/nope/progress", json={"progress": 5})
        self.assertEqual(r.status_code, 404)

    def test_exception_500(self):
        with patch("orbit.core.goal_bp.get_goal_tracker", side_effect=RuntimeError("x")):
            r = self.client.post("/api/goals/g1/progress", json={"progress": 5})
        self.assertEqual(r.status_code, 500)


class TestMilestone(GoalBpBase):
    def test_add_success(self):
        with patch("orbit.core.goal_bp.get_goal_tracker") as gt:
            gt.return_value.add_milestone.return_value = {"id": "m1", "title": "M"}
            r = self.client.post("/api/goals/g1/milestone", json={"title": "M"})
        self.assertEqual(r.status_code, 200)
        gt.return_value.add_milestone.assert_called_once_with("g1", "M", "")

    def test_add_with_target(self):
        with patch("orbit.core.goal_bp.get_goal_tracker") as gt:
            gt.return_value.add_milestone.return_value = {"id": "m1"}
            r = self.client.post("/api/goals/g1/milestone",
                                 json={"title": "M", "target": "T"})
        gt.return_value.add_milestone.assert_called_once_with("g1", "M", "T")

    def test_add_missing_title_400(self):
        with patch("orbit.core.goal_bp.get_goal_tracker") as gt:
            r = self.client.post("/api/goals/g1/milestone", json={"target": "x"})
        self.assertEqual(r.status_code, 400)
        gt.return_value.add_milestone.assert_not_called()

    def test_goal_not_found_404(self):
        with patch("orbit.core.goal_bp.get_goal_tracker") as gt:
            gt.return_value.add_milestone.return_value = None
            r = self.client.post("/api/goals/nope/milestone", json={"title": "M"})
        self.assertEqual(r.status_code, 404)

    def test_complete_ok(self):
        with patch("orbit.core.goal_bp.get_goal_tracker") as gt:
            gt.return_value.complete_milestone.return_value = True
            r = self.client.post("/api/goals/g1/milestone/0/complete")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        gt.return_value.complete_milestone.assert_called_once_with("g1", 0)

    def test_complete_not_found_404(self):
        with patch("orbit.core.goal_bp.get_goal_tracker") as gt:
            gt.return_value.complete_milestone.return_value = False
            r = self.client.post("/api/goals/nope/milestone/3/complete")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"], "not found")

    def test_complete_non_int_idx_404(self):
        # <int:idx> converter rejects non-int -> 404
        r = self.client.post("/api/goals/g1/milestone/abc/complete")
        self.assertEqual(r.status_code, 404)

    def test_complete_exception_500(self):
        with patch("orbit.core.goal_bp.get_goal_tracker", side_effect=RuntimeError("x")):
            r = self.client.post("/api/goals/g1/milestone/0/complete")
        self.assertEqual(r.status_code, 500)


class TestSubGoal(GoalBpBase):
    def test_add_success(self):
        with patch("orbit.core.goal_bp.get_goal_tracker") as gt:
            gt.return_value.add_sub_goal.return_value = {"id": "s1", "title": "S"}
            r = self.client.post("/api/goals/g1/subgoal", json={"title": "S"})
        self.assertEqual(r.status_code, 200)
        gt.return_value.add_sub_goal.assert_called_once_with("g1", "S")

    def test_add_missing_title_400(self):
        with patch("orbit.core.goal_bp.get_goal_tracker") as gt:
            r = self.client.post("/api/goals/g1/subgoal", json={})
        self.assertEqual(r.status_code, 400)
        gt.return_value.add_sub_goal.assert_not_called()

    def test_goal_not_found_404(self):
        with patch("orbit.core.goal_bp.get_goal_tracker") as gt:
            gt.return_value.add_sub_goal.return_value = None
            r = self.client.post("/api/goals/nope/subgoal", json={"title": "S"})
        self.assertEqual(r.status_code, 404)

    def test_exception_500(self):
        with patch("orbit.core.goal_bp.get_goal_tracker", side_effect=RuntimeError("x")):
            r = self.client.post("/api/goals/g1/subgoal", json={"title": "S"})
        self.assertEqual(r.status_code, 500)


class TestGoalDelete(GoalBpBase):
    def test_delete_ok(self):
        with patch("orbit.core.goal_bp.get_goal_tracker") as gt:
            gt.return_value.delete_goal.return_value = True
            r = self.client.delete("/api/goals/g1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "deleted")

    def test_delete_not_found_404(self):
        with patch("orbit.core.goal_bp.get_goal_tracker") as gt:
            gt.return_value.delete_goal.return_value = False
            r = self.client.delete("/api/goals/nope")
        self.assertEqual(r.status_code, 404)

    def test_delete_exception_500(self):
        with patch("orbit.core.goal_bp.get_goal_tracker", side_effect=RuntimeError("x")):
            r = self.client.delete("/api/goals/g1")
        self.assertEqual(r.status_code, 500)


class TestSuggestionsStats(GoalBpBase):
    def test_suggestions(self):
        with patch("orbit.core.goal_bp.get_goal_tracker") as gt:
            gt.return_value.get_suggestions.return_value = ["do X"]
            r = self.client.get("/api/goals/suggestions")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["suggestions"], ["do X"])

    def test_suggestions_exception_500(self):
        with patch("orbit.core.goal_bp.get_goal_tracker", side_effect=RuntimeError("x")):
            r = self.client.get("/api/goals/suggestions")
        self.assertEqual(r.status_code, 500)

    def test_stats(self):
        with patch("orbit.core.goal_bp.get_goal_tracker") as gt:
            gt.return_value.get_stats.return_value = {"total": 5, "done": 2}
            r = self.client.get("/api/goals/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)

    def test_stats_exception_500(self):
        with patch("orbit.core.goal_bp.get_goal_tracker", side_effect=RuntimeError("x")):
            r = self.client.get("/api/goals/stats")
        self.assertEqual(r.status_code, 500)


if __name__ == "__main__":
    unittest.main()
