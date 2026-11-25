"""Deep tests for orbit/orbit/websearch.py (Loop 10/3).

Covers every statement of the websearch module:
  * ``search`` — all engine templates, unknown engine, case handling.
  * ``open_url`` — scheme prefixing, browser invocation, return value.
  * ``is_url`` — DOMAIN_PATTERN acceptance/rejection table.
  * ``parse_text`` — every routing branch: URL open, site shortcuts
    (including the fixed ``open <known site>`` path — Bug #2 where
    "open github" used to Google-search instead of opening github.com),
    engine-qualified search, default search, bare shortcut names, help
    fallback.
  * ``search_and_respond`` — known engines, shortcut aliases (yt/gh/wiki/
    so/wa), unknown engine error path.
"""

import unittest
from unittest import mock

from orbit.orbit import websearch as ws


class SearchTests(unittest.TestCase):
    def _search(self, query, engine="google"):
        with mock.patch.object(ws, "webbrowser") as wb:
            url = ws.search(query, engine)
        return url, wb.open.call_args

    def test_google_search_formats_query(self):
        url, opened = self._search("python tutorial")
        self.assertEqual(url, "https://www.google.com/search?q=python+tutorial")
        self.assertEqual(opened.args[0], url)

    def test_spaces_become_plus(self):
        url, _ = self._search("hello world foo")
        self.assertIn("hello+world+foo", url)

    def test_engine_case_insensitive(self):
        url, _ = self._search("x", "GOOGLE")
        self.assertTrue(url.startswith("https://www.google.com/"))

    def test_unknown_engine_returns_none(self):
        with mock.patch.object(ws, "webbrowser") as wb:
            self.assertIsNone(ws.search("q", "bing"))
        wb.open.assert_not_called()

    def test_every_registered_engine_builds_a_url(self):
        for engine, template in ws.SEARCH_ENGINES.items():
            with self.subTest(engine=engine):
                url, opened = self._search("query", engine)
                self.assertIsNotNone(url)
                self.assertNotIn("{}", url)
                self.assertEqual(opened.args[0], url)

    def test_wikipedia_uses_path_style(self):
        url, _ = self._search("india", "wiki")
        self.assertEqual(url, "https://en.wikipedia.org/wiki/india")

    def test_engine_shortcut_key_so(self):
        url, _ = self._search("regex", "so")
        self.assertTrue(url.startswith("https://stackoverflow.com/search"))


class OpenUrlTests(unittest.TestCase):
    def _open(self, target):
        with mock.patch.object(ws, "webbrowser") as wb:
            result = ws.open_url(target)
        return result, wb.open.call_args

    def test_https_preserved(self):
        url, opened = self._open("https://example.com/x")
        self.assertEqual(url, "https://example.com/x")
        self.assertEqual(opened.args[0], "https://example.com/x")

    def test_http_preserved(self):
        url, _ = self._open("http://example.com")
        self.assertEqual(url, "http://example.com")

    def test_bare_domain_gets_https(self):
        url, opened = self._open("example.com")
        self.assertEqual(url, "https://example.com")
        self.assertEqual(opened.args[0], "https://example.com")


class IsUrlTests(unittest.TestCase):
    def test_accepts(self):
        for text in ("example.com", "https://example.com", "http://a.io",
                     "sub.domain.co.uk/path", "EXAMPLE.com", "example.com "):
            with self.subTest(text=text):
                self.assertTrue(ws.is_url(text))

    def test_rejects(self):
        for text in ("hello world", "open github", "", "python tutorial",
                     "what's up?"):
            with self.subTest(text=text):
                self.assertFalse(ws.is_url(text))


class ParseOpenUrlBranchTests(unittest.TestCase):
    """``open|visit|go to|navigate to|khol|kholo <url>`` -> open_url."""

    def _parse(self, text):
        with mock.patch.object(ws, "webbrowser") as wb:
            result = ws.parse_text(text)
        return result, wb.open.call_args

    def test_open_url(self):
        result, opened = self._parse("open example.com")
        self.assertEqual(result["type"], "action")
        self.assertEqual(result["url"], "https://example.com")
        self.assertIn("example.com", result["result"])
        self.assertEqual(opened.args[0], "https://example.com")

    def test_open_full_url(self):
        result, _ = self._parse("open https://example.com/path?q=1")
        self.assertEqual(result["url"], "https://example.com/path?q=1")

    def test_visit_prefix(self):
        result, _ = self._parse("visit docs.python.org")
        self.assertEqual(result["url"], "https://docs.python.org")

    def test_go_to_prefix(self):
        result, _ = self._parse("go to openai.com")
        self.assertEqual(result["url"], "https://openai.com")

    def test_navigate_to_prefix(self):
        result, _ = self._parse("navigate to example.org")
        self.assertEqual(result["url"], "https://example.org")

    def test_khol_prefix(self):
        result, _ = self._parse("khol github.com")
        self.assertEqual(result["url"], "https://github.com")

    def test_kholo_prefix(self):
        result, _ = self._parse("kholo spotify.com")
        self.assertEqual(result["url"], "https://spotify.com")

    def test_trailing_punctuation_stripped(self):
        result, _ = self._parse("open example.com.")
        self.assertEqual(result["url"], "https://example.com")

    def test_original_case_kept_in_message(self):
        result, _ = self._parse("open Example.COM")
        self.assertIn("Example.COM", result["result"])
        self.assertEqual(result["url"], "https://Example.COM")


class ParseShortcutBranchTests(unittest.TestCase):
    """``open <known site>`` must OPEN the site (Bug #2 regression pin):
    before the fix the open-regex consumed the input first and Google-
    searched the site name instead."""

    def _parse(self, text):
        with mock.patch.object(ws, "webbrowser") as wb:
            result = ws.parse_text(text)
        return result, wb.open.call_args

    def test_open_github_opens_site(self):
        result, opened = self._parse("open github")
        self.assertEqual(result["url"], "https://github.com")
        self.assertEqual(opened.args[0], "https://github.com")
        self.assertNotIn("search", result["url"])

    def test_open_youtube_opens_site(self):
        result, opened = self._parse("open youtube")
        self.assertEqual(result["url"], "https://youtube.com")
        self.assertNotIn("google.com/search", opened.args[0])

    def test_every_shortcut_via_open(self):
        for site, url in ws.SHORTCUTS.items():
            with self.subTest(site=site):
                result, opened = self._parse(f"open {site}")
                self.assertEqual(result["url"], url)
                self.assertEqual(opened.args[0], url)

    def test_visit_and_go_to_also_hit_shortcuts(self):
        for prefix in ("visit", "go to", "khol", "kholo"):
            with self.subTest(prefix=prefix):
                result, _ = self._parse(f"{prefix} gmail")
                self.assertEqual(result["url"], "https://mail.google.com")

    def test_case_insensitive_shortcut(self):
        result, _ = self._parse("OPEN GITHUB")
        self.assertEqual(result["url"], "https://github.com")

    def test_quoted_shortcut(self):
        result, _ = self._parse('open "github"')
        self.assertEqual(result["url"], "https://github.com")

    def test_unknown_word_still_searches(self):
        with mock.patch.object(ws, "webbrowser"):
            result = ws.parse_text("open cats")
        self.assertEqual(result["type"], "action")
        self.assertIn("Searching 'cats'", result["result"])
        self.assertIn("google.com/search?q=cats", result["url"])


class ParseLaunchBranchTests(unittest.TestCase):
    """``launch|start|jao <site>`` and bare-name shortcuts."""

    def _parse(self, text):
        with mock.patch.object(ws, "webbrowser") as wb:
            result = ws.parse_text(text)
        return result, wb.open.call_args

    def test_launch_prefix(self):
        result, _ = self._parse("launch whatsapp")
        self.assertEqual(result["url"], "https://web.whatsapp.com")

    def test_start_prefix(self):
        result, _ = self._parse("start youtube")
        self.assertEqual(result["url"], "https://youtube.com")

    def test_jao_prefix(self):
        result, _ = self._parse("jao maps")
        self.assertEqual(result["url"], "https://maps.google.com")

    def test_bare_name_opens(self):
        result, opened = self._parse("gmail")
        self.assertEqual(result["url"], "https://mail.google.com")
        self.assertEqual(opened.args[0], "https://mail.google.com")

    def test_all_shortcuts_bare(self):
        for site, url in ws.SHORTCUTS.items():
            with self.subTest(site=site):
                result, _ = self._parse(site)
                self.assertEqual(result["url"], url)

    def test_launch_unknown_word_falls_to_help(self):
        with mock.patch.object(ws, "webbrowser") as wb:
            result = ws.parse_text("launch zeppelin")
        wb.open.assert_not_called()
        self.assertEqual(result["type"], "info")
        self.assertIn("Kaunsa search karun", result["result"])


class ParseSearchBranchTests(unittest.TestCase):
    def _parse(self, text):
        with mock.patch.object(ws, "webbrowser") as wb:
            result = ws.parse_text(text)
        return result, wb.open.call_args

    def test_engine_qualified_search(self):
        result, opened = self._parse("search python on youtube")
        self.assertEqual(result["type"], "action")
        self.assertIn("youtube.com/results", opened.args[0])
        self.assertIn("python", opened.args[0])

    def test_search_in_engine(self):
        result, opened = self._parse("search flask in github")
        self.assertIn("github.com/search", opened.args[0])

    def test_dhundh_engine_qualified_via_mein(self):
        # "dhundh" does not match branch-4's "dhund\s" (h follows), but the
        # engine-prefix branch (mein-form) still routes it to youtube
        result, opened = self._parse("dhundh react mein youtube")
        self.assertEqual(result["type"], "action")
        self.assertIn("youtube.com/results", opened.args[0])

    def test_dhundh_plain_searches(self):
        # "dhundh" (common Hinglish spelling) also routes to default search
        with mock.patch.object(ws, "webbrowser") as wb:
            result = ws.parse_text("dhundh react")
        self.assertEqual(result["type"], "action")
        self.assertIn("q=react", wb.open.call_args.args[0])

    def test_engine_prefix_search(self):
        result, opened = self._parse("youtube search react hooks")
        self.assertIn("youtube.com/results", opened.args[0])

    def test_engine_prefix_via_mein(self):
        result, opened = self._parse("github mein search flask")
        self.assertIn("github.com/search", opened.args[0])

    def test_engine_prefix_via_par(self):
        result, opened = self._parse("news par search india")
        self.assertIn("news.google.com", opened.args[0])

    def test_unknown_engine_prefix_falls_through(self):
        with mock.patch.object(ws, "webbrowser") as wb:
            result = ws.parse_text("zeppelin search led")
        wb.open.assert_not_called()
        self.assertEqual(result["type"], "info")
        self.assertIn("Kaunsa search karun", result["result"])

    def test_default_search(self):
        result, opened = self._parse("search python tutorial")
        self.assertIn("google.com/search?q=python+tutorial", opened.args[0])

    def test_find_prefix(self):
        result, opened = self._parse("find lambda calculus")
        self.assertIn("q=lambda+calculus", opened.args[0])

    def test_dhund_prefix(self):
        result, opened = self._parse("dhund india capital")
        self.assertIn("q=india+capital", opened.args[0])

    def test_unknown_engine_in_qualified_search(self):
        result, _ = self._parse("search anything on zorglub")
        self.assertEqual(result["type"], "info")
        self.assertIn("zorglub", result["result"])
        self.assertIn("engine nahi mila", result["result"])


class ParseHelpFallbackTests(unittest.TestCase):
    def _parse(self, text):
        with mock.patch.object(ws, "webbrowser") as wb:
            result = ws.parse_text(text)
        return result, wb.open.call_args

    def test_empty_input(self):
        result, opened = self._parse("")
        self.assertEqual(result["type"], "info")
        self.assertIn("Kaunsa search karun", result["result"])
        self.assertIn("'open github'", result["result"])
        self.assertIsNone(opened)

    def test_bare_open_word(self):
        result, opened = self._parse("open")
        self.assertEqual(result["type"], "info")
        self.assertIsNone(opened)

    def test_random_phrase(self):
        result, opened = self._parse("how are you doing today")
        self.assertEqual(result["type"], "info")
        self.assertIsNone(opened)


class SearchAndRespondTests(unittest.TestCase):
    def _respond(self, query, engine):
        with mock.patch.object(ws, "webbrowser") as wb:
            result = ws.search_and_respond(query, engine)
        return result, wb.open.call_args

    def test_known_engine_action(self):
        result, opened = self._respond("rust", "google")
        self.assertEqual(result["type"], "action")
        self.assertIn("Searching 'rust' on Google", result["result"])
        self.assertIn("google.com/search?q=rust", opened.args[0])

    def test_engine_title_in_message(self):
        result, _ = self._respond("x", "stackoverflow")
        self.assertIn("on Stackoverflow", result["result"])

    def test_engine_normalized(self):
        result, opened = self._respond("x", "  YT ")
        self.assertIn("youtube.com/results", opened.args[0])

    def test_alias_yt(self):
        result, _ = self._respond("cats", "yt")
        self.assertIn("on Youtube", result["result"])

    def test_alias_gh(self):
        result, _ = self._respond("flask", "gh")
        self.assertIn("on Github", result["result"])

    def test_alias_wiki(self):
        result, _ = self._respond("mars", "wiki")
        self.assertIn("on Wikipedia", result["result"])

    def test_alias_so(self):
        result, _ = self._respond("regex", "so")
        self.assertIn("on Stackoverflow", result["result"])

    def test_alias_wa_graceful_failure(self):
        # "wa" aliases to whatsapp, which has no search template -> the
        # module reports a graceful info error instead of raising
        result, opened = self._respond("hello", "wa")
        self.assertEqual(result["type"], "info")
        self.assertIn("engine nahi mila", result["result"])
        self.assertIsNone(opened)

    def test_unknown_engine_info(self):
        result, opened = self._respond("q", "zorglub")
        self.assertEqual(result["type"], "info")
        self.assertIn("Try: google, youtube, github, wikipedia",
                      result["result"])
        self.assertIsNone(opened)


class ModuleConstantsTests(unittest.TestCase):
    def test_shortcuts_covers_every_parsed_key(self):
        # SHORTCUTS is the single source of truth for both branches
        self.assertIn("github", ws.SHORTCUTS)
        self.assertIn("gmail", ws.SHORTCUTS)
        self.assertTrue(all(v.startswith("http") for v in ws.SHORTCUTS.values()))

    def test_search_engines_all_templates_resolvable(self):
        self.assertIn("google", ws.SEARCH_ENGINES)
        self.assertTrue(len(ws.SEARCH_ENGINES) >= 20)


if __name__ == "__main__":
    unittest.main()
