"""Unit tests for orbit/orbit/core/text_similarity.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.text_similarity import TextSimilarity, get_similarity


class TestTextSimilarity(unittest.TestCase):
    def setUp(self):
        self.ts = TextSimilarity()

    def test_instantiation(self):
        self.assertIsNotNone(self.ts)

    def test_compare_identical(self):
        r = self.ts.compare("hello world", "hello world")
        self.assertEqual(r["jaccard"], 1.0)
        self.assertEqual(r["levenshtein"], 1.0)

    def test_compare_different(self):
        r = self.ts.compare("hello world", "foo bar")
        self.assertEqual(r["jaccard"], 0.0)

    def test_compare_empty(self):
        r = self.ts.compare("", "")
        self.assertEqual(r["jaccard"], 0.0)

    def test_common_words(self):
        r = self.ts.compare("hello world foo", "hello bar foo")
        self.assertEqual(r["common_words"]["count"], 2)
        self.assertIn("hello", r["common_words"]["words"])

    def test_cosine(self):
        r = self.ts.compare("a b", "a b")
        self.assertEqual(r["cosine"], 1.0)

    def test_truncate(self):
        long = "a " * 10000
        r = self.ts.compare(long, long)
        self.assertIsNotNone(r)

    def test_singleton(self):
        a = get_similarity()
        b = get_similarity()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
