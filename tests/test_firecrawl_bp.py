"""Unit tests for orbit/orbit/core/firecrawl_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.firecrawl_bp import firecrawl_bp


class TestFirecrawlBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(firecrawl_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(firecrawl_bp.name, "firecrawl_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/firecrawl/status", "/api/firecrawl/scrape", "/api/firecrawl/crawl",
                  "/api/firecrawl/map", "/api/firecrawl/extract", "/api/firecrawl/cache",
                  "/api/firecrawl/stats"]:
            self.assertIn(p, rules)

    def test_status(self):
        with patch("orbit.core.firecrawl_scraper.get_scraper") as gs:
            gs.return_value.get_status.return_value = {"ok": True}
            r = self.client.get("/api/firecrawl/status")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])

    def test_scrape_missing_url_400(self):
        r = self.client.post("/api/firecrawl/scrape", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_scrape_blocked_403(self):
        with patch("orbit.core.firecrawl_bp.validate_url", return_value=(False, "nope")):
            r = self.client.post("/api/firecrawl/scrape", json={"url": "http://bad"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("url not allowed", r.get_json()["error"])

    def test_scrape_success(self):
        with patch("orbit.core.firecrawl_bp.validate_url", return_value=(True, "ok")), \
             patch("orbit.core.firecrawl_scraper.get_scraper") as gs:
            gs.return_value.scrape.return_value = {"content": "hi"}
            r = self.client.post("/api/firecrawl/scrape", json={"url": "http://good", "formats": ["md"]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["content"], "hi")
        gs.return_value.scrape.assert_called_once_with("http://good", formats=["md"])

    def test_scrape_no_body(self):
        r = self.client.post("/api/firecrawl/scrape")
        self.assertEqual(r.status_code, 400)

    def test_crawl_missing_url_400(self):
        r = self.client.post("/api/firecrawl/crawl", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_crawl_blocked_403(self):
        with patch("orbit.core.firecrawl_bp.validate_url", return_value=(False, "nope")):
            r = self.client.post("/api/firecrawl/crawl", json={"url": "http://bad"})
        self.assertEqual(r.status_code, 403)

    def test_crawl_success(self):
        with patch("orbit.core.firecrawl_bp.validate_url", return_value=(True, "ok")), \
             patch("orbit.core.firecrawl_scraper.get_scraper") as gs:
            gs.return_value.crawl.return_value = {"pages": 3}
            r = self.client.post("/api/firecrawl/crawl", json={"url": "http://good", "max_pages": 10, "ignore_sitemap": True})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["pages"], 3)
        gs.return_value.crawl.assert_called_once_with("http://good", max_pages=10, ignore_sitemap=True)

    def test_crawl_no_body(self):
        r = self.client.post("/api/firecrawl/crawl")
        self.assertEqual(r.status_code, 400)

    def test_map_missing_url_400(self):
        r = self.client.post("/api/firecrawl/map", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_map_blocked_403(self):
        with patch("orbit.core.firecrawl_bp.validate_url", return_value=(False, "nope")):
            r = self.client.post("/api/firecrawl/map", json={"url": "http://bad"})
        self.assertEqual(r.status_code, 403)

    def test_map_success(self):
        with patch("orbit.core.firecrawl_bp.validate_url", return_value=(True, "ok")), \
             patch("orbit.core.firecrawl_scraper.get_scraper") as gs:
            gs.return_value.map_url.return_value = {"links": ["a"]}
            r = self.client.post("/api/firecrawl/map", json={"url": "http://good", "search": "q"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["links"], ["a"])
        gs.return_value.map_url.assert_called_once_with("http://good", search="q")

    def test_map_no_body(self):
        r = self.client.post("/api/firecrawl/map")
        self.assertEqual(r.status_code, 400)

    def test_extract_missing_urls_400(self):
        r = self.client.post("/api/firecrawl/extract", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_extract_blocked_403(self):
        with patch("orbit.core.firecrawl_bp.validate_url", return_value=(False, "nope")):
            r = self.client.post("/api/firecrawl/extract", json={"urls": ["http://bad"]})
        self.assertEqual(r.status_code, 403)
        self.assertIn("url not allowed", r.get_json()["error"])

    def test_extract_success(self):
        with patch("orbit.core.firecrawl_bp.validate_url", return_value=(True, "ok")), \
             patch("orbit.core.firecrawl_scraper.get_scraper") as gs:
            gs.return_value.extract.return_value = {"extracted": True}
            r = self.client.post("/api/firecrawl/extract", json={"urls": ["http://good"], "prompt": "p"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["extracted"])
        gs.return_value.extract.assert_called_once_with(["http://good"], prompt="p")

    def test_extract_no_body(self):
        r = self.client.post("/api/firecrawl/extract")
        self.assertEqual(r.status_code, 400)

    def test_clear_cache(self):
        with patch("orbit.core.firecrawl_scraper.get_scraper") as gs:
            r = self.client.delete("/api/firecrawl/cache")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        gs.return_value.clear_cache.assert_called_once()

    def test_stats(self):
        with patch("orbit.core.firecrawl_scraper.get_scraper") as gs:
            gs.return_value.get_stats.return_value = {"total": 5}
            r = self.client.get("/api/firecrawl/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)


if __name__ == "__main__":
    unittest.main()
