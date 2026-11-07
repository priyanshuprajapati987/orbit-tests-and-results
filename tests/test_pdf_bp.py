"""Unit tests for orbit/orbit/core/pdf_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.pdf_bp import pdf_bp


class TestPdfBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(pdf_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(pdf_bp.name, "pdf")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/pdf/read", "/api/pdf/analyze", "/api/pdf/metadata"]:
            self.assertIn(p, rules)

    def test_read_missing_path_400(self):
        r = self.client.post("/api/pdf/read", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_read_success(self):
        with patch("orbit.core.pdf_bp.read_pdf", return_value={"content": "text"}) as rp, \
             patch("orbit.tools.pdf_reader.read_pdf", return_value={"content": "text"}):
            r = self.client.post("/api/pdf/read", json={"path": "doc.pdf"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["content"], "text")
        rp.assert_called_once_with("doc.pdf")

    def test_read_no_body(self):
        r = self.client.post("/api/pdf/read")
        self.assertEqual(r.status_code, 400)

    def test_analyze_missing_path_400(self):
        r = self.client.post("/api/pdf/analyze", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_analyze_success(self):
        agent = patch("orbit.agents.multimodal_agent.get_multimodal_agent").start()
        agent.return_value.analyze_pdf.return_value = {"status": "analyzed"}
        r = self.client.post("/api/pdf/analyze", json={"path": "doc.pdf"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertEqual(r.get_json()["result"]["status"], "analyzed")
        agent.return_value.analyze_pdf.assert_called_once_with("doc.pdf")
        patch.stopall()

    def test_analyze_no_body(self):
        r = self.client.post("/api/pdf/analyze")
        self.assertEqual(r.status_code, 400)

    def test_metadata_missing_path_400(self):
        r = self.client.post("/api/pdf/metadata", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_metadata_success(self):
        with patch("orbit.core.pdf_bp.read_pdf", return_value={
            "file": "doc.pdf", "size_mb": 1.2, "metadata": {"pages": 3},
            "engine": "pypdf", "content": "hello world"
        }), patch("orbit.tools.pdf_reader.read_pdf", return_value={
            "file": "doc.pdf", "size_mb": 1.2, "metadata": {"pages": 3},
            "engine": "pypdf", "content": "hello world"
        }):
            r = self.client.post("/api/pdf/metadata", json={"path": "doc.pdf"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["file"], "doc.pdf")
        self.assertEqual(body["size_mb"], 1.2)
        self.assertEqual(body["metadata"]["pages"], 3)
        self.assertEqual(body["engine"], "pypdf")
        self.assertEqual(body["content_preview"], "hello world")

    def test_metadata_error(self):
        with patch("orbit.core.pdf_bp.read_pdf", return_value={"error": "bad pdf"}), \
             patch("orbit.tools.pdf_reader.read_pdf", return_value={"error": "bad pdf"}):
            r = self.client.post("/api/pdf/metadata", json={"path": "doc.pdf"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_metadata_no_body(self):
        r = self.client.post("/api/pdf/metadata")
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
