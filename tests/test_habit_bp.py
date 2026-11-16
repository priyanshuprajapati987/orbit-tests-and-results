"""Unit tests for orbit/orbit/core/habit_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.habit_bp import habit_bp


class TestHabitBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(habit_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(habit_bp.name, "habit_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/habits", "/api/habits/<habit_id>", "/api/habits/add",
                  "/api/habits/complete/<habit_id>", "/api/habits/uncomplete/<habit_id>",
                  "/api/habits/delete/<habit_id>", "/api/habits/streaks",
                  "/api/habits/report", "/api/habits/reset-daily"]:
            self.assertIn(p, rules)

    def test_list_habits(self):
        with patch("orbit.core.habit_bp.get_habit_tracker") as gh:
            gh.return_value.list_habits.return_value = [{"id": "h1"}]
            r = self.client.get("/api/habits?category=health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["habits"], [{"id": "h1"}])
        gh.return_value.list_habits.assert_called_once_with(category="health")

    def test_list_habits_default(self):
        with patch("orbit.core.habit_bp.get_habit_tracker") as gh:
            gh.return_value.list_habits.return_value = []
            r = self.client.get("/api/habits")
        gh.return_value.list_habits.assert_called_once_with(category=None)

    def test_list_habits_error(self):
        with patch("orbit.core.habit_bp.get_habit_tracker") as gh:
            gh.return_value.list_habits.side_effect = RuntimeError("boom")
            r = self.client.get("/api/habits")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_habit_detail_found(self):
        with patch("orbit.core.habit_bp.get_habit_tracker") as gh:
            gh.return_value.get_habit.return_value = {"id": "h1"}
            r = self.client.get("/api/habits/h1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], "h1")
        gh.return_value.get_habit.assert_called_once_with("h1")

    def test_habit_detail_not_found_404(self):
        with patch("orbit.core.habit_bp.get_habit_tracker") as gh:
            gh.return_value.get_habit.return_value = None
            r = self.client.get("/api/habits/h1")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_habit_detail_error(self):
        with patch("orbit.core.habit_bp.get_habit_tracker") as gh:
            gh.return_value.get_habit.side_effect = RuntimeError("boom")
            r = self.client.get("/api/habits/h1")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_habit_add_missing_name_400(self):
        r = self.client.post("/api/habits/add", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_habit_add_success(self):
        with patch("orbit.core.habit_bp.get_habit_tracker") as gh:
            gh.return_value.add_habit.return_value = {"id": "h1"}
            r = self.client.post("/api/habits/add", json={"name": "run", "category": "health", "frequency": "daily"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], "h1")
        gh.return_value.add_habit.assert_called_once_with(name="run", category="health", frequency="daily")

    def test_habit_add_defaults(self):
        with patch("orbit.core.habit_bp.get_habit_tracker") as gh:
            gh.return_value.add_habit.return_value = {"id": "h2"}
            r = self.client.post("/api/habits/add", json={"name": "run"})
        gh.return_value.add_habit.assert_called_once_with(name="run", category="general", frequency="daily")

    def test_habit_add_no_body(self):
        r = self.client.post("/api/habits/add")
        self.assertEqual(r.status_code, 400)

    def test_habit_add_error(self):
        with patch("orbit.core.habit_bp.get_habit_tracker") as gh:
            gh.return_value.add_habit.side_effect = RuntimeError("boom")
            r = self.client.post("/api/habits/add", json={"name": "run"})
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_habit_complete_success(self):
        with patch("orbit.core.habit_bp.get_habit_tracker") as gh:
            gh.return_value.complete_habit.return_value = {"id": "h1", "done": True}
            r = self.client.post("/api/habits/complete/h1")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["done"])
        gh.return_value.complete_habit.assert_called_once_with("h1")

    def test_habit_complete_not_found_404(self):
        with patch("orbit.core.habit_bp.get_habit_tracker") as gh:
            gh.return_value.complete_habit.return_value = None
            r = self.client.post("/api/habits/complete/h1")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_habit_complete_error(self):
        with patch("orbit.core.habit_bp.get_habit_tracker") as gh:
            gh.return_value.complete_habit.side_effect = RuntimeError("boom")
            r = self.client.post("/api/habits/complete/h1")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_habit_uncomplete_success(self):
        with patch("orbit.core.habit_bp.get_habit_tracker") as gh:
            gh.return_value.uncomplete_habit.return_value = {"id": "h1", "done": False}
            r = self.client.post("/api/habits/uncomplete/h1")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()["done"])
        gh.return_value.uncomplete_habit.assert_called_once_with("h1")

    def test_habit_uncomplete_not_found_404(self):
        with patch("orbit.core.habit_bp.get_habit_tracker") as gh:
            gh.return_value.uncomplete_habit.return_value = None
            r = self.client.post("/api/habits/uncomplete/h1")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_habit_uncomplete_error(self):
        with patch("orbit.core.habit_bp.get_habit_tracker") as gh:
            gh.return_value.uncomplete_habit.side_effect = RuntimeError("boom")
            r = self.client.post("/api/habits/uncomplete/h1")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_habit_delete_success(self):
        with patch("orbit.core.habit_bp.get_habit_tracker") as gh:
            gh.return_value.delete_habit.return_value = True
            r = self.client.post("/api/habits/delete/h1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "deleted")
        gh.return_value.delete_habit.assert_called_once_with("h1")

    def test_habit_delete_not_found_404(self):
        with patch("orbit.core.habit_bp.get_habit_tracker") as gh:
            gh.return_value.delete_habit.return_value = False
            r = self.client.post("/api/habits/delete/h1")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_habit_delete_error(self):
        with patch("orbit.core.habit_bp.get_habit_tracker") as gh:
            gh.return_value.delete_habit.side_effect = RuntimeError("boom")
            r = self.client.post("/api/habits/delete/h1")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_habit_streaks(self):
        with patch("orbit.core.habit_bp.get_habit_tracker") as gh:
            gh.return_value.get_streaks.return_value = {"h1": 3}
            r = self.client.get("/api/habits/streaks")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["streaks"], {"h1": 3})

    def test_habit_streaks_error(self):
        with patch("orbit.core.habit_bp.get_habit_tracker") as gh:
            gh.return_value.get_streaks.side_effect = RuntimeError("boom")
            r = self.client.get("/api/habits/streaks")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_habit_report(self):
        with patch("orbit.core.habit_bp.get_habit_tracker") as gh:
            gh.return_value.get_report.return_value = {"total": 5}
            r = self.client.get("/api/habits/report")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)

    def test_habit_report_error(self):
        with patch("orbit.core.habit_bp.get_habit_tracker") as gh:
            gh.return_value.get_report.side_effect = RuntimeError("boom")
            r = self.client.get("/api/habits/report")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_habit_reset_daily(self):
        with patch("orbit.core.habit_bp.get_habit_tracker") as gh:
            r = self.client.post("/api/habits/reset-daily")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "reset")
        gh.return_value.reset_daily.assert_called_once()

    def test_habit_reset_daily_error(self):
        with patch("orbit.core.habit_bp.get_habit_tracker") as gh:
            gh.return_value.reset_daily.side_effect = RuntimeError("boom")
            r = self.client.post("/api/habits/reset-daily")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())


if __name__ == "__main__":
    unittest.main()
