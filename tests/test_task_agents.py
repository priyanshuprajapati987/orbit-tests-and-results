"""Unit tests for orbit/orbit/agents/task_agents.py (tools + LLM mocked)."""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.agents.task_agents import TaskAgent, CodeAgent


class TestTaskAgentCanHandle(unittest.TestCase):
    def setUp(self):
        self.agent = TaskAgent()

    def test_instantiation(self):
        self.assertEqual(self.agent.label, "TAS")

    def test_two_keywords(self):
        self.assertTrue(self.agent.can_handle("run the command"))

    def test_intent_single(self):
        self.assertTrue(self.agent.can_handle("run", intent="computer"))

    def test_single_no_intent(self):
        self.assertFalse(self.agent.can_handle("run"))

    def test_none(self):
        self.assertFalse(self.agent.can_handle("hello world"))


class TestTaskAgentFileOps(unittest.TestCase):
    def setUp(self):
        self.agent = TaskAgent()
        self.ft = MagicMock()
        patcher = patch.object(self.agent, "_get_file_tool", return_value=self.ft)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_create_with_content(self):
        self.ft.write.return_value = {"success": True}
        r = self.agent.execute("create notes.txt with hello world")
        self.ft.write.assert_called_once_with("notes.txt", "hello world")
        self.assertIn("success", r)

    def test_move(self):
        self.ft.move.return_value = {"success": True}
        self.agent.execute("move a.txt to b.txt")
        self.ft.move.assert_called_once_with("a.txt", "b.txt")

    def test_rename(self):
        self.ft.move.return_value = {"success": True}
        self.agent.execute("rename a.txt to b.txt")
        self.ft.move.assert_called_once_with("a.txt", "b.txt")

    def test_append_quoted(self):
        self.ft.append.return_value = {"success": True}
        self.agent.execute("append 'line one' to log.txt")
        self.ft.append.assert_called_once_with("log.txt", "line one")

    def test_read_path(self):
        self.ft.read.return_value = {"content": "file contents here"}
        r = self.agent.execute("read notes.txt")
        self.assertEqual(r, "file contents here")

    def test_read_path_error(self):
        self.ft.read.return_value = {"error": "not found"}
        r = self.agent.execute("read notes.txt")
        self.assertIn("Error: not found", r)

    def test_read_path_non_dict(self):
        self.ft.read.return_value = "raw text"
        r = self.agent.execute("read notes.txt")
        self.assertEqual(r, "raw text")

    def test_delete_path(self):
        self.ft.delete.return_value = {"success": True}
        self.agent.execute("delete old.txt")
        self.ft.delete.assert_called_once_with("old.txt")

    def test_list_files(self):
        self.ft.list_dir.return_value = {
            "path": "orbit", "count": 2,
            "items": [{"name": "a.py", "type": "file"}, {"name": "sub", "type": "dir"}],
        }
        r = self.agent.execute("list files in orbit")
        self.assertIn("Files in orbit", r)
        self.assertIn("a.py", r)

    def test_list_python_typed(self):
        self.ft.list_dir.return_value = {
            "path": "src", "count": 2,
            "items": [{"name": "a.py", "type": "file"}, {"name": "b.txt", "type": "file"}],
        }
        r = self.agent.execute("list python files in src")
        self.assertIn("Found 1 Python files", r)

    def test_list_error(self):
        self.ft.list_dir.return_value = {"error": "denied"}
        r = self.agent.execute("list files in secret")
        self.assertIn("Error: denied", r)

    def test_search_files(self):
        self.ft.search.return_value = {"matches": [{"path": "src/a.py"}], "count": 1}
        r = self.agent.execute("search for py files in src")
        self.assertIn("Found 1 files", r)
        self.ft.search.assert_called_once_with("src", "*.py")

    def test_search_no_matches(self):
        self.ft.search.return_value = {"matches": [], "count": 0}
        r = self.agent.execute("search for py files in src")
        self.assertIn("No files matching", r)

    def test_read_pdf(self):
        self.ft.read_pdf.return_value = {"content": "pdf text content"}
        r = self.agent.execute("read pdf report.pdf")
        self.assertEqual(r, "pdf text content")

    def test_file_info(self):
        self.ft.info.return_value = {"path": "C:/x/report.pdf", "type": "file", "size": 123}
        r = self.agent.execute("file info report.pdf")
        self.assertIn("report.pdf", r)
        self.assertIn("123 bytes", r)

    def test_copy_file_unquoted(self):
        self.ft.copy.return_value = {"success": True}
        self.agent.execute("copy file a.txt to b.txt")
        self.ft.copy.assert_called_once_with("a.txt", "b.txt")

    def test_copy_file_quoted(self):
        self.ft.copy.return_value = {"success": True}
        self.agent.execute("copy file 'a.txt' to 'b.txt'")
        self.ft.copy.assert_called_once_with("a.txt", "b.txt")

    def test_copy_file_usage(self):
        r = self.agent.execute("copy file something")
        self.assertIn("Usage: copy file", r)

    def test_edit_file_usage(self):
        r = self.agent.execute("edit file notes.txt")
        self.assertIn("Edit requires", r)

    def test_write_file_usage(self):
        r = self.agent.execute("write file a.txt")
        self.assertIn("Usage: write file", r)

    def test_write_file_quoted(self):
        self.ft.write.return_value = {"success": True}
        self.agent.execute("write file 'a.txt' 'hello world'")
        self.ft.write.assert_called_once_with("a.txt", "hello world")

    def test_delete_file_keyword(self):
        self.ft.delete.return_value = {"success": True}
        self.agent.execute("delete file")
        self.ft.delete.assert_called_once()


class TestTaskAgentSystemOps(unittest.TestCase):
    def setUp(self):
        self.agent = TaskAgent()
        self.tool = MagicMock()
        patcher = patch.object(self.agent, "_get_tool", return_value=self.tool)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_unavailable(self):
        with patch.object(self.agent, "_get_tool", return_value=None):
            r = self.agent.execute("do something random")
        self.assertEqual(r, "Task agent unavailable.")

    def test_handle_natural_success(self):
        self.tool.handle_natural.return_value = {"success": True, "stdout": "cmd output"}
        r = self.agent.execute("do something random")
        self.assertEqual(r, "cmd output")

    def test_handle_natural_non_dict(self):
        self.tool.handle_natural.return_value = "plain result"
        r = self.agent.execute("do something random")
        self.assertEqual(r, "plain result")

    def test_fallback_failure_file_like(self):
        self.tool.handle_natural.return_value = {"success": False, "error": "nope"}
        with patch("orbit.tools.github_tool.GitHubTool", side_effect=RuntimeError("no gh")):
            r = self.agent.execute("read the file")
        self.assertIn("Error: nope", r)

    def test_fallback_failure_non_file(self):
        self.tool.handle_natural.return_value = {"success": False, "error": "nope"}
        with patch("orbit.tools.desktop.DesktopAutomationTool") as dt_cls, \
             patch("orbit.tools.github_tool.GitHubTool", side_effect=RuntimeError("no gh")):
            dt_cls.return_value.is_available.return_value = False
            r = self.agent.execute("tell me a joke")
        self.assertIn("Error: nope", r)

    def test_clipboard_get(self):
        self.tool.handle_natural.return_value = {"success": True, "text": "copied value"}
        r = self.agent.execute("get clipboard")
        self.assertIn("Clipboard: copied value", r)

    def test_clipboard_set(self):
        self.tool.handle_natural.return_value = {"success": True, "stdout": "value"}
        r = self.agent.execute("clipboard set hello")
        self.assertIn("Clipboard set: value", r)

    def test_clipboard_error(self):
        self.tool.handle_natural.return_value = {"success": False, "error": "locked"}
        r = self.agent.execute("clipboard")
        self.assertIn("Error: locked", r)

    def test_clipboard_non_dict(self):
        self.tool.handle_natural.return_value = "clipboard text"
        r = self.agent.execute("clipboard")
        self.assertEqual(r, "clipboard text")

    def test_ip_address(self):
        self.tool.run_command.return_value = {"success": True, "stdout": "adapter\n IPv4: 192.168.1.5\n"}
        r = self.agent.execute("what's my ip")
        self.assertIn("Your IP: 192.168.1.5", r)

    def test_ip_no_ipv4(self):
        self.tool.run_command.return_value = {"success": True, "stdout": "no addresses here"}
        r = self.agent.execute("my ip address")
        self.assertEqual(r, "no addresses here")

    def test_ip_failure(self):
        self.tool.run_command.return_value = {"success": False, "error": "fail"}
        r = self.agent.execute("my ip")
        self.assertIn("fail", r)


class TestTaskAgentCua(unittest.TestCase):
    def setUp(self):
        self.agent = TaskAgent()

    def test_cua_unavailable(self):
        with patch("orbit.tools.cua_computer.is_available", return_value=False):
            r = self.agent.execute("cua screenshot")
        self.assertIn("cua-driver not running", r)

    def test_cua_screenshot(self):
        cc = MagicMock()
        cc.get_desktop_state.return_value = {"element_count": 7, "tree_markdown": "tree here"}
        with patch("orbit.tools.cua_computer.is_available", return_value=True), \
             patch("orbit.tools.cua_computer.CuaComputerTool", return_value=cc):
            r = self.agent.execute("cua screenshot")
        self.assertIn("Desktop state captured", r)
        self.assertIn("7 elements", r)

    def test_cua_screenshot_error(self):
        cc = MagicMock()
        cc.get_desktop_state.return_value = {"error": "no display"}
        with patch("orbit.tools.cua_computer.is_available", return_value=True), \
             patch("orbit.tools.cua_computer.CuaComputerTool", return_value=cc):
            r = self.agent.execute("cua screenshot")
        self.assertIn("Error: no display", r)

    def test_cua_apps(self):
        cc = MagicMock()
        cc.list_apps.return_value = {"apps": [{"name": "Notepad", "pid": 42, "running": True}]}
        with patch("orbit.tools.cua_computer.is_available", return_value=True), \
             patch("orbit.tools.cua_computer.CuaComputerTool", return_value=cc):
            r = self.agent.execute("cua apps")
        self.assertIn("Notepad", r)
        self.assertIn("pid=42", r)

    def test_cua_click(self):
        cc = MagicMock()
        cc.click.return_value = {"status": "ok"}
        with patch("orbit.tools.cua_computer.is_available", return_value=True), \
             patch("orbit.tools.cua_computer.CuaComputerTool", return_value=cc):
            r = self.agent.execute("cua click 5 pid 123")
        self.assertIn("Clicked element [5]", r)
        cc.click.assert_called_once_with(pid=123, element_index=5)

    def test_cua_click_usage(self):
        with patch("orbit.tools.cua_computer.is_available", return_value=True), \
             patch("orbit.tools.cua_computer.CuaComputerTool", return_value=MagicMock()):
            r = self.agent.execute("cua click")
        self.assertIn("Usage", r)

    def test_cua_type_usage(self):
        with patch("orbit.tools.cua_computer.is_available", return_value=True), \
             patch("orbit.tools.cua_computer.CuaComputerTool", return_value=MagicMock()):
            r = self.agent.execute("cua type")
        self.assertIn("Usage", r)

    def test_cua_help(self):
        with patch("orbit.tools.cua_computer.is_available", return_value=True), \
             patch("orbit.tools.cua_computer.CuaComputerTool", return_value=MagicMock()):
            r = self.agent.execute("cua help")
        self.assertIn("Cua commands", r)


class TestCodeAgent(unittest.TestCase):
    def setUp(self):
        self.agent = CodeAgent()

    def test_instantiation(self):
        self.assertEqual(self.agent.label, "COD")

    def test_can_handle(self):
        self.assertTrue(self.agent.can_handle("write a function"))

    def test_can_handle_chat_low_conf(self):
        self.assertFalse(self.agent.can_handle("code", intent="chat", confidence=0.2))

    def test_can_handle_chat_high_conf(self):
        self.assertTrue(self.agent.can_handle("code", intent="chat", confidence=0.9))

    def test_can_handle_none(self):
        self.assertFalse(self.agent.can_handle("hello"))

    def test_complete_existing_file(self):
        engine = MagicMock()
        engine.suggest_completions.return_value = [{"text": "suggestion one"}]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write("line1\nline2\n")
            p = f.name
        try:
            with patch.object(self.agent, "_get_completion_engine", return_value=engine):
                r = self.agent.execute(f"complete {p}")
            self.assertIn("Code suggestions", r)
            self.assertIn("suggestion one", r)
        finally:
            os.unlink(p)

    def test_complete_missing_file(self):
        with patch.object(self.agent, "_get_completion_engine", return_value=MagicMock()):
            r = self.agent.execute("complete does_not_exist_xyz.py")
        self.assertIn("Provide a file path", r)

    def test_error_response_passthrough(self):
        with patch("orbit.agents.task_agents.llm_router.generate", return_value="[Error: no provider]"):
            r = self.agent.execute("write code for me")
        self.assertEqual(r, "[Error: no provider]")

    def test_syntax_error_autofix(self):
        bad = "```python\nx = (\n```"
        fixed = "```python\nx = 1\n```"
        with patch("orbit.agents.task_agents.llm_router.generate", side_effect=[bad, fixed]) as gen:
            r = self.agent.execute("write code")
        self.assertIn("Syntax check failed", r)
        self.assertIn("Auto-fixed code", r)
        self.assertEqual(gen.call_count, 2)

    def test_save_success(self):
        response = "```python\nprint(1)\n```"
        ft = MagicMock()
        with patch("orbit.agents.task_agents.llm_router.generate", return_value=response), \
             patch("orbit.tools.file_tools.FileTools", return_value=ft):
            r = self.agent.execute("save to out.py")
        self.assertIn("**Saved to:** `out.py`", r)
        self.assertEqual(ft.write.call_args[0][0], "out.py")

    def test_save_failed(self):
        response = "```python\nprint(1)\n```"
        with patch("orbit.agents.task_agents.llm_router.generate", return_value=response), \
             patch("orbit.tools.file_tools.FileTools", side_effect=RuntimeError("disk error")):
            r = self.agent.execute("save to out.py")
        self.assertIn("**Save failed:**", r)

    def test_save_skipped_on_error_response(self):
        with patch("orbit.agents.task_agents.llm_router.generate", return_value="[Error: boom]"):
            r = self.agent.execute("save to out.py")
        self.assertNotIn("Saved to", r)

    def test_context_appended(self):
        with patch("orbit.agents.task_agents.llm_router.generate", return_value="ok") as gen:
            self.agent.execute("write code now", context="some ctx")
        self.assertIn("[Context]", gen.call_args.kwargs["system_prompt"])


if __name__ == "__main__":
    unittest.main()
