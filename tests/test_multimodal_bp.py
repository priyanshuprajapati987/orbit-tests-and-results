"""Unit tests for orbit/orbit/core/multimodal_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.multimodal_bp import multimodal_bp


class TestMultimodalBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(multimodal_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(multimodal_bp.name, "multimodal")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/multimodal/analyze", rules)
        self.assertIn("/api/multimodal/capabilities", rules)

    def _policy_allowed(self):
        decision = MagicMock()
        decision.allowed = True
        decision.reason = ""
        pe = MagicMock()
        pe.check_path.return_value = decision
        return pe

    def test_analyze_image(self):
        agent = MagicMock()
        agent.analyze_image.return_value = {"status": "ok"}
        pe = self._policy_allowed()
        with patch("orbit.core.multimodal_bp.get_multimodal_agent", return_value=agent), \
             patch("orbit.core.policy_engine.get_policy_engine", return_value=pe):
            r = self.client.post("/api/multimodal/analyze", json={"image_path": "img.png", "type": "image"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertEqual(r.get_json()["result"], {"status": "ok"})
        agent.analyze_image.assert_called_once_with("img.png")
        pe.check_path.assert_called_once_with("img.png", mutate=False)

    def test_analyze_blocked_path_403(self):
        decision = MagicMock()
        decision.allowed = False
        decision.reason = "nope"
        pe = MagicMock()
        pe.check_path.return_value = decision
        with patch("orbit.core.policy_engine.get_policy_engine", return_value=pe):
            r = self.client.post("/api/multimodal/analyze", json={"image_path": "secret.png", "type": "image"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("path not allowed", r.get_json()["error"])

    def test_analyze_screenshot(self):
        agent = MagicMock()
        agent.analyze_screenshot.return_value = {"status": "ok"}
        with patch("orbit.core.multimodal_bp.get_multimodal_agent", return_value=agent):
            r = self.client.post("/api/multimodal/analyze", json={"type": "screenshot"})
        self.assertEqual(r.status_code, 200)
        agent.analyze_screenshot.assert_called_once()

    def test_analyze_pdf(self):
        agent = MagicMock()
        agent.analyze_pdf.return_value = {"status": "ok"}
        pe = self._policy_allowed()
        with patch("orbit.core.multimodal_bp.get_multimodal_agent", return_value=agent), \
             patch("orbit.core.policy_engine.get_policy_engine", return_value=pe):
            r = self.client.post("/api/multimodal/analyze", json={"image_path": "img.png", "pdf_path": "doc.pdf", "type": "pdf"})
        self.assertEqual(r.status_code, 200)
        agent.analyze_pdf.assert_called_once_with("doc.pdf")
        pe.check_path.assert_called_once_with("doc.pdf", mutate=False)

    def test_analyze_pdf_blocked(self):
        decision = MagicMock()
        decision.allowed = False
        decision.reason = "nope"
        pe = MagicMock()
        pe.check_path.return_value = decision
        with patch("orbit.core.policy_engine.get_policy_engine", return_value=pe):
            r = self.client.post("/api/multimodal/analyze", json={"image_path": "img.png", "pdf_path": "secret.pdf", "type": "pdf"})
        self.assertEqual(r.status_code, 403)

    def test_analyze_chart(self):
        agent = MagicMock()
        agent.analyze_chart.return_value = {"status": "ok"}
        pe = self._policy_allowed()
        with patch("orbit.core.multimodal_bp.get_multimodal_agent", return_value=agent), \
             patch("orbit.core.policy_engine.get_policy_engine", return_value=pe):
            r = self.client.post("/api/multimodal/analyze", json={"image_path": "chart.png", "type": "chart"})
        self.assertEqual(r.status_code, 200)
        agent.analyze_chart.assert_called_once_with("chart.png")

    def test_analyze_ocr(self):
        agent = MagicMock()
        agent.ocr_image.return_value = {"text": "hi"}
        pe = self._policy_allowed()
        with patch("orbit.core.multimodal_bp.get_multimodal_agent", return_value=agent), \
             patch("orbit.core.policy_engine.get_policy_engine", return_value=pe):
            r = self.client.post("/api/multimodal/analyze", json={"image_path": "img.png", "type": "ocr"})
        self.assertEqual(r.status_code, 200)
        agent.ocr_image.assert_called_once_with("img.png")

    def test_analyze_error(self):
        agent = MagicMock()
        agent.analyze_image.side_effect = RuntimeError("boom")
        pe = self._policy_allowed()
        with patch("orbit.core.multimodal_bp.get_multimodal_agent", return_value=agent), \
             patch("orbit.core.policy_engine.get_policy_engine", return_value=pe):
            r = self.client.post("/api/multimodal/analyze", json={"image_path": "img.png", "type": "image"})
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_analyze_no_path_skips_policy(self):
        agent = MagicMock()
        agent.analyze_image.return_value = {"status": "ok"}
        with patch("orbit.core.multimodal_bp.get_multimodal_agent", return_value=agent):
            r = self.client.post("/api/multimodal/analyze", json={"type": "image"})
        self.assertEqual(r.status_code, 200)
        agent.analyze_image.assert_called_once_with("")

    def test_capabilities(self):
        with patch("orbit.core.multimodal_bp.get_multimodal_agent"):
            r = self.client.get("/api/multimodal/capabilities")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertIn("capabilities", body)
        types = [c["type"] for c in body["capabilities"]]
        self.assertIn("image", types)
        self.assertIn("pdf", types)


if __name__ == "__main__":
    unittest.main()
