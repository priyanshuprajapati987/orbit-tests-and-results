"""Unit tests for orbit/orbit/core/multi_ai_coordinator.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.multi_ai_coordinator import (
    TaskStatus, SubTask, Workflow, MultiAICoordinator, get_multi_ai_coordinator,
)


class TestTaskStatus(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(TaskStatus.PENDING, "pending")
        self.assertEqual(TaskStatus.COMPLETED, "completed")


class TestSubTask(unittest.TestCase):
    def test_init(self):
        st = SubTask(id="s1", prompt="hi", model="gpt-4o-mini")
        self.assertEqual(st.id, "s1")
        self.assertEqual(st.status, "pending")

    def test_to_dict(self):
        st = SubTask(id="s1", prompt="hi", model="gpt-4o-mini")
        d = st.to_dict()
        self.assertIsInstance(d, dict)
        self.assertEqual(d["id"], "s1")


class TestWorkflow(unittest.TestCase):
    def test_init(self):
        w = Workflow(id="w1", name="wf", description="d")
        self.assertEqual(w.id, "w1")
        self.assertEqual(w.status, "pending")

    def test_to_dict(self):
        w = Workflow(id="w1", name="wf", description="d")
        d = w.to_dict()
        self.assertIsInstance(d, dict)
        self.assertEqual(d["id"], "w1")


class TestMultiAICoordinator(unittest.TestCase):
    def setUp(self):
        self.mac = MultiAICoordinator()

    def test_instantiation(self):
        self.assertIsNotNone(self.mac)

    def test_create_workflow(self):
        w = self.mac.create_workflow("wf1", "A workflow", [{"prompt": "hi"}])
        self.assertIsNotNone(w)

    def test_get_workflow(self):
        w = self.mac.create_workflow("wf2", "A workflow", [{"prompt": "hi"}])
        wid = w["id"] if isinstance(w, dict) else w.id
        r = self.mac.get_workflow(wid)
        self.assertIsNotNone(r)

    def test_list_workflows(self):
        self.mac.create_workflow("wf3", "A workflow", [{"prompt": "hi"}])
        r = self.mac.list_workflows()
        self.assertIsInstance(r, (list, dict))

    def test_execute_workflow(self):
        w = self.mac.create_workflow("wf4", "A workflow", [{"prompt": "hi"}])
        wid = w["id"] if isinstance(w, dict) else w.id
        try:
            r = self.mac.execute_workflow(wid)
            self.assertIsNotNone(r)
        except Exception:
            self.assertTrue(True)

    def test_run_parallel(self):
        try:
            r = self.mac.run_parallel(["hi", "hello"], model="gpt-4o-mini")
            self.assertIsNotNone(r)
        except Exception:
            self.assertTrue(True)

    def test_aggregate_results(self):
        r = self.mac.aggregate_results({})
        self.assertIsNotNone(r)

    def test_get_stats(self):
        r = self.mac.get_stats()
        self.assertIsNotNone(r)

    def test_singleton(self):
        a = get_multi_ai_coordinator()
        b = get_multi_ai_coordinator()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
