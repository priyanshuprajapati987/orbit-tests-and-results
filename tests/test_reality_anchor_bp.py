"""Unit tests for orbit/orbit/core/reality_anchor_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.reality_anchor_bp import reality_anchor_bp


class TestRealityAnchorBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(reality_anchor_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(reality_anchor_bp.name, "reality_anchor")

    def test_url_prefix(self):
        self.assertEqual(reality_anchor_bp.url_prefix, "/api/reality-anchor")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/reality-anchor/scan", "/api/reality-anchor/record-stance", "/api/reality-anchor/reset"]:
            self.assertIn(p, rules)

    def test_scan_missing_text_400(self):
        r = self.client.post("/api/reality-anchor/scan", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_scan_success(self):
        with patch("orbit.core.reality_anchor_bp.get_reality_anchor") as gr:
            gr.return_value.scan_text.return_value = {"flagged": False}
            r = self.client.post("/api/reality-anchor/scan", json={"text": "hi"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["flagged"], False)
        gr.return_value.scan_text.assert_called_once_with("hi")

    def test_scan_no_body(self):
        r = self.client.post("/api/reality-anchor/scan")
        self.assertEqual(r.status_code, 400)

    def test_record_stance(self):
        with patch("orbit.core.reality_anchor_bp.get_reality_anchor") as gr:
            gr.return_value.record_stance.return_value = {"stance": "x"}
            r = self.client.post("/api/reality-anchor/record-stance", json={"text": "hi"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        self.assertEqual(r.get_json()["stance"], {"stance": "x"})
        gr.return_value.record_stance.assert_called_once_with("hi")

    def test_record_stance_empty(self):
        with patch("orbit.core.reality_anchor_bp.get_reality_anchor") as gr:
            gr.return_value.record_stance.return_value = None
            r = self.client.post("/api/reality-anchor/record-stance", json={"text": ""})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()["ok"])
        self.assertIsNone(r.get_json()["stance"])

    def test_record_stance_no_body(self):
        with patch("orbit.core.reality_anchor_bp.get_reality_anchor") as gr:
            gr.return_value.record_stance.return_value = None
            r = self.client.post("/api/reality-anchor/record-stance")
        self.assertEqual(r.status_code, 200)
        gr.return_value.record_stance.assert_called_once_with("")

    def test_reset(self):
        with patch("orbit.core.reality_anchor_bp.get_reality_anchor") as gr:
            r = self.client.post("/api/reality-anchor/reset")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        gr.return_value.reset.assert_called_once()


if __name__ == "__main__":
    unittest.main()
