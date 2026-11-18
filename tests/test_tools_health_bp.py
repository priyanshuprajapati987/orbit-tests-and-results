"""Unit tests for orbit/orbit/core/tools_health_bp.py."""

import contextlib
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.tools_health_bp import tools_health_bp

# Lazy-imported callables inside tools_health()
CALLABLES = [
    "orbit.tools.web_search.WebSearchTool",
    "orbit.tools.seo_tool.SEOTool",
    "orbit.tools.file_tools.FileTools",
    "orbit.tools.email_tool.EmailTool",
    "orbit.tools.calendar_tool.CalendarTool",
    "orbit.tools.computer.ComputerTool",
    "orbit.tools.security.SecurityTool",
    "orbit.tools.n8n.N8nTool",
    "orbit.tools.news.NewsTool",
    "orbit.tools.github_tool.GitHubTool",
    "orbit.tools.browser_tool.BrowserTool",
    "orbit.tools.smart_browser.SmartBrowser",
    "orbit.tools.cua_computer.is_available",
    "orbit.tools.desktop.DesktopAutomationTool",
    "orbit.tools.code_completion.CodeCompletionEngine",
    "orbit.tools.smart_actions.SmartActions",
    "orbit.tools.mcp_tool.get_manager",
]

# Module-level feature flags read at health-check time
FLAGS = [
    "orbit.tools.github_tool.GITHUB_AVAILABLE",
    "orbit.tools.browser_tool._PLAYWRIGHT_AVAILABLE",
    "orbit.tools.desktop.PYAUTOGUI_AVAILABLE",
]

ALL_KEYS = [
    "web_search", "seo", "file_tools", "email", "calendar", "computer",
    "security", "n8n", "news", "github", "browser", "smart_browser",
    "cua_computer", "pdf_reader", "desktop", "code_completion",
    "smart_actions", "cai_security", "mcp",
]


class ToolsHealthBase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(tools_health_bp)
        self.client = self.app.test_client()

    def _patch_tools(self, raise_on=(), flags=None):
        """Patch every lazy import; optionally raise for given targets.

        Non-raising callables get explicit JSON-safe return values since
        MagicMock instances are not JSON-serializable.
        """
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        mocks = {}
        for target in CALLABLES:
            if target in raise_on:
                m = stack.enter_context(
                    patch(target, side_effect=RuntimeError("tool down")))
            else:
                m = stack.enter_context(patch(target))
                m.return_value = MagicMock()
            mocks[target] = m
        # JSON-safe defaults for value-producing callables
        mocks["orbit.tools.github_tool.GitHubTool"].return_value \
            .is_configured.return_value = True
        mocks["orbit.tools.smart_browser.SmartBrowser"].return_value \
            .is_available.return_value = True
        mocks["orbit.tools.cua_computer.is_available"].return_value = True
        mocks["orbit.tools.mcp_tool.get_manager"].return_value \
            .list_tools.return_value = []
        for target in FLAGS:
            value = (flags or {}).get(target, True)
            stack.enter_context(patch(target, value))
        return mocks

    def test_blueprint_name(self):
        self.assertEqual(tools_health_bp.name, "tools_health_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/tools/health", rules)


class TestAllAvailable(ToolsHealthBase):
    def test_summary_shape(self):
        self._patch_tools()
        r = self.client.get("/api/tools/health")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["total"], 19)
        self.assertEqual(body["available"], 19)
        self.assertEqual(body["unavailable"], 0)
        self.assertEqual(body["score"], 100)

    def test_all_19_keys_present(self):
        self._patch_tools()
        body = self.client.get("/api/tools/health").get_json()
        self.assertEqual(set(body["tools"].keys()), set(ALL_KEYS))
        self.assertEqual(len(body["tools"]), 19)

    def test_github_configured_field(self):
        mocks = self._patch_tools()
        mocks["orbit.tools.github_tool.GitHubTool"].return_value \
            .is_configured.return_value = True
        body = self.client.get("/api/tools/health").get_json()
        gh = body["tools"]["github"]
        self.assertIn("configured", gh)
        self.assertTrue(gh["configured"])

    def test_mcp_connected_tools_count(self):
        mocks = self._patch_tools()
        mocks["orbit.tools.mcp_tool.get_manager"].return_value \
            .list_tools.return_value = ["a", "b", "c"]
        body = self.client.get("/api/tools/health").get_json()
        self.assertEqual(body["tools"]["mcp"]["connected_tools"], 3)

    def test_mcp_zero_tools(self):
        mocks = self._patch_tools()
        mocks["orbit.tools.mcp_tool.get_manager"].return_value \
            .list_tools.return_value = []
        body = self.client.get("/api/tools/health").get_json()
        self.assertEqual(body["tools"]["mcp"]["connected_tools"], 0)

    def test_status_ok_for_plain_tools(self):
        self._patch_tools()
        body = self.client.get("/api/tools/health").get_json()
        for key in ("web_search", "seo", "file_tools", "email", "calendar",
                    "computer", "security", "n8n", "news", "pdf_reader",
                    "code_completion", "smart_actions", "cai_security"):
            self.assertEqual(body["tools"][key],
                             {"available": True, "status": "ok"}, key)


class TestFailures(ToolsHealthBase):
    def test_single_failure_counts(self):
        self._patch_tools(
            raise_on=["orbit.tools.web_search.WebSearchTool"])
        body = self.client.get("/api/tools/health").get_json()
        self.assertEqual(body["total"], 19)
        self.assertEqual(body["available"], 18)
        self.assertEqual(body["unavailable"], 1)
        self.assertEqual(body["score"], 95)  # round(18/19*100)
        ws = body["tools"]["web_search"]
        self.assertFalse(ws["available"])
        self.assertEqual(ws["error"], "tool down")

    def test_score_rounding_53(self):
        # 10 available of 19 -> round(52.63) = 53
        self._patch_tools(raise_on=CALLABLES[:9])
        body = self.client.get("/api/tools/health").get_json()
        self.assertEqual(body["available"], 10)
        self.assertEqual(body["score"], 53)

    def test_all_fail(self):
        self._patch_tools(raise_on=CALLABLES)
        body = self.client.get("/api/tools/health").get_json()
        # pdf_reader + cai_security have no imports -> always available
        self.assertEqual(body["available"], 2)
        self.assertEqual(body["unavailable"], 17)
        self.assertEqual(body["score"], 11)  # round(2/19*100)
        for key, val in body["tools"].items():
            if key in ("pdf_reader", "cai_security"):
                self.assertTrue(val["available"], key)
                continue
            self.assertFalse(val["available"], key)
            self.assertIn("error", val, key)

    def test_error_message_passthrough(self):
        self._patch_tools(
            raise_on=["orbit.tools.email_tool.EmailTool"])
        body = self.client.get("/api/tools/health").get_json()
        self.assertEqual(body["tools"]["email"]["error"], "tool down")

    def test_unavailable_tool_has_no_status(self):
        self._patch_tools(
            raise_on=["orbit.tools.news.NewsTool"])
        body = self.client.get("/api/tools/health").get_json()
        self.assertNotIn("status", body["tools"]["news"])


class TestFeatureFlags(ToolsHealthBase):
    def test_github_not_available(self):
        self._patch_tools(
            flags={"orbit.tools.github_tool.GITHUB_AVAILABLE": False})
        body = self.client.get("/api/tools/health").get_json()
        self.assertFalse(body["tools"]["github"]["available"])
        # counts as unavailable
        self.assertEqual(body["available"], 18)
        self.assertEqual(body["unavailable"], 1)

    def test_browser_playwright_missing(self):
        self._patch_tools(
            flags={"orbit.tools.browser_tool._PLAYWRIGHT_AVAILABLE": False})
        body = self.client.get("/api/tools/health").get_json()
        self.assertFalse(body["tools"]["browser"]["available"])
        self.assertEqual(body["available"], 18)

    def test_desktop_pyautogui_missing(self):
        self._patch_tools(
            flags={"orbit.tools.desktop.PYAUTOGUI_AVAILABLE": False})
        body = self.client.get("/api/tools/health").get_json()
        self.assertFalse(body["tools"]["desktop"]["available"])
        self.assertEqual(body["available"], 18)

    def test_smart_browser_unavailable(self):
        mocks = self._patch_tools()
        mocks["orbit.tools.smart_browser.SmartBrowser"].return_value \
            .is_available.return_value = False
        body = self.client.get("/api/tools/health").get_json()
        self.assertFalse(body["tools"]["smart_browser"]["available"])
        self.assertEqual(body["available"], 18)

    def test_cua_unavailable(self):
        mocks = self._patch_tools()
        mocks["orbit.tools.cua_computer.is_available"].return_value = False
        body = self.client.get("/api/tools/health").get_json()
        self.assertFalse(body["tools"]["cua_computer"]["available"])
        self.assertEqual(body["available"], 18)


class TestAlwaysAvailable(ToolsHealthBase):
    """Blocks with no failing import (pdf_reader, cai_security)."""

    def test_pdf_reader_survives_total_failure(self):
        self._patch_tools(raise_on=CALLABLES)
        body = self.client.get("/api/tools/health").get_json()
        self.assertTrue(body["tools"]["pdf_reader"]["available"])
        self.assertTrue(body["tools"]["cai_security"]["available"])
        # only these 2 of 19 remain available
        self.assertEqual(body["available"], 2)
        self.assertEqual(body["score"], 11)  # round(2/19*100)


if __name__ == "__main__":
    unittest.main()
