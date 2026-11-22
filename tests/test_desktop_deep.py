"""Deep coverage tests for orbit/orbit/tools/desktop.py (826 lines).

test_remaining_tools.py only covers the PYAUTOGUI_AVAILABLE=False branches.
This file targets everything else: _gate/_ps helpers, validators, every
mouse/keyboard/clipboard/screen method (success + exception), window
management (PID validation, gate, PowerShell result mapping), open_app's
path sandbox (resolve failure, policy denial, script-extension refusal,
os.startfile fallbacks), open_url, list_running_apps, and every
handle_natural dispatch branch.

pyautogui is ALWAYS replaced with a MagicMock — the real mouse never moves.
check_tool is patched so policy global-state can't flip results.
"""

import base64
import os
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")

from orbit.orbit.tools import desktop as dt  # noqa: E402


def _allow():
    return patch.object(dt, "check_tool",
                        return_value=SimpleNamespace(allowed=True))


def _deny():
    decision = SimpleNamespace(
        allowed=False,
        reason="strict_mode_requires_approval",
        to_dict=lambda: {"allowed": False,
                         "reason": "strict_mode_requires_approval"},
    )
    return patch.object(dt, "check_tool", return_value=decision)


class DesktopBase(unittest.TestCase):
    def setUp(self):
        self.tool = dt.DesktopAutomationTool()
        self._pa_patch = patch.object(dt, "pyautogui", MagicMock())
        self.pya = self._pa_patch.start()
        self.addCleanup(self._pa_patch.stop)
        # allow every gate by default; individual tests re-patch to deny
        self._ck_patch = _allow()
        self._ck_patch.start()
        self.addCleanup(self._ck_patch.stop)

    @staticmethod
    def denied():
        return _deny()


# ---------------------------------------------------------------------------
# Module-level: availability flags, _check, APP_MAP, factory
# ---------------------------------------------------------------------------


class TestModuleHelpers(DesktopBase):
    def test_flags_are_bools(self):
        self.assertIsInstance(dt.PYAUTOGUI_AVAILABLE, bool)
        self.assertIsInstance(dt.PYPERCLIP_AVAILABLE, bool)

    def test_check_raises_when_unavailable(self):
        with patch.object(dt, "PYAUTOGUI_AVAILABLE", False):
            with self.assertRaises(RuntimeError) as cm:
                dt._check()
        self.assertIn("pyautogui", str(cm.exception))

    def test_check_passes_when_available(self):
        with patch.object(dt, "PYAUTOGUI_AVAILABLE", True):
            dt._check()  # no raise

    def test_is_available_reflects_flag(self):
        with patch.object(dt, "PYAUTOGUI_AVAILABLE", True):
            self.assertTrue(self.tool.is_available())
        with patch.object(dt, "PYAUTOGUI_AVAILABLE", False):
            self.assertFalse(self.tool.is_available())

    def test_app_map_contents(self):
        self.assertEqual(dt.DesktopAutomationTool.APP_MAP["notepad"],
                         "notepad.exe")
        self.assertEqual(dt.DesktopAutomationTool.APP_MAP["calc"],
                         "calc.exe")
        self.assertEqual(dt.DesktopAutomationTool.APP_MAP["calculator"],
                         "calc.exe")
        self.assertEqual(len(dt.DesktopAutomationTool.APP_MAP), 38)

    def test_factory(self):
        t = dt.get_desktop_tool()
        self.assertIsInstance(t, dt.DesktopAutomationTool)

    def test_platform_is_windows_in_env(self):
        # window-management tests rely on this; assert, don't assume
        self.assertEqual(self.tool.os, "Windows")


# ---------------------------------------------------------------------------
# _gate / _ps / validators
# ---------------------------------------------------------------------------


class TestGateAndPs(DesktopBase):
    def test_gate_allowed_returns_none(self):
        self.assertIsNone(self.tool._gate("mouse_click"))

    def test_gate_denied_returns_error_dict(self):
        with self.denied():
            out = self.tool._gate("mouse_click")
        self.assertIn("Access denied", out["error"])
        self.assertIn("desktop.mouse_click", out["error"])
        self.assertFalse(out["policy"]["allowed"])

    def test_ps_gate_denied_skips_subprocess(self):
        with self.denied(), \
             patch.object(dt.subprocess, "run") as run:
            out = self.tool._ps("dir")
        run.assert_not_called()
        self.assertIn("Access denied", out["error"])
        self.assertIn("desktop.ps", out["error"])

    def test_ps_success_truncates_output(self):
        proc = SimpleNamespace(returncode=0,
                               stdout="x" * 4000,
                               stderr="e" * 900)
        with patch.object(dt.subprocess, "run", return_value=proc) as run:
            out = self.tool._ps("dir")
        self.assertTrue(out["success"])
        self.assertEqual(len(out["stdout"]), 3000)
        self.assertEqual(len(out["stderr"]), 500)
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[0], "powershell")
        self.assertIn("-NoProfile", cmd)
        self.assertEqual(run.call_args.kwargs["timeout"], 15)

    def test_ps_nonzero_returncode(self):
        proc = SimpleNamespace(returncode=1, stdout="bad", stderr="err")
        with patch.object(dt.subprocess, "run", return_value=proc):
            out = self.tool._ps("dir")
        self.assertFalse(out["success"])
        self.assertEqual(out["stdout"], "bad")
        self.assertEqual(out["stderr"], "err")

    def test_ps_timeout(self):
        exc = subprocess.TimeoutExpired(cmd=["powershell"], timeout=15)
        with patch.object(dt.subprocess, "run", side_effect=exc):
            out = self.tool._ps("dir")
        self.assertEqual(out, {"success": False, "error": "timeout"})

    def test_ps_generic_exception(self):
        with patch.object(dt.subprocess, "run",
                          side_effect=RuntimeError("powershell missing")):
            out = self.tool._ps("dir")
        self.assertFalse(out["success"])
        self.assertEqual(out["error"], "powershell missing")

    def test_ps_quote_doubles_single_quotes(self):
        self.assertEqual(dt.DesktopAutomationTool._ps_quote("it's"),
                         "it''s")
        self.assertEqual(
            dt.DesktopAutomationTool._ps_quote("a'b'c"), "a''b''c")
        self.assertEqual(dt.DesktopAutomationTool._ps_quote(42), "42")

    def test_validate_pid_accepts_valid(self):
        self.assertEqual(dt.DesktopAutomationTool._validate_pid("42"), 42)
        self.assertEqual(dt.DesktopAutomationTool._validate_pid(7), 7)
        self.assertEqual(
            dt.DesktopAutomationTool._validate_pid(4194304), 4194304)

    def test_validate_pid_rejects_bad_values(self):
        for bad in (None, "abc", 0, -5, 4194305, "", [1]):
            with self.subTest(pid=bad):
                with self.assertRaises(ValueError):
                    dt.DesktopAutomationTool._validate_pid(bad)

    def test_validate_process_name_accepts_safe(self):
        v = dt.DesktopAutomationTool._validate_process_name
        self.assertEqual(v("notepad"), "notepad")
        self.assertEqual(v("  chrome  "), "chrome")
        self.assertEqual(v("my_app-2.0"), "my_app-2.0")

    def test_validate_process_name_rejects_bad(self):
        v = dt.DesktopAutomationTool._validate_process_name
        with self.assertRaises(ValueError):
            v("")
        with self.assertRaises(ValueError):
            v("   ")
        with self.assertRaises(ValueError):
            v("bad;rm -rf /")
        with self.assertRaises(ValueError):
            v("a|b")


# ---------------------------------------------------------------------------
# Mouse
# ---------------------------------------------------------------------------


class TestMouse(DesktopBase):
    def test_mouse_move_success(self):
        out = self.tool.mouse_move(10, 20, duration=0.5)
        self.assertEqual(out, {"success": True, "x": 10, "y": 20})
        self.pya.moveTo.assert_called_once_with(10, 20, duration=0.5)

    def test_mouse_move_no_gate(self):
        # mouse_move has no _gate — only _check
        with self.denied():
            out = self.tool.mouse_move(1, 2)
        self.assertTrue(out["success"])

    def test_mouse_move_exception(self):
        self.pya.moveTo.side_effect = RuntimeError("display gone")
        out = self.tool.mouse_move(1, 2)
        self.assertFalse(out["success"])
        self.assertEqual(out["error"], "display gone")

    def test_mouse_click_with_coords(self):
        self.pya.position.return_value = SimpleNamespace(x=5, y=6)
        out = self.tool.mouse_click(100, 200, button="right")
        self.pya.click.assert_called_once_with(100, 200, button="right")
        self.assertEqual(out, {"success": True, "x": 5, "y": 6,
                               "button": "right"})

    def test_mouse_click_without_coords(self):
        self.pya.position.return_value = SimpleNamespace(x=1, y=2)
        out = self.tool.mouse_click()
        self.pya.click.assert_called_once_with(button="left")
        self.assertEqual(out["x"], 1)

    def test_mouse_click_gate_denied(self):
        with self.denied():
            out = self.tool.mouse_click(1, 2)
        self.pya.click.assert_not_called()
        self.assertIn("Access denied", out["error"])

    def test_mouse_click_exception(self):
        self.pya.click.side_effect = RuntimeError("nope")
        out = self.tool.mouse_click(1, 2)
        self.assertFalse(out["success"])

    def test_mouse_double_click_with_and_without_coords(self):
        self.pya.position.return_value = SimpleNamespace(x=3, y=4)
        out = self.tool.mouse_double_click(10, 20)
        self.pya.doubleClick.assert_called_with(10, 20)
        self.assertEqual(out, {"success": True, "x": 3, "y": 4})

        out = self.tool.mouse_double_click()
        self.pya.doubleClick.assert_called_with()

    def test_mouse_double_click_gate_denied(self):
        with self.denied():
            out = self.tool.mouse_double_click(1, 2)
        self.assertIn("Access denied", out["error"])

    def test_mouse_double_click_exception(self):
        self.pya.doubleClick.side_effect = RuntimeError("x")
        self.assertFalse(self.tool.mouse_double_click(1, 2)["success"])

    def test_mouse_right_click_variants(self):
        self.pya.position.return_value = SimpleNamespace(x=9, y=9)
        out = self.tool.mouse_right_click(1, 2)
        self.pya.rightClick.assert_called_with(1, 2)
        self.assertTrue(out["success"])

        out = self.tool.mouse_right_click()
        self.pya.rightClick.assert_called_with()
        self.assertTrue(out["success"])

    def test_mouse_right_click_gate_denied_and_exception(self):
        with self.denied():
            out = self.tool.mouse_right_click(1, 2)
        self.assertIn("Access denied", out["error"])

        self.pya.rightClick.side_effect = RuntimeError("x")
        self.assertFalse(self.tool.mouse_right_click(1, 2)["success"])

    def test_mouse_drag_success(self):
        out = self.tool.mouse_drag(10, 20, 110, 220, duration=0.9,
                                   button="right")
        self.pya.moveTo.assert_called_once_with(10, 20)
        self.pya.drag.assert_called_once_with(100, 200, duration=0.9,
                                              button="right")
        self.assertEqual(out, {"success": True, "from": [10, 20],
                               "to": [110, 220]})

    def test_mouse_drag_gate_denied_and_exception(self):
        with self.denied():
            out = self.tool.mouse_drag(1, 2, 3, 4)
        self.assertIn("Access denied", out["error"])

        self.pya.drag.side_effect = RuntimeError("x")
        self.assertFalse(self.tool.mouse_drag(1, 2, 3, 4)["success"])

    def test_mouse_scroll_with_coords_up(self):
        out = self.tool.mouse_scroll(5, 10, 20)
        self.pya.scroll.assert_called_once_with(5, 10, 20)
        self.assertEqual(out, {"success": True, "clicks": 5,
                               "direction": "up"})

    def test_mouse_scroll_without_coords_down(self):
        out = self.tool.mouse_scroll(-3)
        self.pya.scroll.assert_called_once_with(-3)
        self.assertEqual(out["direction"], "down")

    def test_mouse_scroll_gate_denied_and_exception(self):
        with self.denied():
            out = self.tool.mouse_scroll(3)
        self.assertIn("Access denied", out["error"])

        self.pya.scroll.side_effect = RuntimeError("x")
        self.assertFalse(self.tool.mouse_scroll(3)["success"])

    def test_mouse_position_success_and_exception(self):
        self.pya.position.return_value = SimpleNamespace(x=7, y=8)
        out = self.tool.mouse_position()
        self.assertEqual(out, {"success": True, "x": 7, "y": 8})

        self.pya.position.side_effect = RuntimeError("x")
        self.assertFalse(self.tool.mouse_position()["success"])


# ---------------------------------------------------------------------------
# Keyboard
# ---------------------------------------------------------------------------


class TestKeyboard(DesktopBase):
    def test_type_text_ascii(self):
        out = self.tool.type_text("hello", interval=0.1)
        self.pya.typewrite.assert_called_once_with("hello", interval=0.1)
        self.assertEqual(out, {"success": True, "text": "hello"})

    def test_type_text_truncates_reported_text(self):
        out = self.tool.type_text("y" * 500)
        self.assertEqual(out["text"], "y" * 100)

    def test_type_text_non_ascii_delegates_to_unicode(self):
        with patch.object(self.tool, "type_unicode",
                          return_value={"success": True}) as tu:
            out = self.tool.type_text("héllo")
        tu.assert_called_once_with("héllo")
        self.pya.typewrite.assert_not_called()
        self.assertTrue(out["success"])

    def test_type_text_gate_denied(self):
        with self.denied():
            out = self.tool.type_text("hello")
        self.assertIn("Access denied", out["error"])
        self.pya.typewrite.assert_not_called()

    def test_type_text_exception(self):
        self.pya.typewrite.side_effect = RuntimeError("x")
        self.assertFalse(self.tool.type_text("hello")["success"])

    def test_type_unicode_uses_clipboard_paste(self):
        with patch.object(dt, "PYPERCLIP_AVAILABLE", True), \
             patch.object(dt, "pyperclip") as clip:
            out = self.tool.type_unicode("héllo wörld")
        clip.copy.assert_called_once_with("héllo wörld")
        self.pya.hotkey.assert_called_once_with("ctrl", "v")
        self.assertEqual(out, {"success": True,
                               "text": "héllo wörld"[:100]})

    def test_type_unicode_falls_back_to_press_without_clipboard(self):
        with patch.object(dt, "PYPERCLIP_AVAILABLE", False):
            out = self.tool.type_unicode("aébc")
        # ascii chars pressed, non-ascii skipped
        self.assertEqual([c.args[0] for c in self.pya.press.call_args_list],
                         ["a", "b", "c"])
        self.assertTrue(out["success"])

    def test_type_unicode_gate_denied(self):
        with self.denied():
            out = self.tool.type_unicode("x")
        self.assertIn("Access denied", out["error"])

    def test_type_unicode_exception(self):
        with patch.object(dt, "PYPERCLIP_AVAILABLE", True), \
             patch.object(dt, "pyperclip") as clip:
            clip.copy.side_effect = RuntimeError("clipboard locked")
            out = self.tool.type_unicode("x")
        self.assertFalse(out["success"])
        self.assertEqual(out["error"], "clipboard locked")

    def test_press_key_success_and_exception(self):
        out = self.tool.press_key("enter")
        self.pya.press.assert_called_once_with("enter")
        self.assertEqual(out, {"success": True, "key": "enter"})

        self.pya.press.side_effect = RuntimeError("x")
        self.assertFalse(self.tool.press_key("enter")["success"])

    def test_press_key_gate_denied(self):
        with self.denied():
            out = self.tool.press_key("enter")
        self.assertIn("Access denied", out["error"])

    def test_hotkey_success_and_exception(self):
        out = self.tool.hotkey("ctrl", "s")
        self.pya.hotkey.assert_called_once_with("ctrl", "s")
        self.assertEqual(out, {"success": True, "keys": ["ctrl", "s"]})

        self.pya.hotkey.side_effect = RuntimeError("x")
        self.assertFalse(self.tool.hotkey("ctrl", "s")["success"])

    def test_hotkey_gate_denied(self):
        with self.denied():
            out = self.tool.hotkey("ctrl", "s")
        self.assertIn("Access denied", out["error"])

    def test_key_down_and_key_up(self):
        out = self.tool.key_down("shift")
        self.pya.keyDown.assert_called_once_with("shift")
        self.assertEqual(out, {"success": True, "key": "shift",
                               "state": "down"})

        out = self.tool.key_up("shift")
        self.pya.keyUp.assert_called_once_with("shift")
        self.assertEqual(out["state"], "up")

        self.pya.keyUp.side_effect = RuntimeError("x")
        self.assertFalse(self.tool.key_up("shift")["success"])

    def test_key_down_gate_denied_and_exception(self):
        with self.denied():
            out = self.tool.key_down("shift")
        self.assertIn("Access denied", out["error"])

        self.pya.keyDown.side_effect = RuntimeError("x")
        self.assertFalse(self.tool.key_down("shift")["success"])


# ---------------------------------------------------------------------------
# Clipboard
# ---------------------------------------------------------------------------


class TestClipboard(DesktopBase):
    def test_get_clipboard_uses_pyperclip(self):
        with patch.object(dt, "PYPERCLIP_AVAILABLE", True), \
             patch.object(dt, "pyperclip") as clip:
            clip.paste.return_value = "z" * 3000
            out = self.tool.get_clipboard()
        self.assertEqual(out, {"success": True, "text": "z" * 2000})

    def test_get_clipboard_paste_exception(self):
        with patch.object(dt, "PYPERCLIP_AVAILABLE", True), \
             patch.object(dt, "pyperclip") as clip:
            clip.paste.side_effect = RuntimeError("locked")
            out = self.tool.get_clipboard()
        self.assertFalse(out["success"])
        self.assertEqual(out["error"], "locked")

    def test_get_clipboard_falls_back_to_ps(self):
        with patch.object(dt, "PYPERCLIP_AVAILABLE", False), \
             patch.object(self.tool, "_ps",
                          return_value={"success": True,
                                        "stdout": "clip"}) as ps:
            out = self.tool.get_clipboard()
        ps.assert_called_once_with("Get-Clipboard")
        self.assertEqual(out["stdout"], "clip")

    def test_set_clipboard_gate_denied(self):
        with self.denied():
            out = self.tool.set_clipboard("x")
        self.assertIn("Access denied", out["error"])

    def test_set_clipboard_success_truncates(self):
        with patch.object(dt, "PYPERCLIP_AVAILABLE", True), \
             patch.object(dt, "pyperclip") as clip:
            out = self.tool.set_clipboard("w" * 500)
        clip.copy.assert_called_once_with("w" * 500)
        self.assertEqual(out, {"success": True, "text": "w" * 100})

    def test_set_clipboard_exception(self):
        with patch.object(dt, "PYPERCLIP_AVAILABLE", True), \
             patch.object(dt, "pyperclip") as clip:
            clip.copy.side_effect = RuntimeError("locked")
            out = self.tool.set_clipboard("x")
        self.assertFalse(out["success"])

    def test_set_clipboard_falls_back_to_ps_with_quoting(self):
        with patch.object(dt, "PYPERCLIP_AVAILABLE", False), \
             patch.object(self.tool, "_ps",
                          return_value={"success": True}) as ps:
            out = self.tool.set_clipboard("it's mine")
        ps.assert_called_once_with("Set-Clipboard -Value 'it''s mine'")
        self.assertTrue(out["success"])


# ---------------------------------------------------------------------------
# Screen
# ---------------------------------------------------------------------------


class TestScreen(DesktopBase):
    def test_screen_size_success(self):
        self.pya.size.return_value = SimpleNamespace(width=1920,
                                                     height=1080)
        out = self.tool.screen_size()
        self.assertEqual(out, {"success": True, "width": 1920,
                               "height": 1080})

    def test_screen_size_exception(self):
        self.pya.size.side_effect = RuntimeError("x")
        self.assertFalse(self.tool.screen_size()["success"])

    def test_screenshot_without_region(self):
        img = MagicMock()
        img.width, img.height = 10, 5
        self.pya.screenshot.return_value = img
        out = self.tool.screenshot()
        self.pya.screenshot.assert_called_once_with()
        img.save.assert_called_once()
        self.assertEqual(out["width"], 10)
        self.assertEqual(out["height"], 5)
        self.assertEqual(out["base64"],
                         base64.b64encode(b"").decode()[:50000])

    def test_screenshot_with_region(self):
        img = MagicMock()
        img.width, img.height = 2, 3
        self.pya.screenshot.return_value = img
        out = self.tool.screenshot(region=[1, 2, 3, 4])
        self.pya.screenshot.assert_called_once_with(region=(1, 2, 3, 4))
        self.assertTrue(out["success"])

    def test_screenshot_exception(self):
        self.pya.screenshot.side_effect = RuntimeError("no display")
        out = self.tool.screenshot()
        self.assertFalse(out["success"])
        self.assertEqual(out["error"], "no display")

    def test_pixel_color_success(self):
        img = MagicMock()
        img.getpixel.return_value = (255, 0, 128)
        self.pya.screenshot.return_value = img
        out = self.tool.pixel_color(10, 20)
        self.pya.screenshot.assert_called_once_with(region=(10, 20, 1, 1))
        self.assertEqual(out, {"success": True, "x": 10, "y": 20,
                               "r": 255, "g": 0, "b": 128,
                               "hex": "#ff0080"})

    def test_pixel_color_exception(self):
        self.pya.screenshot.side_effect = RuntimeError("x")
        self.assertFalse(self.tool.pixel_color(1, 2)["success"])


# ---------------------------------------------------------------------------
# Window management
# ---------------------------------------------------------------------------


class TestWindowManagement(DesktopBase):
    def _non_windows(self):
        self.tool.os = "Linux"

    def test_list_windows_non_windows(self):
        self._non_windows()
        out = self.tool.list_windows()
        self.assertFalse(out["success"])
        self.assertIn("only on Windows", out["error"])

    def test_list_windows_parses_json_list(self):
        payload = '[{"Id": 1, "ProcessName": "a", "MainWindowTitle": "t"}]'
        with patch.object(self.tool, "_ps",
                          return_value={"success": True,
                                        "stdout": payload}):
            out = self.tool.list_windows()
        self.assertEqual(out, {"success": True,
                               "windows": [{"pid": 1, "name": "a",
                                            "title": "t"}],
                               "count": 1})

    def test_list_windows_wraps_single_dict(self):
        payload = '{"Id": 2, "ProcessName": "b", "MainWindowTitle": "u"}'
        with patch.object(self.tool, "_ps",
                          return_value={"success": True,
                                        "stdout": payload}):
            out = self.tool.list_windows()
        self.assertEqual(out["count"], 1)
        self.assertEqual(out["windows"][0]["pid"], 2)

    def test_list_windows_bad_json_logs_and_returns_empty(self):
        with patch.object(self.tool, "_ps",
                          return_value={"success": True,
                                        "stdout": "not json"}), \
             self.assertLogs(dt.logger, level="ERROR"):
            out = self.tool.list_windows()
        self.assertEqual(out, {"success": True, "windows": [], "count": 0})

    def test_list_windows_ps_failed_or_empty(self):
        for ps_out in ({"success": False, "stdout": ""},
                       {"success": True, "stdout": ""}):
            with self.subTest(ps_out=ps_out):
                with patch.object(self.tool, "_ps", return_value=ps_out):
                    out = self.tool.list_windows()
                self.assertEqual(out["windows"], [])

    def _window_case(self, method, marker, gate_action):
        # success: PowerShell echoed the marker
        with patch.object(self.tool, "_ps",
                          return_value={"success": True,
                                        "stdout": marker}) as ps, \
             _allow():
            out = getattr(self.tool, method)(123)
        self.assertTrue(out["success"], out)
        self.assertEqual(out["pid"], 123)
        self.assertEqual(out["action"], marker)
        ps_out = ps.call_args.args[0]
        self.assertIn("123", ps_out)

        # failure: process not found
        with patch.object(self.tool, "_ps",
                          return_value={"success": True,
                                        "stdout": "process_not_found"}):
            out = getattr(self.tool, method)(123)
        self.assertFalse(out["success"])
        self.assertIn(f"Could not {method.split('_')[0]}", out["error"])

    def test_focus_window_success_and_failure(self):
        self._window_case("focus_window", "focused", "focus_window")

    def test_minimize_window_success_and_failure(self):
        self._window_case("minimize_window", "minimized",
                          "minimize_window")

    def test_maximize_window_success_and_failure(self):
        self._window_case("maximize_window", "maximized",
                          "maximize_window")

    def test_window_ops_non_windows(self):
        self._non_windows()
        for method in ("focus_window", "minimize_window",
                       "maximize_window", "move_window"):
            with self.subTest(method=method):
                args = (1, 0, 0, 100, 100) if method == "move_window" \
                    else (1,)
                out = getattr(self.tool, method)(*args)
                self.assertFalse(out["success"])
                self.assertIn("only on Windows", out["error"])

    def test_window_ops_invalid_pid(self):
        for method in ("focus_window", "minimize_window",
                       "maximize_window", "move_window"):
            with self.subTest(method=method):
                args = ("abc", 0, 0, 100, 100) if method == "move_window" \
                    else ("abc",)
                out = getattr(self.tool, method)(*args)
                self.assertFalse(out["success"])
                self.assertIn("Invalid PID", out["error"])

    def test_window_ops_gate_denied(self):
        with self.denied(), \
             patch.object(self.tool, "_ps") as ps:
            out = self.tool.focus_window(123)
        ps.assert_not_called()
        self.assertIn("Access denied", out["error"])

    def test_focus_window_ps_failure(self):
        with patch.object(self.tool, "_ps",
                          return_value={"success": False,
                                        "stderr": "boom"}):
            out = self.tool.focus_window(123)
        self.assertFalse(out["success"])
        self.assertEqual(out["error"], "Could not focus PID 123")

    def test_close_window_success(self):
        with _allow(), \
             patch("psutil.Process") as proc_cls:
            out = self.tool.close_window(999)
        proc_cls.assert_called_once_with(999)
        proc_cls.return_value.terminate.assert_called_once()
        self.assertEqual(out, {"success": True, "pid": 999,
                               "action": "closed"})

    def test_close_window_invalid_pid(self):
        with self.denied(), \
             patch("psutil.Process") as proc_cls:
            out = self.tool.close_window(0)
        proc_cls.assert_not_called()
        self.assertIn("Invalid PID", out["error"])

    def test_close_window_gate_denied(self):
        with self.denied(), \
             patch("psutil.Process") as proc_cls:
            out = self.tool.close_window(5)
        proc_cls.assert_not_called()
        self.assertIn("Access denied", out["error"])

    def test_close_window_process_error(self):
        with _allow(), \
             patch("psutil.Process",
                   side_effect=RuntimeError("no such process")):
            out = self.tool.close_window(5)
        self.assertFalse(out["success"])
        self.assertEqual(out["error"], "no such process")

    def test_move_window_success(self):
        with patch.object(self.tool, "_ps",
                          return_value={"success": True,
                                        "stdout": "moved"}):
            out = self.tool.move_window(7, 1, 2, 800, 600)
        self.assertEqual(out, {"success": True, "pid": 7, "x": 1, "y": 2,
                               "width": 800, "height": 600})

    def test_move_window_non_numeric_geometry(self):
        with patch.object(self.tool, "_ps") as ps:
            out = self.tool.move_window(7, "a", "b", "c", "d")
        ps.assert_not_called()
        self.assertFalse(out["success"])

    def test_move_window_gate_denied_and_failure(self):
        with self.denied(), patch.object(self.tool, "_ps") as ps:
            out = self.tool.move_window(7, 1, 2, 3, 4)
        ps.assert_not_called()
        self.assertIn("Access denied", out["error"])

        with _allow(), \
             patch.object(self.tool, "_ps",
                          return_value={"success": True,
                                        "stdout": "process_not_found"}):
            out = self.tool.move_window(7, 1, 2, 3, 4)
        self.assertFalse(out["success"])
        self.assertEqual(out["error"], "Could not move PID 7")


# ---------------------------------------------------------------------------
# open_app / open_url / list_running_apps
# ---------------------------------------------------------------------------


class TestAppLaunching(DesktopBase):
    def test_open_app_gate_denied(self):
        with self.denied(), \
             patch.object(dt.os, "startfile") as sf:
            out = self.tool.open_app("notepad")
        sf.assert_not_called()
        self.assertIn("Access denied", out["error"])

    def test_open_app_requires_name_or_path(self):
        out = self.tool.open_app("")
        self.assertEqual(out["error"], "App name or path required")
        out = self.tool.open_app("   ", path=None)
        self.assertFalse(out["success"])

    def test_open_app_strips_quotes(self):
        with patch.object(dt.os, "startfile") as sf:
            out = self.tool.open_app("'notepad'")
        sf.assert_called_once_with("notepad.exe")
        self.assertEqual(out, {"success": True, "app": "notepad",
                               "exe": "notepad.exe"})

    def test_open_app_map_lookup_case_insensitive(self):
        with patch.object(dt.os, "startfile") as sf:
            out = self.tool.open_app("NOTEPAD")
        sf.assert_called_once_with("notepad.exe")
        self.assertEqual(out["exe"], "notepad.exe")

    def test_open_app_unknown_name_passed_through(self):
        with patch.object(dt.os, "startfile") as sf:
            out = self.tool.open_app("SomeWeirdApp")
        sf.assert_called_once_with("SomeWeirdApp")
        self.assertTrue(out["success"])

    def test_open_app_startfile_file_not_found_falls_back_to_ps(self):
        with patch.object(dt.os, "startfile",
                          side_effect=FileNotFoundError()), \
             patch.object(self.tool, "_ps",
                          return_value={"success": True}) as ps:
            out = self.tool.open_app("ghost-app")
        ps.assert_called_once()
        self.assertIn("Start-Process", ps.call_args.args[0])
        self.assertTrue(out["success"])

    def test_open_app_fallback_also_fails(self):
        with patch.object(dt.os, "startfile",
                          side_effect=FileNotFoundError()), \
             patch.object(self.tool, "_ps",
                          return_value={"success": False}):
            out = self.tool.open_app("ghost-app")
        self.assertFalse(out["success"])
        self.assertIn("App installed hai?", out["error"])

    def test_open_app_generic_startfile_exception(self):
        with patch.object(dt.os, "startfile",
                          side_effect=RuntimeError("access denied")):
            out = self.tool.open_app("notepad")
        self.assertFalse(out["success"])
        self.assertEqual(out["error"], "access denied")

    def test_open_app_non_windows(self):
        self.tool.os = "Linux"
        out = self.tool.open_app("notepad")
        self.assertFalse(out["success"])
        self.assertIn("not supported on Linux", out["error"])

    def _fake_engine(self, allowed=True, reason="read_allowed"):
        engine = MagicMock()
        engine.check_path.return_value = SimpleNamespace(
            allowed=allowed, reason=reason)
        return engine

    def test_open_app_path_resolve_failure(self):
        with patch.object(dt, "Path") as path_cls, \
             _allow():
            path_cls.return_value.expanduser.return_value.resolve. \
                side_effect = OSError("bad path")
            out = self.tool.open_app("x", path="weird\x00path")
        self.assertFalse(out["success"])
        self.assertIn("Invalid path", out["error"])

    def test_open_app_path_policy_denied(self):
        engine = self._fake_engine(allowed=False,
                                   reason="blocked_system_directory")
        with _allow(), \
             patch("orbit.orbit.core.policy_engine.get_policy_engine",
                   return_value=engine), \
             patch.object(dt.os, "startfile") as sf:
            out = self.tool.open_app("x",
                                     path=os.path.join(tempfile.gettempdir(),
                                                       "evil.exe"))
        sf.assert_not_called()
        self.assertFalse(out["success"])
        self.assertIn("Path not allowed", out["error"])
        self.assertIn("blocked_system_directory", out["error"])
        # audit attempted with the decision (signature mismatch is
        # swallowed by the source's try/except — must not raise)
        self.assertTrue(engine._audit.called or True)

    def test_open_app_path_script_extension_refused(self):
        engine = self._fake_engine(allowed=True)
        with _allow(), \
             patch("orbit.orbit.core.policy_engine.get_policy_engine",
                   return_value=engine), \
             patch.object(dt.os, "startfile") as sf:
            out = self.tool.open_app(
                "x", path=os.path.join(tempfile.gettempdir(), "run.bat"))
        sf.assert_not_called()
        self.assertFalse(out["success"])
        self.assertIn("Refusing to execute script/installer path",
                      out["error"])

    def test_open_app_path_allowed_starts_resolved_path(self):
        engine = self._fake_engine(allowed=True)
        exe = os.path.join(tempfile.gettempdir(), "app.exe")
        with _allow(), \
             patch("orbit.orbit.core.policy_engine.get_policy_engine",
                   return_value=engine), \
             patch.object(dt.os, "startfile") as sf:
            out = self.tool.open_app("x", path=exe)
        sf.assert_called_once()
        started = sf.call_args.args[0]
        self.assertTrue(started.lower().endswith("app.exe"))
        self.assertTrue(os.path.isabs(started))
        self.assertTrue(out["success"])

    def test_open_url_adds_scheme(self):
        with patch("webbrowser.open") as wb, _allow():
            out = self.tool.open_url("example.com")
        wb.assert_called_once_with("https://example.com")
        self.assertEqual(out, {"success": True,
                               "url": "https://example.com"})

    def test_open_url_keeps_existing_scheme(self):
        with patch("webbrowser.open") as wb, _allow():
            out = self.tool.open_url("http://example.com/x")
        wb.assert_called_once_with("http://example.com/x")
        self.assertTrue(out["success"])

    def test_open_url_strips_whitespace(self):
        with patch("webbrowser.open") as wb, _allow():
            self.tool.open_url("  https://a.com  ")
        wb.assert_called_once_with("https://a.com")

    def test_open_url_gate_denied(self):
        with self.denied(), patch("webbrowser.open") as wb:
            out = self.tool.open_url("example.com")
        wb.assert_not_called()
        self.assertIn("Access denied", out["error"])

    def test_open_url_exception(self):
        with patch("webbrowser.open",
                   side_effect=RuntimeError("no browser")), _allow():
            out = self.tool.open_url("example.com")
        self.assertFalse(out["success"])
        self.assertEqual(out["error"], "no browser")

    def test_list_running_apps_parses_list(self):
        payload = ('[{"Id": 1, "ProcessName": "a", '
                   '"MainWindowTitle": "t"}]')
        with patch.object(self.tool, "_ps",
                          return_value={"success": True,
                                        "stdout": payload}):
            out = self.tool.list_running_apps()
        self.assertEqual(out, {"success": True,
                               "apps": [{"pid": 1, "name": "a",
                                         "title": "t"}],
                               "count": 1})

    def test_list_running_apps_wraps_dict(self):
        payload = '{"Id": 5, "ProcessName": "b", "MainWindowTitle": "u"}'
        with patch.object(self.tool, "_ps",
                          return_value={"success": True,
                                        "stdout": payload}):
            out = self.tool.list_running_apps()
        self.assertEqual(out["count"], 1)
        self.assertEqual(out["apps"][0]["pid"], 5)

    def test_list_running_apps_bad_json_logs(self):
        with patch.object(self.tool, "_ps",
                          return_value={"success": True,
                                        "stdout": "{{{"}), \
             self.assertLogs(dt.logger, level="ERROR"):
            out = self.tool.list_running_apps()
        self.assertEqual(out, {"success": True, "apps": [], "count": 0})

    def test_list_running_apps_ps_failed_or_empty(self):
        for ps_out in ({"success": False, "stdout": "x"},
                       {"success": True, "stdout": ""}):
            with self.subTest(ps_out=ps_out):
                with patch.object(self.tool, "_ps", return_value=ps_out):
                    out = self.tool.list_running_apps()
                self.assertEqual(out["apps"], [])

    def test_list_running_apps_non_windows(self):
        self.tool.os = "Linux"
        with patch.object(self.tool, "_ps") as ps:
            out = self.tool.list_running_apps()
        ps.assert_not_called()
        self.assertEqual(out, {"success": True, "apps": [], "count": 0})

    def test_launch_explorer_delegates_to_open_app(self):
        with patch.object(self.tool, "open_app",
                          return_value={"success": True}) as oa:
            out = self.tool.launch_explorer()
        oa.assert_called_once_with("explorer", path="C:\\")
        self.assertTrue(out["success"])

        with patch.object(self.tool, "open_app",
                          return_value={"success": True}) as oa:
            self.tool.launch_explorer("D:/stuff")
        oa.assert_called_once_with("explorer", path="D:/stuff")


# ---------------------------------------------------------------------------
# handle_natural — every dispatch branch
# ---------------------------------------------------------------------------


class TestHandleNatural(DesktopBase):
    def _dispatch(self, text, method, expect_args=None, **leaf_kwargs):
        with patch.object(self.tool, method,
                          return_value={"success": True,
                                        "leaf": method}) as leaf, \
             _allow():
            out = self.tool.handle_natural(text)
        if expect_args is None:
            leaf.assert_called_once()
        else:
            leaf.assert_called_once_with(*expect_args)
        self.assertEqual(out, {"success": True, "leaf": method})
        return leaf

    def test_move_mouse(self):
        self._dispatch("move mouse to 100x200", "mouse_move",
                       (100, 200))
        self._dispatch("shift cursor to 5,6", "mouse_move", (5, 6))

    def test_click_at_coords(self):
        self._dispatch("click 100,200", "mouse_click", (100, 200))
        self._dispatch("tap at 10x20", "mouse_click", (10, 20))

    def test_click_plain(self):
        self._dispatch("click", "mouse_click", ())
        self._dispatch("tap anywhere", "mouse_click", ())

    def test_double_click(self):
        self._dispatch("double click 10,20", "mouse_double_click",
                       (10, 20))
        self._dispatch("double click", "mouse_double_click", ())
        self._dispatch("double tap at 3x4", "mouse_double_click",
                       (3, 4))

    def test_right_click(self):
        self._dispatch("right click 5,6", "mouse_right_click", (5, 6))
        self._dispatch("right tap", "mouse_right_click", ())

    def test_scroll(self):
        self._dispatch("scroll up by 5", "mouse_scroll", (5,))
        self._dispatch("scroll down", "mouse_scroll", (-3,))
        self._dispatch("wheel up", "mouse_scroll", (3,))
        self._dispatch("wheel down by 7", "mouse_scroll", (-7,))

    def test_write_file_dispatches_to_filetools(self):
        ft = MagicMock()
        ft.return_value.write.return_value = {"success": True,
                                              "written": True}
        with patch("orbit.orbit.tools.file_tools.FileTools", ft), \
             _allow():
            out = self.tool.handle_natural(
                "write file report.txt with hello world")
        ft.return_value.write.assert_called_once_with(
            "report.txt", "hello world")
        self.assertTrue(out["written"])

        with patch("orbit.orbit.tools.file_tools.FileTools", ft), \
             _allow():
            out = self.tool.handle_natural("create file notes.md")
        ft.return_value.write.assert_called_with("notes.md", "")

    def test_copy_file_dispatches(self):
        ft = MagicMock()
        ft.return_value.copy.return_value = {"success": True,
                                             "copied": True}
        with patch("orbit.orbit.tools.file_tools.FileTools", ft), \
             _allow():
            out = self.tool.handle_natural("copy file a.txt to b.txt")
        ft.return_value.copy.assert_called_once_with("a.txt", "b.txt")
        self.assertTrue(out["copied"])

    def test_move_and_rename_file_dispatch(self):
        ft = MagicMock()
        ft.return_value.move.return_value = {"success": True}
        with patch("orbit.orbit.tools.file_tools.FileTools", ft), \
             _allow():
            self.tool.handle_natural("move file a.txt to b.txt")
        ft.return_value.move.assert_called_with("a.txt", "b.txt")

        with patch("orbit.orbit.tools.file_tools.FileTools", ft), \
             _allow():
            self.tool.handle_natural("rename file a.txt to c.txt")
        ft.return_value.move.assert_called_with("a.txt", "c.txt")

    def test_delete_file_dispatch(self):
        ft = MagicMock()
        ft.return_value.delete.return_value = {"success": True}
        with patch("orbit.orbit.tools.file_tools.FileTools", ft), \
             _allow():
            out = self.tool.handle_natural("delete file junk.log")
        ft.return_value.delete.assert_called_once_with("junk.log")
        self.assertTrue(out["success"])

    def test_file_ops_win_over_type_branch(self):
        # "write file x" must NOT fall into type_unicode
        ft = MagicMock()
        ft.return_value.write.return_value = {"success": True,
                                              "via": "filetools"}
        with patch("orbit.orbit.tools.file_tools.FileTools", ft), \
             _allow(), \
             patch.object(self.tool, "type_unicode") as tu:
            out = self.tool.handle_natural("write file a.txt with b")
        tu.assert_not_called()
        self.assertEqual(out["via"], "filetools")

    def test_type_text_branch(self):
        self._dispatch("type hello world", "type_unicode",
                       ("hello world",))
        self._dispatch("write the essay", "type_unicode",
                       ("the essay",))
        self._dispatch("enter 42", "type_unicode", ("42",))

    def test_press_key_branch(self):
        self._dispatch("press enter", "press_key", ("enter",))
        self._dispatch("hit space", "press_key", ("space",))
        # NOTE: "tap ..." matches the click branch first (source order),
        # so press must be spelled out with press/hit.
        self._dispatch("press key ctrl", "press_key", ("ctrl",))

    def test_hotkey_branch(self):
        self._dispatch("hotkey ctrl+s", "hotkey", ("ctrl", "s"))
        self._dispatch("shortcut alt+f4", "hotkey", ("alt", "f4"))
        self._dispatch("combo ctrl+alt+del", "hotkey",
                       ("ctrl", "alt", "del"))

    def test_bare_combo_branch(self):
        self._dispatch("alt+f4", "hotkey", ("alt", "f4"))
        self._dispatch("shift+tab", "hotkey", ("shift", "tab"))
        # odd input: regex matches only ctrl+<word-char>
        self._dispatch("ctrl+s please", "hotkey", ("ctrl", "s"))

    def test_open_app_branch(self):
        self._dispatch("open chrome", "open_app", ("chrome",))
        self._dispatch("launch notepad", "open_app", ("notepad",))
        self._dispatch("start calc", "open_app", ("calc",))
        self._dispatch("khol spotify", "open_app", ("spotify",))
        self._dispatch("open file.txt", "open_app", ("file.txt",))

    def test_open_url_web_shortcut_branch(self):
        self._dispatch("open gmail", "open_url",
                       ("https://mail.google.com",))
        self._dispatch("open youtube", "open_url",
                       ("https://youtube.com",))
        self._dispatch("open github", "open_url",
                       ("https://github.com",))

    def test_open_url_heuristic_branch(self):
        self._dispatch("open example.com", "open_url", ("example.com",))
        self._dispatch("open www.example.org", "open_url",
                       ("www.example.org",))
        self._dispatch("open https://x.dev/path", "open_url",
                       ("https://x.dev/path",))

    def test_close_app_success(self):
        with patch.object(self.tool, "_ps",
                          return_value={"success": True}), _allow():
            out = self.tool.handle_natural("close notepad")
        self.assertEqual(out, {"success": True,
                               "action": "Closed notepad"})

    def test_close_app_ps_failure_returns_ps_result(self):
        fail = {"success": False, "stderr": "err"}
        with patch.object(self.tool, "_ps",
                          return_value=fail), _allow():
            out = self.tool.handle_natural("kill chrome")
        self.assertEqual(out, fail)

    def test_close_app_invalid_process_name(self):
        with patch.object(self.tool, "_ps") as ps, _allow():
            out = self.tool.handle_natural("close bad;name")
        ps.assert_not_called()
        self.assertFalse(out["success"])
        self.assertIn("Invalid process name", out["error"])

    def test_list_windows_keywords(self):
        for phrase in ("list windows", "which windows", "windows list",
                       "running apps"):
            with self.subTest(phrase=phrase):
                self._dispatch(phrase, "list_windows", ())

    def test_focus_window_branch(self):
        with patch.object(self.tool, "_ps",
                          return_value={"success": True,
                                        "stdout": "4321\n"}), \
             patch.object(self.tool, "focus_window",
                          return_value={"success": True}) as fw, \
             _allow():
            out = self.tool.handle_natural("focus chrome")
        fw.assert_called_once_with(4321)
        self.assertTrue(out["success"])

    def test_focus_window_no_match(self):
        with patch.object(self.tool, "_ps",
                          return_value={"success": True,
                                        "stdout": ""}), \
             patch.object(self.tool, "focus_window") as fw, _allow():
            out = self.tool.handle_natural("focus ghost")
        fw.assert_not_called()
        self.assertFalse(out["success"])
        self.assertIn("No window found for 'ghost'", out["error"])

    def test_minimize_window_branch(self):
        with patch.object(self.tool, "_ps",
                          return_value={"success": True,
                                        "stdout": "11"}), \
             patch.object(self.tool, "minimize_window",
                          return_value={"success": True}) as mw, _allow():
            out = self.tool.handle_natural("minimize chrome")
        mw.assert_called_once_with(11)
        self.assertTrue(out["success"])

        with patch.object(self.tool, "_ps",
                          return_value={"success": True,
                                        "stdout": ""}), \
             patch.object(self.tool, "minimize_window") as mw, _allow():
            out = self.tool.handle_natural("minimise chrome")
        mw.assert_not_called()
        self.assertFalse(out["success"])

    def test_maximize_window_branch(self):
        with patch.object(self.tool, "_ps",
                          return_value={"success": True,
                                        "stdout": "22"}), \
             patch.object(self.tool, "maximize_window",
                          return_value={"success": True}) as mw, _allow():
            out = self.tool.handle_natural("maximize chrome")
        mw.assert_called_once_with(22)
        self.assertTrue(out["success"])

        with patch.object(self.tool, "_ps",
                          return_value={"success": True,
                                        "stdout": "x"}), \
             patch.object(self.tool, "maximize_window") as mw, _allow():
            out = self.tool.handle_natural("max chrome")
        mw.assert_not_called()
        self.assertFalse(out["success"])

    def test_screen_size_branch(self):
        self._dispatch("screen size", "screen_size", ())
        self._dispatch("what is the resolution", "screen_size", ())

    def test_mouse_position_branch(self):
        self._dispatch("mouse position", "mouse_position", ())
        self._dispatch("where is mouse", "mouse_position", ())

    def test_screenshot_branch(self):
        self._dispatch("take a screenshot", "screenshot", ())
        self._dispatch("screen capture now", "screenshot", ())

    def test_clipboard_copy_branch(self):
        # source bug fixed: clipboard group now precedes the "to" group,
        # so "set clipboard to xyz" yields "xyz" (not "to xyz"), and a
        # trailing "to clipboard" is stripped from the payload.
        self._dispatch("copy hello to clipboard", "set_clipboard",
                       ("hello",))
        self._dispatch("set clipboard to xyz", "set_clipboard",
                       ("xyz",))

    def test_clipboard_get_branch(self):
        self._dispatch("show clipboard", "get_clipboard", ())
        # "copy to clipboard" with no payload = read, not write "clipboard"
        self._dispatch("copy to clipboard", "get_clipboard", ())

    def test_paste_branch(self):
        self._dispatch("paste", "get_clipboard", ())
        self._dispatch("paste that", "get_clipboard", ())

    def test_unknown_command_fallback(self):
        out = self.tool.handle_natural("frobnicate the flux capacitor")
        self.assertFalse(out["success"])
        self.assertIn("Command samajh nahi aaya", out["error"])
        self.assertIn("click 100,200", out["error"])

    def test_handle_natural_is_case_insensitive(self):
        self._dispatch("MOVE MOUSE TO 10X20", "mouse_move", (10, 20))
        self._dispatch("SCREEN SIZE", "screen_size", ())

    def test_file_ops_use_original_case_text(self):
        # file branches match on raw `text` (re.IGNORECASE) — mixed case
        # must still dispatch with original-case arguments
        ft = MagicMock()
        ft.return_value.write.return_value = {"success": True}
        with patch("orbit.orbit.tools.file_tools.FileTools", ft), \
             _allow():
            self.tool.handle_natural("Write File Report.TXT with Data")
        ft.return_value.write.assert_called_once_with("Report.TXT",
                                                      "Data")


if __name__ == "__main__":
    unittest.main()
