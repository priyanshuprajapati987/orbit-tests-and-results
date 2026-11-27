"""Deep tests for orbit/orbit/core/screen_control.py (Loop 16/1)."""

import sys
import time
import types
import unittest
from pathlib import Path
from unittest import mock

from orbit.orbit.core import screen_control as sc


def _make_pyautogui():
    m = mock.MagicMock()
    m.click.return_value = None
    m.doubleClick.return_value = None
    m.typewrite.return_value = None
    m.hotkey.return_value = None
    m.scroll.return_value = None
    m.moveTo.return_value = None
    m.drag.return_value = None
    shot = mock.MagicMock()
    shot.size = (1920, 1080)
    shot.save = mock.MagicMock()
    m.screenshot.return_value = shot
    m.size.return_value = mock.MagicMock(width=1920, height=1080)
    m.position.return_value = mock.MagicMock(x=100, y=200)
    return m


class UnavailableTests(unittest.TestCase):
    """pyautogui not installed."""

    def setUp(self):
        self._saved = sys.modules.get("pyautogui", _MISSING2)
        sys.modules["pyautogui"] = None  # force ImportError
        import importlib
        importlib.reload(sc)
        self.assertTrue(sc.HAS_PYAUTOGUI is False)
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is _MISSING2:
            sys.modules.pop("pyautogui", None)
        else:
            sys.modules["pyautogui"] = self._saved
        import importlib
        importlib.reload(sc)

    def test_is_available_false(self):
        self.assertFalse(sc.ScreenController().is_available())

    def test_click_unavailable(self):
        self.assertEqual(sc.ScreenController().click(1, 2),
                         {"error": "pyautogui not installed"})

    def test_double_click_unavailable(self):
        self.assertEqual(sc.ScreenController().double_click(),
                         {"error": "pyautogui not installed"})

    def test_type_text_unavailable(self):
        self.assertEqual(sc.ScreenController().type_text("hi"),
                         {"error": "pyautogui not installed"})

    def test_hotkey_unavailable(self):
        self.assertEqual(sc.ScreenController().hotkey("ctrl", "c"),
                         {"error": "pyautogui not installed"})

    def test_scroll_unavailable(self):
        self.assertEqual(sc.ScreenController().scroll(),
                         {"error": "pyautogui not installed"})

    def test_move_unavailable(self):
        self.assertEqual(sc.ScreenController().move(1, 2),
                         {"error": "pyautogui not installed"})

    def test_drag_unavailable(self):
        self.assertEqual(sc.ScreenController().drag(1, 2),
                         {"error": "pyautogui not installed"})

    def test_screenshot_unavailable(self):
        self.assertEqual(sc.ScreenController().screenshot(),
                         {"error": "pyautogui not installed"})

    def test_get_screen_size_unavailable(self):
        self.assertEqual(sc.ScreenController().get_screen_size(),
                         {"error": "pyautogui not installed"})

    def test_get_mouse_position_unavailable(self):
        self.assertEqual(sc.ScreenController().get_mouse_position(),
                         {"error": "pyautogui not installed"})

    def test_right_click_unavailable(self):
        self.assertEqual(sc.ScreenController().right_click(1, 2),
                         {"error": "pyautogui not installed"})


class AvailableTests(unittest.TestCase):
    """pyautogui available (mocked)."""

    def setUp(self):
        self.pg = _make_pyautogui()
        sys.modules["pyautogui"] = self.pg
        import importlib
        importlib.reload(sc)
        self.assertTrue(sc.HAS_PYAUTOGUI)
        self.ctrl = sc.ScreenController()
        self.addCleanup(self._restore)

    def _restore(self):
        sys.modules.pop("pyautogui", None)
        import importlib
        importlib.reload(sc)

    def test_is_available(self):
        self.assertTrue(self.ctrl.is_available())

    def test_click_with_coords(self):
        r = self.ctrl.click(10, 20, button="right")
        self.pg.click.assert_called_once_with(10, 20, button="right")
        self.assertEqual(r, {"status": "clicked", "x": 10, "y": 20, "button": "right"})
        self.assertEqual(self.ctrl._action_count, 1)

    def test_click_without_coords(self):
        r = self.ctrl.click()
        self.pg.click.assert_called_once_with(button="left")
        self.assertEqual(r["status"], "clicked")

    def test_click_exception(self):
        self.pg.click.side_effect = RuntimeError("boom")
        r = self.ctrl.click(1, 2)
        self.assertEqual(r, {"error": "boom"})

    def test_double_click_with_coords(self):
        r = self.ctrl.double_click(5, 6)
        self.pg.doubleClick.assert_called_once_with(5, 6)
        self.assertEqual(r, {"status": "double_clicked", "x": 5, "y": 6})

    def test_double_click_without_coords(self):
        r = self.ctrl.double_click()
        self.pg.doubleClick.assert_called_once_with()

    def test_double_click_exception(self):
        self.pg.doubleClick.side_effect = RuntimeError("boom")
        self.assertEqual(self.ctrl.double_click(1, 2), {"error": "boom"})

    def test_right_click_delegates(self):
        with mock.patch.object(self.ctrl, "click", return_value={"ok": True}) as c:
            r = self.ctrl.right_click(1, 2)
        c.assert_called_once_with(1, 2, button="right")
        self.assertEqual(r, {"ok": True})

    def test_type_text(self):
        r = self.ctrl.type_text("hello", interval=0.05)
        self.pg.typewrite.assert_called_once_with("hello", interval=0.05)
        self.assertEqual(r, {"status": "typed", "length": 5})

    def test_type_text_exception(self):
        self.pg.typewrite.side_effect = RuntimeError("boom")
        self.assertEqual(self.ctrl.type_text("hi"), {"error": "boom"})

    def test_hotkey(self):
        r = self.ctrl.hotkey("ctrl", "c")
        self.pg.hotkey.assert_called_once_with("ctrl", "c")
        self.assertEqual(r, {"status": "hotkey", "keys": ["ctrl", "c"]})

    def test_hotkey_exception(self):
        self.pg.hotkey.side_effect = RuntimeError("boom")
        self.assertEqual(self.ctrl.hotkey("a"), {"error": "boom"})

    def test_scroll(self):
        r = self.ctrl.scroll(5)
        self.pg.scroll.assert_called_once_with(5)
        self.assertEqual(r, {"status": "scrolled", "clicks": 5})

    def test_scroll_exception(self):
        self.pg.scroll.side_effect = RuntimeError("boom")
        self.assertEqual(self.ctrl.scroll(), {"error": "boom"})

    def test_move(self):
        r = self.ctrl.move(10, 20)
        self.pg.moveTo.assert_called_once_with(10, 20)
        self.assertEqual(r, {"status": "moved", "x": 10, "y": 20})

    def test_move_exception(self):
        self.pg.moveTo.side_effect = RuntimeError("boom")
        self.assertEqual(self.ctrl.move(1, 2), {"error": "boom"})

    def test_drag(self):
        r = self.ctrl.drag(10, 20, duration=0.3)
        self.pg.drag.assert_called_once_with(10, 20, duration=0.3)
        self.assertEqual(r, {"status": "dragged", "x": 10, "y": 20})

    def test_drag_exception(self):
        self.pg.drag.side_effect = RuntimeError("boom")
        self.assertEqual(self.ctrl.drag(1, 2), {"error": "boom"})

    def test_screenshot(self):
        import tempfile, os
        d = tempfile.mkdtemp()
        shot_dir = Path(d) / "screenshots"
        shot_dir.mkdir(parents=True, exist_ok=True)
        img_path = shot_dir / "screen_12345.png"
        with mock.patch("orbit.orbit.core.runtime_paths.orbit_data_dir",
                        return_value=Path(d)), \
                mock.patch("time.time", return_value=12345):
            r = self.ctrl.screenshot()
        self.assertEqual(r["status"], "screenshot")
        self.assertEqual(r["size"], (1920, 1080))
        self.assertIn("screen_12345.png", r["path"])

    def test_screenshot_exception(self):
        self.pg.screenshot.side_effect = RuntimeError("boom")
        self.assertEqual(self.ctrl.screenshot(), {"error": "boom"})

    def test_get_screen_size(self):
        r = self.ctrl.get_screen_size()
        self.assertEqual(r, {"width": 1920, "height": 1080})

    def test_get_mouse_position(self):
        r = self.ctrl.get_mouse_position()
        self.assertEqual(r, {"x": 100, "y": 200})

    def test_get_status(self):
        self.ctrl._record("click", "1,2")
        s = self.ctrl.get_status()
        self.assertTrue(s["available"])
        self.assertEqual(s["action_count"], 1)
        self.assertEqual(s["last_action"]["action"], "click")

    def test_get_status_no_action(self):
        s = self.ctrl.get_status()
        self.assertIsNone(s["last_action"])
        self.assertEqual(s["action_count"], 0)

    def test_record(self):
        self.ctrl._record("move", "1,2")
        self.assertEqual(self.ctrl._last_action["action"], "move")
        self.assertEqual(self.ctrl._last_action["detail"], "1,2")
        self.assertIn("time", self.ctrl._last_action)

    def test_singleton(self):
        sc._controller = None
        a = sc.get_screen_controller()
        b = sc.get_screen_controller()
        self.assertIs(a, b)
        sc._controller = None

    def test_singleton_creates(self):
        sc._controller = None
        a = sc.get_screen_controller()
        self.assertIsInstance(a, sc.ScreenController)
        sc._controller = None


_MISSING2 = object()


if __name__ == "__main__":
    unittest.main()
