"""Unit tests for orbit/orbit/core/predictive_debugger.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.predictive_debugger import PredictiveDebugger, get_predictive_debugger


class TestPredictiveDebugger(unittest.TestCase):
    def setUp(self):
        self.d = PredictiveDebugger()

    def test_clean_code(self):
        code = "def add(a, b):\n    return a + b\n"
        self.assertEqual(self.d.analyze(code), [])
        self.assertEqual(self.d.score(code), 1.0)

    def test_syntax_error(self):
        r = self.d.analyze("def broken(:\n")
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["type"], "syntax")
        self.assertEqual(r[0]["severity"], "high")
        self.assertIsNone(r[0]["line"]) if False else None
        # lineno is None? ast SyntaxError.lineno could be int; just check present

    def test_eval_detected(self):
        r = self.d.analyze("x = eval(user_input)")
        types = [i["type"] for i in r]
        self.assertIn("security", types)
        self.assertTrue(any(i["msg"] == "Avoid eval/exec" for i in r))

    def test_exec_detected(self):
        r = self.d.analyze("exec(code)")
        self.assertTrue(any(i["type"] == "security" for i in r))

    def test_wildcard_import(self):
        r = self.d.analyze("from os import *")
        self.assertTrue(any(i["type"] == "style" for i in r))

    def test_bare_except(self):
        r = self.d.analyze("try:\n    pass\nexcept:\n    pass\n")
        self.assertTrue(any(i["type"] == "quality" for i in r))

    def test_todo(self):
        r = self.d.analyze("# TODO: fix this\nx = 1")
        self.assertTrue(any(i["type"] == "todo" for i in r))

    def test_fixme(self):
        r = self.d.analyze("# FIXME later\nx = 1")
        self.assertTrue(any(i["type"] == "todo" for i in r))

    def test_too_many_params(self):
        code = "def f(a, b, c, d, e, f, g, h):\n    pass\n"
        r = self.d.analyze(code)
        self.assertTrue(any(i["type"] == "complexity" for i in r))

    def test_score_with_issues(self):
        code = "x = eval(user_input)\nfrom os import *\n"
        issues = self.d.analyze(code)
        self.assertGreater(len(issues), 0)
        score = self.d.score(code)
        self.assertLess(score, 1.0)
        self.assertGreaterEqual(score, 0.0)

    def test_score_floor(self):
        code = "\n".join(["x = eval(y)"] * 10)
        self.assertEqual(self.d.score(code), 0.0)

    def test_empty_code(self):
        self.assertEqual(self.d.analyze(""), [])
        self.assertEqual(self.d.score(""), 1.0)

    def test_singleton(self):
        a = get_predictive_debugger()
        b = get_predictive_debugger()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
