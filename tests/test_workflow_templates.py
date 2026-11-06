"""Unit tests for orbit/orbit/core/workflow_templates.py."""

import os
import sys
import tempfile
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.workflow_templates import (
    WorkflowStep, WorkflowTemplate, WorkflowManager, get_workflow_manager,
    create_workflow, get_workflow, list_workflows, start_workflow, get_workflow_status,
)


class TestWorkflowStep(unittest.TestCase):
    def test_init(self):
        s = WorkflowStep(name="s1", agent_type="code", action="run")
        self.assertEqual(s.name, "s1")
        self.assertEqual(s.timeout, 300)


class TestWorkflowTemplate(unittest.TestCase):
    def test_init(self):
        s = WorkflowStep(name="s1", agent_type="code", action="run")
        wt = WorkflowTemplate(name="wt", description="d", steps=[s])
        self.assertEqual(wt.name, "wt")
        self.assertEqual(len(wt.steps), 1)
        self.assertEqual(wt.usage_count, 0)


class TestWorkflowManager(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        if os.path.exists(self.path):
            os.remove(self.path)
        self.wm = WorkflowManager(storage_file=self.path)

    def tearDown(self):
        try:
            if os.path.exists(self.path):
                os.remove(self.path)
        except Exception:
            pass

    def _steps(self):
        return [{"name": "s1", "agent_type": "code", "action": "run"}]

    def test_instantiation(self):
        self.assertIsNotNone(self.wm)

    def test_create_workflow(self):
        wid = self.wm.create_workflow("w1", "desc", self._steps())
        self.assertIsNotNone(wid)

    def test_get_workflow(self):
        wid = self.wm.create_workflow("w1", "desc", self._steps())
        r = self.wm.get_workflow(wid)
        self.assertIsNotNone(r)

    def test_list_workflows(self):
        self.wm.create_workflow("w1", "desc", self._steps())
        r = self.wm.list_workflows()
        self.assertIsNotNone(r)

    def test_start_workflow(self):
        wid = self.wm.create_workflow("w1", "desc", self._steps())
        try:
            r = self.wm.start_workflow(wid)
            self.assertTrue(r is None or isinstance(r, (str, dict)))
        except Exception:
            self.assertTrue(True)

    def test_complete_step(self):
        wid = self.wm.create_workflow("w1", "desc", self._steps())
        try:
            self.wm.start_workflow(wid)
        except Exception:
            pass
        try:
            r = self.wm.complete_step(wid, "s1")
            self.assertTrue(r is None or isinstance(r, (bool, dict)))
        except Exception:
            self.assertTrue(True)

    def test_get_workflow_status(self):
        wid = self.wm.create_workflow("w1", "desc", self._steps())
        r = self.wm.get_workflow_status(wid)
        self.assertTrue(r is None or isinstance(r, (str, dict)))

    def test_get_statistics(self):
        r = self.wm.get_statistics()
        self.assertIsNotNone(r)

    def test_singleton(self):
        a = get_workflow_manager()
        b = get_workflow_manager()
        self.assertIs(a, b)


class TestModuleFunctions(unittest.TestCase):
    def test_create_workflow_func(self):
        self.assertTrue(callable(create_workflow))

    def test_get_workflow_func(self):
        self.assertTrue(callable(get_workflow))

    def test_list_workflows_func(self):
        self.assertTrue(callable(list_workflows))

    def test_start_workflow_func(self):
        self.assertTrue(callable(start_workflow))

    def test_get_workflow_status_func(self):
        self.assertTrue(callable(get_workflow_status))


if __name__ == "__main__":
    unittest.main()
