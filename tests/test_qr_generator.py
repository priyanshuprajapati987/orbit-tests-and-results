"""Unit tests for orbit/orbit/core/qr_generator.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.qr_generator import QRGenerator, get_qr_generator


class TestQRGenerator(unittest.TestCase):
    def setUp(self):
        self.qr = QRGenerator()

    def test_instantiation(self):
        self.assertIsNotNone(self.qr)

    def test_generate_empty(self):
        r = self.qr.generate("")
        self.assertIn("error", r)

    def test_generate_too_long(self):
        r = self.qr.generate("a" * 5000)
        self.assertIn("error", r)

    def test_generate_valid(self):
        r = self.qr.generate("hello")
        self.assertEqual(r.get("status"), "generated")
        self.assertIn("image_base64", r)

    def test_generate_svg(self):
        r = self.qr.generate_svg("hello")
        self.assertEqual(r.get("status"), "generated")
        self.assertIn("svg", r)

    def test_generate_svg_empty(self):
        r = self.qr.generate_svg("")
        self.assertIn("error", r)

    def test_singleton(self):
        a = get_qr_generator()
        b = get_qr_generator()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
