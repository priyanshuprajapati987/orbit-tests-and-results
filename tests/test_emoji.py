"""Unit tests for orbit/orbit/emoji.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.emoji import search, search_format, parse_text, get_random


class TestEmoji(unittest.TestCase):
    def test_search(self):
        r = search("happy")
        self.assertIsInstance(r, list)

    def test_search_format(self):
        r = search_format("happy")
        self.assertIsInstance(r, str)

    def test_parse_text(self):
        r = parse_text("emoji happy")
        self.assertIsInstance(r, dict)

    def test_get_random(self):
        r = get_random()
        self.assertIsInstance(r, str)
        self.assertGreater(len(r), 0)


if __name__ == "__main__":
    unittest.main()
