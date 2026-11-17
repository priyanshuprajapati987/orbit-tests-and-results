"""Unit tests for orbit/orbit/core/color_picker.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

import orbit.core.color_picker as cp_mod
from orbit.core.color_picker import ColorPicker, get_color_picker, _get_pyautogui


class TestRgbToHsl(unittest.TestCase):
    def setUp(self):
        self.cp = ColorPicker()

    def test_black(self):
        r = self.cp._rgb_to_hsl(0, 0, 0)
        self.assertEqual(r, {"h": 0, "s": 0, "l": 0})

    def test_white(self):
        r = self.cp._rgb_to_hsl(255, 255, 255)
        self.assertEqual(r["l"], 100)
        self.assertEqual(r["s"], 0)

    def test_red(self):
        r = self.cp._rgb_to_hsl(255, 0, 0)
        self.assertEqual(r["h"], 0)
        self.assertEqual(r["s"], 100)
        self.assertEqual(r["l"], 50)

    def test_green(self):
        r = self.cp._rgb_to_hsl(0, 255, 0)
        self.assertEqual(r["h"], 120)
        self.assertEqual(r["s"], 100)
        self.assertEqual(r["l"], 50)

    def test_blue(self):
        r = self.cp._rgb_to_hsl(0, 0, 255)
        self.assertEqual(r["h"], 240)
        self.assertEqual(r["s"], 100)
        self.assertEqual(r["l"], 50)

    def test_gray(self):
        r = self.cp._rgb_to_hsl(128, 128, 128)
        self.assertEqual(r["s"], 0)
        self.assertEqual(r["l"], 50)

    def test_yellow(self):
        r = self.cp._rgb_to_hsl(255, 255, 0)
        self.assertEqual(r["h"], 60)
        self.assertEqual(r["l"], 50)

    def test_cyan(self):
        r = self.cp._rgb_to_hsl(0, 255, 255)
        self.assertEqual(r["h"], 180)

    def test_magenta(self):
        r = self.cp._rgb_to_hsl(255, 0, 255)
        self.assertEqual(r["h"], 300)

    def test_light_dominant(self):
        # l > 0.5 branch (s = d / (2 - max - min))
        r = self.cp._rgb_to_hsl(255, 128, 128)
        self.assertIn("h", r)
        self.assertIn("s", r)
        self.assertIn("l", r)

    def test_dark_dominant(self):
        # l <= 0.5 branch (s = d / (max + min))
        r = self.cp._rgb_to_hsl(128, 0, 0)
        self.assertIn("h", r)
        self.assertEqual(r["l"], 25)

    def test_keys_are_ints(self):
        r = self.cp._rgb_to_hsl(100, 150, 200)
        for v in r.values():
            self.assertIsInstance(v, int)


class TestHexToRgb(unittest.TestCase):
    def setUp(self):
        self.cp = ColorPicker()

    def test_with_hash(self):
        self.assertEqual(self.cp.hex_to_rgb("#ff0000"), {"r": 255, "g": 0, "b": 0})

    def test_without_hash(self):
        self.assertEqual(self.cp.hex_to_rgb("00ff00"), {"r": 0, "g": 255, "b": 0})

    def test_uppercase(self):
        self.assertEqual(self.cp.hex_to_rgb("#FF0000"), {"r": 255, "g": 0, "b": 0})

    def test_black(self):
        self.assertEqual(self.cp.hex_to_rgb("#000000"), {"r": 0, "g": 0, "b": 0})

    def test_white(self):
        self.assertEqual(self.cp.hex_to_rgb("#ffffff"), {"r": 255, "g": 255, "b": 255})

    def test_invalid_hex(self):
        r = self.cp.hex_to_rgb("#zzzzzz")
        self.assertEqual(r["error"], "Invalid hex color")

    def test_too_short(self):
        r = self.cp.hex_to_rgb("#ff")
        self.assertEqual(r["error"], "Invalid hex color")

    def test_empty(self):
        r = self.cp.hex_to_rgb("")
        self.assertEqual(r["error"], "Invalid hex color")

    def test_none(self):
        r = self.cp.hex_to_rgb(None)
        self.assertEqual(r["error"], "Invalid hex color")


class TestRgbToHex(unittest.TestCase):
    def setUp(self):
        self.cp = ColorPicker()

    def test_red(self):
        self.assertEqual(self.cp.rgb_to_hex(255, 0, 0), "#ff0000")

    def test_green(self):
        self.assertEqual(self.cp.rgb_to_hex(0, 255, 0), "#00ff00")

    def test_blue(self):
        self.assertEqual(self.cp.rgb_to_hex(0, 0, 255), "#0000ff")

    def test_black(self):
        self.assertEqual(self.cp.rgb_to_hex(0, 0, 0), "#000000")

    def test_white(self):
        self.assertEqual(self.cp.rgb_to_hex(255, 255, 255), "#ffffff")

    def test_single_digit_padding(self):
        self.assertEqual(self.cp.rgb_to_hex(1, 2, 3), "#010203")

    def test_roundtrip(self):
        for rgb in [(0, 0, 0), (255, 255, 255), (18, 52, 86), (255, 0, 128)]:
            h = self.cp.rgb_to_hex(*rgb)
            self.assertEqual(tuple(self.cp.hex_to_rgb(h)[k] for k in ("r", "g", "b")), rgb)


class TestGetPyautogui(unittest.TestCase):
    def test_returns_something_or_none(self):
        # pyautogui may or may not be installed; just ensure no crash
        r = _get_pyautogui()
        self.assertTrue(r is None or hasattr(r, "screenshot"))

    @patch.dict(sys.modules, {"pyautogui": None})
    def test_import_failure_returns_none(self):
        # force re-detection
        old_flag = cp_mod.HAS_PYAUTOGUI
        old_mod = cp_mod._pyautogui
        cp_mod.HAS_PYAUTOGUI = None
        cp_mod._pyautogui = None
        try:
            r = _get_pyautogui()
            self.assertIsNone(r)
            self.assertFalse(cp_mod.HAS_PYAUTOGUI)
        finally:
            cp_mod.HAS_PYAUTOGUI = old_flag
            cp_mod._pyautogui = old_mod


class TestGetPixelColor(unittest.TestCase):
    def setUp(self):
        self.cp = ColorPicker()

    def test_no_pyautogui_returns_error(self):
        with patch("orbit.core.color_picker._get_pyautogui", return_value=None):
            r = self.cp.get_pixel_color(10, 20)
        self.assertEqual(r["error"], "pyautogui not installed")

    def test_success(self):
        pag = MagicMock()
        img = MagicMock()
        img.getpixel.return_value = (255, 128, 64)
        pag.screenshot.return_value = img
        with patch("orbit.core.color_picker._get_pyautogui", return_value=pag):
            r = self.cp.get_pixel_color(10, 20)
        self.assertEqual(r["rgb"], {"r": 255, "g": 128, "b": 64})
        self.assertEqual(r["hex"], "#ff8040")
        self.assertEqual(r["position"], {"x": 10, "y": 20})
        self.assertIn("hsl", r)
        pag.screenshot.assert_called_once_with(region=(10, 20, 1, 1))

    def test_screenshot_exception(self):
        pag = MagicMock()
        pag.screenshot.side_effect = RuntimeError("screen locked")
        with patch("orbit.core.color_picker._get_pyautogui", return_value=pag):
            r = self.cp.get_pixel_color(1, 1)
        self.assertEqual(r["error"], "screen locked")


class TestGetMouseColor(unittest.TestCase):
    def setUp(self):
        self.cp = ColorPicker()

    def test_no_pyautogui_returns_error(self):
        with patch("orbit.core.color_picker._get_pyautogui", return_value=None):
            r = self.cp.get_mouse_color()
        self.assertEqual(r["error"], "pyautogui not installed")

    def test_success(self):
        pag = MagicMock()
        pag.position.return_value = MagicMock(x=5, y=7)
        img = MagicMock()
        img.getpixel.return_value = (1, 2, 3)
        pag.screenshot.return_value = img
        with patch("orbit.core.color_picker._get_pyautogui", return_value=pag):
            r = self.cp.get_mouse_color()
        self.assertEqual(r["rgb"], {"r": 1, "g": 2, "b": 3})
        self.assertEqual(r["position"], {"x": 5, "y": 7})
        pag.screenshot.assert_called_once_with(region=(5, 7, 1, 1))


class TestGetColorPicker(unittest.TestCase):
    def test_singleton(self):
        self.assertIs(get_color_picker(), get_color_picker())

    def test_type(self):
        self.assertIsInstance(get_color_picker(), ColorPicker)


if __name__ == "__main__":
    unittest.main()
