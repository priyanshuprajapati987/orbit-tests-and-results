"""Unit tests for orbit/orbit/screen_sharing.py."""

import base64
import io
import os
import sys
import time
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

import orbit.screen_sharing as ss


class TestScreenSharing(unittest.TestCase):
    def setUp(self):
        ss.stop()
        ss.set_on_frame(None)
        # reset globals
        ss._mss = None
        ss._thread = None

    def tearDown(self):
        ss.stop()
        ss.set_on_frame(None)
        ss._mss = None
        time.sleep(0.05)

    def test_set_on_frame(self):
        cb = lambda d: None
        ss.set_on_frame(cb)
        self.assertIs(ss._on_frame, cb)

    def test_is_active_initially_false(self):
        self.assertFalse(ss.is_active())

    def test_start(self):
        self.assertTrue(ss.start(quality=80, fps=100))
        self.assertTrue(ss.is_active())
        self.assertEqual(ss._quality, 80)
        self.assertEqual(ss._fps, 100)

    def test_start_already_active(self):
        ss.start(fps=100)
        self.assertFalse(ss.start(fps=100))

    def test_stop(self):
        ss.start(fps=100)
        self.assertTrue(ss.stop())
        self.assertFalse(ss.is_active())

    def test_stop_when_inactive(self):
        self.assertTrue(ss.stop())

    def test_get_mss_import_error(self):
        with patch.dict(sys.modules, {"mss": None}):
            ss._mss = None
            with self.assertRaises(ModuleNotFoundError):
                ss._get_mss()

    def test_get_mss_success(self):
        mss_mod = MagicMock()
        sct = MagicMock()
        mss_mod.mss.return_value = sct
        with patch.dict(sys.modules, {"mss": mss_mod}):
            ss._mss = None
            r = ss._get_mss()
        self.assertIs(r, sct)

    def test_capture_frame_no_mss(self):
        with patch.dict(sys.modules, {"mss": None, "PIL": None, "PIL.Image": None}):
            ss._mss = None
            r = ss._capture_frame()
        self.assertIsNone(r)

    def test_capture_frame_mss_success(self):
        mss_mod = MagicMock()
        sct = MagicMock()
        monitor = {"width": 2, "height": 2}
        sct.monitors = [None, monitor]
        screenshot = MagicMock()
        screenshot.size = (2, 2)
        screenshot.rgb = b"\x00" * 12
        sct.grab.return_value = screenshot
        mss_mod.mss.return_value = sct

        PIL = MagicMock()
        img = MagicMock()
        buf = io.BytesIO()
        def save_side_effect(buffer, format=None, quality=None, optimize=None):
            buffer.write(b"JPEGDATA")
        img.save.side_effect = save_side_effect
        PIL.Image.frombytes.return_value = img

        with patch.dict(sys.modules, {"mss": mss_mod, "PIL": PIL, "PIL.Image": PIL.Image}):
            ss._mss = None
            r = ss._capture_frame()
        self.assertIsNotNone(r)
        # base64 of JPEGDATA
        self.assertEqual(r, base64.b64encode(b"JPEGDATA").decode())

    def test_capture_frame_pyautogui_fallback(self):
        # mss fails (no mss module), pyautogui succeeds
        PIL = MagicMock()
        img = MagicMock()
        def save_side_effect(buffer, format=None, quality=None, optimize=None):
            buffer.write(b"FALLBACK")
        img.save.side_effect = save_side_effect
        PIL.Image = MagicMock()
        pyautogui_mod = MagicMock()
        pyautogui_mod.screenshot.return_value = img
        with patch.dict(sys.modules, {"mss": None, "PIL": PIL, "PIL.Image": PIL.Image, "pyautogui": pyautogui_mod}):
            ss._mss = None
            # _get_mss returns None (mss unavailable) → first try fails → fallback
            r = ss._capture_frame()
        self.assertEqual(r, base64.b64encode(b"FALLBACK").decode())

    def test_capture_frame_all_fail(self):
        with patch.dict(sys.modules, {"mss": None, "PIL": None, "PIL.Image": None, "pyautogui": None}):
            ss._mss = None
            r = ss._capture_frame()
        self.assertIsNone(r)

    def test_capture_loop_calls_on_frame(self):
        calls = []
        ss.set_on_frame(calls.append)
        ss.start(quality=50, fps=100)
        # wait for at least one frame callback
        for _ in range(50):
            if calls:
                break
            time.sleep(0.02)
        ss.stop()
        self.assertGreater(len(calls), 0)
        self.assertEqual(calls[0]["cmd"], "screen_frame")
        self.assertEqual(calls[0]["args"]["quality"], 50)
        self.assertIn("image", calls[0]["args"])
        self.assertIn("ts", calls[0]["args"])

    def test_capture_loop_no_on_frame(self):
        ss.set_on_frame(None)
        ss.start(fps=100)
        time.sleep(0.05)
        ss.stop()
        # no crash
        self.assertFalse(ss.is_active())


if __name__ == "__main__":
    unittest.main()
