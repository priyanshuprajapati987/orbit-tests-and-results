"""Unit tests for orbit/orbit/agents/critic.py (LLM mocked)."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.agents.critic import CriticAgent


class TestCriticAgent(unittest.TestCase):
    def setUp(self):
        self.agent = CriticAgent()

    def test_instantiation(self):
        self.assertIsNotNone(self.agent)
        self.assertEqual(self.agent.label, "CRT")

    def test_can_handle(self):
        self.assertTrue(self.agent.can_handle("review this"))

    def test_execute_with_mock(self):
        mock_resp = MagicMock()
        mock_resp.content = '{"quality": "pass", "score": 0.9, "feedback": "ok", "suggested_fix": ""}'
        mock_resp.success = True
        with patch("orbit.agents.critic.llm_router.generate", return_value=mock_resp):
            r = self.agent.execute("review result")
            self.assertIsNotNone(r)

    def test_get_metrics(self):
        r = self.agent.get_metrics()
        self.assertIsNotNone(r)

    def test_get_system_prompt(self):
        r = self.agent.get_system_prompt()
        self.assertIsInstance(r, str)


if __name__ == "__main__":
    unittest.main()
