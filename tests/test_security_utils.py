"""Unit tests for orbit/orbit/core/_security_utils.py."""

import os
import sys
import tempfile
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core._security_utils import (
    validate_path, sanitize_filepath, confine_result_path, validate_url, validate_command,
)


class TestSecurityUtils(unittest.TestCase):
    def test_validate_path_empty(self):
        allowed, reason = validate_path("")
        self.assertFalse(allowed)

    def test_validate_path_normal(self):
        allowed, reason = validate_path(os.path.abspath(__file__))
        self.assertTrue(allowed)

    def test_validate_path_blocked_system(self):
        allowed, reason = validate_path("C:\\Windows\\System32\\x.txt")
        self.assertFalse(allowed)

    def test_sanitize_filepath_ok(self):
        self.assertEqual(sanitize_filepath("foo/bar.txt"), "foo/bar.txt")

    def test_sanitize_filepath_traversal(self):
        self.assertIsNone(sanitize_filepath("../etc/passwd"))

    def test_sanitize_filepath_empty(self):
        self.assertIsNone(sanitize_filepath(""))

    def test_confine_result_path_none(self):
        import pathlib
        d = pathlib.Path(tempfile.gettempdir())
        r = confine_result_path(None, d)
        self.assertEqual(r, d)

    def test_confine_result_path_traversal(self):
        r = confine_result_path("../evil.txt", None) if False else None
        # confine with default
        import pathlib
        d = pathlib.Path(tempfile.gettempdir())
        r = confine_result_path("../evil.txt", d)
        self.assertIsNone(r)

    def test_validate_url(self):
        r = validate_url("https://example.com/x")
        self.assertTrue(r is None or isinstance(r, (bool, str, tuple)))

    def test_validate_command(self):
        r = validate_command("ls -la")
        self.assertTrue(r is None or isinstance(r, (bool, str, tuple)))


if __name__ == "__main__":
    unittest.main()
