"""Unit tests for orbit/orbit/core/doc_summarizer.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.doc_summarizer import DocumentSummarizer, get_document_summarizer


class TestDocumentSummarizer(unittest.TestCase):
    def setUp(self):
        self.s = DocumentSummarizer()

    def test_short_text_returned(self):
        text = "Hello world. This is short."
        self.assertEqual(self.s.summarize(text, 3), text)

    def test_summarize_returns_n_sentences(self):
        text = (
            "Python is great. "
            "It has many libraries. "
            "Data science uses python. "
            "Machine learning too. "
            "Web development as well."
        )
        r = self.s.summarize(text, 2)
        # Should contain 2 sentences
        self.assertEqual(len([s for s in r.split(". ") if s.strip()]), 2)

    def test_summarize_default(self):
        text = "A. B. C. D. E."
        r = self.s.summarize(text)
        self.assertTrue(isinstance(r, str))

    def test_empty_text(self):
        r = self.s.summarize("", 3)
        self.assertEqual(r, "")

    def test_singleton(self):
        a = get_document_summarizer()
        b = get_document_summarizer()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
