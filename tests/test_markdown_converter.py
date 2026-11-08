"""Unit tests for orbit/orbit/core/markdown_converter.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

import orbit.core.markdown_converter as mc
from orbit.core.markdown_converter import MarkdownConverter, get_markdown_converter


class TestMarkdownConverter(unittest.TestCase):
    def setUp(self):
        self.c = MarkdownConverter()

    def test_to_html_success(self):
        r = self.c.to_html("# Hello")
        self.assertIn("html", r)
        self.assertIn("<h1", r["html"])
        self.assertIn("Hello", r["html"])
        self.assertEqual(r["length"], len(r["html"]))

    def test_to_html_empty(self):
        r = self.c.to_html("")
        self.assertIn("html", r)

    def test_extract_toc(self):
        text = "# Title\n## Sub\n### Subsub\n"
        r = self.c.extract_toc(text)
        self.assertEqual(r["count"], 3)
        self.assertEqual(r["toc"][0], {"level": 1, "text": "Title"})
        self.assertEqual(r["toc"][1], {"level": 2, "text": "Sub"})

    def test_extract_toc_empty(self):
        r = self.c.extract_toc("no headings here")
        self.assertEqual(r["count"], 0)
        self.assertEqual(r["toc"], [])

    def test_strip_markdown(self):
        text = "# Title\n**bold** and *italic* [link](url) `code`"
        r = self.c.strip_markdown(text)
        self.assertEqual(r["text"], "Title\nbold and italic link code")

    def test_strip_code_block(self):
        text = "before\n```\ncode here\n```\nafter"
        r = self.c.strip_markdown(text)
        self.assertIn("text", r)
        self.assertIn("before", r["text"])
        self.assertIn("after", r["text"])

    def test_no_markdown_module(self):
        with patch.object(mc, "HAS_MARKDOWN", False):
            r = mc.MarkdownConverter().to_html("# hi")
            r2 = mc.MarkdownConverter().extract_toc("# hi")
        self.assertIn("error", r)
        self.assertIn("error", r2)

    def test_singleton(self):
        # reset global
        mc._md = None
        a = get_markdown_converter()
        b = get_markdown_converter()
        self.assertIs(a, b)
        mc._md = None


if __name__ == "__main__":
    unittest.main()
