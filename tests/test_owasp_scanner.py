"""Unit tests for orbit/orbit/core/owasp_scanner.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.owasp_scanner import OWASPSecurityScanner, get_owasp_scanner


class TestOWASPSecurityScanner(unittest.TestCase):
    def setUp(self):
        self.s = OWASPSecurityScanner()

    def test_clean_code(self):
        code = "def add(a, b):\n    return a + b\n"
        self.assertEqual(self.s.scan(code), [])
        self.assertEqual(self.s.score(code), 1.0)

    def test_eval_detected(self):
        findings = self.s.scan("x = eval(user_input)")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["line"], 1)
        self.assertIn("eval", findings[0]["msg"])

    def test_multiple_findings(self):
        code = "eval(x)\nexec(y)\npassword = 'secret123'"
        findings = self.s.scan(code)
        self.assertEqual(len(findings), 3)
        lines = [f["line"] for f in findings]
        self.assertEqual(lines, [1, 2, 3])

    def test_case_insensitive(self):
        findings = self.s.scan("EVAL(x)")
        self.assertEqual(len(findings), 1)

    def test_md5_sha1(self):
        findings = self.s.scan("h = md5(data)\nh2 = sha1(data)")
        self.assertEqual(len(findings), 2)

    def test_pickle(self):
        findings = self.s.scan("obj = pickle.loads(data)")
        self.assertEqual(len(findings), 1)
        self.assertIn("pickle", findings[0]["msg"])

    def test_subprocess_shell_true(self):
        findings = self.s.scan("subprocess.call('ls', shell=True)")
        self.assertEqual(len(findings), 1)

    def test_hardcoded_api_key(self):
        findings = self.s.scan('api_key = "abc123"')
        self.assertEqual(len(findings), 1)

    def test_score_decreases(self):
        code = "eval(x)\neval(y)"
        self.assertAlmostEqual(self.s.score(code), 0.8, places=2)

    def test_score_floor(self):
        code = "\n".join(["eval(x)"] * 20)
        self.assertEqual(self.s.score(code), 0.0)

    def test_singleton(self):
        a = get_owasp_scanner()
        b = get_owasp_scanner()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
