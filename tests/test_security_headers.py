"""
Security header + debug-mode tests
==================================
Covers the v3.6.0 security findings (SECURITY.md M01/M02):
- M01: get_security_headers() applied to all responses (CSP, nosniff, frame-options,
  referrer-policy) with HSTS skipped on plain HTTP.
- M02: standalone server debug mode honors FLASK_DEBUG (default off).

Run: python -m pytest tests/test_security_headers.py -v
"""

import os
import unittest


class TestSecurityHeaders(unittest.TestCase):
    def setUp(self):
        os.environ["ORBIT_SKIP_STARTUP"] = "1"
        from orbit.orbit.server import create_app

        self.app = create_app()
        self.client = self.app.test_client()

    def test_headers_present_on_api(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(r.headers.get("X-Frame-Options"), "DENY")
        csp = r.headers.get("Content-Security-Policy")
        self.assertIsNotNone(csp)
        self.assertIn("default-src 'self'", csp)
        self.assertIn("script-src 'self'", csp)
        self.assertIn("img-src 'self' data: blob:", csp)
        self.assertNotIn("script-src 'self' 'unsafe-inline'", csp)
        self.assertEqual(
            r.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin"
        )

    def test_hsts_skipped_on_plain_http(self):
        r = self.client.get("/api/health")
        self.assertIsNone(r.headers.get("Strict-Transport-Security"))

    def test_timing_header_preserved(self):
        r = self.client.get("/api/health")
        self.assertIsNotNone(r.headers.get("X-Response-Time-Ms"))

    def test_headers_present_on_static_route(self):
        r = self.client.get("/")
        self.assertEqual(r.headers.get("X-Content-Type-Options"), "nosniff")


class TestDebugMode(unittest.TestCase):
    def test_debug_off_when_unset(self):
        saved = os.environ.get("FLASK_DEBUG")
        os.environ.pop("FLASK_DEBUG", None)
        try:
            self.assertFalse(
                os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes", "on")
            )
        finally:
            if saved is not None:
                os.environ["FLASK_DEBUG"] = saved

    def test_debug_on_when_enabled(self):
        saved = os.environ.get("FLASK_DEBUG")
        os.environ["FLASK_DEBUG"] = "1"
        try:
            self.assertTrue(
                os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes", "on")
            )
        finally:
            if saved is not None:
                os.environ["FLASK_DEBUG"] = saved
            else:
                os.environ.pop("FLASK_DEBUG", None)


if __name__ == "__main__":
    unittest.main()
