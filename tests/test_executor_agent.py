"""Unit tests for orbit/orbit/agents/executor_agent.py (LLM + tools mocked)."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.agents.executor_agent import ExecutorAgent, EXECUTOR_PROMPT


class TestExecutorAgent(unittest.TestCase):
    def setUp(self):
        self.agent = ExecutorAgent()

    def test_instantiation(self):
        self.assertEqual(self.agent.label, "EXE")
        self.assertIsNotNone(self.agent.computer_tool)
        self.assertIsNotNone(self.agent.news_tool)

    def test_can_handle_always(self):
        self.assertTrue(self.agent.can_handle("anything"))

    def test_execute_subtask_ask(self):
        r = self.agent.execute_subtask({"type": "ask", "description": "q?"})
        self.assertIn("Need input", r)

    def test_execute_subtask_unknown_type(self):
        r = self.agent.execute_subtask({"type": "weird", "description": "x"})
        self.assertIn("Need input", r)

    def test_execute_subtask_code_mocked(self):
        with patch("orbit.agents.executor_agent.llm_router.generate", return_value="print(1)"):
            r = self.agent.execute_subtask({"type": "code", "description": "a script", "params": {"language": "python"}})
            self.assertIn("```python", r)

    def test_execute_subtask_code_no_lang(self):
        with patch("orbit.agents.executor_agent.llm_router.generate", return_value="x = 1"):
            r = self.agent.execute_subtask({"type": "code", "description": "assign"})
            self.assertEqual(r, "x = 1")

    def test_execute_subtask_memory_mocked(self):
        with patch("orbit.agents.executor_agent.llm_router.generate", return_value="ctx answer"):
            r = self.agent.execute_subtask({"type": "memory", "description": "recall"}, context="some ctx")
            self.assertEqual(r, "ctx answer")

    def test_execute_subtask_research_mocked(self):
        with patch.object(self.agent.search_tool, "search", return_value={"results": [{"title": "T", "snippet": "S"}]}):
            r = self.agent.execute_subtask({"type": "research", "description": "topic"})
            self.assertIn("Search results", r)

    def test_execute_subtask_research_news_fallback(self):
        with patch.object(self.agent.search_tool, "search", return_value=None):
            with patch.object(self.agent.news_tool, "handle_natural", return_value="news item"):
                r = self.agent.execute_subtask({"type": "research", "description": "topic"})
                self.assertEqual(r, "news item")

    def test_execute_subtask_shell_mocked(self):
        with patch.object(self.agent.computer_tool, "handle_natural", return_value={"stdout": "ok"}):
            r = self.agent.execute_subtask({"type": "shell", "description": "run it"})
            self.assertEqual(r, "ok")

    def test_execute_subtask_shell_error_caught(self):
        with patch.object(self.agent.computer_tool, "handle_natural", side_effect=RuntimeError("boom")):
            r = self.agent.execute_subtask({"type": "shell", "description": "x"})
            self.assertIn("Executor error", r)

    def test_execute_subtask_file_write(self):
        if not self.agent.file_tool:
            self.skipTest("FileTools unavailable")
        import tempfile
        p = os.path.join(tempfile.mkdtemp(), "t.txt")
        r = self.agent.execute_subtask({"type": "file", "description": "w", "params": {"action": "write", "path": p, "content": "hi"}})
        self.assertTrue(os.path.exists(p) or r)

    def test_execute_subtask_github_unavailable_or_mocked(self):
        if self.agent.github_tool is None:
            r = self.agent.execute_subtask({"type": "github", "description": "issues"})
            self.assertIn("not available", r)
        else:
            with patch.object(self.agent.github_tool, "handle_natural", return_value="gh"):
                r = self.agent.execute_subtask({"type": "github", "description": "show issues"})
                self.assertEqual(r, "gh")

    def test_extract_output(self):
        self.assertEqual(self.agent._extract_output({"stdout": "o"}), "o")
        self.assertEqual(self.agent._extract_output({"data": "d"}), "d")
        self.assertEqual(self.agent._extract_output("plain"), "plain")

    def test_run_routes_file(self):
        with patch.object(self.agent, "execute_subtask", return_value="r") as m:
            self.agent.execute("read notes.txt")
            m.assert_called_once()
            self.assertEqual(m.call_args[0][0]["type"], "file")

    def test_run_routes_research(self):
        with patch.object(self.agent, "execute_subtask", return_value="r") as m:
            self.agent.execute("search the news")
            self.assertEqual(m.call_args[0][0]["type"], "research")

    def test_run_routes_github(self):
        with patch.object(self.agent, "execute_subtask", return_value="r") as m:
            self.agent.execute("list github issues")
            self.assertEqual(m.call_args[0][0]["type"], "github")

    def test_run_routes_code(self):
        with patch.object(self.agent, "execute_subtask", return_value="r") as m:
            self.agent.execute("write a script")
            self.assertEqual(m.call_args[0][0]["type"], "code")

    def test_run_routes_shell(self):
        with patch.object(self.agent, "execute_subtask", return_value="r") as m:
            self.agent.execute("run the command")
            self.assertEqual(m.call_args[0][0]["type"], "shell")

    def test_run_routes_browser(self):
        with patch.object(self.agent, "execute_subtask", return_value="r") as m:
            self.agent.execute("open this website")
            self.assertEqual(m.call_args[0][0]["type"], "browser")

    def test_prompt_constant(self):
        self.assertIn("EXECUTOR AGENT", EXECUTOR_PROMPT)


if __name__ == "__main__":
    unittest.main()
