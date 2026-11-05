"""Tests for SmartBrowser, MCPTool, and their blueprints."""

import json
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), "..")))

from orbit.orbit.tools.mcp_tool import MCPClient, MCPManager, get_manager
from orbit.orbit.tools.smart_browser import _PLAYWRIGHT_AVAILABLE, SmartBrowser


class TestSmartBrowserAvailability:
    def test_is_available_when_playwright_installed(self):
        sb = SmartBrowser()
        assert sb.is_available() == _PLAYWRIGHT_AVAILABLE

    def test_no_args_init(self):
        sb = SmartBrowser()
        assert sb._page is None
        assert sb._browser is None
        assert sb._history == []

    @patch("orbit.orbit.tools.smart_browser._PLAYWRIGHT_AVAILABLE", False)
    def test_is_available_false(self):
        sb = SmartBrowser()
        assert sb.is_available() is False


class TestSmartBrowserStepPlanning:
    def test_plan_navigate(self):
        sb = SmartBrowser()
        steps = sb._plan_steps("go to https://example.com")
        assert len(steps) > 0
        assert steps[0]["action"] == "navigate"

    def test_plan_search(self):
        sb = SmartBrowser()
        steps = sb._plan_steps("search for python tutorials on google")
        assert len(steps) > 0
        assert any(s["action"] == "search" for s in steps)

    def test_plan_click(self):
        sb = SmartBrowser()
        steps = sb._plan_steps("click the login button")
        assert len(steps) > 0
        assert any(s["action"] == "click" for s in steps)

    def test_plan_type(self):
        sb = SmartBrowser()
        steps = sb._plan_steps('type "hello" in search box')
        assert len(steps) > 0
        assert any(s["action"] == "type" for s in steps)

    def test_plan_screenshot(self):
        sb = SmartBrowser()
        steps = sb._plan_steps("take a screenshot")
        assert len(steps) > 0
        assert any(s["action"] == "screenshot" for s in steps)

    def test_plan_extract(self):
        sb = SmartBrowser()
        steps = sb._plan_steps("extract content from page")
        assert len(steps) > 0
        assert any(s["action"] == "extract" for s in steps)

    def test_plan_scroll(self):
        sb = SmartBrowser()
        steps = sb._plan_steps("scroll down")
        assert len(steps) > 0
        assert any(s["action"] == "scroll" for s in steps)

    def test_plan_empty(self):
        sb = SmartBrowser()
        steps = sb._plan_steps("")
        assert isinstance(steps, list)

    def test_plan_unknown(self):
        sb = SmartBrowser()
        steps = sb._plan_steps("do something random")
        assert isinstance(steps, list)

    def test_plan_complex_multi_step(self):
        sb = SmartBrowser()
        steps = sb._plan_steps(
            "go to google.com and search for python and take a screenshot"
        )
        assert len(steps) >= 2


class TestSmartBrowserSelfHeal:
    def test_suggest_selectors(self):
        sb = SmartBrowser()
        selectors = sb._suggest_selectors("login button")
        assert len(selectors) > 0
        assert any("login" in s.lower() for s in selectors)

    def test_suggest_selectors_text(self):
        sb = SmartBrowser()
        selectors = sb._suggest_selectors("submit")
        assert any("text=" in s or "Submit" in s or "submit" in s for s in selectors)


class TestSmartBrowserContentParsing:
    @patch("orbit.orbit.tools.smart_browser._PLAYWRIGHT_AVAILABLE", True)
    @patch("orbit.orbit.tools.smart_browser.SmartBrowser._ensure", lambda self: None)
    def test_screenshot_no_page(self):
        # _ensure stubbed: with a real browser it would CREATE the page,
        # defeating the no-page branch, and sync_playwright().start()
        # leaves a running event loop that poisons later async tests.
        sb = SmartBrowser()
        result = sb.screenshot()
        assert "error" in result

    @patch("orbit.orbit.tools.smart_browser._PLAYWRIGHT_AVAILABLE", True)
    @patch("orbit.orbit.tools.smart_browser.SmartBrowser._ensure", lambda self: None)
    def test_get_content_no_page(self):
        sb = SmartBrowser()
        result = sb.get_content()
        assert "error" in result

    def test_task_history_empty(self):
        sb = SmartBrowser()
        history = sb.get_task_history()
        assert history == []


class TestSmartBrowserClose:
    def test_close_no_browser(self):
        sb = SmartBrowser()
        sb.close()
        assert sb._browser is None
        assert sb._page is None


class TestMCPManager:
    def test_init(self):
        mgr = MCPManager()
        assert len(mgr._clients) == 0

    def test_load_config_no_file(self):
        mgr = MCPManager()
        count = mgr.load_config("/nonexistent/path.json")
        assert count == 0

    def test_load_config_invalid_json(self):
        mgr = MCPManager()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json {{{")
            path = f.name
        count = mgr.load_config(path)
        assert count == 0
        os.unlink(path)

    def test_load_config_empty(self):
        mgr = MCPManager()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({}, f)
            path = f.name
        count = mgr.load_config(path)
        assert count == 0
        os.unlink(path)

    def test_load_config_with_servers(self):
        mgr = MCPManager()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(
                {"mcpServers": {"test-server": {"command": "echo", "args": ["test"]}}},
                f,
            )
            path = f.name
        with patch("orbit.orbit.tools.mcp_tool.MCPClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.start.return_value = True
            MockClient.return_value = mock_instance
            count = mgr.load_config(path)
            assert count == 1
        os.unlink(path)

    def test_list_tools_empty(self):
        mgr = MCPManager()
        tools = mgr.list_tools()
        assert tools == []

    def test_get_status_empty(self):
        mgr = MCPManager()
        status = mgr.get_status()
        assert isinstance(status, (dict, list))

    def test_stop_all(self):
        mgr = MCPManager()
        mock_client = MagicMock()
        mgr._clients["test"] = mock_client
        mgr.stop_all()
        mock_client.stop.assert_called_once()
        assert len(mgr._clients) == 0


class TestMCPClient:
    def test_init(self):
        client = MCPClient("test", "echo", ["hello"])
        assert client.name == "test"
        assert client._process is None
        assert client._available is False

    def test_get_status_not_started(self):
        client = MCPClient("test", "echo", [])
        status = client.get_status()
        assert status["name"] == "test"
        assert status["available"] is False
        assert status["tools"] == 0

    def test_stop_no_process(self):
        client = MCPClient("test", "echo", [])
        client.stop()
        assert client._process is None


class TestMCPManagerSingleton:
    def test_get_manager_returns_same(self):
        mgr1 = get_manager()
        mgr2 = get_manager()
        assert mgr1 is mgr2
