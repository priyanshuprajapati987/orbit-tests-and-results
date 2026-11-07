"""Unit tests for orbit/orbit/core/markdown_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.markdown_bp import markdown_bp


class TestMarkdownBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(markdown_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(markdown_bp.name, "markdown_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/markdown/to-html", "/api/markdown/toc", "/api/markdown/strip"]:
            self.assertIn(p, rules)

    def test_to_html(self):
        with patch("orbit.core.markdown_bp.get_markdown_converter") as gm:
            gm.return_value.to_html.return_value = "<p>hi</p>"
            r = self.client.post("/api/markdown/to-html", json={"markdown": "# hi"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), "<p>hi</p>")

    def test_toc(self):
        with patch("orbit.core.markdown_bp.get_markdown_converter") as gm:
            gm.return_value.extract_toc.return_value = ["h1"]
            r = self.client.post("/api/markdown/toc", json={"markdown": "# hi"})
        self.assertEqual(r.get_json(), ["h1"])

    def test_strip(self):
        with patch("orbit.core.markdown_bp.get_markdown_converter") as gm:
            gm.return_value.strip_markdown.return_value = "hi"
            r = self.client.post("/api/markdown/strip", json={"markdown": "# hi"})
        self.assertEqual(r.get_json(), "hi")

    def test_no_body(self):
        with patch("orbit.core.markdown_bp.get_markdown_converter") as gm:
            gm.return_value.to_html.return_value = ""
            r = self.client.post("/api/markdown/to-html")
        self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()
