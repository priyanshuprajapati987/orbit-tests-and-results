"""
Phase 1 Foundation Audit tests
==============================
Covers the v3.5.0 foundation-fix artifacts:
- Per-IP scoped rate limiting (BUG-08: global limiter was a silent no-op)
- Startup diagnostics report (BUG-05)
- Secret-redacted structured logging (BUG-11)
- Config re-export shim parity (BUG-01)

Run: python -m pytest tests/test_phase1_audit.py -v
"""

import unittest

from orbit.orbit.core.rate_limiter import RateLimiterRegistry


class TestScopedRateLimiter(unittest.TestCase):
    def test_scoped_per_ip_burst(self):
        limiter = RateLimiterRegistry()
        limiter.register("test:bucket", rate=1.0, burst=2)
        results = [limiter.scoped_check("test:bucket", "10.0.0.1") for _ in range(3)]
        self.assertEqual(results, [True, True, False])

    def test_scoped_ip_isolation(self):
        limiter = RateLimiterRegistry()
        limiter.register("test:iso", rate=1.0, burst=1)
        self.assertTrue(limiter.scoped_check("test:iso", "10.0.0.1"))
        self.assertFalse(limiter.scoped_check("test:iso", "10.0.0.1"))
        self.assertTrue(limiter.scoped_check("test:iso", "10.0.0.2"))

    def test_scoped_unregistered_base_allowed(self):
        limiter = RateLimiterRegistry()
        self.assertTrue(limiter.scoped_check("does:not:exist", "10.0.0.1"))

    def test_scoped_refills_over_time(self):
        import time

        limiter = RateLimiterRegistry()
        limiter.register("test:refill", rate=100.0, burst=1)
        self.assertTrue(limiter.scoped_check("test:refill", "10.0.0.1"))
        time.sleep(0.02)
        self.assertTrue(limiter.scoped_check("test:refill", "10.0.0.1"))

    def test_legacy_check_unchanged(self):
        limiter = RateLimiterRegistry()
        self.assertTrue(limiter.check("missing"))
        limiter.register("legacy", rate=1.0, burst=1)
        self.assertTrue(limiter.check("legacy"))
        self.assertFalse(limiter.check("legacy"))


class TestStartupDiagnostics(unittest.TestCase):
    def test_run_diagnostics_shape(self):
        from orbit.orbit.core.startup_diagnostics import run_diagnostics

        report = run_diagnostics()
        self.assertIn("timestamp", report)
        self.assertIn("status", report)
        self.assertIn("checks", report)
        self.assertIn(report["status"], ("OK", "DEGRADED", "FAIL"))
        self.assertIsInstance(report["checks"], list)
        for check in report["checks"]:
            self.assertIn("name", check)
            self.assertIn("verdict", check)
            self.assertIn(check["verdict"], ("ok", "warn", "fail"))

    def test_print_report_smoke(self):
        import contextlib
        import io

        from orbit.orbit.core.startup_diagnostics import print_report, run_diagnostics

        report = run_diagnostics()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_report(report)
        out = buf.getvalue()
        self.assertIn("ORBIT Startup Diagnostics", out)

    def test_main_returns_exit_code(self):
        from orbit.orbit.core.startup_diagnostics import main

        code = main()
        self.assertIn(code, (0, 1))

    def test_check_python_version(self):
        from orbit.orbit.core.startup_diagnostics import check_python

        diag = check_python()
        self.assertEqual(diag.verdict, "ok")


class TestLoggingRedaction(unittest.TestCase):
    def test_json_formatter_redacts_secrets(self):
        import logging

        from orbit.orbit.logging_config import JSONFormatter

        fmt = JSONFormatter()
        record = logging.LogRecord(
            "t",
            logging.INFO,
            "m",
            1,
            "key sk-abc123def456ghi789jkl and bearer tok-xyz in text",
            None,
            None,
        )
        out = fmt.format(record)
        self.assertIn("REDACTED", out)
        self.assertNotIn("sk-abc123def456ghi789jkl", out)
        self.assertNotIn("tok-xyz", out)

    def test_json_formatter_parses_as_json(self):
        import json
        import logging

        from orbit.orbit.logging_config import JSONFormatter

        record = logging.LogRecord(
            "t", logging.WARNING, "m", 1, "hello world", None, None
        )
        data = json.loads(JSONFormatter().format(record))
        self.assertEqual(data["level"], "WARNING")
        self.assertEqual(data["message"], "hello world")

    def test_setup_logging_env_toggle(self):
        import logging
        import os

        from orbit.orbit.logging_config import setup_logging

        os.environ["ORBIT_JSON_LOGS"] = "1"
        try:
            setup_logging()
        finally:
            os.environ.pop("ORBIT_JSON_LOGS", None)
        root_handlers = logging.getLogger().handlers
        self.assertTrue(len(root_handlers) > 0)


class TestConfigShimParity(unittest.TestCase):
    def test_outer_reexports_inner_names(self):
        import orbit.config as outer
        import orbit.orbit.config as inner

        inner_names = {n for n in dir(inner) if not n.startswith("_")}
        for name in inner_names:
            if isinstance(
                getattr(inner, name),
                (int, float, str, bool, type(None), tuple, list, dict),
            ):
                self.assertTrue(hasattr(outer, name), f"outer missing {name}")

    def test_outer_memory_file_resolves(self):
        from pathlib import Path

        from orbit.orbit.memory import MEMORY_FILE

        self.assertTrue(str(MEMORY_FILE).endswith("orbit_memory.json"))
        # Absolute on ANY drive (was hardcoded "D:" — stale, repo moved to C:)
        self.assertTrue(Path(str(MEMORY_FILE)).is_absolute())


if __name__ == "__main__":
    unittest.main()
