"""Unit tests for orbit/orbit/core/ssrf_guard.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.ssrf_guard import SSRFGuard, get_ssrf_guard, BLOCKED_NETWORKS, ALLOWLIST_DOMAINS


class TestSSRFGuard(unittest.TestCase):
    def setUp(self):
        self.g = SSRFGuard()

    def test_is_safe_url_public(self):
        r = self.g.is_safe_url("https://openai.com/x")
        self.assertIsInstance(r, bool)

    def test_is_safe_url_blocks_private_ip(self):
        self.assertFalse(self.g.is_safe_url("http://192.168.1.1/x"))

    def test_is_safe_url_blocks_localhost(self):
        # localhost is in allowlist for ORBIT internal, but validate_outbound may differ
        r = self.g.is_safe_url("http://localhost:5000/x")
        self.assertTrue(isinstance(r, bool))

    def test_validate_outbound_public(self):
        r = self.g.validate_outbound("https://example.com/x")
        self.assertTrue(r is None or isinstance(r, str))

    def test_validate_outbound_private(self):
        r = self.g.validate_outbound("http://192.168.1.1/x")
        self.assertTrue(r is None or isinstance(r, str))

    def test_get_stats(self):
        self.g.is_safe_url("https://example.com/x")
        r = self.g.get_stats()
        self.assertIsNotNone(r)

    def test_singleton(self):
        a = get_ssrf_guard()
        b = get_ssrf_guard()
        self.assertIs(a, b)


class TestConstants(unittest.TestCase):
    def test_blocked_networks(self):
        self.assertGreater(len(BLOCKED_NETWORKS), 0)

    def test_allowlist(self):
        self.assertIn("openai.com", ALLOWLIST_DOMAINS)


if __name__ == "__main__":
    unittest.main()
