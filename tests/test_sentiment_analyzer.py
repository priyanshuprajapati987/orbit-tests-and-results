"""Unit tests for orbit/orbit/core/sentiment_analyzer.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.sentiment_analyzer import SentimentAnalyzer, get_sentiment_analyzer


class TestSentimentAnalyzer(unittest.TestCase):
    def setUp(self):
        self.a = SentimentAnalyzer()

    def test_positive(self):
        r = self.a.analyze("This is great and amazing, I love it")
        self.assertEqual(r["sentiment"], "positive")
        self.assertGreater(r["positive"], 0)
        self.assertEqual(r["negative"], 0)

    def test_negative(self):
        r = self.a.analyze("This is terrible and awful, I hate it")
        self.assertEqual(r["sentiment"], "negative")
        self.assertGreater(r["negative"], 0)

    def test_neutral_no_keywords(self):
        r = self.a.analyze("The sky is blue today")
        self.assertEqual(r["sentiment"], "neutral")
        self.assertEqual(r["score"], 0.0)

    def test_neutral_mixed(self):
        r = self.a.analyze("good bad")
        self.assertEqual(r["sentiment"], "neutral")

    def test_score_rounded(self):
        r = self.a.analyze("good great bad")
        self.assertEqual(r["score"], round((2 - 1) / 3, 2))

    def test_empty_text(self):
        r = self.a.analyze("")
        self.assertEqual(r["sentiment"], "neutral")
        self.assertEqual(r["positive"], 0)
        self.assertEqual(r["negative"], 0)

    def test_singleton(self):
        a = get_sentiment_analyzer()
        b = get_sentiment_analyzer()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
