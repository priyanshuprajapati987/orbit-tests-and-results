"""Unit tests for orbit/orbit/core/dead_hand_policy.py."""

import os
import sys
import time
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.dead_hand_policy import (
    load_profile, severity, risk_from_attempts, response_for, summarize,
    PROFILES, DEFAULT_PROFILE, SIGNAL_SEVERITY, RISK_WINDOW_SEC,
    RESTRICTED_RISK, LOCKOUT_RISK,
)


class TestLoadProfile(unittest.TestCase):
    def test_explicit_valid(self):
        self.assertEqual(load_profile("audit"), "audit")
        self.assertEqual(load_profile("restricted"), "restricted")
        self.assertEqual(load_profile("lockout"), "lockout")
        self.assertEqual(load_profile("shutdown"), "shutdown")

    def test_explicit_invalid(self):
        self.assertEqual(load_profile("foo"), DEFAULT_PROFILE)
        self.assertEqual(load_profile(""), DEFAULT_PROFILE)

    def test_explicit_case_insensitive(self):
        self.assertEqual(load_profile("AUDIT"), "audit")
        self.assertEqual(load_profile("  Restricted  "), "restricted")

    def test_env_fallback(self):
        import os
        os.environ["ORBIT_DEADHAND_RESPONSE"] = "lockout"
        try:
            self.assertEqual(load_profile(None), "lockout")
        finally:
            del os.environ["ORBIT_DEADHAND_RESPONSE"]

    def test_env_missing(self):
        import os
        os.environ.pop("ORBIT_DEADHAND_RESPONSE", None)
        self.assertEqual(load_profile(None), DEFAULT_PROFILE)

    def test_env_invalid(self):
        import os
        os.environ["ORBIT_DEADHAND_RESPONSE"] = "nope"
        try:
            self.assertEqual(load_profile(None), DEFAULT_PROFILE)
        finally:
            del os.environ["ORBIT_DEADHAND_RESPONSE"]


class TestSeverity(unittest.TestCase):
    def test_known(self):
        self.assertEqual(severity("debugger"), 1)
        self.assertEqual(severity("re_tool"), 1)
        self.assertEqual(severity("integrity"), 3)
        self.assertEqual(severity("integrity_new"), 2)
        self.assertEqual(severity("state_tamper"), 3)

    def test_unknown_default(self):
        self.assertEqual(severity("unknown"), 1)
        self.assertEqual(severity(""), 1)


class TestRiskFromAttempts(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(risk_from_attempts([]), 0)
        self.assertEqual(risk_from_attempts(None), 0)

    def test_within_window(self):
        now = 1000.0
        attempts = [
            {"ts": 990.0, "kind": "integrity"},
            {"ts": 995.0, "kind": "debugger"},
        ]
        self.assertEqual(risk_from_attempts(attempts, window_sec=60, now=now), 4)

    def test_outside_window(self):
        now = 1000.0
        attempts = [{"ts": 900.0, "kind": "integrity"}]
        self.assertEqual(risk_from_attempts(attempts, window_sec=60, now=now), 0)

    def test_explicit_severity_overrides_kind(self):
        now = 1000.0
        attempts = [{"ts": 999.0, "kind": "debugger", "severity": 5}]
        self.assertEqual(risk_from_attempts(attempts, window_sec=60, now=now), 5)

    def test_missing_ts_skipped(self):
        attempts = [{"kind": "integrity"}]
        self.assertEqual(risk_from_attempts(attempts, now=1000.0), 0)

    def test_bad_ts_skipped(self):
        attempts = [{"ts": "not-a-number", "kind": "integrity"}]
        self.assertEqual(risk_from_attempts(attempts, now=1000.0), 0)

    def test_bad_severity_raises(self):
        attempts = [{"ts": 999.0, "kind": "integrity", "severity": "bad"}]
        with self.assertRaises(ValueError):
            risk_from_attempts(attempts, window_sec=60, now=1000.0)

    def test_zero_severity_uses_kind(self):
        attempts = [{"ts": 999.0, "kind": "integrity", "severity": 0}]
        self.assertEqual(risk_from_attempts(attempts, window_sec=60, now=1000.0), 3)


class TestResponseFor(unittest.TestCase):
    def test_no_risk(self):
        self.assertEqual(response_for(0, "audit"), "none")
        self.assertEqual(response_for(-1, "audit"), "none")

    def test_audit_profile(self):
        # audit profile ceiling 0 -> all risk capped to "audit"
        self.assertEqual(response_for(1, "audit"), "audit")
        self.assertEqual(response_for(3, "audit"), "audit")
        self.assertEqual(response_for(6, "audit"), "audit")

    def test_restricted_profile(self):
        self.assertEqual(response_for(1, "restricted"), "audit")
        self.assertEqual(response_for(3, "restricted"), "restricted")
        self.assertEqual(response_for(6, "restricted"), "restricted")

    def test_lockout_profile(self):
        self.assertEqual(response_for(1, "lockout"), "audit")
        self.assertEqual(response_for(3, "lockout"), "restricted")
        self.assertEqual(response_for(6, "lockout"), "lockout")

    def test_shutdown_profile(self):
        self.assertEqual(response_for(6, "shutdown"), "shutdown")
        self.assertEqual(response_for(3, "shutdown"), "restricted")

    def test_invalid_profile_defaults(self):
        self.assertEqual(response_for(3, "foo"), response_for(3, "audit"))


class TestSummarize(unittest.TestCase):
    def test_structure(self):
        r = summarize(3, "audit")
        self.assertEqual(r["risk"], 3)
        self.assertEqual(r["profile"], "audit")
        self.assertEqual(r["response"], "audit")
        self.assertEqual(r["restricted_at"], RESTRICTED_RISK)
        self.assertEqual(r["lockout_at"], LOCKOUT_RISK)
        self.assertEqual(r["window_sec"], RISK_WINDOW_SEC)

    def test_constants(self):
        self.assertEqual(PROFILES, ("audit", "restricted", "lockout", "shutdown"))
        self.assertEqual(DEFAULT_PROFILE, "audit")
        self.assertEqual(RESTRICTED_RISK, 3)
        self.assertEqual(LOCKOUT_RISK, 6)


if __name__ == "__main__":
    unittest.main()
