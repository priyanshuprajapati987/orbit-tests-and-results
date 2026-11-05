"""Tests for screen understanding improvements (content-aware prompts, mode detection)."""

from unittest.mock import MagicMock, patch


class TestScreenAnalysisPrompts:
    def test_prompt_dict_has_all_modes(self):
        from orbit.orbit.screen import SCREEN_ANALYSIS_PROMPTS

        expected = {
            "quick",
            "detailed",
            "ui_elements",
            "code",
            "browser",
            "terminal",
            "document",
            "ocr",
        }
        assert expected.issubset(set(SCREEN_ANALYSIS_PROMPTS.keys()))

    def test_prompt_values_are_strings(self):
        from orbit.orbit.screen import SCREEN_ANALYSIS_PROMPTS

        for mode, prompt in SCREEN_ANALYSIS_PROMPTS.items():
            assert isinstance(prompt, str), f"Mode {mode} prompt is not a string"
            assert len(prompt) > 20, f"Mode {mode} prompt too short"

    def test_vision_models_list(self):
        from orbit.orbit.screen import VISION_MODELS

        assert "llava" in VISION_MODELS
        assert "gemma3:4b" in VISION_MODELS
        assert "gemma3:12b" in VISION_MODELS
        assert "minicpm-v" in VISION_MODELS


class TestAnalyzeScreenshot:
    @patch("orbit.orbit.screen.vision_analyze")
    def test_analyze_screenshot_quick_mode(self, mock_vision):
        mock_vision.return_value = "A desktop with a code editor open"
        from orbit.orbit.screen import analyze_screenshot

        with patch(
            "orbit.orbit.screen._image_to_base64",
            return_value="data:image/png;base64,abc",
        ), patch("builtins.open", MagicMock()):
            with patch("orbit.orbit.screen.os.path.exists", return_value=True):
                result = analyze_screenshot("/tmp/test.png", mode="quick")
                assert "text" in result

    @patch("orbit.orbit.screen.vision_analyze")
    def test_analyze_screenshot_ocr_mode(self, mock_vision):
        mock_vision.return_value = ""
        from orbit.orbit.screen import analyze_screenshot

        with patch(
            "orbit.orbit.screen._image_to_base64",
            return_value="data:image/png;base64,abc",
        ), patch("builtins.open", MagicMock()):
            with patch("orbit.orbit.screen.os.path.exists", return_value=True):
                result = analyze_screenshot("/tmp/test.png", mode="ocr")
                assert "text" in result

    def test_analyze_screenshot_missing_file(self):
        from orbit.orbit.screen import analyze_screenshot

        result = analyze_screenshot("/nonexistent/file.png")
        assert "failed" in result["text"].lower()

    @patch("orbit.orbit.screen.vision_analyze")
    def test_analyze_screenshot_code_mode(self, mock_vision):
        mock_vision.return_value = "Python code with a class definition"
        from orbit.orbit.screen import analyze_screenshot

        with patch(
            "orbit.orbit.screen._image_to_base64",
            return_value="data:image/png;base64,abc",
        ), patch("builtins.open", MagicMock()):
            with patch("orbit.orbit.screen.os.path.exists", return_value=True):
                result = analyze_screenshot("/tmp/test.png", mode="code")
                assert "text" in result


class TestCaptureAndAnalyze:
    @patch("orbit.orbit.screen.capture_screen", return_value=None)
    def test_capture_failure(self, mock_cap):
        from orbit.orbit.screen import capture_and_analyze

        result = capture_and_analyze()
        assert "failed" in result["text"].lower()
        assert result["path"] is None

    @patch("orbit.orbit.screen.analyze_screenshot")
    @patch("orbit.orbit.screen.capture_screen", return_value="/tmp/test.png")
    def test_mode_passthrough(self, mock_cap, mock_analyze):
        mock_analyze.return_value = {"text": "ok", "image_b64": ""}
        from orbit.orbit.screen import capture_and_analyze

        capture_and_analyze(mode="detailed")
        mock_analyze.assert_called_once()


class TestMultiModalAgent:
    def test_detect_content_mode_code(self):
        from orbit.orbit.agents.multimodal_agent import MultiModalAgent

        agent = MultiModalAgent()
        assert agent._detect_content_mode("show me the code in vscode") == "code"

    def test_detect_content_mode_browser(self):
        from orbit.orbit.agents.multimodal_agent import MultiModalAgent

        agent = MultiModalAgent()
        assert agent._detect_content_mode("what's on the browser page") == "browser"

    def test_detect_content_mode_terminal(self):
        from orbit.orbit.agents.multimodal_agent import MultiModalAgent

        agent = MultiModalAgent()
        assert agent._detect_content_mode("check the terminal output") == "terminal"

    def test_detect_content_mode_document(self):
        from orbit.orbit.agents.multimodal_agent import MultiModalAgent

        agent = MultiModalAgent()
        assert agent._detect_content_mode("read the word document") == "document"

    def test_detect_content_mode_ui_elements(self):
        from orbit.orbit.agents.multimodal_agent import MultiModalAgent

        agent = MultiModalAgent()
        assert agent._detect_content_mode("what buttons are visible") == "ui_elements"

    def test_detect_content_mode_detailed(self):
        from orbit.orbit.agents.multimodal_agent import MultiModalAgent

        agent = MultiModalAgent()
        assert agent._detect_content_mode("describe everything in detail") == "detailed"

    def test_detect_content_mode_quick_default(self):
        from orbit.orbit.agents.multimodal_agent import MultiModalAgent

        agent = MultiModalAgent()
        assert agent._detect_content_mode("what's on screen") == "quick"

    def test_can_handle_screenshot(self):
        from orbit.orbit.agents.multimodal_agent import MultiModalAgent

        agent = MultiModalAgent()
        assert agent.can_handle("take a screenshot")

    def test_can_handle_ocr(self):
        from orbit.orbit.agents.multimodal_agent import MultiModalAgent

        agent = MultiModalAgent()
        assert agent.can_handle("ocr this image")
