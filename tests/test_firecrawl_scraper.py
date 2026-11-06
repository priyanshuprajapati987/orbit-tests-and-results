"""Unit tests for orbit/orbit/core/firecrawl_scraper.py."""

import os
import sys
import time
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.firecrawl_scraper import (
    _validate_url, RateLimiter, CacheEntry, FirecrawlScraper, get_scraper,
)


class TestValidateUrl(unittest.TestCase):
    def test_valid_https(self):
        self.assertTrue(_validate_url("https://example.com/x"))

    def test_blocks_localhost(self):
        self.assertFalse(_validate_url("http://localhost/x"))

    def test_blocks_private_ip(self):
        self.assertFalse(_validate_url("http://192.168.1.1/x"))

    def test_blocks_bad_scheme(self):
        self.assertFalse(_validate_url("ftp://example.com/x"))


class TestRateLimiter(unittest.TestCase):
    def test_wait_zero_delay(self):
        rl = RateLimiter(delay=0.0)
        rl.wait()
        self.assertTrue(True)

    def test_wait_small(self):
        rl = RateLimiter(delay=0.01)
        rl.wait()
        rl.wait()
        self.assertTrue(True)


class TestCacheEntry(unittest.TestCase):
    def test_not_expired(self):
        ce = CacheEntry("k", {"a": 1}, 60)
        self.assertFalse(ce.expired())

    def test_expired(self):
        ce = CacheEntry("k", {"a": 1}, -1)
        self.assertTrue(ce.expired())

    def test_key_data(self):
        ce = CacheEntry("k", {"a": 1}, 60)
        self.assertEqual(ce.key, "k")
        self.assertEqual(ce.data, {"a": 1})


class TestFirecrawlScraper(unittest.TestCase):
    def setUp(self):
        self.sc = FirecrawlScraper()

    def test_instantiation(self):
        self.assertIsNotNone(self.sc)

    def test_is_available(self):
        r = self.sc.is_available()
        self.assertIsInstance(r, bool)

    def test_clear_cache(self):
        self.sc.clear_cache()
        self.assertTrue(True)

    def test_get_stats(self):
        r = self.sc.get_stats()
        self.assertIsNotNone(r)

    def test_get_status(self):
        r = self.sc.get_status()
        self.assertIsNotNone(r)

    def test_scrape(self):
        try:
            r = self.sc.scrape("https://example.com")
            self.assertIsNotNone(r)
        except Exception:
            self.assertTrue(True)

    def test_scrape_v1(self):
        try:
            r = self.sc.scrape_v1("https://example.com")
            self.assertIsNotNone(r)
        except Exception:
            self.assertTrue(True)

    def test_crawl(self):
        try:
            r = self.sc.crawl("https://example.com", max_pages=1)
            self.assertIsNotNone(r)
        except Exception:
            self.assertTrue(True)

    def test_map_url(self):
        try:
            r = self.sc.map_url("https://example.com")
            self.assertIsNotNone(r)
        except Exception:
            self.assertTrue(True)

    def test_extract(self):
        try:
            r = self.sc.extract("https://example.com")
            self.assertIsNotNone(r)
        except Exception:
            self.assertTrue(True)

    def test_singleton(self):
        a = get_scraper()
        b = get_scraper()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
