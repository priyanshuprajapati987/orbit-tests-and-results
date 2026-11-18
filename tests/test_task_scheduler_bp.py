"""Unit tests for orbit/orbit/core/task_scheduler_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.task_scheduler_bp import task_scheduler_bp, _request_user_id


def _task(tid="t1", name="Task"):
    t = MagicMock()
    t.task_id = tid
    t.name = name
    t.description = "desc"
    t.interval_seconds = 60
    t.enabled = True
    t.priority = 3
    t.run_count = 7
    t.fail_count = 1
    t.next_run = "2026-01-01T00:00:00"
    return t


def _execution(success=True, result="ok", start=1.0, end=1.25):
    e = MagicMock()
    e.success = success
    e.result = result
    e.start_time = start
    e.end_time = end
    return e


class SchedBpBase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(task_scheduler_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(task_scheduler_bp.name, "task_scheduler_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/scheduler/tasks", "/api/scheduler/add",
                  "/api/scheduler/remove/<task_id>",
                  "/api/scheduler/enable/<task_id>",
                  "/api/scheduler/run/<task_id>",
                  "/api/scheduler/start", "/api/scheduler/stop",
                  "/api/scheduler/stats", "/api/scheduler/executions"]:
            self.assertIn(p, rules)


class TestUserId(SchedBpBase):
    def test_fallback_local_without_auth(self):
        # no auth context in bare test app -> "local"
        self.assertEqual(_request_user_id(), "local")

    def test_uses_auth_user_when_available(self):
        with patch("orbit.core.auth.guards.current_user") as cu:
            cu.return_value = {"id": "user-42"}
            self.assertEqual(_request_user_id(), "user-42")

    def test_empty_id_becomes_local(self):
        with patch("orbit.core.auth.guards.current_user") as cu:
            cu.return_value = {"id": ""}
            self.assertEqual(_request_user_id(), "local")


class TestTasks(SchedBpBase):
    def test_tasks_serialization(self):
        with patch("orbit.core.task_scheduler_bp.get_scheduler") as gs:
            gs.return_value.list_tasks.return_value = [_task()]
            r = self.client.get("/api/scheduler/tasks")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual(len(data), 1)
        t = data[0]
        self.assertEqual(t["task_id"], "t1")
        self.assertEqual(t["name"], "Task")
        self.assertEqual(t["interval_seconds"], 60)
        self.assertTrue(t["enabled"])
        self.assertEqual(t["priority"], 3)
        self.assertEqual(t["run_count"], 7)
        self.assertEqual(t["fail_count"], 1)
        gs.return_value.list_tasks.assert_called_once_with(user_id="local")

    def test_tasks_empty(self):
        with patch("orbit.core.task_scheduler_bp.get_scheduler") as gs:
            gs.return_value.list_tasks.return_value = []
            r = self.client.get("/api/scheduler/tasks")
        self.assertEqual(r.get_json(), [])

    def test_tasks_exception_500_json(self):
        with patch("orbit.core.task_scheduler_bp.get_scheduler") as gs:
            gs.return_value.list_tasks.side_effect = RuntimeError("boom")
            r = self.client.get("/api/scheduler/tasks")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "boom")


class TestAdd(SchedBpBase):
    def test_add_defaults(self):
        with patch("orbit.core.task_scheduler_bp.get_scheduler") as gs:
            gs.return_value.add_task.return_value = _task()
            r = self.client.post("/api/scheduler/add", json={"name": "N"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["task_id"], "t1")
        self.assertEqual(body["status"], "added")
        gs.return_value.add_task.assert_called_once_with(
            name="N", description="", interval_seconds=0, delay_seconds=0,
            priority=0, payload={}, user_id="local")

    def test_add_all_fields(self):
        with patch("orbit.core.task_scheduler_bp.get_scheduler") as gs:
            gs.return_value.add_task.return_value = _task()
            r = self.client.post("/api/scheduler/add", json={
                "name": "N", "description": "D", "interval_seconds": 30,
                "delay_seconds": 5, "priority": 9, "payload": {"a": 1}})
        gs.return_value.add_task.assert_called_once_with(
            name="N", description="D", interval_seconds=30, delay_seconds=5,
            priority=9, payload={"a": 1}, user_id="local")

    def test_add_missing_name_400(self):
        with patch("orbit.core.task_scheduler_bp.get_scheduler") as gs:
            r = self.client.post("/api/scheduler/add", json={"description": "x"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("name required", r.get_json()["error"])
        gs.return_value.add_task.assert_not_called()

    def test_add_no_body_400(self):
        r = self.client.post("/api/scheduler/add")
        self.assertEqual(r.status_code, 400)

    def test_add_exception_500(self):
        with patch("orbit.core.task_scheduler_bp.get_scheduler") as gs:
            gs.return_value.add_task.side_effect = RuntimeError("x")
            r = self.client.post("/api/scheduler/add", json={"name": "N"})
        self.assertEqual(r.status_code, 500)


class TestRemove(SchedBpBase):
    def test_remove_ok(self):
        with patch("orbit.core.task_scheduler_bp.get_scheduler") as gs:
            gs.return_value.remove_task.return_value = True
            r = self.client.post("/api/scheduler/remove/t1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "removed")
        gs.return_value.remove_task.assert_called_once_with("t1", user_id="local")

    def test_remove_not_found(self):
        with patch("orbit.core.task_scheduler_bp.get_scheduler") as gs:
            gs.return_value.remove_task.return_value = False
            r = self.client.post("/api/scheduler/remove/nope")
        self.assertEqual(r.get_json()["status"], "not_found")


class TestEnable(SchedBpBase):
    def test_enable_default(self):
        with patch("orbit.core.task_scheduler_bp.get_scheduler") as gs:
            gs.return_value.enable_task.return_value = True
            r = self.client.post("/api/scheduler/enable/t1", json={})
        self.assertEqual(r.get_json()["status"], "enabled")
        gs.return_value.enable_task.assert_called_once_with(
            "t1", True, user_id="local")

    def test_disable(self):
        with patch("orbit.core.task_scheduler_bp.get_scheduler") as gs:
            gs.return_value.enable_task.return_value = True
            r = self.client.post("/api/scheduler/enable/t1",
                                 json={"enabled": False})
        gs.return_value.enable_task.assert_called_once_with(
            "t1", False, user_id="local")

    def test_enable_no_body(self):
        with patch("orbit.core.task_scheduler_bp.get_scheduler") as gs:
            gs.return_value.enable_task.return_value = True
            r = self.client.post("/api/scheduler/enable/t1")
        self.assertEqual(r.status_code, 200)

    def test_enable_not_found(self):
        with patch("orbit.core.task_scheduler_bp.get_scheduler") as gs:
            gs.return_value.enable_task.return_value = False
            r = self.client.post("/api/scheduler/enable/nope", json={})
        self.assertEqual(r.get_json()["status"], "not_found")


class TestRun(SchedBpBase):
    def test_run_success(self):
        with patch("orbit.core.task_scheduler_bp.get_scheduler") as gs:
            gs.return_value.get_task.return_value = _task()
            gs.return_value.run_task_now.return_value = _execution(
                success=True, result="done", start=10.0, end=10.5)
            r = self.client.post("/api/scheduler/run/t1", json={})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["success"])
        self.assertEqual(body["result"], "done")
        self.assertEqual(body["duration_ms"], 500.0)
        gs.return_value.run_task_now.assert_called_once_with(
            "t1", idempotency_key="")

    def test_run_with_idempotency_key(self):
        with patch("orbit.core.task_scheduler_bp.get_scheduler") as gs:
            gs.return_value.get_task.return_value = _task()
            gs.return_value.run_task_now.return_value = _execution()
            r = self.client.post("/api/scheduler/run/t1",
                                 json={"idempotency_key": "k-1"})
        gs.return_value.run_task_now.assert_called_once_with(
            "t1", idempotency_key="k-1")

    def test_run_task_not_found_404(self):
        with patch("orbit.core.task_scheduler_bp.get_scheduler") as gs:
            gs.return_value.get_task.return_value = None
            r = self.client.post("/api/scheduler/run/nope", json={})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"], "task not found")
        gs.return_value.run_task_now.assert_not_called()

    def test_run_execution_none_404(self):
        with patch("orbit.core.task_scheduler_bp.get_scheduler") as gs:
            gs.return_value.get_task.return_value = _task()
            gs.return_value.run_task_now.return_value = None
            r = self.client.post("/api/scheduler/run/t1", json={})
        self.assertEqual(r.status_code, 404)

    def test_run_no_body(self):
        with patch("orbit.core.task_scheduler_bp.get_scheduler") as gs:
            gs.return_value.get_task.return_value = _task()
            gs.return_value.run_task_now.return_value = _execution()
            r = self.client.post("/api/scheduler/run/t1")
        self.assertEqual(r.status_code, 200)


class TestStartStop(SchedBpBase):
    def test_start_default_interval(self):
        with patch("orbit.core.task_scheduler_bp.get_scheduler") as gs:
            r = self.client.post("/api/scheduler/start", json={})
        self.assertEqual(r.get_json()["status"], "started")
        gs.return_value.start.assert_called_once_with(10)

    def test_start_custom_interval(self):
        with patch("orbit.core.task_scheduler_bp.get_scheduler") as gs:
            r = self.client.post("/api/scheduler/start", json={"interval": 30})
        gs.return_value.start.assert_called_once_with(30)

    def test_start_no_body(self):
        with patch("orbit.core.task_scheduler_bp.get_scheduler") as gs:
            r = self.client.post("/api/scheduler/start")
        self.assertEqual(r.status_code, 200)

    def test_stop(self):
        with patch("orbit.core.task_scheduler_bp.get_scheduler") as gs:
            r = self.client.post("/api/scheduler/stop")
        self.assertEqual(r.get_json()["status"], "stopped")
        gs.return_value.stop.assert_called_once()


class TestStatsExecutions(SchedBpBase):
    def test_stats(self):
        with patch("orbit.core.task_scheduler_bp.get_scheduler") as gs:
            gs.return_value.get_stats.return_value = {"tasks": 4}
            r = self.client.get("/api/scheduler/stats")
        self.assertEqual(r.get_json(), {"tasks": 4})

    def test_executions_default_limit(self):
        with patch("orbit.core.task_scheduler_bp.get_scheduler") as gs:
            gs.return_value.get_executions.return_value = []
            r = self.client.get("/api/scheduler/executions")
        gs.return_value.get_executions.assert_called_once_with(50)

    def test_executions_custom_limit(self):
        with patch("orbit.core.task_scheduler_bp.get_scheduler") as gs:
            gs.return_value.get_executions.return_value = []
            r = self.client.get("/api/scheduler/executions?limit=5")
        gs.return_value.get_executions.assert_called_once_with(5)

    def test_executions_bad_limit_fallback(self):
        with patch("orbit.core.task_scheduler_bp.get_scheduler") as gs:
            gs.return_value.get_executions.return_value = []
            r = self.client.get("/api/scheduler/executions?limit=abc")
        gs.return_value.get_executions.assert_called_once_with(50)


if __name__ == "__main__":
    unittest.main()
