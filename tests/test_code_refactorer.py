"""Unit tests for orbit/orbit/core/code_refactorer.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.code_refactorer import CodeRefactorer, get_code_refactorer


class TestCodeRefactorer(unittest.TestCase):
    def setUp(self):
        self.r = CodeRefactorer()

    def test_clean_code(self):
        code = "def add(a, b):\n    return a + b\n"
        self.assertEqual(self.r.suggest(code), [])

    def test_syntax_error(self):
        r = self.r.suggest("def broken(:\n")
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["type"], "error")

    def test_long_function(self):
        body = "    pass\n" * 55
        code = f"def big():\n{body}"
        r = self.r.suggest(code)
        types = [s["type"] for s in r]
        self.assertIn("long_function", types)

    def test_too_many_params(self):
        code = "def f(a, b, c, d, e, f):\n    pass\n"
        r = self.r.suggest(code)
        types = [s["type"] for s in r]
        self.assertIn("too_many_params", types)

    def test_line_too_long(self):
        code = "x = " + "a" * 120 + "\n"
        r = self.r.suggest(code)
        types = [s["type"] for s in r]
        self.assertIn("line_too_long", types)

    def test_multiple_suggestions(self):
        code = "def f(a,b,c,d,e,f):\n    pass\n" + "x = " + "y" * 120 + "\n"
        r = self.r.suggest(code)
        self.assertGreaterEqual(len(r), 2)

    def test_singleton(self):
        a = get_code_refactorer()
        b = get_code_refactorer()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
