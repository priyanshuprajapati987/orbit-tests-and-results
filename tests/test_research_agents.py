"""Unit tests for orbit/orbit/agents/research_agents.py (LLM + tools mocked)."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.agents.research_agents import (
    ResearchAgent,
    WritingAgent,
    SEOAgent,
    FineTuneAgent,
    ThumbnailAgent,
)


SEARCH_RESULTS = {
    "results": [
        {"title": "Python Guide", "snippet": "Learn python basics", "url": "https://a.com"},
        {"title": "Advanced Python", "snippet": "Advanced techniques here", "url": "https://b.com"},
    ]
}


class TestResearchAgent(unittest.TestCase):
    def setUp(self):
        self.agent = ResearchAgent()

    def test_instantiation(self):
        self.assertEqual(self.agent.label, "RES")
        self.assertIsNone(self.agent._tool)

    def test_can_handle_two_keywords(self):
        self.assertTrue(self.agent.can_handle("latest news today"))

    def test_can_handle_intent_single(self):
        self.assertTrue(self.agent.can_handle("news", intent="news"))

    def test_can_handle_single_no_intent(self):
        self.assertFalse(self.agent.can_handle("news"))

    def test_can_handle_none(self):
        self.assertFalse(self.agent.can_handle("hello there"))

    def test_run_news(self):
        tool = MagicMock()
        tool.handle_natural.return_value = "5 headlines"
        with patch.object(self.agent, "_get_tool", return_value=tool):
            r = self.agent.execute("latest news about ai")
        self.assertEqual(r, "5 headlines")

    def test_run_news_empty_falls_to_llm(self):
        tool = MagicMock()
        tool.handle_natural.return_value = ""
        with patch.object(self.agent, "_get_tool", return_value=tool), \
             patch("orbit.agents.research_agents.llm_router.generate", return_value="llm answer"):
            r = self.agent.execute("latest news")
        self.assertEqual(r, "llm answer")

    def test_run_search_results(self):
        search = MagicMock()
        search.search.return_value = SEARCH_RESULTS
        with patch.object(self.agent, "_get_search_tool", return_value=search):
            r = self.agent.execute("search for python tips")
        self.assertIn("Search results for 'python tips'", r)
        self.assertIn("Python Guide", r)

    def test_run_search_failed(self):
        search = MagicMock()
        search.search.return_value = None
        with patch.object(self.agent, "_get_search_tool", return_value=search):
            r = self.agent.execute("search for python")
        self.assertIn("Search failed", r)

    def test_run_search_no_results(self):
        search = MagicMock()
        search.search.return_value = {"results": []}
        with patch.object(self.agent, "_get_search_tool", return_value=search):
            r = self.agent.execute("search for python")
        self.assertIn("No search results", r)

    def test_run_fallback_llm(self):
        with patch.object(self.agent, "_get_tool", return_value=None), \
             patch("orbit.agents.research_agents.llm_router.generate", return_value="llm answer") as gen:
            r = self.agent.execute("tell me a story")
        self.assertEqual(r, "llm answer")
        self.assertIn("RESEARCH specialist", gen.call_args.kwargs["system_prompt"])

    def test_run_context_appended(self):
        with patch.object(self.agent, "_get_tool", return_value=None), \
             patch("orbit.agents.research_agents.llm_router.generate", return_value="x") as gen:
            self.agent.execute("plain text", context="ctx")
        self.assertIn("[Context]", gen.call_args.kwargs["system_prompt"])


class TestWritingAgent(unittest.TestCase):
    def setUp(self):
        self.agent = WritingAgent()

    def test_instantiation(self):
        self.assertEqual(self.agent.label, "WRI")

    def test_can_handle_two_keywords(self):
        self.assertTrue(self.agent.can_handle("write an email"))

    def test_can_handle_single(self):
        self.assertFalse(self.agent.can_handle("email"))

    def test_can_handle_none(self):
        self.assertFalse(self.agent.can_handle("hello"))

    def test_email_not_configured(self):
        email_tool = MagicMock()
        email_tool.check_config.return_value = {"configured": False}
        with patch("orbit.tools.email_tool.EmailTool", return_value=email_tool):
            r = self.agent.execute("send email to someone@example.com")
        self.assertIn("not configured", r)

    def test_email_no_recipient(self):
        email_tool = MagicMock()
        email_tool.check_config.return_value = {"configured": True}
        with patch("orbit.tools.email_tool.EmailTool", return_value=email_tool):
            r = self.agent.execute("send email please")
        self.assertIn("Provide recipient email", r)

    def test_email_sent(self):
        email_tool = MagicMock()
        email_tool.check_config.return_value = {"configured": True}
        email_tool.send.return_value = {"success": True}
        with patch("orbit.tools.email_tool.EmailTool", return_value=email_tool), \
             patch("orbit.agents.research_agents.llm_router.generate", return_value="body text"):
            r = self.agent.execute("send email to user@example.com subject Hello there")
        self.assertIn("Email sent to user@example.com", r)
        email_tool.send.assert_called_once()

    def test_email_failed(self):
        email_tool = MagicMock()
        email_tool.check_config.return_value = {"configured": True}
        email_tool.send.return_value = {"success": False, "error": "smtp down"}
        with patch("orbit.tools.email_tool.EmailTool", return_value=email_tool), \
             patch("orbit.agents.research_agents.llm_router.generate", return_value="body"):
            r = self.agent.execute("send email to user@example.com")
        self.assertIn("Email failed", r)

    def test_email_tool_error(self):
        with patch("orbit.tools.email_tool.EmailTool", side_effect=RuntimeError("bad smtp")):
            r = self.agent.execute("send email to user@example.com")
        self.assertIn("Email tool error", r)

    def test_save_success(self):
        ft = MagicMock()
        ft.write.return_value = {"success": True}
        with patch.object(self.agent, "_get_file_tool", return_value=ft), \
             patch("orbit.agents.research_agents.llm_router.generate", return_value="written content"):
            r = self.agent.execute("write to notes.txt")
        self.assertIn("Saved to: notes.txt", r)

    def test_save_failure(self):
        ft = MagicMock()
        ft.write.return_value = {"success": False, "error": "denied"}
        with patch.object(self.agent, "_get_file_tool", return_value=ft), \
             patch("orbit.agents.research_agents.llm_router.generate", return_value="content"):
            r = self.agent.execute("save to out.txt")
        self.assertIn("Failed to save", r)

    def test_save_exception(self):
        ft = MagicMock()
        ft.write.side_effect = RuntimeError("disk full")
        with patch.object(self.agent, "_get_file_tool", return_value=ft), \
             patch("orbit.agents.research_agents.llm_router.generate", return_value="content"):
            r = self.agent.execute("save to out.txt")
        self.assertIn("Save failed", r)

    def test_plain_write(self):
        with patch("orbit.agents.research_agents.llm_router.generate", return_value="a poem"):
            r = self.agent.execute("write a poem about rain")
        self.assertEqual(r, "a poem")


class TestSEOAgent(unittest.TestCase):
    def setUp(self):
        self.agent = SEOAgent()

    def test_instantiation(self):
        self.assertEqual(self.agent.label, "SEO")

    def test_can_handle(self):
        self.assertTrue(self.agent.can_handle("seo audit please"))
        self.assertFalse(self.agent.can_handle("hello world"))

    def test_analyze_page_with_url(self):
        seo = MagicMock()
        seo.full_audit.return_value = {"report": "AUDIT REPORT"}
        with patch.object(self.agent, "_get_seo_tool", return_value=seo):
            r = self.agent.execute("analyze page https://example.com")
        self.assertEqual(r, "AUDIT REPORT")

    def test_analyze_page_error(self):
        seo = MagicMock()
        seo.full_audit.return_value = {"error": "timeout"}
        with patch.object(self.agent, "_get_seo_tool", return_value=seo):
            r = self.agent.execute("analyze page https://example.com")
        self.assertIn("SEO audit failed", r)

    def test_analyze_page_no_url(self):
        with patch.object(self.agent, "_get_seo_tool", return_value=MagicMock()):
            r = self.agent.execute("analyze page")
        self.assertIn("Provide a URL", r)

    def test_keyword_density(self):
        seo = MagicMock()
        seo._fetch_html.return_value = "<html>python python</html>"
        seo._parse_html.return_value = {"text": "python python is fun"}
        seo.keyword_density.return_value = {
            "total_words": 4, "unique_words": 3, "target_keyword": "python",
            "keyword_count": 2, "keyword_density_pct": 50.0, "advice": "ok",
            "top_words": [("python", 2), ("is", 1)],
        }
        with patch.object(self.agent, "_get_seo_tool", return_value=seo):
            r = self.agent.execute("keyword density for python https://example.com")
        self.assertIn("Keyword Density Analysis", r)
        self.assertIn("Total words: 4", r)

    def test_keyword_density_no_url(self):
        with patch.object(self.agent, "_get_seo_tool", return_value=MagicMock()):
            r = self.agent.execute("keyword density for python")
        self.assertIn("Provide a URL and keyword", r)

    def test_keyword_research(self):
        search = MagicMock()
        search.search.return_value = SEARCH_RESULTS
        with patch.object(self.agent, "_get_search_tool", return_value=search):
            r = self.agent.execute("keyword research python")
        self.assertIn("Keyword research for 'python'", r)
        self.assertIn("Based on 2 search results", r)

    def test_keyword_research_empty_query(self):
        with patch.object(self.agent, "_get_search_tool", return_value=MagicMock()):
            r = self.agent.execute("keyword research")
        self.assertIn("What topic", r)

    def test_keyword_research_search_fail(self):
        search = MagicMock()
        search.search.return_value = None
        with patch.object(self.agent, "_get_search_tool", return_value=search):
            r = self.agent.execute("keyword research python")
        self.assertIn("Search failed", r)

    def test_serp_analysis(self):
        search = MagicMock()
        search.search.return_value = SEARCH_RESULTS
        with patch.object(self.agent, "_get_search_tool", return_value=search):
            r = self.agent.execute("serp analysis for python")
        self.assertIn("SERP Analysis for 'python'", r)
        self.assertIn("Found 2 results", r)

    def test_competitor_analysis(self):
        search = MagicMock()
        search.search.return_value = SEARCH_RESULTS
        with patch.object(self.agent, "_get_search_tool", return_value=search):
            r = self.agent.execute("competitor analysis for notion")
        self.assertIn("Competitor Analysis", r)

    def test_backlink_analysis(self):
        search = MagicMock()
        search.search.return_value = SEARCH_RESULTS
        with patch.object(self.agent, "_get_search_tool", return_value=search):
            r = self.agent.execute("backlinks for example.com")
        self.assertIn("Backlink Analysis", r)
        self.assertIn("Ahrefs", r)

    def test_backlink_empty_query(self):
        with patch.object(self.agent, "_get_search_tool", return_value=MagicMock()):
            r = self.agent.execute("backlink")
        self.assertIn("What domain", r)

    def test_check_url_audit(self):
        seo = MagicMock()
        seo.full_audit.return_value = {"report": "OK REPORT"}
        with patch.object(self.agent, "_get_seo_tool", return_value=seo):
            r = self.agent.execute("check https://example.com")
        self.assertEqual(r, "OK REPORT")

    def test_fallback_llm(self):
        with patch.object(self.agent, "_get_search_tool", return_value=MagicMock()), \
             patch.object(self.agent, "_get_seo_tool", return_value=MagicMock()), \
             patch("orbit.agents.research_agents.llm_router.generate", return_value="llm seo text") as gen:
            r = self.agent.execute("optimize my site")
        self.assertEqual(r, "llm seo text")
        self.assertIn("SEO specialist", gen.call_args.kwargs["system_prompt"])


class TestFineTuneAgent(unittest.TestCase):
    def setUp(self):
        self.agent = FineTuneAgent()

    def test_instantiation(self):
        self.assertEqual(self.agent.label, "FTN")

    def test_can_handle_two_keywords(self):
        self.assertTrue(self.agent.can_handle("fine-tune training data"))

    def test_can_handle_single(self):
        self.assertFalse(self.agent.can_handle("train the model"))

    def test_save_success(self):
        ft = MagicMock()
        ft.write.return_value = {"success": True}
        with patch.object(self.agent, "_get_file_tool", return_value=ft), \
             patch("orbit.agents.research_agents.llm_router.generate", return_value="tuning notes"):
            r = self.agent.execute("save to tune.json")
        self.assertIn("Saved to: tune.json", r)

    def test_save_no_match_returns_content(self):
        with patch("orbit.agents.research_agents.llm_router.generate", return_value="content"):
            r = self.agent.execute("save my work")
        self.assertEqual(r, "content")

    def test_research_with_results(self):
        search = MagicMock()
        search.search.return_value = SEARCH_RESULTS
        with patch.object(self.agent, "_get_search_tool", return_value=search), \
             patch("orbit.agents.research_agents.llm_router.generate", return_value="llm research") as gen:
            r = self.agent.execute("find best practices for llm")
        self.assertEqual(r, "llm research")
        self.assertIn("[Research Data]", gen.call_args.kwargs["system_prompt"])

    def test_research_empty_query_fallback(self):
        with patch("orbit.agents.research_agents.llm_router.generate", return_value="llm text"):
            r = self.agent.execute("find")
        self.assertEqual(r, "llm text")

    def test_research_no_results_fallback(self):
        search = MagicMock()
        search.search.return_value = {"results": []}
        with patch.object(self.agent, "_get_search_tool", return_value=search), \
             patch("orbit.agents.research_agents.llm_router.generate", return_value="llm text"):
            r = self.agent.execute("find tips for training")
        self.assertEqual(r, "llm text")

    def test_fallback_llm(self):
        with patch("orbit.agents.research_agents.llm_router.generate", return_value="llm text") as gen:
            r = self.agent.execute("hello")
        self.assertEqual(r, "llm text")
        self.assertIn("FINE-TUNING specialist", gen.call_args.kwargs["system_prompt"])


class TestThumbnailAgent(unittest.TestCase):
    def setUp(self):
        self.agent = ThumbnailAgent()

    def test_instantiation(self):
        self.assertEqual(self.agent.label, "THB")

    def test_can_handle_two_keywords(self):
        self.assertTrue(self.agent.can_handle("thumbnail design ideas"))

    def test_can_handle_single(self):
        self.assertFalse(self.agent.can_handle("banner"))

    def test_save_success(self):
        ft = MagicMock()
        ft.write.return_value = {"success": True}
        with patch.object(self.agent, "_get_file_tool", return_value=ft), \
             patch("orbit.agents.research_agents.llm_router.generate", return_value="thumb desc"):
            r = self.agent.execute("save to thumb.txt")
        self.assertIn("Saved to: thumb.txt", r)

    def test_save_no_match_returns_content(self):
        with patch("orbit.agents.research_agents.llm_router.generate", return_value="content"):
            r = self.agent.execute("save the design")
        self.assertEqual(r, "content")

    def test_reference_search(self):
        search = MagicMock()
        search.search.return_value = SEARCH_RESULTS
        with patch.object(self.agent, "_get_search_tool", return_value=search):
            r = self.agent.execute("show reference examples for gaming thumbnails")
        self.assertIn("Reference designs for", r)
        self.assertIn("Python Guide", r)

    def test_reference_no_results_fallback(self):
        search = MagicMock()
        search.search.return_value = {"results": []}
        with patch.object(self.agent, "_get_search_tool", return_value=search), \
             patch("orbit.agents.research_agents.llm_router.generate", return_value="llm text"):
            r = self.agent.execute("find inspiration for poster")
        self.assertEqual(r, "llm text")

    def test_fallback_llm(self):
        with patch("orbit.agents.research_agents.llm_router.generate", return_value="llm text") as gen:
            r = self.agent.execute("describe a poster")
        self.assertEqual(r, "llm text")
        self.assertIn("THUMBNAIL DESIGN specialist", gen.call_args.kwargs["system_prompt"])


if __name__ == "__main__":
    unittest.main()
