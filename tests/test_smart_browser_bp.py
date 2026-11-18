"""Unit tests for orbit/orbit/tools/smart_browser_bp.py."""

import os
import sys
import time
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

import orbit.tools.smart_browser_bp as sbp
from flask import Flask
from orbit.tools.smart_browser_bp import smart_browser_bp


class SmartBrowserBpBase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(smart_browser_bp)
        self.client = self.app.test_client()
        # reset module globals between tests
        self._old_sb = sbp._sb
        self._old_last = sbp._last_used
        sbp._sb = None
        sbp._last_used = 0.0

    def tearDown(self):
        sbp._sb = self._old_sb
        sbp._last_used = self._old_last

    def test_blueprint_name(self):
        self.assertEqual(smart_browser_bp.name, "smart_browser")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/smart-browser/status", "/api/smart-browser/navigate",
                  "/api/smart-browser/action", "/api/smart-browser/extract",
                  "/api/smart-browser/screenshot", "/api/smart-browser/close"]:
            self.assertIn(p, rules)


class TestGetSb(SmartBrowserBpBase):
    def test_creates_instance(self):
        mock = MagicMock()
        with patch.object(sbp, "SmartBrowser", return_value=mock) as ctor:
            sb = sbp._get_sb()
        self.assertIs(sb, mock)
        ctor.assert_called_once()
        self.assertIsNotNone(sbp._last_used)

    def test_reuses_instance(self):
        mock = MagicMock()
        with patch.object(sbp, "SmartBrowser", return_value=mock) as ctor:
            sbp._get_sb()
            sb = sbp._get_sb()
        self.assertIs(sb, mock)
        self.assertEqual(ctor.call_count, 1)

    def test_idle_close_then_recreate(self):
        first = MagicMock()
        second = MagicMock()
        with patch.object(sbp, "SmartBrowser", side_effect=[first, second]):
            sbp._get_sb()
            # simulate idle > 600s
            sbp._last_used = time.monotonic() - sbp._IDLE_CLOSE_SEC - 1
            sb = sbp._get_sb()
        first.close.assert_called_once()
        self.assertIs(sb, second)

    def test_idle_close_failure_still_recreates(self):
        first = MagicMock()
        first.close.side_effect = RuntimeError("boom")
        second = MagicMock()
        with patch.object(sbp, "SmartBrowser", side_effect=[first, second]):
            sbp._get_sb()
            sbp._last_used = time.monotonic() - sbp._IDLE_CLOSE_SEC - 1
            sb = sbp._get_sb()
        self.assertIs(sb, second)
        self.assertIsNotNone(sbp._sb)


class TestStatus(SmartBrowserBpBase):
    def test_status(self):
        mock = MagicMock()
        mock.is_available.return_value = True
        mock._history = [1, 2, 3]
        with patch.object(sbp, "SmartBrowser", return_value=mock):
            r = self.client.get("/api/smart-browser/status")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["available"])
        self.assertEqual(body["history"], 3)


class TestNavigate(SmartBrowserBpBase):
    def test_missing_url_400(self):
        r = self.client.post("/api/smart-browser/navigate", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("url required", r.get_json()["error"])

    def test_no_body_400(self):
        r = self.client.post("/api/smart-browser/navigate")
        self.assertEqual(r.status_code, 400)

    def test_blocked_url_403(self):
        r = self.client.post("/api/smart-browser/navigate",
                             json={"url": "javascript:alert(1)"})
        self.assertEqual(r.status_code, 403)
        body = r.get_json()
        self.assertEqual(body["error"], "url not allowed")
        self.assertIn("javascript", body["reason"])

    def test_blocked_host_403(self):
        r = self.client.post("/api/smart-browser/navigate",
                             json={"url": "http://localhost:8080"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(body_reason(r), "blocked_host")

    def test_allowed_url_success(self):
        mock = MagicMock()
        mock.navigate.return_value = {"status": "ok", "title": "Example"}
        with patch.object(sbp, "SmartBrowser", return_value=mock):
            r = self.client.post("/api/smart-browser/navigate",
                                 json={"url": "https://example.com"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        mock.navigate.assert_called_once_with("https://example.com")


def body_reason(r):
    return r.get_json()["reason"]


class TestAction(SmartBrowserBpBase):
    def test_missing_goal_400(self):
        r = self.client.post("/api/smart-browser/action", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("goal required", r.get_json()["error"])

    def test_success(self):
        mock = MagicMock()
        mock.execute_task.return_value = {"done": True}
        with patch.object(sbp, "SmartBrowser", return_value=mock):
            r = self.client.post("/api/smart-browser/action",
                                 json={"goal": "search weather"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["done"])
        mock.execute_task.assert_called_once_with("search weather")


class TestExtract(SmartBrowserBpBase):
    def test_with_url(self):
        mock = MagicMock()
        mock.extract_page.return_value = {"text": "hello"}
        with patch.object(sbp, "SmartBrowser", return_value=mock):
            r = self.client.post("/api/smart-browser/extract",
                                 json={"url": "https://example.com"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["text"], "hello")
        mock.extract_page.assert_called_once_with("https://example.com")
        mock.get_content.assert_not_called()

    def test_without_url_uses_current_content(self):
        mock = MagicMock()
        mock.get_content.return_value = {"text": "current"}
        with patch.object(sbp, "SmartBrowser", return_value=mock):
            r = self.client.post("/api/smart-browser/extract", json={})
        self.assertEqual(r.get_json()["text"], "current")
        mock.get_content.assert_called_once()


class TestScreenshot(SmartBrowserBpBase):
    def test_screenshot(self):
        mock = MagicMock()
        mock.screenshot.return_value = {"path": "/tmp/shot.png"}
        with patch.object(sbp, "SmartBrowser", return_value=mock):
            r = self.client.post("/api/smart-browser/screenshot")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["path"], "/tmp/shot.png")
        mock.screenshot.assert_called_once()


class TestClose(SmartBrowserBpBase):
    def test_close_with_instance(self):
        mock = MagicMock()
        sbp._sb = mock
        r = self.client.post("/api/smart-browser/close")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        mock.close.assert_called_once()
        self.assertIsNone(sbp._sb)

    def test_close_without_instance(self):
        r = self.client.post("/api/smart-browser/close")
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(sbp._sb)


class TestShutdownClose(SmartBrowserBpBase):
    def test_shutdown_with_instance(self):
        mock = MagicMock()
        sbp._sb = mock
        sbp._shutdown_close()
        mock.close.assert_called_once()
        self.assertIsNone(sbp._sb)

    def test_shutdown_without_instance(self):
        sbp._shutdown_close()
        self.assertIsNone(sbp._sb)

    def test_shutdown_swallows_close_error(self):
        mock = MagicMock()
        mock.close.side_effect = RuntimeError("boom")
        sbp._sb = mock
        sbp._shutdown_close()  # must not raise
        self.assertIsNone(sbp._sb)


if __name__ == "__main__":
    unittest.main()
