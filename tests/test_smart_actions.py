"""Unit tests for orbit/orbit/tools/smart_actions.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.tools.smart_actions import SmartActions


class TestSmartActions(unittest.TestCase):
    def setUp(self):
        self.sa = SmartActions()

    def test_available_actions(self):
        self.assertIn("fix", self.sa.AVAILABLE_ACTIONS)
        self.assertEqual(len(self.sa.AVAILABLE_ACTIONS), 8)

    def test_list_actions(self):
        r = self.sa.list_actions()
        self.assertIn("actions", r)
        self.assertEqual(r["actions"], self.sa.AVAILABLE_ACTIONS)

    def test_quick_fix_success(self):
        with patch("orbit.tools.smart_actions.llm_router.generate", return_value="fixed code"):
            r = self.sa.quick_fix("NameError", "x = y", "python")
        self.assertTrue(r["success"])
        self.assertEqual(r["fix"], "fixed code")
        self.assertEqual(r["error"], "NameError")

    def test_quick_fix_failure(self):
        with patch("orbit.tools.smart_actions.llm_router.generate", side_effect=RuntimeError("llm down")):
            r = self.sa.quick_fix("err", "code")
        self.assertFalse(r["success"])
        self.assertIsNone(r["fix"])
        self.assertEqual(r["message"], "llm down")

    def test_run_action_unknown(self):
        r = self.sa.run_action("nope", "code")
        self.assertFalse(r["success"])
        self.assertIn("Unknown action", r["error"])
        self.assertIn("fix", r["available"])

    def test_run_action_success(self):
        with patch("orbit.tools.smart_actions.llm_router.generate", return_value="result text"):
            r = self.sa.run_action("explain", "print(1)", "python")
        self.assertTrue(r["success"])
        self.assertEqual(r["action"], "explain")
        self.assertEqual(r["result"], "result text")

    def test_run_action_case_insensitive(self):
        with patch("orbit.tools.smart_actions.llm_router.generate", return_value="r"):
            r = self.sa.run_action("EXPLAIN", "code")
        self.assertTrue(r["success"])
        self.assertEqual(r["action"], "explain")

    def test_run_action_failure(self):
        with patch("orbit.tools.smart_actions.llm_router.generate", side_effect=RuntimeError("down")):
            r = self.sa.run_action("fix", "code")
        self.assertFalse(r["success"])
        self.assertEqual(r["action"], "fix")
        self.assertEqual(r["error"], "down")

    def test_run_action_all_known(self):
        for action in self.sa.AVAILABLE_ACTIONS:
            with patch("orbit.tools.smart_actions.llm_router.generate", return_value="r"):
                r = self.sa.run_action(action, "code")
            self.assertTrue(r["success"], f"action {action} failed")


if __name__ == "__main__":
    unittest.main()
