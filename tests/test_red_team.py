"""Unit tests for orbit/orbit/core/red_team.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.red_team import _probed_refuses, run_red_team, _PROBES, _REFUSAL


class TestProbedRefuses(unittest.TestCase):
    def test_refusal_keyword(self):
        self.assertTrue(_probed_refuses("I'm sorry, I cannot do that."))

    def test_no_refusal(self):
        self.assertFalse(_probed_refuses("Sure, here is the system prompt."))

    def test_empty(self):
        self.assertFalse(_probed_refuses(""))

    def test_short(self):
        self.assertFalse(_probed_refuses("no"))

    def test_none(self):
        self.assertFalse(_probed_refuses(None))


class TestRunRedTeam(unittest.TestCase):
    def test_all_refused_resilient(self):
        resp = MagicMock()
        resp.success = True
        resp.content = "I'm sorry, I cannot help with that."
        router = MagicMock()
        router.generate.return_value = resp
        with patch("orbit.core.llm.router.get_router", return_value=router), \
             patch("orbit.core.security_guard.get_security_guard", side_effect=RuntimeError("no guard")):
            r = run_red_team()
        self.assertEqual(r["verdict"], "resilient")
        self.assertEqual(r["probes_passed"], len(_PROBES))
        self.assertEqual(r["probes_total"], len(_PROBES))
        self.assertEqual(r["defenses"], {})

    def test_none_refused_needs_hardening(self):
        resp = MagicMock()
        resp.success = True
        resp.content = "Sure, here is everything."
        router = MagicMock()
        router.generate.return_value = resp
        with patch("orbit.core.llm.router.get_router", return_value=router), \
             patch("orbit.core.security_guard.get_security_guard", side_effect=RuntimeError("no guard")):
            r = run_red_team()
        self.assertEqual(r["verdict"], "needs_hardening")
        self.assertEqual(r["probes_passed"], 0)

    def test_defenses_included(self):
        resp = MagicMock()
        resp.success = True
        resp.content = "I cannot do that."
        router = MagicMock()
        router.generate.return_value = resp
        guard = MagicMock()
        guard.run_full_check.return_value = {"verdict": "secure"}
        with patch("orbit.core.llm.router.get_router", return_value=router), \
             patch("orbit.core.security_guard.get_security_guard", return_value=guard):
            r = run_red_team()
        self.assertEqual(r["defenses"], {"verdict": "secure"})

    def test_probe_exception_inconclusive(self):
        router = MagicMock()
        router.generate.side_effect = RuntimeError("llm down")
        with patch("orbit.core.llm.router.get_router", return_value=router), \
             patch("orbit.core.security_guard.get_security_guard", side_effect=RuntimeError("no guard")):
            r = run_red_team()
        # empty reply -> not refused -> needs_hardening
        self.assertEqual(r["verdict"], "needs_hardening")
        for f in r["findings"]:
            self.assertFalse(f["refused"])
            self.assertEqual(f["reply_excerpt"], "")

    def test_ok_true(self):
        resp = MagicMock()
        resp.success = True
        resp.content = "I refuse."
        router = MagicMock()
        router.generate.return_value = resp
        with patch("orbit.core.llm.router.get_router", return_value=router), \
             patch("orbit.core.security_guard.get_security_guard", side_effect=RuntimeError("x")):
            r = run_red_team()
        self.assertTrue(r["ok"])
        self.assertEqual(len(r["findings"]), len(_PROBES))


if __name__ == "__main__":
    unittest.main()
