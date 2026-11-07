"""Unit tests for orbit/orbit/agents/base.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.agents.base import BaseAgent


class TestBaseAgent(unittest.TestCase):
    def setUp(self):
        self.agent = BaseAgent()

    def test_defaults(self):
        self.assertEqual(self.agent.label, "GEN")
        self.assertEqual(self.agent.metrics["calls"], 0)

    def test_can_handle_false(self):
        self.assertFalse(self.agent.can_handle("anything"))

    def test_execute_raises_not_implemented_caught(self):
        r = self.agent.execute("hello")
        self.assertIn("encountered an error", r)
        self.assertEqual(self.agent.metrics["calls"], 1)

    def test_get_metrics(self):
        self.agent.execute("x")
        m = self.agent.get_metrics()
        self.assertEqual(m["calls"], 1)
        self.assertIsNotNone(m["last_call"])
        self.assertGreaterEqual(m["avg_ms"], 0)

    def test_get_system_prompt_fallback(self):
        r = self.agent.get_system_prompt()
        self.assertIsInstance(r, str)
        self.assertTrue(r)

    def test_get_learning_context(self):
        r = self.agent.get_learning_context("text")
        self.assertIsInstance(r, str)

    def test_record_mistake_and_success(self):
        self.agent.record_mistake("t", "exp", "act")
        self.agent.record_success("t", "out")

    def test_execute_with_working_run(self):
        class GoodAgent(BaseAgent):
            def _run(self, text, context=None):
                return f"ran:{text}"

        a = GoodAgent()
        self.assertEqual(a.execute("hi"), "ran:hi")
        self.assertEqual(a.get_metrics()["calls"], 1)

    def test_execute_accepts_assistant(self):
        a = BaseAgent(assistant="obj")
        self.assertEqual(a.assistant, "obj")


if __name__ == "__main__":
    unittest.main()
