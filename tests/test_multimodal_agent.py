"""Unit tests for orbit/orbit/agents/multimodal_agent.py (vision/screen/LLM mocked)."""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.agents.multimodal_agent import (
    AnalysisResult,
    MultiModalAgent,
    get_multimodal_agent,
)


class TestAnalysisResult(unittest.TestCase):
    def test_defaults(self):
        r = AnalysisResult()
        self.assertEqual(r.source_type, "")
        self.assertEqual(r.metadata, {})


class TestMultiModalAgent(unittest.TestCase):
    def setUp(self):
        self.agent = MultiModalAgent()

    def test_instantiation(self):
        self.assertEqual(self.agent.label, "MMA")
        self.assertEqual(self.agent._task_type, "vision")

    def test_can_handle_image(self):
        self.assertTrue(self.agent.can_handle("analyze this image"))

    def test_can_handle_screenshot(self):
        self.assertTrue(self.agent.can_handle("take a screenshot"))

    def test_can_handle_pdf(self):
        self.assertTrue(self.agent.can_handle("summarize this pdf"))

    def test_can_handle_plain(self):
        self.assertFalse(self.agent.can_handle("hello there"))

    def test_detect_content_mode_code(self):
        self.assertEqual(self.agent._detect_content_mode("show me the code editor"), "code")

    def test_detect_content_mode_browser(self):
        self.assertEqual(self.agent._detect_content_mode("open browser page"), "browser")

    def test_detect_content_mode_terminal(self):
        self.assertEqual(self.agent._detect_content_mode("terminal output"), "terminal")

    def test_detect_content_mode_document(self):
        self.assertEqual(self.agent._detect_content_mode("word document"), "document")

    def test_detect_content_mode_ui(self):
        self.assertEqual(self.agent._detect_content_mode("click the button"), "ui_elements")

    def test_detect_content_mode_detailed(self):
        self.assertEqual(self.agent._detect_content_mode("describe everything"), "detailed")

    def test_detect_content_mode_quick(self):
        self.assertEqual(self.agent._detect_content_mode("plain text"), "quick")

    def test_run_ocr_with_file(self):
        with patch.object(self.agent, "ocr_image", return_value={"text": "OCR TEXT"}) as m:
            r = self.agent.execute("ocr C:/imgs/scan.png")
            self.assertEqual(r, "OCR TEXT")
            m.assert_called_once()

    def test_run_ocr_no_file(self):
        with patch.object(self.agent, "_capture_and_ocr", return_value={"text": "captured"}):
            r = self.agent.execute("ocr the screen")
            self.assertEqual(r, {"text": "captured"})

    def test_run_screenshot(self):
        with patch.object(self.agent, "analyze_screenshot", return_value={"analysis": "a screen"}):
            r = self.agent.execute("screenshot please")
            self.assertEqual(r, "a screen")

    def test_run_image_file(self):
        with patch.object(self.agent, "analyze_image", return_value={"status": "analyzed"}) as m:
            r = self.agent.execute("analyze C:/pics/photo.png now")
            self.assertEqual(r["status"], "analyzed")
            m.assert_called_once()

    def test_run_generic(self):
        with patch.object(self.agent, "analyze_image_text", return_value={"status": "ok"}) as m:
            r = self.agent.execute("read this chart")
            self.assertEqual(r["status"], "ok")
            m.assert_called_once()

    def test_capture_and_ocr_no_path(self):
        with patch("orbit.screen.capture_screen", return_value=None):
            r = self.agent._capture_and_ocr()
            self.assertIn("unavailable", r["text"].lower())

    def test_capture_and_ocr_failure(self):
        with patch("orbit.screen.capture_screen", side_effect=RuntimeError("no display")):
            r = self.agent._capture_and_ocr()
            self.assertIn("failed", r["text"].lower())

    def test_analyze_image_missing(self):
        r = self.agent.analyze_image("C:/does/not/exist/xyz.png")
        self.assertIn("error", r)

    def test_analyze_image_success(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"\x89PNG fake bytes")
            p = f.name
        try:
            with patch("orbit.screen._detect_vision_model", return_value="gemini"), \
                 patch("orbit.screen.vision_analyze", return_value="a cat on a table"):
                r = self.agent.analyze_image(p)
            self.assertEqual(r["status"], "analyzed")
            self.assertEqual(r["analysis"], "a cat on a table")
            self.assertEqual(r["vision_model"], "gemini")
        finally:
            os.unlink(p)

    def test_analyze_image_vision_error(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"jpg")
            p = f.name
        try:
            with patch("orbit.screen._detect_vision_model", side_effect=RuntimeError("no model")):
                r = self.agent.analyze_image(p)
            self.assertIn("error", r)
        finally:
            os.unlink(p)

    def test_analyze_image_text_with_path(self):
        with patch.object(self.agent, "analyze_image", return_value={"status": "analyzed"}) as m:
            r = self.agent.analyze_image_text("look at C:/pics/shot.webp please")
            self.assertEqual(r["status"], "analyzed")
            m.assert_called_once()

    def test_analyze_image_text_screen_ok(self):
        with patch("orbit.screen.capture_and_analyze", return_value={"text": "screen says hi", "image_b64": "b64", "path": "/p.png"}):
            r = self.agent.analyze_image_text("what do you see")
            self.assertEqual(r["status"], "analyzed")
            self.assertEqual(r["analysis"], "screen says hi")

    def test_analyze_image_text_screen_fail(self):
        with patch("orbit.screen.capture_and_analyze", side_effect=RuntimeError("no cam")):
            r = self.agent.analyze_image_text("describe")
            self.assertEqual(r["status"], "error")

    def test_analyze_image_text_no_capture(self):
        with patch("orbit.screen.capture_and_analyze", return_value={}):
            r = self.agent.analyze_image_text("describe")
            self.assertEqual(r["status"], "error")

    def test_analyze_screenshot_ok(self):
        with patch("orbit.screen.capture_and_analyze", return_value={"text": "ui text", "image_b64": "x", "path": "/s.png"}):
            r = self.agent.analyze_screenshot(mode="code")
            self.assertEqual(r["status"], "analyzed")
            self.assertEqual(r["mode"], "code")

    def test_analyze_screenshot_error(self):
        with patch("orbit.screen.capture_and_analyze", side_effect=RuntimeError("fail")):
            r = self.agent.analyze_screenshot()
            self.assertEqual(r["status"], "error")

    def test_analyze_pdf_error(self):
        with patch("orbit.tools.pdf_reader.read_pdf", return_value={"error": "bad pdf"}):
            r = self.agent.analyze_pdf("x.pdf")
            self.assertIn("error", r)

    def test_analyze_pdf_ok(self):
        fake = {"content": "some text " * 50, "metadata": {"pages": 3}, "engine": "pypdf", "file": "x.pdf", "size_mb": 0.1}
        with patch("orbit.tools.pdf_reader.read_pdf", return_value=fake):
            with patch("orbit.core.llm.legacy_adapter.generate", return_value="summary here"):
                r = self.agent.analyze_pdf("x.pdf")
        self.assertEqual(r["status"], "analyzed")
        self.assertEqual(r["pages"], 3)
        self.assertEqual(r["analysis"], "summary here")

    def test_analyze_chart_flag(self):
        with patch.object(self.agent, "analyze_image", return_value={"status": "analyzed"}):
            r = self.agent.analyze_chart("chart.png")
        self.assertTrue(r["chart_analysis"])

    def test_ocr_image_missing(self):
        r = self.agent.ocr_image("C:/no/such/file.png")
        self.assertIn("error", r)

    def test_ocr_image_fallback_screen(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"png")
            p = f.name
        try:
            with patch.dict(sys.modules, {"pytesseract": None}):
                # force ImportError path by making pytesseract import fail
                with patch("orbit.screen.analyze_screenshot", return_value={"text": "ocr text"}):
                    r = self.agent.ocr_image(p)
            self.assertEqual(r["status"], "success")
            self.assertEqual(r["text"], "ocr text")
        finally:
            os.unlink(p)

    def test_singleton(self):
        a = get_multimodal_agent()
        b = get_multimodal_agent()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
