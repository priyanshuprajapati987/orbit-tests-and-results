"""Tests for ORBIT multi-modal screen understanding.

Verifies the unified vision fallback chain (vision_analyze: Ollama -> OpenRouter
-> graceful), its result cache, and that ScreenIntelligence actually analyzes
screenshots (previously it passed a truncated base64 string as text to the LLM
router, so analysis never happened).
"""

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from orbit.orbit.agents.multimodal_agent import MultiModalAgent
from orbit.orbit.core.screen_intelligence import ScreenIntelligence
from orbit.orbit.screen import (
    _VISION_CACHE,
    analyze_screenshot,
    vision_analyze,
)


def _make_png(path):
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\nFAKEDATA")


class TestVisionAnalyze(unittest.TestCase):
    def setUp(self):
        _VISION_CACHE.clear()

    def test_empty_image_returns_empty_without_calling(self):
        with patch("orbit.orbit.screen.requests.post") as mp:
            self.assertEqual(vision_analyze("", "describe"), "")
            mp.assert_not_called()

    def test_uses_ollama_first_with_images_array(self):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"message": {"content": "a cat"}}
        with (
            patch("orbit.orbit.screen.requests.post", return_value=resp) as mp,
            patch("orbit.orbit.screen._detect_vision_model", return_value="llava"),
        ):
            out = vision_analyze("BASE64DATA", "describe")
        self.assertEqual(out, "a cat")
        args, kwargs = mp.call_args_list[0]
        self.assertIn("/api/chat", args[0])
        self.assertEqual(kwargs["json"]["messages"][0]["images"], ["BASE64DATA"])

    def test_openrouter_fallback_when_ollama_empty(self):
        ollama_resp = MagicMock(status_code=200)
        ollama_resp.json.return_value = {}  # -> empty content, triggers fallback
        or_resp = MagicMock(status_code=200)
        or_resp.json.return_value = {
            "choices": [{"message": {"content": "openrouter dog"}}]
        }

        def fake_post(url, **kwargs):
            return or_resp if "openrouter" in url else ollama_resp

        with (
            patch("orbit.orbit.screen.requests.post", side_effect=fake_post),
            patch("orbit.orbit.screen._detect_vision_model", return_value="llava"),
            patch("orbit.orbit.config.decrypt_env", return_value="sk-test"),
        ):
            out = vision_analyze("BASE64DATA", "describe")
        self.assertEqual(out, "openrouter dog")

    def test_all_fail_returns_empty(self):
        with (
            patch("orbit.orbit.screen.requests.post", side_effect=Exception("boom")),
            patch("orbit.orbit.screen._detect_vision_model", return_value="llava"),
            patch("orbit.orbit.config.decrypt_env", return_value=""),
        ):
            self.assertEqual(vision_analyze("BASE64DATA", "describe"), "")

    def test_caches_identical_frames(self):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"message": {"content": "same"}}
        with (
            patch("orbit.orbit.screen.requests.post", return_value=resp) as mp,
            patch("orbit.orbit.screen._detect_vision_model", return_value="llava"),
        ):
            vision_analyze("IMG", "p")
            vision_analyze("IMG", "p")
        self.assertEqual(mp.call_count, 1)


class TestAnalyzeScreenshot(unittest.TestCase):
    def test_vision_path_returns_analysis(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            _make_png(f.name)
            path = f.name
        try:
            with patch(
                "orbit.orbit.screen.vision_analyze", return_value="desktop with code"
            ) as mv:
                res = analyze_screenshot(path, "describe this")
            self.assertEqual(res["text"], "desktop with code")
            mv.assert_called_once()
        finally:
            os.unlink(path)

    def test_none_path_returns_dict(self):
        self.assertIn("text", analyze_screenshot(None))


class TestMultiModalAnalyzeImage(unittest.TestCase):
    def test_analyze_image_uses_vision_analyze(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            _make_png(f.name)
            path = f.name
        try:
            with (
                patch(
                    "orbit.orbit.screen.vision_analyze", return_value="a red ball"
                ) as mv,
                patch("orbit.orbit.screen._detect_vision_model", return_value="llava"),
            ):
                res = MultiModalAgent().analyze_image(path)
            self.assertEqual(res["analysis"], "a red ball")
            self.assertEqual(res["vision_model"], "llava")
            mv.assert_called_once()
        finally:
            os.unlink(path)


class TestScreenIntelligenceVision(unittest.TestCase):
    def test_analyze_parses_json_from_real_image(self):
        si = ScreenIntelligence()
        payload = json.dumps(
            {
                "activity": "coding",
                "details": "writing code",
                "energy_hint": "high",
                "should_interrupt": False,
            }
        )
        with patch("orbit.orbit.screen.vision_analyze", return_value=payload):
            result = si._analyze_screenshot("BASE64IMG")
        self.assertIsNotNone(result)
        self.assertEqual(result.activity, "coding")
        self.assertFalse(result.should_interrupt)

    def test_analyze_no_response_returns_none(self):
        si = ScreenIntelligence()
        with patch("orbit.orbit.screen.vision_analyze", return_value=""):
            self.assertIsNone(si._analyze_screenshot("BASE64IMG"))


if __name__ == "__main__":
    unittest.main()
