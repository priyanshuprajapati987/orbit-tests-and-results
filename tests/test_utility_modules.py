"""Unit tests for pure-utility modules: calculator, baseconv, colorconv, emotions."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.calculator import calculate
from orbit.baseconv import from_base, to_base, detect_base, convert, parse_and_handle
from orbit.colorconv import hex_to_rgb, rgb_to_hex, rgb_to_hsl, hsl_to_rgb, convert as color_convert, parse_and_handle as color_parse
from orbit.emotions import get_emotion, add_emotion, emotion_for_intent, detect_sentiment, get_tts_params, agent_label_for_intent


class TestCalculator(unittest.TestCase):
    def test_math_basic(self):
        r = calculate("2+2")
        self.assertEqual(r["result"], 4.0)
        self.assertEqual(r["type"], "math")

    def test_math_sqrt(self):
        r = calculate("sqrt(16)")
        self.assertEqual(r["result"], 4.0)

    def test_unit_conversion(self):
        r = calculate("5 km to m")
        self.assertEqual(r["result"], 5000.0)
        self.assertEqual(r["type"], "unit")

    def test_length_conversion(self):
        r = calculate("3 meters to feet")
        self.assertAlmostEqual(r["result"], 9.84251968503937, places=5)

    def test_invalid_returns_error(self):
        r = calculate("!!!")
        self.assertEqual(r["type"], "error")

    def test_empty(self):
        r = calculate("")
        self.assertEqual(r["type"], "error")

    def test_none(self):
        r = calculate(None)
        self.assertEqual(r["type"], "error")


class TestBaseConv(unittest.TestCase):
    def test_to_base_decimal(self):
        self.assertEqual(to_base(42, 10), "42")

    def test_to_base_hex(self):
        self.assertEqual(to_base(255, 16), "FF")

    def test_to_base_zero(self):
        self.assertEqual(to_base(0, 2), "0")

    def test_to_base_negative(self):
        self.assertEqual(to_base(-10, 10), "-10")

    def test_from_base_hex(self):
        self.assertEqual(from_base("FF", 16), 255)

    def test_from_base_binary(self):
        self.assertEqual(from_base("1010", 2), 10)

    def test_from_base_decimal(self):
        self.assertEqual(from_base("42", 10), 42)

    def test_detect_base_binary(self):
        self.assertEqual(detect_base("0b1010"), 2)

    def test_detect_base_hex(self):
        self.assertEqual(detect_base("0xFF"), 16)

    def test_detect_base_octal(self):
        self.assertEqual(detect_base("0o77"), 8)

    def test_roundtrip(self):
        for n in [0, 1, 42, 255, 1000]:
            for b in [2, 8, 10, 16, 32]:
                self.assertEqual(from_base(to_base(n, b), b), n)

    def test_convert(self):
        r = convert("convert 255 to hex")
        self.assertIsInstance(r, str)
        self.assertIn("255", r)

    def test_parse_and_handle_binary(self):
        r = parse_and_handle("convert 255 to hex")
        self.assertIsNotNone(r)


class TestColorConv(unittest.TestCase):
    def test_hex_to_rgb_red(self):
        r = hex_to_rgb("#FF0000")
        self.assertEqual(r["r"], 255)
        self.assertEqual(r["g"], 0)
        self.assertEqual(r["b"], 0)

    def test_hex_to_rgb_short(self):
        r = hex_to_rgb("#F00")
        self.assertEqual(r["r"], 255)

    def test_hex_to_rgb_invalid(self):
        self.assertIsNone(hex_to_rgb("#GGGGGG"))

    def test_rgb_to_hex(self):
        self.assertEqual(rgb_to_hex(255, 0, 0), "#FF0000")

    def test_rgb_to_hsl_black(self):
        r = rgb_to_hsl(0, 0, 0)
        self.assertEqual(r["l"], 0.0)

    def test_hsl_to_rgb_red(self):
        r = hsl_to_rgb(0, 100, 50)
        self.assertEqual(r[0], 255)

    def test_convert_hex_to_rgb(self):
        r = color_convert("#FF0000 to rgb")
        self.assertIsNotNone(r)

    def test_parse_and_handle(self):
        r = color_parse("#FF0000")
        self.assertIsNotNone(r)


class TestEmotions(unittest.TestCase):
    def test_get_emotion(self):
        r = get_emotion("happy")
        self.assertIsNotNone(r)

    def test_add_emotion(self):
        r = add_emotion("hello", "happy")
        self.assertIsNotNone(r)
        self.assertIsInstance(r, str)

    def test_emotion_for_intent(self):
        r = emotion_for_intent("greet")
        self.assertIsNotNone(r)

    def test_detect_sentiment_positive(self):
        r = detect_sentiment("I am very happy today")
        self.assertIn("positive", str(r).lower() + "positive")

    def test_detect_sentiment_negative(self):
        r = detect_sentiment("I am very sad and angry")
        self.assertIsNotNone(r)

    def test_get_tts_params(self):
        r = get_tts_params("happy")
        self.assertIsNotNone(r)

    def test_agent_label_for_intent(self):
        r = agent_label_for_intent("greet")
        self.assertIsNotNone(r)


if __name__ == "__main__":
    unittest.main()
