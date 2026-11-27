"""Deep tests for orbit/orbit/tools/web_search.py (Loop 18/1)."""

import os
import unittest
from unittest import mock

from orbit.orbit.tools import web_search as ws


class SearchDispatchTests(unittest.TestCase):
    def setUp(self):
        self.tool = ws.WebSearchTool()

    def test_dispatch_duckduckgo(self):
        with mock.patch.object(self.tool, "_search_duckduckgo",
                               return_value={"engine": "ddg"}) as m:
            r = self.tool.search("q", 3, "duckduckgo")
        m.assert_called_once_with("q", 3)
        self.assertEqual(r, {"engine": "ddg"})

    def test_dispatch_google(self):
        with mock.patch.object(self.tool, "_search_google",
                               return_value={"engine": "g"}) as m:
            r = self.tool.search("q", 4, "google")
        m.assert_called_once_with("q", 4)

    def test_dispatch_bing(self):
        with mock.patch.object(self.tool, "_search_bing",
                               return_value={"engine": "b"}) as m:
            r = self.tool.search("q", 5, "bing")
        m.assert_called_once_with("q", 5)

    def test_dispatch_unknown_falls_to_duckduckgo(self):
        with mock.patch.object(self.tool, "_search_duckduckgo",
                               return_value={"engine": "ddg"}) as m:
            r = self.tool.search("q", 2, "nope")
        m.assert_called_once_with("q", 2)

    def test_dispatch_exception_returns_error(self):
        with mock.patch.object(self.tool, "_search_duckduckgo",
                               side_effect=RuntimeError("boom")):
            r = self.tool.search("q")
        self.assertEqual(r, {"error": "boom", "results": []})

    def test_default_params(self):
        with mock.patch.object(self.tool, "_search_duckduckgo",
                               return_value={"engine": "ddg"}) as m:
            self.tool.search("q")
        m.assert_called_once_with("q", 5)


class DuckDuckGoTests(unittest.TestCase):
    def setUp(self):
        self.tool = ws.WebSearchTool()

    def test_ssrf_blocked(self):
        guard = mock.MagicMock()
        guard.is_safe_url.return_value = False
        with mock.patch("orbit.orbit.core.ssrf_guard.get_ssrf_guard",
                        return_value=guard):
            r = self.tool._search_duckduckgo("q", 3)
        self.assertEqual(r, {"error": "SSRF blocked", "results": []})

    def test_success_with_abstract_and_topics(self):
        guard = mock.MagicMock()
        guard.is_safe_url.return_value = True
        data = {
            "AbstractText": "abs text", "Heading": "Head",
            "AbstractURL": "http://x", "AbstractSource": "src",
            "RelatedTopics": [
                {"Text": "topic1", "FirstURL": "http://t1"},
                {"Text": "topic2", "FirstURL": "http://t2"},
                "not-a-dict",
            ],
        }
        resp = mock.MagicMock(status_code=200)
        resp.json.return_value = data
        with mock.patch("orbit.orbit.core.ssrf_guard.get_ssrf_guard",
                        return_value=guard), \
                mock.patch("requests.get", return_value=resp):
            r = self.tool._search_duckduckgo("q", 2)
        self.assertEqual(r["engine"], "duckduckgo")
        self.assertEqual(r["query"], "q")
        # abstract + 2 topics capped to num_results=2
        self.assertEqual(len(r["results"]), 2)
        self.assertEqual(r["results"][0]["title"], "Head")
        self.assertEqual(r["results"][0]["snippet"], "abs text")
        self.assertEqual(r["results"][0]["source"], "src")

    def test_success_no_abstract(self):
        guard = mock.MagicMock()
        guard.is_safe_url.return_value = True
        data = {"RelatedTopics": [{"Text": "t", "FirstURL": "u"}]}
        resp = mock.MagicMock(status_code=200)
        resp.json.return_value = data
        with mock.patch("orbit.orbit.core.ssrf_guard.get_ssrf_guard",
                        return_value=guard), \
                mock.patch("requests.get", return_value=resp):
            r = self.tool._search_duckduckgo("q", 5)
        self.assertEqual(len(r["results"]), 1)
        self.assertEqual(r["results"][0]["source"], "DuckDuckGo")

    def test_non_200_falls_to_scrape(self):
        guard = mock.MagicMock()
        guard.is_safe_url.return_value = True
        resp = mock.MagicMock(status_code=500)
        with mock.patch("orbit.orbit.core.ssrf_guard.get_ssrf_guard",
                        return_value=guard), \
                mock.patch("requests.get", return_value=resp), \
                mock.patch.object(self.tool, "_search_html_scrape",
                                  return_value={"engine": "scrape"}) as scrape:
            r = self.tool._search_duckduckgo("q", 3)
        scrape.assert_called_once_with("q", 3)
        self.assertEqual(r, {"engine": "scrape"})

    def test_exception_falls_to_scrape(self):
        guard = mock.MagicMock()
        guard.is_safe_url.return_value = True
        with mock.patch("orbit.orbit.core.ssrf_guard.get_ssrf_guard",
                        return_value=guard), \
                mock.patch("requests.get", side_effect=Exception("net")), \
                mock.patch.object(self.tool, "_search_html_scrape",
                                  return_value={"engine": "scrape"}) as scrape, \
                mock.patch.object(ws, "logger") as lg:
            r = self.tool._search_duckduckgo("q", 3)
        scrape.assert_called_once_with("q", 3)
        lg.warning.assert_called_once()


class HtmlScrapeTests(unittest.TestCase):
    def setUp(self):
        self.tool = ws.WebSearchTool()

    def test_ssrf_blocked(self):
        guard = mock.MagicMock()
        guard.is_safe_url.return_value = False
        with mock.patch("orbit.orbit.core.ssrf_guard.get_ssrf_guard",
                        return_value=guard):
            r = self.tool._search_html_scrape("q", 3)
        self.assertEqual(r, {"error": "SSRF blocked", "results": []})

    def test_success_parses_results(self):
        guard = mock.MagicMock()
        guard.is_safe_url.return_value = True
        html = (
            '<a class="result__a" href="http://u1">Title1</a>'
            '<a class="result__snippet">Snippet1</a>'
            '<a class="result__a" href="http://u2">Title2</a>'
            '<a class="result__snippet">Snippet2</a>'
        )
        resp = mock.MagicMock(status_code=200)
        resp.text = html
        with mock.patch("orbit.orbit.core.ssrf_guard.get_ssrf_guard",
                        return_value=guard), \
                mock.patch("requests.post", return_value=resp):
            r = self.tool._search_html_scrape("q", 5)
        self.assertEqual(r["engine"], "duckduckgo_html")
        self.assertEqual(r["query"], "q")
        self.assertEqual(len(r["results"]), 2)
        self.assertEqual(r["results"][0]["title"], "Title1")
        self.assertEqual(r["results"][0]["source"], "DuckDuckGo")

    def test_non_200_returns_failure(self):
        guard = mock.MagicMock()
        guard.is_safe_url.return_value = True
        resp = mock.MagicMock(status_code=500)
        with mock.patch("orbit.orbit.core.ssrf_guard.get_ssrf_guard",
                        return_value=guard), \
                mock.patch("requests.post", return_value=resp):
            r = self.tool._search_html_scrape("q", 3)
        self.assertEqual(r, {"query": "q", "results": [], "engine": "none",
                             "error": "All search engines failed"})

    def test_exception_returns_failure(self):
        guard = mock.MagicMock()
        guard.is_safe_url.return_value = True
        with mock.patch("orbit.orbit.core.ssrf_guard.get_ssrf_guard",
                        return_value=guard), \
                mock.patch("requests.post", side_effect=Exception("net")), \
                mock.patch.object(ws, "logger") as lg:
            r = self.tool._search_html_scrape("q", 3)
        self.assertEqual(r["engine"], "none")
        self.assertEqual(r["error"], "All search engines failed")
        lg.warning.assert_called_once()

    def test_num_results_cap(self):
        guard = mock.MagicMock()
        guard.is_safe_url.return_value = True
        html = ""
        for i in range(5):
            html += (f'<a class="result__a" href="u{i}">T{i}</a>'
                     f'<a class="result__snippet">S{i}</a>')
        resp = mock.MagicMock(status_code=200)
        resp.text = html
        with mock.patch("orbit.orbit.core.ssrf_guard.get_ssrf_guard",
                        return_value=guard), \
                mock.patch("requests.post", return_value=resp):
            r = self.tool._search_html_scrape("q", 2)
        self.assertEqual(len(r["results"]), 2)


class GoogleTests(unittest.TestCase):
    def setUp(self):
        self.tool = ws.WebSearchTool()

    def test_no_api_key(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            r = self.tool._search_google("q", 3)
        self.assertEqual(r, {"query": "q", "results": [],
                             "error": "Google API key not configured",
                             "engine": "google"})

    def test_no_cse_id(self):
        with mock.patch.dict(os.environ, {"GOOGLE_API_KEY": "k"}):
            r = self.tool._search_google("q", 3)
        self.assertEqual(r["error"], "Google API key not configured")

    def test_success(self):
        with mock.patch.dict(os.environ, {"GOOGLE_API_KEY": "k",
                                         "GOOGLE_CSE_ID": "c"}):
            data = {"items": [
                {"title": "T1", "snippet": "S1", "link": "u1"},
                {"title": "T2", "snippet": "S2", "link": "u2"},
            ]}
            resp = mock.MagicMock(status_code=200)
            resp.json.return_value = data
            with mock.patch("requests.get", return_value=resp) as rg:
                r = self.tool._search_google("q", 5)
        self.assertEqual(r["engine"], "google")
        self.assertEqual(len(r["results"]), 2)
        self.assertEqual(r["results"][0]["source"], "Google")
        self.assertEqual(rg.call_args.kwargs["params"]["key"], "k")
        self.assertEqual(rg.call_args.kwargs["params"]["cx"], "c")
        self.assertEqual(rg.call_args.kwargs["params"]["num"], 5)

    def test_num_results_capped_at_10(self):
        with mock.patch.dict(os.environ, {"GOOGLE_API_KEY": "k",
                                         "GOOGLE_CSE_ID": "c"}):
            resp = mock.MagicMock(status_code=200)
            resp.json.return_value = {"items": []}
            with mock.patch("requests.get", return_value=resp) as rg:
                self.tool._search_google("q", 50)
        self.assertEqual(rg.call_args.kwargs["params"]["num"], 10)

    def test_non_200_returns_failure(self):
        with mock.patch.dict(os.environ, {"GOOGLE_API_KEY": "k",
                                         "GOOGLE_CSE_ID": "c"}):
            resp = mock.MagicMock(status_code=403)
            with mock.patch("requests.get", return_value=resp):
                r = self.tool._search_google("q", 3)
        self.assertEqual(r, {"query": "q", "results": [], "engine": "google",
                             "error": "Google search failed"})

    def test_exception_returns_failure(self):
        with mock.patch.dict(os.environ, {"GOOGLE_API_KEY": "k",
                                         "GOOGLE_CSE_ID": "c"}), \
                mock.patch("requests.get", side_effect=Exception("net")), \
                mock.patch.object(ws, "logger") as lg:
            r = self.tool._search_google("q", 3)
        self.assertEqual(r["error"], "Google search failed")
        lg.error.assert_called_once()


class BingTests(unittest.TestCase):
    def setUp(self):
        self.tool = ws.WebSearchTool()

    def test_no_api_key(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            r = self.tool._search_bing("q", 3)
        self.assertEqual(r, {"query": "q", "results": [],
                             "error": "Bing API key not configured",
                             "engine": "bing"})

    def test_success(self):
        with mock.patch.dict(os.environ, {"BING_API_KEY": "bk"}):
            data = {"webPages": {"value": [
                {"name": "T1", "snippet": "S1", "url": "u1"},
                {"name": "T2", "snippet": "S2", "url": "u2"},
            ]}}
            resp = mock.MagicMock(status_code=200)
            resp.json.return_value = data
            with mock.patch("requests.get", return_value=resp) as rg:
                r = self.tool._search_bing("q", 5)
        self.assertEqual(r["engine"], "bing")
        self.assertEqual(len(r["results"]), 2)
        self.assertEqual(r["results"][0]["source"], "Bing")
        self.assertEqual(rg.call_args.kwargs["headers"]
                         ["Ocp-Apim-Subscription-Key"], "bk")

    def test_num_results_capped_at_50(self):
        with mock.patch.dict(os.environ, {"BING_API_KEY": "bk"}):
            resp = mock.MagicMock(status_code=200)
            resp.json.return_value = {"webPages": {"value": []}}
            with mock.patch("requests.get", return_value=resp) as rg:
                self.tool._search_bing("q", 100)
        self.assertEqual(rg.call_args.kwargs["params"]["count"], 50)

    def test_non_200_returns_failure(self):
        with mock.patch.dict(os.environ, {"BING_API_KEY": "bk"}):
            resp = mock.MagicMock(status_code=401)
            with mock.patch("requests.get", return_value=resp):
                r = self.tool._search_bing("q", 3)
        self.assertEqual(r, {"query": "q", "results": [], "engine": "bing",
                             "error": "Bing search failed"})

    def test_exception_returns_failure(self):
        with mock.patch.dict(os.environ, {"BING_API_KEY": "bk"}), \
                mock.patch("requests.get", side_effect=Exception("net")), \
                mock.patch.object(ws, "logger") as lg:
            r = self.tool._search_bing("q", 3)
        self.assertEqual(r["error"], "Bing search failed")
        lg.error.assert_called_once()


class GetNewsTests(unittest.TestCase):
    def setUp(self):
        self.tool = ws.WebSearchTool()

    def test_feedparser_not_installed(self):
        # block feedparser import
        with mock.patch.dict("sys.modules", {"feedparser": None}):
            r = self.tool.get_news("technology", 3)
        self.assertEqual(r, {"topic": "technology", "results": [],
                             "error": "feedparser not installed"})

    def test_success(self):
        feedparser = mock.MagicMock()
        entry = mock.MagicMock()
        entry.get = lambda k, default="": {
            "title": "News Title", "link": "http://news",
            "published": "2026-01-01", "source": {"title": "Src"}}.get(k, default)
        feedparser.parse.return_value = mock.MagicMock(entries=[entry])
        with mock.patch.dict("sys.modules", {"feedparser": feedparser}):
            r = self.tool.get_news("science", 2)
        self.assertEqual(r["topic"], "science")
        self.assertEqual(r["engine"], "google_news_rss")
        self.assertEqual(len(r["results"]), 1)
        self.assertEqual(r["results"][0]["title"], "News Title")
        self.assertEqual(r["results"][0]["source"], "Src")

    def test_source_not_dict(self):
        feedparser = mock.MagicMock()
        entry = mock.MagicMock()
        entry.get = lambda k, default="": {
            "title": "T", "link": "u", "published": "p",
            "source": "not-a-dict"}.get(k, default)
        feedparser.parse.return_value = mock.MagicMock(entries=[entry])
        with mock.patch.dict("sys.modules", {"feedparser": feedparser}):
            r = self.tool.get_news("world", 1)
        self.assertEqual(r["results"][0]["source"], "Google News")

    def test_unknown_topic_defaults_technology_feed(self):
        feedparser = mock.MagicMock()
        feedparser.parse.return_value = mock.MagicMock(entries=[])
        with mock.patch.dict("sys.modules", {"feedparser": feedparser}):
            r = self.tool.get_news("unknown-topic", 1)
        self.assertEqual(r["topic"], "unknown-topic")
        self.assertEqual(r["results"], [])

    def test_exception_returns_error(self):
        feedparser = mock.MagicMock()
        feedparser.parse.side_effect = Exception("parse fail")
        with mock.patch.dict("sys.modules", {"feedparser": feedparser}), \
                mock.patch.object(ws, "logger") as lg:
            r = self.tool.get_news("technology", 1)
        self.assertEqual(r["topic"], "technology")
        self.assertEqual(r["results"], [])
        self.assertEqual(r["error"], "parse fail")
        lg.error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
