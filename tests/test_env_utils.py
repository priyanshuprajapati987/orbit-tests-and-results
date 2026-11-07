"""Unit tests for orbit/orbit/core/env_utils.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.env_utils import int_env, float_env


class TestIntEnv(unittest.TestCase):
    def setUp(self):
        self.key = "ORBIT_TEST_INT_ENV"

    def tearDown(self):
        os.environ.pop(self.key, None)

    def test_missing_returns_default(self):
        os.environ.pop(self.key, None)
        self.assertEqual(int_env(self.key, 42), 42)

    def test_empty_returns_default(self):
        os.environ[self.key] = ""
        self.assertEqual(int_env(self.key, 42), 42)

    def test_whitespace_returns_default(self):
        os.environ[self.key] = "   "
        self.assertEqual(int_env(self.key, 42), 42)

    def test_valid_int(self):
        os.environ[self.key] = "7"
        self.assertEqual(int_env(self.key, 42), 7)

    def test_valid_int_with_spaces(self):
        os.environ[self.key] = "  7  "
        self.assertEqual(int_env(self.key, 42), 7)

    def test_bad_value_returns_default(self):
        os.environ[self.key] = "abc"
        self.assertEqual(int_env(self.key, 42), 42)

    def test_lo_clamp(self):
        os.environ[self.key] = "1"
        self.assertEqual(int_env(self.key, 42, lo=5), 5)

    def test_hi_clamp(self):
        os.environ[self.key] = "100"
        self.assertEqual(int_env(self.key, 42, hi=10), 10)

    def test_both_clamp(self):
        os.environ[self.key] = "5"
        self.assertEqual(int_env(self.key, 42, lo=10, hi=20), 10)


class TestFloatEnv(unittest.TestCase):
    def setUp(self):
        self.key = "ORBIT_TEST_FLOAT_ENV"

    def tearDown(self):
        os.environ.pop(self.key, None)

    def test_missing_returns_default(self):
        os.environ.pop(self.key, None)
        self.assertEqual(float_env(self.key, 1.5), 1.5)

    def test_empty_returns_default(self):
        os.environ[self.key] = ""
        self.assertEqual(float_env(self.key, 1.5), 1.5)

    def test_valid_float(self):
        os.environ[self.key] = "2.5"
        self.assertEqual(float_env(self.key, 1.5), 2.5)

    def test_bad_value_returns_default(self):
        os.environ[self.key] = "nope"
        self.assertEqual(float_env(self.key, 1.5), 1.5)

    def test_lo_clamp(self):
        os.environ[self.key] = "0.1"
        self.assertEqual(float_env(self.key, 1.5, lo=1.0), 1.0)

    def test_hi_clamp(self):
        os.environ[self.key] = "10.0"
        self.assertEqual(float_env(self.key, 1.5, hi=5.0), 5.0)

    def test_int_string_accepted(self):
        os.environ[self.key] = "3"
        self.assertEqual(float_env(self.key, 1.5), 3.0)


if __name__ == "__main__":
    unittest.main()
