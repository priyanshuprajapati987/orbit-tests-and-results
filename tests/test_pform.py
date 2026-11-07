"""Unit tests for orbit/orbit/core/pform.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

import orbit.core.pform as pform


class TestPform(unittest.TestCase):
    def setUp(self):
        pform.set_platform("desktop")

    def tearDown(self):
        pform.set_platform("desktop")

    def test_constants(self):
        self.assertEqual(pform.PLATFORM_DESKTOP, "desktop")
        self.assertEqual(pform.PLATFORM_SERVER, "server")
        self.assertEqual(pform.PLATFORM_MOBILE, "mobile")

    def test_get_platform_default(self):
        self.assertEqual(pform.get_platform(), "desktop")

    def test_set_platform_lowercases(self):
        pform.set_platform("SERVER")
        self.assertEqual(pform.get_platform(), "server")

    def test_set_platform_stringifies(self):
        pform.set_platform(123)
        self.assertEqual(pform.get_platform(), "123")

    def test_is_desktop_true(self):
        pform.set_platform("desktop")
        self.assertTrue(pform.is_desktop())

    def test_is_desktop_false(self):
        pform.set_platform("server")
        self.assertFalse(pform.is_desktop())


if __name__ == "__main__":
    unittest.main()
