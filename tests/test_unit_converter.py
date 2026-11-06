"""Unit tests for orbit/orbit/core/unit_converter.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.unit_converter import UnitConverter, get_converter, CONVERSIONS


class TestUnitConverter(unittest.TestCase):
    def setUp(self):
        self.uc = UnitConverter()

    def test_length(self):
        r = self.uc.convert(5, "km", "m")
        self.assertEqual(r["value"], 5000.0)
        self.assertEqual(r["category"], "length")

    def test_mass(self):
        r = self.uc.convert(1, "kg", "g")
        self.assertEqual(r["value"], 1000.0)

    def test_temperature_c_to_f(self):
        r = self.uc.convert(0, "C", "F", category="temperature")
        self.assertEqual(r["value"], 32.0)

    def test_temperature_f_to_c(self):
        r = self.uc.convert(32, "F", "C", category="temperature")
        self.assertEqual(r["value"], 0.0)

    def test_data(self):
        r = self.uc.convert(1, "KB", "B")
        self.assertEqual(r["value"], 1024.0)

    def test_time(self):
        r = self.uc.convert(1, "hour", "min")
        self.assertEqual(r["value"], 60.0)

    def test_speed(self):
        r = self.uc.convert(1, "km/h", "m/s")
        self.assertAlmostEqual(r["value"], 0.277778, places=5)

    def test_unknown_units(self):
        r = self.uc.convert(1, "foo", "bar")
        self.assertIn("error", r)

    def test_list_categories(self):
        r = self.uc.list_categories()
        self.assertIsInstance(r, dict)
        self.assertIn("length", r)

    def test_singleton(self):
        a = get_converter()
        b = get_converter()
        self.assertIs(a, b)


class TestConstants(unittest.TestCase):
    def test_conversions(self):
        self.assertIn("length", CONVERSIONS)
        self.assertIn("m", CONVERSIONS["length"])


if __name__ == "__main__":
    unittest.main()
