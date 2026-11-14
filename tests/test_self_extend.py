"""Unit tests for orbit/orbit/core/self_extend.py."""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.self_extend import propose, list_proposed


class TestSelfExtend(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.proposed_dir = os.path.join(self.tmp, "proposed")
        os.makedirs(self.proposed_dir, exist_ok=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _router(self, code, success=True):
        router = MagicMock()
        resp = MagicMock()
        resp.content = code
        resp.success = success
        router.generate.return_value = resp
        return router

    def test_empty_description(self):
        r = propose("")
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"], "empty description")

    def test_none_description(self):
        r = propose(None)
        self.assertFalse(r["ok"])

    def test_draft_failed_empty(self):
        router = self._router("")
        with patch("orbit.core.llm.router.get_router", return_value=router), \
             patch("orbit.core.self_extend._proposed_dir", return_value=self.proposed_dir):
            r = propose("do something")
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"], "draft failed")

    def test_draft_failed_exception(self):
        router = MagicMock()
        router.generate.side_effect = RuntimeError("llm down")
        with patch("orbit.core.llm.router.get_router", return_value=router), \
             patch("orbit.core.self_extend._proposed_dir", return_value=self.proposed_dir):
            r = propose("do something")
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"], "draft failed")

    def test_propose_valid_code(self):
        code = "def run(**kwargs):\n    return {'ok': True}\n"
        router = self._router(code)
        with patch("orbit.core.llm.router.get_router", return_value=router), \
             patch("orbit.core.self_extend._proposed_dir", return_value=self.proposed_dir):
            r = propose("do something", name="my tool")
        self.assertTrue(r["ok"])
        self.assertEqual(r["name"], "my_tool")
        self.assertTrue(r["compiles"])
        self.assertEqual(r["compile_error"], "")
        self.assertTrue(os.path.exists(r["staged_path"]))
        # code truncated to 1500
        self.assertEqual(r["code"], code.strip()[:1500])

    def test_propose_invalid_code(self):
        code = "def run(:\n    pass\n"
        router = self._router(code)
        with patch("orbit.core.llm.router.get_router", return_value=router), \
             patch("orbit.core.self_extend._proposed_dir", return_value=self.proposed_dir):
            r = propose("do something")
        self.assertTrue(r["ok"])  # still staged
        self.assertFalse(r["compiles"])
        self.assertTrue(r["compile_error"])

    def test_strip_markdown_fences(self):
        code = "```python\ndef run(**kwargs):\n    return {}\n```"
        router = self._router(code)
        with patch("orbit.core.llm.router.get_router", return_value=router), \
             patch("orbit.core.self_extend._proposed_dir", return_value=self.proposed_dir):
            r = propose("do something")
        self.assertTrue(r["ok"])
        # code should be stripped of fences
        self.assertFalse(r["code"].startswith("```"))
        self.assertTrue(r["compiles"])

    def test_safe_name_sanitization(self):
        code = "def run(**kwargs):\n    return {}\n"
        router = self._router(code)
        with patch("orbit.core.llm.router.get_router", return_value=router), \
             patch("orbit.core.self_extend._proposed_dir", return_value=self.proposed_dir):
            r = propose("do something", name="!!!bad name-123")
        self.assertTrue(r["ok"])
        # safe_name: spaces→_, dashes→_, then keep alnum+underscore
        self.assertEqual(r["name"], "bad_name_123")

    def test_safe_name_empty_fallback(self):
        code = "def run(**kwargs):\n    return {}\n"
        router = self._router(code)
        with patch("orbit.core.llm.router.get_router", return_value=router), \
             patch("orbit.core.self_extend._proposed_dir", return_value=self.proposed_dir):
            r = propose("do something", name="!!!")
        self.assertTrue(r["ok"])
        self.assertEqual(r["name"], "tool")

    def test_safe_name_truncated(self):
        code = "def run(**kwargs):\n    return {}\n"
        router = self._router(code)
        long_name = "a" * 100
        with patch("orbit.core.llm.router.get_router", return_value=router), \
             patch("orbit.core.self_extend._proposed_dir", return_value=self.proposed_dir):
            r = propose("do something", name=long_name)
        self.assertTrue(r["ok"])
        self.assertEqual(len(r["name"]), 40)

    def test_list_proposed(self):
        # create a file in proposed dir
        with open(os.path.join(self.proposed_dir, "tool.py"), "w") as f:
            f.write("x")
        with patch("orbit.core.self_extend._proposed_dir", return_value=self.proposed_dir):
            r = list_proposed()
        self.assertEqual(r, ["tool.py"])

    def test_list_proposed_empty(self):
        with patch("orbit.core.self_extend._proposed_dir", return_value=self.proposed_dir):
            r = list_proposed()
        self.assertEqual(r, [])

    def test_list_proposed_exception(self):
        with patch("orbit.core.self_extend._proposed_dir", return_value="/nonexistent/path/xyz"):
            r = list_proposed()
        self.assertEqual(r, [])

    def test_cache_param_passed(self):
        code = "def run(**kwargs):\n    return {}\n"
        router = self._router(code)
        with patch("orbit.core.llm.router.get_router", return_value=router), \
             patch("orbit.core.self_extend._proposed_dir", return_value=self.proposed_dir):
            propose("do something", use_cache=False)
        req = router.generate.call_args[0][0]
        self.assertFalse(req.use_cache)


if __name__ == "__main__":
    unittest.main()
