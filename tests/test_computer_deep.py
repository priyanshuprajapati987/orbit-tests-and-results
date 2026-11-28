"""Deep tests for orbit/orbit/tools/computer.py (Loop 23/2)."""

import os
import platform
import re
import shlex
import subprocess
import unittest
from unittest import mock

from orbit.orbit.tools import computer as comp


class GateTests(unittest.TestCase):
    def test_gate_allowed(self):
        with mock.patch("orbit.orbit.tools.computer.check_tool",
                        return_value=mock.MagicMock(allowed=True)):
            self.assertIsNone(comp.ComputerTool()._gate("x"))

    def test_gate_blocked(self):
        dec = mock.MagicMock(allowed=False, reason="nope")
        dec.to_dict.return_value = {"r": 1}
        with mock.patch("orbit.orbit.tools.computer.check_tool", return_value=dec):
            r = comp.ComputerTool()._gate("x")
        self.assertEqual(r, {"success": False,
                             "error": "Access denied (nope): x",
                             "policy": {"r": 1}})


class PsQuoteTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(comp.ComputerTool._ps_quote("hi"), "'hi'")

    def test_quotes(self):
        self.assertEqual(comp.ComputerTool._ps_quote("a'b"), "'a''b'")

    def test_newline(self):
        self.assertEqual(comp.ComputerTool._ps_quote("a\nb"), "'a`nb'")

    def test_cr(self):
        self.assertEqual(comp.ComputerTool._ps_quote("a\rb"), "'a`rb'")

    def test_tab(self):
        self.assertEqual(comp.ComputerTool._ps_quote("a\tb"), "'a`tb'")


class RunPowershellTests(unittest.TestCase):
    def test_success(self):
        tool = comp.ComputerTool()
        r = mock.MagicMock(stdout="  out  ", stderr="  err  ", returncode=0)
        with mock.patch("subprocess.run", return_value=r):
            self.assertEqual(tool._run_powershell("cmd"),
                             {"success": True, "stdout": "out",
                              "stderr": "err", "returncode": 0})

    def test_truncation(self):
        tool = comp.ComputerTool()
        r = mock.MagicMock(stdout="x" * 3000, stderr="y" * 600, returncode=0)
        with mock.patch("subprocess.run", return_value=r):
            res = tool._run_powershell("cmd")
        self.assertEqual(len(res["stdout"]), 2000)
        self.assertEqual(len(res["stderr"]), 500)

    def test_timeout(self):
        tool = comp.ComputerTool()
        with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("x", 30)):
            self.assertEqual(tool._run_powershell("cmd"),
                             {"success": False, "error": "Command timed out"})

    def test_exception(self):
        tool = comp.ComputerTool()
        with mock.patch("subprocess.run", side_effect=Exception("boom")):
            self.assertEqual(tool._run_powershell("cmd"),
                             {"success": False, "error": "boom"})


class GetClipboardTests(unittest.TestCase):
    def test_with_stdout(self):
        tool = comp.ComputerTool()
        with mock.patch.object(tool, "_run_powershell",
                              return_value={"success": True, "stdout": "hello"}):
            r = tool.get_clipboard()
        self.assertEqual(r["stdout"], "hello")

    def test_empty_stdout_replaced(self):
        tool = comp.ComputerTool()
        with mock.patch.object(tool, "_run_powershell",
                              return_value={"success": True, "stdout": "   "}):
            r = tool.get_clipboard()
        self.assertIn("Clipboard mein image", r["stdout"])

    def test_failure(self):
        tool = comp.ComputerTool()
        with mock.patch.object(tool, "_run_powershell",
                              return_value={"success": False}):
            r = tool.get_clipboard()
        self.assertFalse(r["success"])


class SetClipboardTests(unittest.TestCase):
    def test_gate_blocked(self):
        tool = comp.ComputerTool()
        with mock.patch.object(tool, "_gate", return_value={"success": False, "error": "denied"}):
            r = tool.set_clipboard("hi")
        self.assertEqual(r, {"success": False, "error": "denied"})

    def test_success(self):
        tool = comp.ComputerTool()
        with mock.patch.object(tool, "_gate", return_value=None), \
                mock.patch.object(tool, "_run_powershell", return_value={"success": True}) as rp:
            r = tool.set_clipboard("hi")
        rp.assert_called_once()
        self.assertTrue(r["success"])


class RunCommandTests(unittest.TestCase):
    def test_dangerous_chars(self):
        tool = comp.ComputerTool()
        for c in [";", "&", "|", "`", "$", "(", ")", "{", "}", "[", "]", "!", "#", "~"]:
            r = tool.run_command(f"tasklist {c}")
            self.assertFalse(r["success"])
            self.assertEqual(r["error"], "Shell metacharacters not allowed")

    def test_not_allowed(self):
        tool = comp.ComputerTool()
        r = tool.run_command("rm -rf /")
        self.assertFalse(r["success"])
        self.assertIn("not allowed", r["error"])

    def test_empty_command(self):
        tool = comp.ComputerTool()
        r = tool.run_command("")
        self.assertFalse(r["success"])
        self.assertIn("not allowed", r["error"])

    def test_success(self):
        tool = comp.ComputerTool()
        result = mock.MagicMock(returncode=0, stdout="out\n", stderr="err\n")
        with mock.patch("subprocess.run", return_value=result), \
                mock.patch("platform.system", return_value="Windows"):
            r = tool.run_command("tasklist")
        self.assertTrue(r["success"])
        self.assertEqual(r["stdout"], "out")
        self.assertEqual(r["stderr"], "err")
        self.assertEqual(r["returncode"], 0)

    def test_timeout(self):
        tool = comp.ComputerTool()
        with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("x", 30)), \
                mock.patch("platform.system", return_value="Windows"):
            r = tool.run_command("tasklist")
        self.assertFalse(r["success"])
        self.assertEqual(r["error"], "Command timed out")

    def test_exception(self):
        tool = comp.ComputerTool()
        with mock.patch("subprocess.run", side_effect=Exception("boom")), \
                mock.patch("platform.system", return_value="Windows"):
            r = tool.run_command("tasklist")
        self.assertFalse(r["success"])
        self.assertEqual(r["error"], "boom")

    def test_shlex_posix_false_on_windows(self):
        tool = comp.ComputerTool()
        result = mock.MagicMock(returncode=0, stdout="", stderr="")
        with mock.patch("subprocess.run", return_value=result) as run, \
                mock.patch("platform.system", return_value="Windows"):
            tool.run_command("tasklist /v")
        args = run.call_args.args[0]
        self.assertIsInstance(args, list)

    def test_shlex_posix_on_non_windows(self):
        tool = comp.ComputerTool()
        result = mock.MagicMock(returncode=0, stdout="", stderr="")
        with mock.patch("subprocess.run", return_value=result) as run, \
                mock.patch("platform.system", return_value="Linux"):
            tool.run_command("ps aux")
        args = run.call_args.args[0]
        self.assertIsInstance(args, list)


class ListProcessesTests(unittest.TestCase):
    def test_windows(self):
        tool = comp.ComputerTool()
        tool.os = "Windows"
        with mock.patch.object(tool, "_run_powershell", return_value={"success": True}) as rp:
            r = tool.list_processes()
        rp.assert_called_once()
        self.assertTrue(r["success"])

    def test_non_windows(self):
        tool = comp.ComputerTool()
        tool.os = "Linux"
        with mock.patch.object(tool, "run_command", return_value={"success": True}) as rc:
            r = tool.list_processes()
        rc.assert_called_once_with("ps aux --no-headers")
        self.assertTrue(r["success"])


class ListFilesTests(unittest.TestCase):
    def test_non_windows(self):
        tool = comp.ComputerTool()
        tool.os = "Linux"
        r = tool.list_files(".")
        self.assertEqual(r, {"success": False, "error": "File listing on non-Windows not implemented"})

    def test_windows(self):
        tool = comp.ComputerTool()
        tool.os = "Windows"
        with mock.patch.object(tool, "_run_powershell", return_value={"success": True, "stdout": "ok"}) as rp:
            r = tool.list_files("C:\\")
        rp.assert_called_once()
        self.assertTrue(r["success"])


class ListFilesResponseTests(unittest.TestCase):
    def _tool(self):
        return comp.ComputerTool()

    def test_success_false_passthrough(self):
        tool = self._tool()
        with mock.patch.object(tool, "list_files", return_value={"success": False, "error": "boom"}):
            r = tool._list_files_response("list files", ".")
        self.assertEqual(r, {"success": False, "error": "boom"})

    def test_no_meta_header(self):
        tool = self._tool()
        with mock.patch.object(tool, "list_files", return_value={"success": True, "stdout": "a.txt\nb.py"}):
            r = tool._list_files_response("list files", ".")
        self.assertTrue(r["success"])
        self.assertIn("Found 0 files", r["stdout"])
        self.assertIn("a.txt", r["stdout"])

    def test_meta_header_parsed(self):
        tool = self._tool()
        stdout = "__META__ 5 2\na.txt\nb.py\n"
        with mock.patch.object(tool, "list_files", return_value={"success": True, "stdout": stdout}):
            r = tool._list_files_response("list files", ".")
        self.assertTrue(r["success"])
        self.assertIn("Found 5 files", r["stdout"])
        self.assertIn("(2 Python files)", r["stdout"])

    def test_meta_header_invalid(self):
        tool = self._tool()
        stdout = "__META__ abc def\na.txt\n"
        with mock.patch.object(tool, "list_files", return_value={"success": True, "stdout": stdout}):
            r = tool._list_files_response("list files", ".")
        self.assertTrue(r["success"])
        # total=0, py_total=0 (parse failed) but names still shown
        self.assertIn("Found 0 files", r["stdout"])

    def test_type_filter_python(self):
        tool = self._tool()
        stdout = "__META__ 5 2\na.py\nb.txt\nc.py\n"
        with mock.patch.object(tool, "list_files", return_value={"success": True, "stdout": stdout}):
            r = tool._list_files_response("list python files", ".")
        self.assertTrue(r["success"])
        self.assertIn("Found 2 Python files", r["stdout"])
        self.assertIn("a.py", r["stdout"])
        self.assertNotIn("b.txt", r["stdout"])

    def test_type_filter_py_keyword(self):
        tool = self._tool()
        stdout = "__META__ 5 2\na.py\nb.txt\n"
        with mock.patch.object(tool, "list_files", return_value={"success": True, "stdout": stdout}):
            r = tool._list_files_response("list py files", ".")
        self.assertIn("Found 5 files", r["stdout"])

    def test_type_filter_no_files_keyword(self):
        tool = self._tool()
        stdout = "__META__ 5 2\na.py\nb.txt\n"
        with mock.patch.object(tool, "list_files", return_value={"success": True, "stdout": stdout}):
            r = tool._list_files_response("list all", ".")
        # "files" not in text_lower -> no type filter -> shows all
        self.assertIn("Found 5 files", r["stdout"])

    def test_type_filter_javascript(self):
        tool = self._tool()
        stdout = "__META__ 5 0\na.js\nb.py\n"
        with mock.patch.object(tool, "list_files", return_value={"success": True, "stdout": stdout}):
            r = tool._list_files_response("list javascript files", ".")
        self.assertIn("Found 1 JavaScript files", r["stdout"])
        self.assertIn("a.js", r["stdout"])

    def test_type_filter_json(self):
        tool = self._tool()
        stdout = "__META__ 5 0\na.json\nb.py\n"
        with mock.patch.object(tool, "list_files", return_value={"success": True, "stdout": stdout}):
            r = tool._list_files_response("list json files", ".")
        self.assertIn("Found 1 JSON files", r["stdout"])

    def test_type_filter_csv(self):
        tool = self._tool()
        stdout = "__META__ 5 0\na.csv\n"
        with mock.patch.object(tool, "list_files", return_value={"success": True, "stdout": stdout}):
            r = tool._list_files_response("list csv files", ".")
        self.assertIn("Found 1 CSV files", r["stdout"])

    def test_type_filter_markdown(self):
        tool = self._tool()
        stdout = "__META__ 5 0\na.md\n"
        with mock.patch.object(tool, "list_files", return_value={"success": True, "stdout": stdout}):
            r = tool._list_files_response("list markdown files", ".")
        self.assertIn("Found 1 Markdown files", r["stdout"])

    def test_type_filter_md(self):
        tool = self._tool()
        stdout = "__META__ 5 0\na.md\n"
        with mock.patch.object(tool, "list_files", return_value={"success": True, "stdout": stdout}):
            r = tool._list_files_response("list md files", ".")
        self.assertIn("Found 1 Markdown files", r["stdout"])

    def test_type_filter_text(self):
        tool = self._tool()
        stdout = "__META__ 5 0\na.txt\n"
        with mock.patch.object(tool, "list_files", return_value={"success": True, "stdout": stdout}):
            r = tool._list_files_response("list text files", ".")
        self.assertIn("Found 1 Text files", r["stdout"])

    def test_type_filter_txt(self):
        tool = self._tool()
        stdout = "__META__ 5 0\na.txt\n"
        with mock.patch.object(tool, "list_files", return_value={"success": True, "stdout": stdout}):
            r = tool._list_files_response("list txt files", ".")
        self.assertIn("Found 1 Text files", r["stdout"])

    def test_type_filter_html(self):
        tool = self._tool()
        stdout = "__META__ 5 0\na.html\n"
        with mock.patch.object(tool, "list_files", return_value={"success": True, "stdout": stdout}):
            r = tool._list_files_response("list html files", ".")
        self.assertIn("Found 1 HTML files", r["stdout"])

    def test_type_filter_css(self):
        tool = self._tool()
        stdout = "__META__ 5 0\na.css\n"
        with mock.patch.object(tool, "list_files", return_value={"success": True, "stdout": stdout}):
            r = tool._list_files_response("list css files", ".")
        self.assertIn("Found 1 CSS files", r["stdout"])

    def test_type_filter_log(self):
        tool = self._tool()
        stdout = "__META__ 5 0\na.log\n"
        with mock.patch.object(tool, "list_files", return_value={"success": True, "stdout": stdout}):
            r = tool._list_files_response("list log files", ".")
        self.assertIn("Found 1 Log files", r["stdout"])

    def test_type_filter_js(self):
        tool = self._tool()
        stdout = "__META__ 5 0\na.js\n"
        with mock.patch.object(tool, "list_files", return_value={"success": True, "stdout": stdout}):
            r = tool._list_files_response("list js files", ".")
        self.assertIn("Found 1 JavaScript files", r["stdout"])

    def test_meta_lines_filtered_from_names(self):
        tool = self._tool()
        stdout = "__META__ 5 2\na.py\n__META__ 1 0\n"
        with mock.patch.object(tool, "list_files", return_value={"success": True, "stdout": stdout}):
            r = tool._list_files_response("list files", ".")
        self.assertNotIn("__META__", r["stdout"].split("Found")[1] if "Found" in r["stdout"] else r["stdout"])


class SystemInfoTests(unittest.TestCase):
    def test_non_windows(self):
        tool = comp.ComputerTool()
        tool.os = "Linux"
        info = tool.system_info()
        self.assertEqual(info, {"os": "Linux", "hostname": __import__("platform").node(),
                                "processor": __import__("platform").processor()})

    def test_windows_success(self):
        tool = comp.ComputerTool()
        tool.os = "Windows"
        with mock.patch.object(tool, "_run_powershell",
                              return_value={"success": True, "stdout": '{"Caption":"Win11"}'}):
            info = tool.system_info()
        self.assertEqual(info["os"], "Windows")
        self.assertEqual(info["os_detail"], '{"Caption":"Win11"}')

    def test_windows_fail(self):
        tool = comp.ComputerTool()
        tool.os = "Windows"
        with mock.patch.object(tool, "_run_powershell",
                              return_value={"success": False}):
            info = tool.system_info()
        self.assertEqual(info["os"], "Windows")
        self.assertNotIn("os_detail", info)


class OpenAppTests(unittest.TestCase):
    def test_gate_blocked(self):
        tool = comp.ComputerTool()
        tool.os = "Windows"
        with mock.patch.object(tool, "_gate", return_value={"success": False, "error": "denied"}):
            r = tool.open_app("notepad")
        self.assertEqual(r, {"success": False, "error": "denied"})

    def test_empty_name(self):
        tool = comp.ComputerTool()
        tool.os = "Windows"
        with mock.patch.object(tool, "_gate", return_value=None):
            r = tool.open_app("   ")
        self.assertEqual(r, {"success": False, "error": "App name required"})

    def test_unknown_app(self):
        tool = comp.ComputerTool()
        tool.os = "Windows"
        with mock.patch.object(tool, "_gate", return_value=None):
            r = tool.open_app("foobar")
        self.assertFalse(r["success"])
        self.assertIn("not in known apps", r["error"])
        self.assertIn("Available:", r["error"])

    def test_startfile_success(self):
        tool = comp.ComputerTool()
        tool.os = "Windows"
        with mock.patch.object(tool, "_gate", return_value=None), \
                mock.patch("os.startfile") as sf:
            r = tool.open_app("notepad")
        sf.assert_called_once_with("notepad.exe")
        self.assertTrue(r["success"])
        self.assertIn("Opened: notepad", r["stdout"])

    def test_startfile_filenotfound_fallback_success(self):
        tool = comp.ComputerTool()
        tool.os = "Windows"
        with mock.patch.object(tool, "_gate", return_value=None), \
                mock.patch("os.startfile", side_effect=FileNotFoundError()), \
                mock.patch.object(tool, "_run_powershell",
                                  return_value={"success": True}) as rp:
            r = tool.open_app("notepad")
        self.assertTrue(r["success"])
        self.assertIn("Opened: notepad", r["stdout"])

    def test_startfile_filenotfound_fallback_fail(self):
        tool = comp.ComputerTool()
        tool.os = "Windows"
        with mock.patch.object(tool, "_gate", return_value=None), \
                mock.patch("os.startfile", side_effect=FileNotFoundError()), \
                mock.patch.object(tool, "_run_powershell",
                                  return_value={"success": False}):
            r = tool.open_app("notepad")
        self.assertFalse(r["success"])
        self.assertIn("Could not find or open", r["error"])

    def test_startfile_other_exception(self):
        tool = comp.ComputerTool()
        tool.os = "Windows"
        with mock.patch.object(tool, "_gate", return_value=None), \
                mock.patch("os.startfile", side_effect=RuntimeError("boom")):
            r = tool.open_app("notepad")
        self.assertFalse(r["success"])
        self.assertIn("Failed to open", r["error"])

    def test_non_windows(self):
        tool = comp.ComputerTool()
        tool.os = "Linux"
        with mock.patch.object(tool, "_gate", return_value=None):
            r = tool.open_app("notepad")
        self.assertEqual(r, {"success": False,
                             "error": "Opening apps not supported on Linux"})

    def test_quoted_app_name(self):
        tool = comp.ComputerTool()
        tool.os = "Windows"
        with mock.patch.object(tool, "_gate", return_value=None), \
                mock.patch("os.startfile") as sf:
            r = tool.open_app("'notepad'")
        sf.assert_called_once_with("notepad.exe")


class LaunchUrlTests(unittest.TestCase):
    def test_gate_blocked(self):
        tool = comp.ComputerTool()
        with mock.patch.object(tool, "_gate", return_value={"success": False, "error": "denied"}):
            r = tool.launch_url("x.com")
        self.assertEqual(r, {"success": False, "error": "denied"})

    def test_adds_https(self):
        tool = comp.ComputerTool()
        with mock.patch.object(tool, "_gate", return_value=None), \
                mock.patch("webbrowser.open") as wb:
            r = tool.launch_url("google.com")
        wb.assert_called_once_with("https://google.com")
        self.assertTrue(r["success"])

    def test_already_https(self):
        tool = comp.ComputerTool()
        with mock.patch.object(tool, "_gate", return_value=None), \
                mock.patch("webbrowser.open") as wb:
            r = tool.launch_url("https://x.com")
        wb.assert_called_once_with("https://x.com")

    def test_http_url(self):
        tool = comp.ComputerTool()
        with mock.patch.object(tool, "_gate", return_value=None), \
                mock.patch("webbrowser.open") as wb:
            r = tool.launch_url("http://x.com")
        wb.assert_called_once_with("http://x.com")

    def test_exception(self):
        tool = comp.ComputerTool()
        with mock.patch.object(tool, "_gate", return_value=None), \
                mock.patch("webbrowser.open", side_effect=Exception("boom")):
            r = tool.launch_url("x.com")
        self.assertFalse(r["success"])
        self.assertIn("Failed to open URL", r["error"])

    def test_strips(self):
        tool = comp.ComputerTool()
        with mock.patch.object(tool, "_gate", return_value=None), \
                mock.patch("webbrowser.open") as wb:
            tool.launch_url("  x.com  ")
        wb.assert_called_once_with("https://x.com")


class HandleNaturalTests(unittest.TestCase):
    def setUp(self):
        self.tool = comp.ComputerTool()
        self.tool.os = "Windows"

    def test_open_url(self):
        with mock.patch.object(self.tool, "launch_url", return_value={"success": True}) as lu:
            r = self.tool.handle_natural("open google.com")
        lu.assert_called_once_with("google.com")
        self.assertTrue(r["success"])

    def test_open_url_with_in_browser(self):
        with mock.patch.object(self.tool, "launch_url", return_value={"success": True}) as lu:
            r = self.tool.handle_natural("open google.com in chrome")
        lu.assert_called_once_with("google.com")

    def test_open_web_shortcut(self):
        with mock.patch.object(self.tool, "launch_url", return_value={"success": True}) as lu:
            r = self.tool.handle_natural("open gmail")
        lu.assert_called_once_with("https://mail.google.com")

    def test_open_app(self):
        with mock.patch.object(self.tool, "open_app", return_value={"success": True}) as oa:
            r = self.tool.handle_natural("open notepad")
        oa.assert_called_once_with("notepad")

    def test_open_chrome_url(self):
        with mock.patch.object(self.tool, "launch_url", return_value={"success": True}) as lu:
            r = self.tool.handle_natural("open youtube")
        lu.assert_called_once_with("https://youtube.com")

    def test_open_kholo(self):
        with mock.patch.object(self.tool, "open_app", return_value={"success": True}) as oa:
            r = self.tool.handle_natural("kholo notepad")
        oa.assert_called_once_with("notepad")

    def test_clipboard_copy(self):
        with mock.patch.object(self.tool, "set_clipboard", return_value={"success": True}) as sc:
            r = self.tool.handle_natural("copy hello to clipboard")
        sc.assert_called_once()
        self.assertTrue(r["success"])

    def test_clipboard_copy_with_text_wrapper(self):
        with mock.patch.object(self.tool, "set_clipboard", return_value={"success": True}) as sc:
            r = self.tool.handle_natural("copy the text hello to the clipboard")
        sc.assert_called_once()

    def test_clipboard_get(self):
        with mock.patch.object(self.tool, "get_clipboard", return_value={"success": True}):
            r = self.tool.handle_natural("clipboard")
        self.assertTrue(r["success"])

    def test_process_kill(self):
        with mock.patch.object(self.tool, "_gate", return_value=None), \
                mock.patch.object(self.tool, "_run_powershell", return_value={"success": True}) as rp:
            r = self.tool.handle_natural("kill process chrome")
        self.assertTrue(r["success"])

    def test_process_list(self):
        with mock.patch.object(self.tool, "list_processes", return_value={"success": True}):
            r = self.tool.handle_natural("list processes")
        self.assertTrue(r["success"])

    def test_list_files_basic(self):
        with mock.patch.object(self.tool, "_list_files_response", return_value={"success": True}) as lf:
            r = self.tool.handle_natural("list files")
        lf.assert_called_once()

    def test_list_files_in_path(self):
        with mock.patch.object(self.tool, "_list_files_response", return_value={"success": True}) as lf:
            r = self.tool.handle_natural("list files in /tmp")
        lf.assert_called_once()

    def test_system_info(self):
        with mock.patch.object(self.tool, "system_info", return_value={"os": "Windows"}):
            r = self.tool.handle_natural("system info")
        self.assertTrue(r["success"])
        self.assertEqual(r["data"]["os"], "Windows")

    def test_spec(self):
        with mock.patch.object(self.tool, "system_info", return_value={"os": "Windows"}):
            r = self.tool.handle_natural("spec")
        self.assertTrue(r["success"])

    def test_screenshot(self):
        with mock.patch("orbit.orbit.tools.cua_computer.is_available", return_value=True), \
                mock.patch("orbit.orbit.tools.cua_computer.ensure_daemon"), \
                mock.patch("orbit.orbit.tools.cua_computer.CuaComputerTool") as C:
            cc = mock.MagicMock()
            cc.screenshot.return_value = {"screenshot_base64": "abc"}
            C.return_value = cc
            r = self.tool.handle_natural("screenshot")
        self.assertTrue(r["success"])
        self.assertEqual(r["screenshot_base64"], "abc")

    def test_ui_tree(self):
        with mock.patch("orbit.orbit.tools.cua_computer.is_available", return_value=True), \
                mock.patch("orbit.orbit.tools.cua_computer.CuaComputerTool") as C:
            cc = mock.MagicMock()
            cc.get_desktop_state.return_value = {"tree_markdown": "tree"}
            C.return_value = cc
            r = self.tool.handle_natural("ui tree")
        self.assertTrue(r["success"])
        self.assertEqual(r["data"], "tree")

    def test_ui_tree_error(self):
        with mock.patch("orbit.orbit.tools.cua_computer.is_available", return_value=True), \
                mock.patch("orbit.orbit.tools.cua_computer.CuaComputerTool") as C:
            cc = mock.MagicMock()
            cc.get_desktop_state.return_value = {"error": "boom"}
            cc.screenshot.return_value = {"screenshot_base64": "abc"}
            C.return_value = cc
            r = self.tool.handle_natural("ui tree")
        self.assertTrue(r["success"])
        self.assertEqual(r["screenshot_base64"], "abc")

    def test_screenshot_error(self):
        with mock.patch("orbit.orbit.tools.cua_computer.is_available", return_value=True), \
                mock.patch("orbit.orbit.tools.cua_computer.CuaComputerTool") as C:
            cc = mock.MagicMock()
            cc.get_desktop_state.return_value = {"error": "boom"}
            cc.screenshot.return_value = {"error": "fail"}
            C.return_value = cc
            r = self.tool.handle_natural("screen")
        self.assertFalse(r["success"])
        self.assertEqual(r["error"], "ORBIT ye command directly run nahi kar sakta. Koi specific tool batao (clipboard, process, file, etc).")

    def test_fallback(self):
        r = self.tool.handle_natural("blah blah")
        self.assertFalse(r["success"])
        self.assertIn("ORBIT ye command directly", r["error"])


if __name__ == "__main__":
    unittest.main()
