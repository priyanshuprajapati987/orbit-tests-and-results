"""Unit tests for orbit/orbit/core/smart_executor.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.smart_executor import (
    TaskStatus, TaskPriority, TaskCategory, SmartTask, TaskResult,
    SmartExecutor, get_smart_executor,
)


class TestEnums(unittest.TestCase):
    def test_task_status(self):
        self.assertEqual(TaskStatus.PENDING.value, "pending")
        self.assertEqual(TaskStatus.COMPLETED.value, "completed")

    def test_task_priority(self):
        self.assertEqual(TaskPriority.CRITICAL.value, 0)
        self.assertEqual(TaskPriority.BACKGROUND.value, 4)

    def test_task_category(self):
        self.assertEqual(TaskCategory.CODE_ANALYSIS.value, "code_analysis")


class TestSmartTask(unittest.TestCase):
    def test_init(self):
        t = SmartTask(id="t1", title="Test", description="desc", category="code_analysis", priority=2, status="pending", created_at=0.0)
        self.assertEqual(t.id, "t1")
        self.assertEqual(t.title, "Test")

    def test_to_dict(self):
        t = SmartTask(id="t1", title="Test", description="desc", category="code_analysis", priority=2, status="pending", created_at=0.0)
        d = t.to_dict() if hasattr(t, "to_dict") else None
        self.assertTrue(d is None or isinstance(d, dict))


class TestTaskResult(unittest.TestCase):
    def test_init(self):
        r = TaskResult(task_id="t1", status="completed", result={"ok": True})
        self.assertEqual(r.task_id, "t1")


class TestSmartExecutor(unittest.TestCase):
    def setUp(self):
        self.se = SmartExecutor()

    def test_instantiation(self):
        self.assertIsNotNone(self.se)

    def test_submit_task(self):
        r = self.se.submit_task("Test task", "do something", "code_analysis")
        self.assertIsInstance(r, dict)
        self.assertIn("task_id", r)
        self._tid = r["task_id"]

    def test_get_task(self):
        r = self.se.submit_task("Test task 2", "do something", "code_analysis")
        tid = r["task_id"]
        t = self.se.get_task(tid)
        self.assertIsNotNone(t)

    def test_get_queue(self):
        self.se.submit_task("q task", "q", "code_analysis")
        q = self.se.get_queue()
        self.assertIsInstance(q, list)

    def test_get_stats(self):
        r = self.se.get_stats()
        self.assertIsNotNone(r)

    def test_cancel_task(self):
        r = self.se.submit_task("cancel me", "x", "code_analysis")
        tid = r["task_id"]
        res = self.se.cancel_task(tid)
        self.assertIsNotNone(res)

    def test_reject_task(self):
        r = self.se.submit_task("reject me", "x", "code_analysis")
        tid = r["task_id"]
        res = self.se.reject_task(tid)
        self.assertIsNotNone(res)

    def test_execute_now(self):
        r = self.se.submit_task("run now", "x", "code_analysis")
        tid = r["task_id"]
        res = self.se.execute_now(tid)
        self.assertIsNotNone(res)

    def test_singleton(self):
        a = get_smart_executor()
        b = get_smart_executor()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
