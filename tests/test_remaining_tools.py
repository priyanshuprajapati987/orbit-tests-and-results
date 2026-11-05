"""Tests for BrowserTool, CuaComputerTool, PdfReader, and DesktopAutomationTool."""

import os
import sys
import tempfile
from unittest.mock import patch

import pytest

sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), "..")))

from orbit.orbit.tools.browser_tool import _PLAYWRIGHT_AVAILABLE, BrowserTool
from orbit.orbit.tools.cua_computer import (
    CuaComputerTool,
)
from orbit.orbit.tools.cua_computer import (
    is_available as cua_is_available,
)
from orbit.orbit.tools.desktop import PYAUTOGUI_AVAILABLE, DesktopAutomationTool
from orbit.orbit.tools.pdf_reader import edit_pdf_text, read_pdf

# ── BrowserTool Tests ─────────────────────────────────────────────────────


class TestBrowserToolInit:
    def test_init(self):
        bt = BrowserTool()
        assert bt.name == "browser"
        assert bt._page is None
        assert bt._browser is None

    def test_is_available(self):
        bt = BrowserTool()
        assert bt.is_available() == _PLAYWRIGHT_AVAILABLE


class TestBrowserToolNoPlaywright:
    @patch("orbit.orbit.tools.browser_tool._PLAYWRIGHT_AVAILABLE", False)
    def test_navigate_no_playwright(self):
        bt = BrowserTool()
        result = bt.navigate("https://example.com")
        assert "error" in result

    @patch("orbit.orbit.tools.browser_tool._PLAYWRIGHT_AVAILABLE", False)
    def test_get_content_no_playwright(self):
        bt = BrowserTool()
        result = bt.get_content()
        assert "error" in result

    @patch("orbit.orbit.tools.browser_tool._PLAYWRIGHT_AVAILABLE", False)
    def test_screenshot_no_playwright(self):
        bt = BrowserTool()
        result = bt.screenshot()
        assert "error" in result

    @patch("orbit.orbit.tools.browser_tool._PLAYWRIGHT_AVAILABLE", False)
    def test_click_no_playwright(self):
        bt = BrowserTool()
        result = bt.click("button")
        assert "error" in result

    @patch("orbit.orbit.tools.browser_tool._PLAYWRIGHT_AVAILABLE", False)
    def test_type_text_no_playwright(self):
        bt = BrowserTool()
        result = bt.type_text("input", "hello")
        assert "error" in result

    @patch("orbit.orbit.tools.browser_tool._PLAYWRIGHT_AVAILABLE", False)
    def test_press_key_no_playwright(self):
        bt = BrowserTool()
        result = bt.press_key("Enter")
        assert "error" in result

    @patch("orbit.orbit.tools.browser_tool._PLAYWRIGHT_AVAILABLE", False)
    def test_evaluate_no_playwright(self):
        bt = BrowserTool()
        result = bt.evaluate("1+1")
        assert "error" in result

    @patch("orbit.orbit.tools.browser_tool._PLAYWRIGHT_AVAILABLE", False)
    def test_search_google_no_playwright(self):
        bt = BrowserTool()
        result = bt.search_google("python")
        assert "error" in result

    @patch("orbit.orbit.tools.browser_tool._PLAYWRIGHT_AVAILABLE", False)
    def test_extract_page_no_playwright(self):
        bt = BrowserTool()
        result = bt.extract_page("https://example.com")
        assert "error" in result


class TestBrowserToolClose:
    def test_close_no_browser(self):
        bt = BrowserTool()
        bt.close()
        assert bt._browser is None
        assert bt._page is None

    def test_context_manager(self):
        with BrowserTool() as bt:
            assert bt._browser is None


# ── CuaComputerTool Tests ────────────────────────────────────────────────


class TestCuaComputerToolInit:
    def test_init(self):
        cua = CuaComputerTool()
        assert cua is not None

    def test_is_available(self):
        result = cua_is_available()
        assert isinstance(result, bool)


class TestCuaComputerToolNoDriver:
    @patch("orbit.orbit.tools.cua_computer._get_binary", return_value=None)
    def test_screenshot_no_driver(self, mock_bin):
        cua = CuaComputerTool()
        result = cua.screenshot()
        assert "error" in result

    @patch("orbit.orbit.tools.cua_computer._get_binary", return_value=None)
    def test_get_screen_size_no_driver(self, mock_bin):
        cua = CuaComputerTool()
        result = cua.get_screen_size()
        assert "error" in result

    @patch("orbit.orbit.tools.cua_computer._get_binary", return_value=None)
    def test_click_no_driver(self, mock_bin):
        cua = CuaComputerTool()
        result = cua.click(1234)
        assert "error" in result

    @patch("orbit.orbit.tools.cua_computer._get_binary", return_value=None)
    def test_type_no_driver(self, mock_bin):
        cua = CuaComputerTool()
        result = cua.type_text(1234, "hello")
        assert "error" in result

    @patch("orbit.orbit.tools.cua_computer._get_binary", return_value=None)
    def test_scroll_no_driver(self, mock_bin):
        cua = CuaComputerTool()
        result = cua.scroll(1234, "down", 3)
        assert "error" in result

    @patch("orbit.orbit.tools.cua_computer._get_binary", return_value=None)
    def test_desktop_state_no_driver(self, mock_bin):
        cua = CuaComputerTool()
        result = cua.get_desktop_state()
        assert "error" in result

    @patch("orbit.orbit.tools.cua_computer._get_binary", return_value=None)
    def test_launch_app_no_driver(self, mock_bin):
        cua = CuaComputerTool()
        result = cua.launch_app("notepad")
        assert "error" in result

    @patch("orbit.orbit.tools.cua_computer._get_binary", return_value=None)
    def test_list_apps_no_driver(self, mock_bin):
        cua = CuaComputerTool()
        result = cua.list_apps()
        assert "error" in result

    @patch("orbit.orbit.tools.cua_computer._get_binary", return_value=None)
    def test_health_report_no_driver(self, mock_bin):
        cua = CuaComputerTool()
        result = cua.health_report()
        assert "error" in result

    @patch("orbit.orbit.tools.cua_computer._get_binary", return_value=None)
    def test_hotkey_no_driver(self, mock_bin):
        cua = CuaComputerTool()
        result = cua.hotkey(1234, ["ctrl", "c"])
        assert "error" in result

    @patch("orbit.orbit.tools.cua_computer._get_binary", return_value=None)
    def test_press_key_no_driver(self, mock_bin):
        cua = CuaComputerTool()
        result = cua.press_key(1234, "Enter")
        assert "error" in result

    @patch("orbit.orbit.tools.cua_computer._get_binary", return_value=None)
    def test_get_cursor_position_no_driver(self, mock_bin):
        cua = CuaComputerTool()
        result = cua.get_cursor_position()
        assert "error" in result

    @patch("orbit.orbit.tools.cua_computer._get_binary", return_value=None)
    def test_move_cursor_no_driver(self, mock_bin):
        cua = CuaComputerTool()
        result = cua.move_cursor(100, 200)
        assert "error" in result

    @patch("orbit.orbit.tools.cua_computer._get_binary", return_value=None)
    def test_bring_to_front_no_driver(self, mock_bin):
        cua = CuaComputerTool()
        result = cua.bring_to_front(1234)
        assert "error" in result

    @patch("orbit.orbit.tools.cua_computer._get_binary", return_value=None)
    def test_kill_app_no_driver(self, mock_bin):
        cua = CuaComputerTool()
        result = cua.kill_app(1234)
        assert "error" in result

    @patch("orbit.orbit.tools.cua_computer._get_binary", return_value=None)
    def test_right_click_no_driver(self, mock_bin):
        cua = CuaComputerTool()
        result = cua.right_click(1234, None, None)
        assert "error" in result

    @patch("orbit.orbit.tools.cua_computer._get_binary", return_value=None)
    def test_double_click_no_driver(self, mock_bin):
        cua = CuaComputerTool()
        result = cua.double_click(1234, None, None)
        assert "error" in result

    @patch("orbit.orbit.tools.cua_computer._get_binary", return_value=None)
    def test_start_end_session_no_driver(self, mock_bin):
        cua = CuaComputerTool()
        result = cua.start_session("test")
        assert "error" in result
        result = cua.end_session("test")
        assert "error" in result


# ── PdfReader Tests ──────────────────────────────────────────────────────


class TestPdfReader:
    def test_read_nonexistent(self):
        result = read_pdf("/nonexistent/file.pdf")
        assert "error" in result
        assert "not found" in result["error"]

    def test_read_not_pdf(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"hello")
            path = f.name
        try:
            result = read_pdf(path)
            assert "error" in result
            assert "Not a PDF" in result["error"]
        finally:
            os.unlink(path)

    def test_read_with_pypdf2(self):
        try:
            from PyPDF2 import PdfWriter

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                writer = PdfWriter()
                writer.add_blank_page(width=612, height=792)
                writer.write(f)
                path = f.name
            try:
                result = read_pdf(path)
                assert result["status"] == "ok"
                assert result["engine"] in ("pypdf2", "opendataloader")
                assert "metadata" in result
                assert result["metadata"]["pages"] == 1
            finally:
                os.unlink(path)
        except ImportError:
            pytest.skip("PyPDF2 not installed")

    def test_edit_pdf_text(self):
        result = edit_pdf_text("test.pdf", "summarize")
        assert result["status"] == "info"
        assert "message" in result


# ── DesktopAutomationTool Tests ──────────────────────────────────────────


class TestDesktopAutomationTool:
    def test_init(self):
        d = DesktopAutomationTool()
        assert d is not None

    def test_is_available(self):
        d = DesktopAutomationTool()
        assert d.is_available() == PYAUTOGUI_AVAILABLE

    @patch("orbit.orbit.tools.desktop.PYAUTOGUI_AVAILABLE", False)
    def test_screenshot_no_pyautogui(self):
        d = DesktopAutomationTool()
        with pytest.raises(RuntimeError):
            d.screenshot()

    @patch("orbit.orbit.tools.desktop.PYAUTOGUI_AVAILABLE", False)
    def test_screen_size_no_pyautogui(self):
        d = DesktopAutomationTool()
        with pytest.raises(RuntimeError):
            d.screen_size()

    @patch("orbit.orbit.tools.desktop.PYAUTOGUI_AVAILABLE", False)
    def test_mouse_move_no_pyautogui(self):
        d = DesktopAutomationTool()
        with pytest.raises(RuntimeError):
            d.mouse_move(100, 200)

    @patch("orbit.orbit.tools.desktop.PYAUTOGUI_AVAILABLE", False)
    def test_mouse_click_no_pyautogui(self):
        d = DesktopAutomationTool()
        with pytest.raises(RuntimeError):
            d.mouse_click(100, 200)

    @patch("orbit.orbit.tools.desktop.PYAUTOGUI_AVAILABLE", False)
    def test_type_text_no_pyautogui(self):
        d = DesktopAutomationTool()
        with pytest.raises(RuntimeError):
            d.type_text("hello")

    @patch("orbit.orbit.tools.desktop.PYAUTOGUI_AVAILABLE", False)
    def test_press_key_no_pyautogui(self):
        d = DesktopAutomationTool()
        with pytest.raises(RuntimeError):
            d.press_key("enter")

    @patch("orbit.orbit.tools.desktop.PYAUTOGUI_AVAILABLE", False)
    def test_mouse_scroll_no_pyautogui(self):
        d = DesktopAutomationTool()
        with pytest.raises(RuntimeError):
            d.mouse_scroll(3)

    @patch("orbit.orbit.tools.desktop.PYAUTOGUI_AVAILABLE", False)
    def test_list_windows_no_pyautogui(self):
        d = DesktopAutomationTool()
        result = d.list_windows()
        assert "success" in result

    @patch("orbit.orbit.tools.desktop.PYAUTOGUI_AVAILABLE", False)
    def test_open_app_no_pyautogui(self):
        d = DesktopAutomationTool()
        result = d.open_app("notepad")
        assert "success" in result

    @patch("orbit.orbit.tools.desktop.PYAUTOGUI_AVAILABLE", False)
    def test_handle_natural_no_pyautogui(self):
        d = DesktopAutomationTool()
        with pytest.raises(RuntimeError):
            d.handle_natural("screenshot")
