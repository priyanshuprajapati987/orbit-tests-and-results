"""Deep tests for orbit/orbit/core/seo_bp.py (Loop 13/3).

Covers every statement of the SEO Flask blueprint:
  * ``/api/seo/analyze`` — missing url 400, success, exception 500.
  * ``/api/seo/audit`` — missing url 400, success, exception 500.
  * ``/api/seo/meta`` — missing both 400, html provided (no fetch),
    url-only fetches html, exception 500.
  * ``/api/seo/headings`` — same shape.
  * ``/api/seo/keywords`` — missing text 400, keyword optional, exception 500.
  * ``/api/seo/agent`` — missing query 400, wraps result, exception 500.
  * ``/api/seo/status`` — available True, has_browser bool, capabilities list,
    exception 500.
"""

import unittest
from unittest import mock

import flask

from orbit.orbit.core import seo_bp


def _tool():
    m = mock.MagicMock()
    m.analyze_page.return_value = {"score": 90}
    m.full_audit.return_value = {"audit": "ok"}
    m._fetch_html.return_value = "<html>fetched</html>"
    m.check_meta_tags.return_value = {"meta": "ok"}
    m.audit_headings.return_value = {"headings": []}
    m.keyword_density.return_value = {"density": 1.5}
    m._get_browser.return_value = mock.MagicMock()  # not None
    return m


def _agent():
    m = mock.MagicMock()
    m.execute.return_value = "SEO result text"
    return m


class SeoBpTests(unittest.TestCase):
    def setUp(self):
        app = flask.Flask(__name__)
        app.register_blueprint(seo_bp.seo_bp)
        self.client = app.test_client()

    # ── analyze ─────────────────────────────────────────────────────

    def test_analyze_missing_url_400(self):
        with mock.patch("orbit.orbit.tools.seo_tool.SEOTool") as T:
            r = self.client.post("/api/seo/analyze", json={})
            r2 = self.client.post("/api/seo/analyze", json={"url": ""})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r2.status_code, 400)
        self.assertEqual(r.get_json()["error"], "URL is required")
        T.assert_not_called()

    def test_analyze_success(self):
        tool = _tool()
        with mock.patch("orbit.orbit.tools.seo_tool.SEOTool", return_value=tool):
            r = self.client.post("/api/seo/analyze", json={"url": "https://x.com"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"score": 90})
        tool.analyze_page.assert_called_once_with("https://x.com")

    def test_analyze_exception_500(self):
        tool = _tool()
        tool.analyze_page.side_effect = RuntimeError("boom")
        with mock.patch("orbit.orbit.tools.seo_tool.SEOTool", return_value=tool):
            r = self.client.post("/api/seo/analyze", json={"url": "u"})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "boom")

    # ── audit ───────────────────────────────────────────────────────

    def test_audit_missing_url_400(self):
        with mock.patch("orbit.orbit.tools.seo_tool.SEOTool") as T:
            r = self.client.post("/api/seo/audit", json={})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "URL is required")
        T.assert_not_called()

    def test_audit_success(self):
        tool = _tool()
        with mock.patch("orbit.orbit.tools.seo_tool.SEOTool", return_value=tool):
            r = self.client.post("/api/seo/audit", json={"url": "u"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"audit": "ok"})
        tool.full_audit.assert_called_once_with("u")

    def test_audit_exception_500(self):
        tool = _tool()
        tool.full_audit.side_effect = RuntimeError("boom")
        with mock.patch("orbit.orbit.tools.seo_tool.SEOTool", return_value=tool):
            r = self.client.post("/api/seo/audit", json={"url": "u"})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "boom")

    # ── meta ────────────────────────────────────────────────────────

    def test_meta_missing_both_400(self):
        with mock.patch("orbit.orbit.tools.seo_tool.SEOTool") as T:
            r = self.client.post("/api/seo/meta", json={})
            r2 = self.client.post("/api/seo/meta", json={"url": "", "html": ""})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r2.status_code, 400)
        self.assertEqual(r.get_json()["error"], "URL or HTML is required")
        T.assert_not_called()

    def test_meta_html_provided_no_fetch(self):
        tool = _tool()
        with mock.patch("orbit.orbit.tools.seo_tool.SEOTool", return_value=tool):
            r = self.client.post("/api/seo/meta",
                                 json={"html": "<h>hi</h>"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"meta": "ok"})
        tool._fetch_html.assert_not_called()
        tool.check_meta_tags.assert_called_once_with("<h>hi</h>")

    def test_meta_url_only_fetches(self):
        tool = _tool()
        with mock.patch("orbit.orbit.tools.seo_tool.SEOTool", return_value=tool):
            r = self.client.post("/api/seo/meta", json={"url": "https://x.com"})
        self.assertEqual(r.status_code, 200)
        tool._fetch_html.assert_called_once_with("https://x.com")
        tool.check_meta_tags.assert_called_once_with("<html>fetched</html>")

    def test_meta_exception_500(self):
        tool = _tool()
        tool.check_meta_tags.side_effect = RuntimeError("boom")
        with mock.patch("orbit.orbit.tools.seo_tool.SEOTool", return_value=tool):
            r = self.client.post("/api/seo/meta", json={"html": "h"})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "boom")

    # ── headings ────────────────────────────────────────────────────

    def test_headings_missing_both_400(self):
        with mock.patch("orbit.orbit.tools.seo_tool.SEOTool") as T:
            r = self.client.post("/api/seo/headings", json={})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "URL or HTML is required")
        T.assert_not_called()

    def test_headings_html_provided(self):
        tool = _tool()
        with mock.patch("orbit.orbit.tools.seo_tool.SEOTool", return_value=tool):
            r = self.client.post("/api/seo/headings",
                                 json={"html": "<h1>hi</h1>"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"headings": []})
        tool._fetch_html.assert_not_called()
        tool.audit_headings.assert_called_once_with("<h1>hi</h1>")

    def test_headings_url_fetches(self):
        tool = _tool()
        with mock.patch("orbit.orbit.tools.seo_tool.SEOTool", return_value=tool):
            r = self.client.post("/api/seo/headings", json={"url": "u"})
        tool._fetch_html.assert_called_once_with("u")
        tool.audit_headings.assert_called_once_with("<html>fetched</html>")

    def test_headings_exception_500(self):
        tool = _tool()
        tool.audit_headings.side_effect = RuntimeError("boom")
        with mock.patch("orbit.orbit.tools.seo_tool.SEOTool", return_value=tool):
            r = self.client.post("/api/seo/headings", json={"html": "h"})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "boom")

    # ── keywords ────────────────────────────────────────────────────

    def test_keywords_missing_text_400(self):
        with mock.patch("orbit.orbit.tools.seo_tool.SEOTool") as T:
            r = self.client.post("/api/seo/keywords", json={})
            r2 = self.client.post("/api/seo/keywords", json={"text": ""})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r2.status_code, 400)
        self.assertEqual(r.get_json()["error"], "Text is required")
        T.assert_not_called()

    def test_keywords_success_with_keyword(self):
        tool = _tool()
        with mock.patch("orbit.orbit.tools.seo_tool.SEOTool", return_value=tool):
            r = self.client.post("/api/seo/keywords",
                                 json={"text": "hello world", "keyword": "hello"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"density": 1.5})
        tool.keyword_density.assert_called_once_with("hello world", "hello")

    def test_keywords_success_default_keyword_none(self):
        tool = _tool()
        with mock.patch("orbit.orbit.tools.seo_tool.SEOTool", return_value=tool):
            self.client.post("/api/seo/keywords", json={"text": "hello"})
        tool.keyword_density.assert_called_once_with("hello", None)

    def test_keywords_exception_500(self):
        tool = _tool()
        tool.keyword_density.side_effect = RuntimeError("boom")
        with mock.patch("orbit.orbit.tools.seo_tool.SEOTool", return_value=tool):
            r = self.client.post("/api/seo/keywords", json={"text": "t"})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "boom")

    # ── agent ───────────────────────────────────────────────────────

    def test_agent_missing_query_400(self):
        with mock.patch("orbit.orbit.agents.specialized.SEOAgent") as A:
            r = self.client.post("/api/seo/agent", json={})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "Query is required")
        A.assert_not_called()

    def test_agent_success(self):
        agent = _agent()
        with mock.patch("orbit.orbit.agents.specialized.SEOAgent",
                        return_value=agent):
            r = self.client.post("/api/seo/agent", json={"query": "audit x"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"result": "SEO result text"})
        agent.execute.assert_called_once_with("audit x")

    def test_agent_exception_500(self):
        agent = _agent()
        agent.execute.side_effect = RuntimeError("boom")
        with mock.patch("orbit.orbit.agents.specialized.SEOAgent",
                        return_value=agent):
            r = self.client.post("/api/seo/agent", json={"query": "q"})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "boom")

    # ── status ──────────────────────────────────────────────────────

    def test_status_browser_present(self):
        tool = _tool()
        # _get_browser returns not None
        with mock.patch("orbit.orbit.tools.seo_tool.SEOTool", return_value=tool):
            r = self.client.get("/api/seo/status")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["available"])
        self.assertTrue(body["has_browser"])
        self.assertIn("analyze_page", body["capabilities"])
        self.assertEqual(len(body["capabilities"]), 7)

    def test_status_browser_absent(self):
        tool = _tool()
        tool._get_browser.return_value = None
        with mock.patch("orbit.orbit.tools.seo_tool.SEOTool", return_value=tool):
            r = self.client.get("/api/seo/status")
        self.assertFalse(r.get_json()["has_browser"])

    def test_status_exception_500(self):
        with mock.patch("orbit.orbit.tools.seo_tool.SEOTool",
                        side_effect=RuntimeError("boom")):
            r = self.client.get("/api/seo/status")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "boom")


if __name__ == "__main__":
    unittest.main()
