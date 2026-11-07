"""Unit tests for orbit/orbit/agents/council.py (LLM mocked)."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.agents.council import (
    CouncilAgent,
    ADVISOR_PROMPTS,
    CHAIRMAN_PROMPT,
)


class TestCouncilAgent(unittest.TestCase):
    def setUp(self):
        self.agent = CouncilAgent()

    def test_instantiation(self):
        self.assertEqual(self.agent.label, "CNC")
        self.assertEqual(self.agent._advisor_cache, {})

    def test_advisor_prompts_complete(self):
        expected = {"contrarian", "first_principles", "expansionist", "outsider", "executor"}
        self.assertEqual(set(ADVISOR_PROMPTS.keys()), expected)
        for p in ADVISOR_PROMPTS.values():
            self.assertTrue(len(p) > 50)

    def test_chairman_prompt(self):
        self.assertIn("CHAIRMAN", CHAIRMAN_PROMPT)

    def test_can_handle_prefix(self):
        self.assertTrue(self.agent.can_handle("council: should we pivot?"))

    def test_can_handle_council_space(self):
        self.assertTrue(self.agent.can_handle("council analyze this"))

    def test_can_handle_intent(self):
        self.assertTrue(self.agent.can_handle("anything", intent="council"))

    def test_can_handle_plain_text(self):
        self.assertFalse(self.agent.can_handle("hello world"))

    def test_set_callback_and_emit(self):
        calls = []
        self.agent.set_callback(calls.append)
        self.agent._emit_advisor("contrarian")
        self.assertEqual(calls, ["contrarian"])

    def test_run_advisor_mocked(self):
        with patch("orbit.agents.council.llm_router.generate", return_value="flaws found"):
            r = self.agent._run_advisor("contrarian", "should we do X?")
            self.assertEqual(r, "flaws found")

    def test_run_advisor_empty_response(self):
        with patch("orbit.agents.council.llm_router.generate", return_value=None):
            r = self.agent._run_advisor("outsider", "q")
            self.assertIn("no response", r)

    def test_run_advisor_error(self):
        with patch("orbit.agents.council.llm_router.generate", side_effect=RuntimeError("llm down")):
            r = self.agent._run_advisor("executor", "q")
            self.assertIn("error", r)

    def test_run_chairman_mocked(self):
        with patch("orbit.agents.council.llm_router.generate", return_value="final verdict"):
            r = self.agent._run_chairman("q", {"contrarian": "a", "executor": "b"})
            self.assertEqual(r, "final verdict")

    def test_run_chairman_error(self):
        with patch("orbit.agents.council.llm_router.generate", side_effect=RuntimeError("x")):
            r = self.agent._run_chairman("q", {})
            self.assertIn("Chairman error", r)

    def test_run_full_flow(self):
        seen = []
        self.agent.set_callback(seen.append)
        with patch("orbit.agents.council.llm_router.generate", return_value="advisor take"):
            r = self.agent.execute("council: should we ship it?")
        self.assertIn("ADVISORY COUNCIL ANALYSIS", r)
        self.assertIn("CHAIRMAN'S FINAL VERDICT", r)
        self.assertIn("Contrarian", r)
        self.assertIn("chairman", seen)

    def test_run_strips_council_prefix(self):
        with patch("orbit.agents.council.llm_router.generate", return_value="take") as m:
            self.agent.execute("council: do the thing")
            first_prompt = m.call_args[0][0]
            self.assertNotIn("council: do the thing", first_prompt.split("Analyze this:")[-1])

    def test_get_metrics(self):
        m = self.agent.get_metrics()
        self.assertEqual(m["calls"], 0)


if __name__ == "__main__":
    unittest.main()
