"""Tests for ORBIT code-generation quality improvements.

Covers: code-block extraction, Python syntax verification, the CodeReviewer
review_code() wrapper, and the CodeAgent pipeline (review actually runs now,
syntax is verified, and only the code — not the prose — is saved to disk).
"""

import unittest
from unittest.mock import MagicMock, patch

from orbit.orbit.agents.task_agents import CodeAgent
from orbit.orbit.core.code_reviewer import (
    CodeReviewer,
    extract_code_blocks,
    verify_python_syntax,
)


class TestCodeBlockExtraction(unittest.TestCase):
    def test_fenced_block_extracted(self):
        text = "Here:\n```python\ndef f():\n    return 1\n```\ndone"
        self.assertEqual(extract_code_blocks(text), ["def f():\n    return 1"])

    def test_no_fence_returns_empty(self):
        self.assertEqual(extract_code_blocks("just code"), [])

    def test_empty_fence_ignored(self):
        text = "```python\n```\nreal:\n```python\nx=1\n```"
        self.assertEqual(extract_code_blocks(text), ["x=1"])


class TestSyntaxVerification(unittest.TestCase):
    def test_valid(self):
        ok, err = verify_python_syntax("def f():\n    return 1")
        self.assertTrue(ok)
        self.assertEqual(err, "")

    def test_invalid(self):
        ok, err = verify_python_syntax("def f(:")
        self.assertFalse(ok)
        self.assertIn("line", err)


class TestReviewCode(unittest.TestCase):
    def test_flags_hardcoded_secret(self):
        report = CodeReviewer().review_code("password = 'hunter2'", language="python")
        msgs = [i["message"] for i in report["issues"]]
        self.assertTrue(any("password" in m.lower() for m in msgs))

    def test_flags_bare_except(self):
        code = "try:\n    x = 1\nexcept:\n    pass\n"
        report = CodeReviewer().review_code(code, language="python")
        msgs = [i["message"] for i in report["issues"]]
        self.assertTrue(any("except" in m.lower() for m in msgs))


class TestCodeAgentPipeline(unittest.TestCase):
    def test_review_actually_runs(self):
        # Previously dead: reviewer.review_code() didn't exist, so review was skipped.
        code = "```python\ntry:\n    x = 1\nexcept:\n    pass\n```"
        with patch("orbit.orbit.agents.task_agents.llm_router") as mr:
            mr.generate.return_value = code
            out = CodeAgent()._run("write some code")
        self.assertIn("Code Review", out)

    def test_syntax_failure_warns_no_autofix(self):
        bad = "```python\ndef foo(:\n```"
        with patch("orbit.orbit.agents.task_agents.llm_router") as mr:
            mr.generate.return_value = bad  # auto-fix returns the same broken code
            out = CodeAgent()._run("write code")
        self.assertIn("Syntax check failed", out)
        self.assertNotIn("Auto-fixed code", out)

    def test_saves_only_code_not_prose(self):
        resp = "Here is your code:\n```python\ndef add(a, b):\n    return a + b\n```\nHope that helps!"
        mock_ft = MagicMock()
        with (
            patch("orbit.orbit.agents.task_agents.llm_router") as mr,
            patch("orbit.orbit.tools.file_tools.FileTools", return_value=mock_ft),
        ):
            mr.generate.return_value = resp
            out = CodeAgent()._run("write a function and save to /tmp/out.py")
        self.assertIn("Saved to", out)
        args, _ = mock_ft.write.call_args
        saved_content = args[1]
        self.assertIn("def add", saved_content)
        self.assertNotIn("Hope that helps", saved_content)
        self.assertNotIn("```", saved_content)


if __name__ == "__main__":
    unittest.main()
