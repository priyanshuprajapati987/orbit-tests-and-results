"""Unit tests for orbit/orbit/core/task_tracker_bp.py."""

import os
import sys
import unittest
from dataclasses import dataclass, field, asdict
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.task_tracker_bp import (
    task_tracker_bp, _coerce_status, _coerce_priority, _VALID_STATUS,
)


def _task(tid="t1", title="Task"):
    t = MagicMock()
    t.to_dict.return_value = {"id": tid, "title": title, "status": "backlog"}
    return t


@dataclass
class FakeComment:
    id: str = "c1"
    text: str = "hello"
    author: str = "user"
    created_at: str = "2026-01-01T00:00:00"
    extra: list = field(default_factory=list)


class TaskTrackerBpBase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(task_tracker_bp)
        self.client = self.app.test_client()
        self.tr = MagicMock()

    def _patch(self):
        return patch("orbit.core.task_tracker_bp.get_task_tracker",
                     return_value=self.tr)

    def test_blueprint_name(self):
        self.assertEqual(task_tracker_bp.name, "task_tracker_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/tasks", "/api/tasks/<task_id>",
                  "/api/tasks/<task_id>/move", "/api/tasks/board",
                  "/api/tasks/backlog", "/api/tasks/stats",
                  "/api/tasks/<task_id>/comments",
                  "/api/tasks/<task_id>/subtasks",
                  "/api/tasks/<task_id>/subtasks/<subtask_id>/toggle"]:
            self.assertIn(p, rules)


class TestCoercionHelpers(TaskTrackerBpBase):
    def test_coerce_status_valid(self):
        self.assertEqual(_coerce_status("done"), "done")

    def test_coerce_status_invalid_default(self):
        self.assertEqual(_coerce_status("bogus"), "backlog")

    def test_coerce_status_none_default(self):
        self.assertEqual(_coerce_status(None), "backlog")

    def test_coerce_priority_int(self):
        self.assertEqual(_coerce_priority(3), 3)

    def test_coerce_priority_string(self):
        self.assertEqual(_coerce_priority("4"), 4)

    def test_coerce_priority_clamp_high(self):
        self.assertEqual(_coerce_priority(99), 4)

    def test_coerce_priority_clamp_low(self):
        self.assertEqual(_coerce_priority(-5), 0)

    def test_coerce_priority_bad_default(self):
        self.assertEqual(_coerce_priority("abc"), 2)
        self.assertEqual(_coerce_priority(None), 2)

    def test_coerce_priority_custom_default(self):
        self.assertEqual(_coerce_priority("abc", 0), 0)


class TestListTasks(TaskTrackerBpBase):
    def test_list_default(self):
        with self._patch():
            self.tr.list_tasks.return_value = [_task()]
            r = self.client.get("/api/tasks")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["tasks"][0]["id"], "t1")
        self.tr.list_tasks.assert_called_once_with(
            status=None, priority=None, assignee=None,
            goal_id=None, tag=None, search=None)

    def test_list_filters(self):
        with self._patch():
            self.tr.list_tasks.return_value = []
            r = self.client.get(
                "/api/tasks?status=todo&priority=2&assignee=me"
                "&goal_id=g1&tag=py&search=hello")
        self.tr.list_tasks.assert_called_once_with(
            status="todo", priority=2, assignee="me",
            goal_id="g1", tag="py", search="hello")

    def test_list_bad_priority_type(self):
        # Flask type=int -> None on parse failure
        with self._patch():
            self.tr.list_tasks.return_value = []
            r = self.client.get("/api/tasks?priority=abc")
        kwargs = self.tr.list_tasks.call_args.kwargs
        self.assertIsNone(kwargs["priority"])


class TestCreateTask(TaskTrackerBpBase):
    def test_create_defaults(self):
        with self._patch():
            self.tr.create.return_value = _task()
            r = self.client.post("/api/tasks", json={"title": "  Hello  "})
        self.assertEqual(r.status_code, 201)
        self.tr.create.assert_called_once_with(
            title="Hello", description="", status="backlog", priority=2,
            assignee="", goal_id="", tags=[], due_date="",
            estimated_minutes=0, dependencies=[])

    def test_create_all_fields(self):
        with self._patch():
            self.tr.create.return_value = _task()
            r = self.client.post("/api/tasks", json={
                "title": "T", "description": "D", "status": "in_progress",
                "priority": 4, "assignee": "me", "goal_id": "g1",
                "tags": ["a"], "due_date": "2026-12-31",
                "estimated_minutes": 90, "dependencies": ["t0"]})
        self.assertEqual(r.status_code, 201)
        self.tr.create.assert_called_once_with(
            title="T", description="D", status="in_progress", priority=4,
            assignee="me", goal_id="g1", tags=["a"], due_date="2026-12-31",
            estimated_minutes=90, dependencies=["t0"])

    def test_create_invalid_status_coerced(self):
        with self._patch():
            self.tr.create.return_value = _task()
            r = self.client.post("/api/tasks",
                                 json={"title": "T", "status": "bogus"})
        kwargs = self.tr.create.call_args.kwargs
        self.assertEqual(kwargs["status"], "backlog")

    def test_create_missing_title_400(self):
        with self._patch():
            r = self.client.post("/api/tasks", json={"description": "x"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("title required", r.get_json()["error"])
        self.tr.create.assert_not_called()

    def test_create_blank_title_400(self):
        r = self.client.post("/api/tasks", json={"title": "   "})
        self.assertEqual(r.status_code, 400)

    def test_create_non_string_title_400(self):
        r = self.client.post("/api/tasks", json={"title": 123})
        self.assertEqual(r.status_code, 400)

    def test_create_no_body_400(self):
        r = self.client.post("/api/tasks")
        self.assertEqual(r.status_code, 400)

    def test_create_non_string_fields_coerced(self):
        with self._patch():
            self.tr.create.return_value = _task()
            r = self.client.post("/api/tasks", json={
                "title": "T", "description": 42, "assignee": None,
                "goal_id": ["x"], "tags": "notalist", "due_date": 5,
                "dependencies": "nope"})
        self.assertEqual(r.status_code, 201)
        kwargs = self.tr.create.call_args.kwargs
        self.assertEqual(kwargs["description"], "")
        self.assertEqual(kwargs["assignee"], "")
        self.assertEqual(kwargs["goal_id"], "")
        self.assertEqual(kwargs["tags"], [])
        self.assertEqual(kwargs["due_date"], "")
        self.assertEqual(kwargs["dependencies"], [])

    def test_create_priority_clamped_and_estimated(self):
        with self._patch():
            self.tr.create.return_value = _task()
            r = self.client.post("/api/tasks",
                                 json={"title": "T", "priority": 99,
                                       "estimated_minutes": "60"})
        kwargs = self.tr.create.call_args.kwargs
        self.assertEqual(kwargs["priority"], 4)
        self.assertEqual(kwargs["estimated_minutes"], 60)


class TestGetTask(TaskTrackerBpBase):
    def test_found(self):
        with self._patch():
            self.tr.get.return_value = _task()
            r = self.client.get("/api/tasks/t1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["task"]["id"], "t1")

    def test_not_found_404(self):
        with self._patch():
            self.tr.get.return_value = None
            r = self.client.get("/api/tasks/nope")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"], "not found")


class TestUpdateTask(TaskTrackerBpBase):
    def test_update_fields(self):
        with self._patch():
            self.tr.update.return_value = _task()
            r = self.client.put("/api/tasks/t1",
                                json={"title": "New", "priority": 3})
        self.assertEqual(r.status_code, 200)
        self.tr.update.assert_called_once_with("t1", title="New", priority=3)

    def test_update_status_valid(self):
        with self._patch():
            self.tr.update.return_value = _task()
            r = self.client.put("/api/tasks/t1", json={"status": "done"})
        self.tr.update.assert_called_once_with("t1", status="done")

    def test_update_status_invalid_400(self):
        with self._patch():
            r = self.client.put("/api/tasks/t1", json={"status": "bogus"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("status must be one of", r.get_json()["error"])
        self.tr.update.assert_not_called()

    def test_update_priority_coerced(self):
        with self._patch():
            self.tr.update.return_value = _task()
            r = self.client.put("/api/tasks/t1", json={"priority": "3"})
        self.tr.update.assert_called_once_with("t1", priority=3)

    def test_update_non_string_title_400(self):
        with self._patch():
            r = self.client.put("/api/tasks/t1", json={"title": 42})
        self.assertEqual(r.status_code, 400)
        self.assertIn("title must be a string", r.get_json()["error"])

    def test_update_pops_id_and_created_at(self):
        with self._patch():
            self.tr.update.return_value = _task()
            r = self.client.put("/api/tasks/t1",
                                json={"id": "hax", "created_at": "x",
                                      "title": "T"})
        self.tr.update.assert_called_once_with("t1", title="T")

    def test_update_not_found_404(self):
        with self._patch():
            self.tr.update.return_value = None
            r = self.client.put("/api/tasks/nope", json={"title": "T"})
        self.assertEqual(r.status_code, 404)

    def test_update_no_body(self):
        with self._patch():
            self.tr.update.return_value = _task()
            r = self.client.put("/api/tasks/t1")
        self.assertEqual(r.status_code, 200)
        self.tr.update.assert_called_once_with("t1")


class TestDeleteTask(TaskTrackerBpBase):
    def test_delete_ok(self):
        with self._patch():
            self.tr.delete.return_value = True
            r = self.client.delete("/api/tasks/t1")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])

    def test_delete_not_found_404(self):
        with self._patch():
            self.tr.delete.return_value = False
            r = self.client.delete("/api/tasks/nope")
        self.assertEqual(r.status_code, 404)


class TestMoveTask(TaskTrackerBpBase):
    def test_move_ok(self):
        with self._patch():
            self.tr.move.return_value = _task()
            r = self.client.post("/api/tasks/t1/move", json={"status": "done"})
        self.assertEqual(r.status_code, 200)
        self.tr.move.assert_called_once_with("t1", "done")

    def test_move_invalid_status_400(self):
        with self._patch():
            r = self.client.post("/api/tasks/t1/move", json={"status": "zzz"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("status must be one of", r.get_json()["error"])
        self.tr.move.assert_not_called()

    def test_move_missing_status_400(self):
        with self._patch():
            r = self.client.post("/api/tasks/t1/move", json={})
        self.assertEqual(r.status_code, 400)

    def test_move_not_found_404(self):
        with self._patch():
            self.tr.move.return_value = None
            r = self.client.post("/api/tasks/nope/move",
                                 json={"status": "todo"})
        self.assertEqual(r.status_code, 404)

    def test_move_all_valid_statuses(self):
        with self._patch():
            self.tr.move.return_value = _task()
            for s in _VALID_STATUS:
                r = self.client.post("/api/tasks/t1/move", json={"status": s})
                self.assertEqual(r.status_code, 200, s)


class TestBoardBacklogStats(TaskTrackerBpBase):
    def test_board(self):
        with self._patch():
            self.tr.get_board.return_value = {"todo": ["t1"]}
            r = self.client.get("/api/tasks/board")
        self.assertEqual(r.get_json(), {"board": {"todo": ["t1"]}})

    def test_backlog(self):
        with self._patch():
            # get_backlog() returns list of dicts (t.to_dict()), not tasks
            self.tr.get_backlog.return_value = [
                {"id": "t1", "title": "Task", "status": "backlog"}]
            r = self.client.get("/api/tasks/backlog")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.get_json()["tasks"]), 1)

    def test_stats(self):
        with self._patch():
            self.tr.get_stats.return_value = {"total": 5, "done": 2}
            r = self.client.get("/api/tasks/stats")
        self.assertEqual(r.get_json(), {"total": 5, "done": 2})


class TestComments(TaskTrackerBpBase):
    def test_add_comment(self):
        with self._patch():
            self.tr.add_comment.return_value = FakeComment(author="bob")
            r = self.client.post("/api/tasks/t1/comments",
                                 json={"text": "  hello  ", "author": "bob"})
        self.assertEqual(r.status_code, 201)
        body = r.get_json()["comment"]
        self.assertEqual(body["id"], "c1")
        self.assertEqual(body["text"], "hello")
        self.assertEqual(body["author"], "bob")
        self.tr.add_comment.assert_called_once_with("t1", "hello", "bob")

    def test_comment_default_author(self):
        with self._patch():
            self.tr.add_comment.return_value = FakeComment()
            r = self.client.post("/api/tasks/t1/comments", json={"text": "hi"})
        self.tr.add_comment.assert_called_once_with("t1", "hi", "user")

    def test_missing_text_400(self):
        with self._patch():
            r = self.client.post("/api/tasks/t1/comments", json={"author": "x"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("text required", r.get_json()["error"])
        self.tr.add_comment.assert_not_called()

    def test_blank_text_400(self):
        r = self.client.post("/api/tasks/t1/comments", json={"text": "   "})
        self.assertEqual(r.status_code, 400)

    def test_no_body_400(self):
        r = self.client.post("/api/tasks/t1/comments")
        self.assertEqual(r.status_code, 400)

    def test_task_not_found_404(self):
        with self._patch():
            self.tr.add_comment.return_value = None
            r = self.client.post("/api/tasks/nope/comments",
                                 json={"text": "hi"})
        self.assertEqual(r.status_code, 404)


class TestSubtasks(TaskTrackerBpBase):
    def test_add_subtask(self):
        with self._patch():
            self.tr.add_subtask.return_value = {"id": "s1", "title": "Sub",
                                                "done": False}
            r = self.client.post("/api/tasks/t1/subtasks",
                                 json={"title": "  Sub  "})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()["subtask"]["id"], "s1")
        self.tr.add_subtask.assert_called_once_with("t1", "Sub")

    def test_missing_title_400(self):
        with self._patch():
            r = self.client.post("/api/tasks/t1/subtasks", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("title required", r.get_json()["error"])
        self.tr.add_subtask.assert_not_called()

    def test_no_body_400(self):
        r = self.client.post("/api/tasks/t1/subtasks")
        self.assertEqual(r.status_code, 400)

    def test_task_not_found_404(self):
        with self._patch():
            self.tr.add_subtask.return_value = None
            r = self.client.post("/api/tasks/nope/subtasks",
                                 json={"title": "x"})
        self.assertEqual(r.status_code, 404)

    def test_toggle_ok(self):
        with self._patch():
            self.tr.toggle_subtask.return_value = True
            r = self.client.post("/api/tasks/t1/subtasks/s1/toggle")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        self.tr.toggle_subtask.assert_called_once_with("t1", "s1")

    def test_toggle_not_found_404(self):
        with self._patch():
            self.tr.toggle_subtask.return_value = False
            r = self.client.post("/api/tasks/nope/subtasks/x/toggle")
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
