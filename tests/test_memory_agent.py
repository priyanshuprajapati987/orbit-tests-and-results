"""Unit tests for orbit/orbit/agents/memory_agent.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.agents.memory_agent import PipelineMemoryAgent, MEMORY_AGENT_PROMPT


class TestPipelineMemoryAgent(unittest.TestCase):
    def setUp(self):
        self.agent = PipelineMemoryAgent()

    def test_instantiation(self):
        self.assertEqual(self.agent.label, "PMA")
        self.assertIsNotNone(self.agent._pool)

    def test_can_handle_always(self):
        self.assertTrue(self.agent.can_handle("anything"))

    def test_save_result(self):
        entry = self.agent.save_result(1, 2, "some result", "ctx")
        self.assertEqual(entry["task_id"], 1)
        self.assertEqual(entry["subtask_id"], 2)
        self.assertIn("timestamp", entry)

    def test_save_result_truncates(self):
        entry = self.agent.save_result(9, 9, "x" * 1000)
        self.assertEqual(len(entry["result"]), 500)

    def test_recall_no_match(self):
        r = self.agent.recall(task_id=999999)
        self.assertIsInstance(r, str)

    def test_recall_query(self):
        r = self.agent.recall(query="nonexistent-xyz-query")
        self.assertIsInstance(r, str)

    def test_recall_after_save(self):
        self.agent.save_result(42, 1, "remember this", "c")
        r = self.agent.recall(task_id=42)
        self.assertIsInstance(r, str)

    def test_summarize_pipeline_empty(self):
        r = self.agent.summarize_pipeline(999999)
        self.assertIsInstance(r, str)

    def test_summarize_pipeline_after_save(self):
        self.agent.save_result(77, 1, "step one")
        r = self.agent.summarize_pipeline(77)
        self.assertIn("summary", r)

    def test_run_delegates_recall(self):
        r = self.agent.execute("find something")
        self.assertIsInstance(r, str)

    def test_prompt_constant(self):
        self.assertIn("MEMORY AGENT", MEMORY_AGENT_PROMPT)


if __name__ == "__main__":
    unittest.main()
