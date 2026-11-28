"""Deep tests for orbit/orbit/naturo_tool.py (Loop 22/3)."""

import json
import shutil
import subprocess
import threading
import unittest
from unittest import mock

from orbit.orbit import naturo_tool as nt


class FindNaturoTests(unittest.TestCase):
    def test_found_on_path(self):
        tool = nt.NaturoTool()
        with mock.patch("shutil.which", return_value="/usr/bin/naturo"):
            self.assertEqual(tool._find_naturo(), "/usr/bin/naturo")

    def test_pip_location_success(self):
        tool = nt.NaturoTool()
        r = mock.MagicMock(returncode=0)
        with mock.patch("shutil.which", return_value=None), \
                mock.patch("subprocess.run", return_value=r):
            self.assertEqual(tool._find_naturo(), "py -m naturo")

    def test_pip_location_fail(self):
        tool = nt.NaturoTool()
        r = mock.MagicMock(returncode=1)
        with mock.patch("shutil.which", return_value=None), \
                mock.patch("subprocess.run", return_value=r):
            self.assertIsNone(tool._find_naturo())

    def test_pip_location_timeout(self):
        tool = nt.NaturoTool()
        with mock.patch("shutil.which", return_value=None), \
                mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("x", 10)):
            self.assertIsNone(tool._find_naturo())

    def test_pip_location_filenotfound(self):
        tool = nt.NaturoTool()
        with mock.patch("shutil.which", return_value=None), \
                mock.patch("subprocess.run", side_effect=FileNotFoundError()):
            self.assertIsNone(tool._find_naturo())

    def test_not_found(self):
        tool = nt.NaturoTool()
        r = mock.MagicMock(returncode=1)
        with mock.patch("shutil.which", return_value=None), \
                mock.patch("subprocess.run", return_value=r):
            self.assertIsNone(tool._find_naturo())


class IsAvailableTests(unittest.TestCase):
    def test_cached_true(self):
        tool = nt.NaturoTool()
        tool._available = True
        tool._naturo_path = "py -m naturo"
        self.assertTrue(tool.is_available())

    def test_cached_false(self):
        tool = nt.NaturoTool()
        tool._available = False
        self.assertFalse(tool.is_available())

    def test_find_success_logs(self):
        tool = nt.NaturoTool()
        with mock.patch.object(tool, "_find_naturo", return_value="/usr/bin/naturo"), \
                mock.patch.object(nt, "logger") as lg:
            self.assertTrue(tool.is_available())
        self.assertEqual(tool._naturo_path, "/usr/bin/naturo")
        lg.info.assert_called_once()

    def test_find_fail_logs_debug(self):
        tool = nt.NaturoTool()
        with mock.patch.object(tool, "_find_naturo", return_value=None), \
                mock.patch.object(nt, "logger") as lg:
            self.assertFalse(tool.is_available())
        lg.debug.assert_called_once()

    def test_reset_availability(self):
        tool = nt.NaturoTool()
        tool._available = True
        tool.reset_availability()
        self.assertIsNone(tool._available)


class RunTests(unittest.TestCase):
    def _tool_available(self):
        tool = nt.NaturoTool()
        tool._available = True
        tool._naturo_path = "naturo"
        return tool

    def test_not_available_returns_none(self):
        tool = nt.NaturoTool()
        tool._available = False
        self.assertIsNone(tool._run(["capture"]))

    def test_success_json_dict(self):
        tool = self._tool_available()
        r = mock.MagicMock(returncode=0, stdout='{"ok": true}', stderr="")
        with mock.patch("subprocess.run", return_value=r):
            self.assertEqual(tool._run(["capture"]), {"ok": True})

    def test_success_json_list_returns_empty_dict(self):
        tool = self._tool_available()
        r = mock.MagicMock(returncode=0, stdout='[1, 2]', stderr="")
        with mock.patch("subprocess.run", return_value=r):
            self.assertEqual(tool._run(["capture"]), {})

    def test_success_non_json(self):
        tool = self._tool_available()
        r = mock.MagicMock(returncode=0, stdout="  hello  ", stderr="")
        with mock.patch("subprocess.run", return_value=r):
            self.assertEqual(tool._run(["capture"]), {"output": "hello"})

    def test_success_empty_stdout(self):
        tool = self._tool_available()
        r = mock.MagicMock(returncode=0, stdout="   ", stderr="")
        with mock.patch("subprocess.run", return_value=r):
            self.assertEqual(tool._run(["capture"]), {"status": "ok"})

    def test_failure(self):
        tool = self._tool_available()
        r = mock.MagicMock(returncode=1, stdout="", stderr="  err msg  ")
        with mock.patch("subprocess.run", return_value=r):
            self.assertEqual(tool._run(["capture"]), {"error": "err msg"})

    def test_failure_stderr_truncated_200(self):
        tool = self._tool_available()
        r = mock.MagicMock(returncode=1, stdout="", stderr="e" * 300)
        with mock.patch("subprocess.run", return_value=r):
            res = tool._run(["capture"])
        self.assertEqual(len(res["error"]), 200)

    def test_timeout(self):
        tool = self._tool_available()
        with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("x", 10)):
            self.assertEqual(tool._run(["capture"]), {"error": "timeout"})

    def test_filenotfound_sets_unavailable(self):
        tool = self._tool_available()
        with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
            self.assertIsNone(tool._run(["capture"]))
        self.assertFalse(tool._available)

    def test_cmd_includes_json_flag(self):
        tool = self._tool_available()
        tool._naturo_path = "naturo"
        r = mock.MagicMock(returncode=0, stdout='{"ok":true}', stderr="")
        with mock.patch("subprocess.run", return_value=r) as run:
            tool._run(["capture", "--path", "x.png"])
        cmd = run.call_args.args[0]
        self.assertEqual(cmd, ["naturo", "capture", "--path", "x.png", "-j"])

    def test_pip_path_split(self):
        tool = self._tool_available()
        tool._naturo_path = "py -m naturo"
        r = mock.MagicMock(returncode=0, stdout='{"ok":true}', stderr="")
        with mock.patch("subprocess.run", return_value=r) as run:
            tool._run(["version"])
        cmd = run.call_args.args[0]
        self.assertEqual(cmd, ["py", "-m", "naturo", "version", "-j"])

    def test_timeout_param_passed(self):
        tool = self._tool_available()
        r = mock.MagicMock(returncode=0, stdout='{"ok":true}', stderr="")
        with mock.patch("subprocess.run", return_value=r) as run:
            tool._run(["capture"], timeout=60)
        self.assertEqual(run.call_args.kwargs["timeout"], 60)


class MethodDispatchTests(unittest.TestCase):
    """Call every public method once to cover arg-building lines."""

    def setUp(self):
        self.tool = nt.NaturoTool()
        self.tool._available = True
        self.tool._naturo_path = "naturo"
        self.mock_run = mock.patch.object(self.tool, "_run", return_value={"ok": True})
        self.mock_run.start()
        self.addCleanup(self.mock_run.stop)

    def test_capture(self):
        self.tool.capture("s.png", app="Notepad")
        self.tool._run.assert_called_with(["capture", "--path", "s.png", "--app", "Notepad"])

    def test_capture_no_app(self):
        self.tool.capture()
        self.tool._run.assert_called_with(["capture", "--path", "screenshot.png"])

    def test_see(self):
        self.tool.see(app="Notepad", depth=3, cascade=True)
        self.tool._run.assert_called_with(["see", "--depth", "3", "--app", "Notepad", "--cascade"],
                                         timeout=60)

    def test_see_no_opts(self):
        self.tool.see()
        self.tool._run.assert_called_with(["see", "--depth", "5"], timeout=60)

    def test_find(self):
        self.tool.find("button", app="Notepad")
        self.tool._run.assert_called_with(["find", "button", "--app", "Notepad"])

    def test_find_no_app(self):
        self.tool.find("button")
        self.tool._run.assert_called_with(["find", "button"])

    def test_click(self):
        self.tool.click("Save", app="Notepad")
        self.tool._run.assert_called_with(["click", "Save", "--app", "Notepad"])

    def test_click_no_app(self):
        self.tool.click("Save")
        self.tool._run.assert_called_with(["click", "Save"])

    def test_type_text(self):
        self.tool.type_text("hi", app="Notepad", paste=True)
        self.tool._run.assert_called_with(["type", "hi", "--app", "Notepad", "--paste"])

    def test_type_text_no_opts(self):
        self.tool.type_text("hi")
        self.tool._run.assert_called_with(["type", "hi"])

    def test_press(self):
        self.tool.press("ctrl+s")
        self.tool._run.assert_called_with(["press", "ctrl+s"])

    def test_scroll(self):
        self.tool.scroll("up", 5)
        self.tool._run.assert_called_with(["scroll", "up", "5"])

    def test_scroll_defaults(self):
        self.tool.scroll()
        self.tool._run.assert_called_with(["scroll", "down", "3"])

    def test_get_element_ref(self):
        self.tool.get_element(ref="e1")
        self.tool._run.assert_called_with(["get", "e1"])

    def test_get_element_aid(self):
        self.tool.get_element(aid="a1")
        self.tool._run.assert_called_with(["get", "--aid", "a1"])

    def test_get_element_role_name(self):
        self.tool.get_element(role="button", name="Save")
        self.tool._run.assert_called_with(["get", "--role", "button", "--name", "Save"])

    def test_get_element_none(self):
        self.assertIsNone(self.tool.get_element())

    def test_set_element(self):
        self.tool.set_element("ref", "val", toggle=True, select=True)
        self.tool._run.assert_called_with(["set", "ref", "val", "--toggle", "--select"])

    def test_set_element_no_opts(self):
        self.tool.set_element("ref", "val")
        self.tool._run.assert_called_with(["set", "ref", "val"])

    def test_app_launch(self):
        self.tool.app_launch("notepad")
        self.tool._run.assert_called_with(["app", "launch", "notepad"])

    def test_app_quit(self):
        self.tool.app_quit("notepad", force=True)
        self.tool._run.assert_called_with(["app", "quit", "notepad", "--force"])

    def test_app_quit_no_force(self):
        self.tool.app_quit("notepad")
        self.tool._run.assert_called_with(["app", "quit", "notepad"])

    def test_app_focus(self):
        self.tool.app_focus("notepad")
        self.tool._run.assert_called_with(["app", "focus", "notepad"])

    def test_app_list(self):
        self.tool.app_list()
        self.tool._run.assert_called_with(["app", "list"])

    def test_app_windows(self):
        self.tool.app_windows("notepad")
        self.tool._run.assert_called_with(["app", "windows", "--app", "notepad"])

    def test_app_windows_no_app(self):
        self.tool.app_windows()
        self.tool._run.assert_called_with(["app", "windows"])

    def test_app_inspect(self):
        self.tool.app_inspect("notepad")
        self.tool._run.assert_called_with(["app", "inspect", "notepad"], timeout=15)

    def test_app_minimize(self):
        self.tool.app_minimize("notepad")
        self.tool._run.assert_called_with(["app", "minimize", "notepad"])

    def test_app_restore(self):
        self.tool.app_restore("notepad")
        self.tool._run.assert_called_with(["app", "restore", "notepad"])

    def test_app_maximize(self):
        self.tool.app_maximize("notepad")
        self.tool._run.assert_called_with(["app", "maximize", "notepad"])

    def test_dialog_detect(self):
        self.tool.dialog_detect()
        self.tool._run.assert_called_with(["dialog", "detect"])

    def test_dialog_accept(self):
        self.tool.dialog_accept()
        self.tool._run.assert_called_with(["dialog", "accept"])

    def test_dialog_dismiss(self):
        self.tool.dialog_dismiss()
        self.tool._run.assert_called_with(["dialog", "dismiss"])

    def test_taskbar_list(self):
        self.tool.taskbar_list()
        self.tool._run.assert_called_with(["taskbar", "list"])

    def test_taskbar_click(self):
        self.tool.taskbar_click("start")
        self.tool._run.assert_called_with(["taskbar", "click", "start"])

    def test_tray_list(self):
        self.tool.tray_list()
        self.tool._run.assert_called_with(["tray", "list"])

    def test_desktop_list(self):
        self.tool.desktop_list()
        self.tool._run.assert_called_with(["desktop", "list"])

    def test_desktop_switch(self):
        self.tool.desktop_switch(2)
        self.tool._run.assert_called_with(["desktop", "switch", "2"])

    def test_desktop_create(self):
        self.tool.desktop_create("work")
        self.tool._run.assert_called_with(["desktop", "create", "--name", "work"])

    def test_desktop_create_no_name(self):
        self.tool.desktop_create()
        self.tool._run.assert_called_with(["desktop", "create"])

    def test_clipboard_get(self):
        self.tool.clipboard_get()
        self.tool._run.assert_called_with(["clipboard", "get"])

    def test_clipboard_set(self):
        self.tool.clipboard_set("hi")
        self.tool._run.assert_called_with(["clipboard", "set", "hi"])

    def test_browser_launch(self):
        self.tool.browser_launch("profile1")
        self.tool._run.assert_called_with(["browser", "launch", "--profile", "profile1"])

    def test_browser_launch_no_profile(self):
        self.tool.browser_launch()
        self.tool._run.assert_called_with(["browser", "launch"])

    def test_browser_navigate(self):
        self.tool.browser_navigate("https://x.com")
        self.tool._run.assert_called_with(["browser", "navigate", "https://x.com"])

    def test_browser_screenshot(self):
        self.tool.browser_screenshot("shot.png")
        self.tool._run.assert_called_with(["browser", "screenshot", "--path", "shot.png"])

    def test_browser_screenshot_default(self):
        self.tool.browser_screenshot()
        self.tool._run.assert_called_with(["browser", "screenshot", "--path", "browser.png"])

    def test_browser_find(self):
        self.tool.browser_find("button")
        self.tool._run.assert_called_with(["browser", "find", "button"])

    def test_browser_click(self):
        self.tool.browser_click("btn")
        self.tool._run.assert_called_with(["browser", "click", "btn"])

    def test_browser_type(self):
        self.tool.browser_type("input", "text")
        self.tool._run.assert_called_with(["browser", "type", "input", "text"])

    def test_record_start(self):
        self.tool.record_start("rec1")
        self.tool._run.assert_called_with(["record", "start", "rec1"])

    def test_record_start_default(self):
        self.tool.record_start()
        self.tool._run.assert_called_with(["record", "start", "recording"])

    def test_record_stop(self):
        self.tool.record_stop()
        self.tool._run.assert_called_with(["record", "stop"])

    def test_record_list(self):
        self.tool.record_list()
        self.tool._run.assert_called_with(["record", "list"])

    def test_highlight(self):
        self.tool.highlight(app="Notepad", ref="e1")
        self.tool._run.assert_called_with(["highlight", "e1", "--app", "Notepad"], timeout=10)

    def test_highlight_no_args(self):
        self.tool.highlight()
        self.tool._run.assert_called_with(["highlight"], timeout=10)

    def test_doctor(self):
        self.tool.doctor()
        self.tool._run.assert_called_with(["doctor"], timeout=15)

    def test_version(self):
        self.tool.version()
        self.tool._run.assert_called_with(["--version"])


class SingletonTests(unittest.TestCase):
    def test_get_naturo_tool(self):
        nt._tool = None
        a = nt.get_naturo_tool()
        b = nt.get_naturo_tool()
        self.assertIs(a, b)
        nt._tool = None

    def test_is_naturo_available(self):
        with mock.patch.object(nt.NaturoTool, "is_available", return_value=True):
            nt._tool = None
            self.assertTrue(nt.is_naturo_available())
            nt._tool = None


class ImportFallbackTests(unittest.TestCase):
    def test_fallback_import(self):
        import importlib
        import sys
        # block orbit.logging_config to force the except branch
        saved = sys.modules.get("orbit.logging_config", _MISSING_NAT)
        sys.modules["orbit.logging_config"] = None
        # also block the relative .logging_config by ensuring parent package path
        try:
            importlib.reload(nt)
            # logger should still be set (via fallback)
            self.assertTrue(hasattr(nt, "logger"))
        finally:
            if saved is _MISSING_NAT:
                sys.modules.pop("orbit.logging_config", None)
            else:
                sys.modules["orbit.logging_config"] = saved
            importlib.reload(nt)

_MISSING_NAT = object()
