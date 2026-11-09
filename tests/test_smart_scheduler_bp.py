"""Unit tests for orbit/orbit/core/smart_scheduler_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.smart_scheduler_bp import smart_scheduler_bp


class TestSmartSchedulerBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(smart_scheduler_bp)
        self.client = self.app.test_client()
        self.fake_ss = MagicMock()
        sys.modules["orbit.orbit.core.smart_scheduler"] = self.fake_ss

    def tearDown(self):
        sys.modules.pop("orbit.orbit.core.smart_scheduler", None)

    def test_blueprint_name(self):
        self.assertEqual(smart_scheduler_bp.name, "smart_scheduler")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/scheduler/cron", "/api/scheduler/interval", "/api/scheduler/natural",
                  "/api/scheduler/check", "/api/scheduler/cancel", "/api/scheduler/tasks",
                  "/api/scheduler/stats"]:
            self.assertIn(p, rules)

    def test_add_cron_missing_400(self):
        r = self.client.post("/api/scheduler/cron", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_add_cron_success(self):
        task = MagicMock()
        task.task_id = "t1"
        task.name = "cron1"
        task.next_run = "2026-01-01"
        self.fake_ss.get_smart_scheduler.return_value.add_cron.return_value = task
        r = self.client.post("/api/scheduler/cron", json={"name": "cron1", "cron": "0 * * * *", "payload": {"x": 1}})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["task_id"], "t1")
        self.fake_ss.get_smart_scheduler.return_value.add_cron.assert_called_once_with("cron1", "0 * * * *", {"x": 1})

    def test_add_cron_value_error_400(self):
        self.fake_ss.get_smart_scheduler.return_value.add_cron.side_effect = ValueError("bad cron")
        r = self.client.post("/api/scheduler/cron", json={"name": "cron1", "cron": "bad"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_add_cron_no_body(self):
        r = self.client.post("/api/scheduler/cron")
        self.assertEqual(r.status_code, 400)

    def test_add_interval_missing_400(self):
        r = self.client.post("/api/scheduler/interval", json={"name": "i1"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_add_interval_zero_seconds_400(self):
        r = self.client.post("/api/scheduler/interval", json={"name": "i1", "seconds": 0})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_add_interval_success(self):
        task = MagicMock()
        task.task_id = "t2"
        task.name = "int1"
        task.next_run = "2026-01-01"
        self.fake_ss.get_smart_scheduler.return_value.add_interval.return_value = task
        r = self.client.post("/api/scheduler/interval", json={"name": "int1", "seconds": 60, "payload": {"y": 2}})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["task_id"], "t2")
        self.fake_ss.get_smart_scheduler.return_value.add_interval.assert_called_once_with("int1", 60, {"y": 2})

    def test_add_interval_no_body(self):
        r = self.client.post("/api/scheduler/interval")
        self.assertEqual(r.status_code, 400)

    def test_add_natural_missing_400(self):
        r = self.client.post("/api/scheduler/natural", json={"name": "n1"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_add_natural_success(self):
        task = MagicMock()
        task.task_id = "t3"
        task.name = "nat1"
        task.next_run = "2026-01-01"
        self.fake_ss.get_smart_scheduler.return_value.add_natural.return_value = task
        r = self.client.post("/api/scheduler/natural", json={"name": "nat1", "time": "09:00", "payload": {"z": 3}})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["task_id"], "t3")
        self.fake_ss.get_smart_scheduler.return_value.add_natural.assert_called_once_with("nat1", "09:00", {"z": 3})

    def test_add_natural_value_error_400(self):
        self.fake_ss.get_smart_scheduler.return_value.add_natural.side_effect = ValueError("bad time")
        r = self.client.post("/api/scheduler/natural", json={"name": "nat1", "time": "bad"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_add_natural_no_body(self):
        r = self.client.post("/api/scheduler/natural")
        self.assertEqual(r.status_code, 400)

    def test_check(self):
        self.fake_ss.get_smart_scheduler.return_value.check_due.return_value = [{"id": "t1"}]
        r = self.client.post("/api/scheduler/check")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["due"], [{"id": "t1"}])
        self.assertEqual(body["count"], 1)

    def test_cancel_missing_task_id_400(self):
        r = self.client.post("/api/scheduler/cancel", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_cancel_success(self):
        self.fake_ss.get_smart_scheduler.return_value.cancel.return_value = True
        r = self.client.post("/api/scheduler/cancel", json={"task_id": "t1"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["cancelled"])
        self.fake_ss.get_smart_scheduler.return_value.cancel.assert_called_once_with("t1")

    def test_cancel_no_body(self):
        r = self.client.post("/api/scheduler/cancel")
        self.assertEqual(r.status_code, 400)

    def test_tasks(self):
        self.fake_ss.get_smart_scheduler.return_value.list_tasks.return_value = [{"id": "t1"}]
        r = self.client.get("/api/scheduler/tasks")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["tasks"], [{"id": "t1"}])

    def test_stats(self):
        self.fake_ss.get_smart_scheduler.return_value.get_stats.return_value = {"total": 5}
        r = self.client.get("/api/scheduler/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)


if __name__ == "__main__":
    unittest.main()
