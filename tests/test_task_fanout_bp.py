"""Unit tests for orbit/orbit/core/task_fanout_bp.py."""

import os
import sys
import unittest
from dataclasses import dataclass
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.task_fanout_bp import task_fanout_bp


@dataclass
class FakeResult:
    task_id: str = "t1"
    status: str = "done"


class TestTaskFanoutBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(task_fanout_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(task_fanout_bp.name, "task_fanout")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/fanout/execute", "/api/fanout/status/<task_id>", "/api/fanout/active", "/api/fanout/stats"]:
            self.assertIn(p, rules)

    def test_execute_missing_goal_400(self):
        r = self.client.post("/api/fanout/execute", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_execute_success(self):
        with patch("orbit.core.task_fanout_bp.get_fanout") as gf:
            fanout = gf.return_value
            fanout.execute.return_value = FakeResult("t1", "done")
            r = self.client.post("/api/fanout/execute", json={"goal": "g", "subtasks": [{"description": "a"}, {"description": "b"}]})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["task_id"], "t1")
        self.assertEqual(body["status"], "done")
        call_args = fanout.execute.call_args
        self.assertEqual(call_args[0][0], "g")
        tasks = call_args[0][1]
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0]["description"], "a")
        self.assertEqual(tasks[1]["description"], "b")

    def test_execute_unnamed_subtask(self):
        with patch("orbit.core.task_fanout_bp.get_fanout") as gf:
            fanout = gf.return_value
            fanout.execute.return_value = FakeResult("t2", "done")
            r = self.client.post("/api/fanout/execute", json={"goal": "g", "subtasks": [{}]})
        tasks = fanout.execute.call_args[0][1]
        self.assertEqual(tasks[0]["description"], "unnamed")

    def test_execute_no_body(self):
        r = self.client.post("/api/fanout/execute")
        self.assertEqual(r.status_code, 400)

    def test_status_found(self):
        with patch("orbit.core.task_fanout_bp.get_fanout") as gf:
            fanout = gf.return_value
            fanout.get_status.return_value = {"status": "running"}
            r = self.client.get("/api/fanout/status/t1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "running")
        fanout.get_status.assert_called_once_with("t1")

    def test_status_not_found_404(self):
        with patch("orbit.core.task_fanout_bp.get_fanout") as gf:
            fanout = gf.return_value
            fanout.get_status.return_value = None
            r = self.client.get("/api/fanout/status/t1")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_active(self):
        with patch("orbit.core.task_fanout_bp.get_fanout") as gf:
            fanout = gf.return_value
            fanout.get_active_count.return_value = 3
            r = self.client.get("/api/fanout/active")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["active_count"], 3)

    def test_stats(self):
        with patch("orbit.core.task_fanout_bp.get_fanout") as gf:
            fanout = gf.return_value
            fanout.max_workers = 4
            fanout.get_active_count.return_value = 2
            r = self.client.get("/api/fanout/stats")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["max_workers"], 4)
        self.assertEqual(body["active_count"], 2)


if __name__ == "__main__":
    unittest.main()
