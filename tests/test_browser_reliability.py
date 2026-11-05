"""Tests for browser tool reliability improvements."""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _disable_playwright(monkeypatch):
    """Keep these error-path tests hermetic.

    sync_playwright().start() (playwright sync API) leaves a RUNNING event
    loop registered in the calling thread until .stop() is called — tests
    that never close the tool poison asyncio in the whole pytest session
    (every later async test dies with 'Cannot run the event loop while
    another loop is running'). Force availability off so _ensure() bails
    before ever starting playwright.
    """
    monkeypatch.setattr(
        "orbit.orbit.tools.browser_tool._PLAYWRIGHT_AVAILABLE", False, raising=False
    )


class TestBrowserTool:
    def test_import(self):
        from orbit.orbit.tools.browser_tool import (
            MAX_RETRIES,
            RETRY_DELAY_MS,
        )

        assert MAX_RETRIES == 3
        assert RETRY_DELAY_MS == 500

    def test_init_defaults(self):
        from orbit.orbit.tools.browser_tool import BrowserTool

        tool = BrowserTool()
        assert tool.headless is True
        assert tool._browser is None
        assert tool._last_error is None
        assert tool._retry_count == 0

    def test_init_headless(self):
        from orbit.orbit.tools.browser_tool import BrowserTool

        tool = BrowserTool(headless=True)
        assert tool.headless is True

    def test_is_available(self):
        from orbit.orbit.tools.browser_tool import _PLAYWRIGHT_AVAILABLE, BrowserTool

        tool = BrowserTool()
        assert tool.is_available() == _PLAYWRIGHT_AVAILABLE

    def test_get_status_when_closed(self):
        from orbit.orbit.tools.browser_tool import BrowserTool

        tool = BrowserTool()
        status = tool.get_status()
        assert status["running"] is False
        assert status["page_loaded"] is False
        assert status["current_url"] is None
        assert status["last_error"] is None
        assert status["retry_count"] == 0

    def test_close_when_not_started(self):
        from orbit.orbit.tools.browser_tool import BrowserTool

        tool = BrowserTool()
        tool.close()  # Should not raise
        assert tool._browser is None
        assert tool._page is None

    def test_context_manager(self):
        from orbit.orbit.tools.browser_tool import BrowserTool

        with BrowserTool() as tool:
            assert tool._browser is None
        assert tool._browser is None

    @patch("orbit.orbit.tools.browser_tool._PLAYWRIGHT_AVAILABLE", False)
    def test_ensure_without_playwright(self):
        from orbit.orbit.tools.browser_tool import BrowserTool

        tool = BrowserTool()
        with pytest.raises(RuntimeError, match="Playwright not installed"):
            tool._ensure()

    def test_navigate_without_browser_returns_error(self):
        from orbit.orbit.tools.browser_tool import BrowserTool

        tool = BrowserTool()
        result = tool.navigate("https://example.com")
        assert "error" in result

    def test_click_without_browser_returns_error(self):
        from orbit.orbit.tools.browser_tool import BrowserTool

        tool = BrowserTool()
        result = tool.click("button")
        assert "error" in result

    def test_type_text_without_browser_returns_error(self):
        from orbit.orbit.tools.browser_tool import BrowserTool

        tool = BrowserTool()
        result = tool.type_text("input", "hello")
        assert "error" in result

    def test_screenshot_without_browser_returns_error(self):
        from orbit.orbit.tools.browser_tool import BrowserTool

        tool = BrowserTool()
        result = tool.screenshot()
        assert "error" in result

    def test_get_content_without_browser_returns_error(self):
        from orbit.orbit.tools.browser_tool import BrowserTool

        tool = BrowserTool()
        result = tool.get_content()
        assert "error" in result

    def test_wait_for_without_browser_returns_error(self):
        from orbit.orbit.tools.browser_tool import BrowserTool

        tool = BrowserTool()
        result = tool.wait_for("div")
        assert "error" in result

    def test_scroll_without_browser_returns_error(self):
        from orbit.orbit.tools.browser_tool import BrowserTool

        tool = BrowserTool()
        result = tool.scroll("down")
        assert "error" in result

    def test_search_google_without_browser_returns_error(self):
        from orbit.orbit.tools.browser_tool import BrowserTool

        tool = BrowserTool()
        result = tool.search_google("test")
        assert "error" in result

    def test_extract_page_without_browser_returns_error(self):
        from orbit.orbit.tools.browser_tool import BrowserTool

        tool = BrowserTool()
        result = tool.extract_page("https://example.com")
        assert "error" in result

    def test_retry_transient_error(self):
        from orbit.orbit.tools.browser_tool import BrowserTool

        tool = BrowserTool()
        call_count = [0]

        def mock_func():
            call_count[0] += 1
            if call_count[0] == 1:
                raise TimeoutError("Page load timeout")
            return "success"

        with patch("orbit.orbit.tools.browser_tool.time.sleep"):
            result = tool._retry(mock_func)
            assert result == "success"
            assert call_count[0] == 2

    def test_retry_non_transient_error_raises(self):
        from orbit.orbit.tools.browser_tool import BrowserTool

        tool = BrowserTool()

        def mock_func():
            raise ValueError("Invalid selector")

        with pytest.raises(ValueError, match="Invalid selector"):
            tool._retry(mock_func)
