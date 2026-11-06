"""Unit tests for orbit/orbit/core/safe_http.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.safe_http import assert_safe, safe_urlopen, safe_requests_get, safe_requests_post, MAX_REDIRECTS


class TestSafeHttp(unittest.TestCase):
    def test_assert_safe_blocks_localhost(self):
        import urllib.error
        with self.assertRaises(urllib.error.URLError):
            assert_safe("http://localhost/x")

    def test_assert_safe_blocks_private_ip(self):
        import urllib.error
        with self.assertRaises(urllib.error.URLError):
            assert_safe("http://192.168.1.1/x")

    def test_safe_urlopen_blocks_localhost(self):
        import urllib.error
        with self.assertRaises(urllib.error.URLError):
            safe_urlopen("http://localhost/x")

    def test_safe_requests_get_blocks_localhost(self):
        import urllib.error
        with self.assertRaises(urllib.error.URLError):
            safe_requests_get("http://localhost/x")

    def test_safe_requests_post_blocks_localhost(self):
        import urllib.error
        with self.assertRaises(urllib.error.URLError):
            safe_requests_post("http://localhost/x")

    def test_max_redirects(self):
        self.assertEqual(MAX_REDIRECTS, 4)


if __name__ == "__main__":
    unittest.main()
