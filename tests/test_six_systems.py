"""Tests for 6 ORBIT systems: VoiceCloner, Screen, RealtimeLearning,
ProactiveAssistant, MultiModalAgent, WakeWord."""

import json
import os
import struct
import tempfile
import threading
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# 1. Voice (xtts.py)
# ---------------------------------------------------------------------------
class TestVoiceCloner:
    """Tests for orbit.orbit.xtts VoiceCloner + helpers."""

    def _make_unavailable_cloner(self):
        from orbit.orbit.xtts import VoiceCloner

        cloner = VoiceCloner.__new__(VoiceCloner)
        cloner.name = "voice_cloning"
        cloner._model = None
        cloner._lock = threading.Lock()
        cloner._available = False
        return cloner

    def test_speak_returns_bool_when_unavailable(self):
        cloner = self._make_unavailable_cloner()
        assert cloner.is_available() is False
        assert cloner.speak("hello world") is False

    def test_clone_voice_unavailable(self):
        cloner = self._make_unavailable_cloner()
        result = cloner.clone_voice("/fake/ref.wav", "hello")
        assert result["success"] is False
        assert "not available" in result["error"]

    def test_clone_with_multiple_refs_empty_list(self):
        cloner = self._make_unavailable_cloner()
        result = cloner.clone_with_multiple_refs([], "hello")
        assert result["success"] is False

    def test_clone_with_multiple_refs_unavailable(self):
        cloner = self._make_unavailable_cloner()
        result = cloner.clone_with_multiple_refs(["/a.wav", "/b.wav"], "text")
        assert result["success"] is False
        assert "not available" in result["error"]

    def test_get_available_voices_returns_dict(self):
        from orbit.orbit.xtts import get_available_voices

        voices = get_available_voices()
        assert isinstance(voices, dict)
        assert len(voices) > 0
        for name, code in voices.items():
            assert isinstance(name, str)
            assert isinstance(code, str)

    def test_estimate_quality_returns_float(self):
        from orbit.orbit.xtts import _estimate_quality

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            with wave.open(path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                samples = [1000, -1000, 2000, -2000, 500, -500] * 200
                wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))
            score = _estimate_quality(path)
            assert isinstance(score, float)
            assert 0.0 <= score <= 1.0
        finally:
            os.unlink(path)

    def test_estimate_quality_short_file(self):
        from orbit.orbit.xtts import _estimate_quality

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            with wave.open(path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(struct.pack("<10h", *([100] * 10)))
            score = _estimate_quality(path)
            assert score in (0.0, 0.1)
        finally:
            os.unlink(path)

    def test_preprocess_audio_returns_none_for_empty(self):
        from orbit.orbit.xtts import _preprocess_audio

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            with wave.open(path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"")
            result = _preprocess_audio(path)
            assert result is None
        finally:
            os.unlink(path)

    def test_preprocess_audio_normalizes(self):
        from orbit.orbit.xtts import _preprocess_audio

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            with wave.open(path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                samples = [50, -50, 30, -30] * 1000
                wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))
            result = _preprocess_audio(path)
            assert result is None or isinstance(result, str)
        finally:
            os.unlink(path)

    def test_get_info_returns_expected_keys(self):
        cloner = self._make_unavailable_cloner()
        info = cloner.get_info()
        assert "available" in info
        assert "model" in info
        assert "samples_dir" in info
        assert "sample_count" in info

    def test_list_samples_returns_list(self):
        cloner = self._make_unavailable_cloner()
        samples = cloner.list_samples()
        assert isinstance(samples, list)


# ---------------------------------------------------------------------------
# 2. Screen (inner orbit/orbit/screen.py)
# ---------------------------------------------------------------------------
class TestScreen:
    """Tests for orbit.orbit.screen (inner package)."""

    def test_detect_vision_model_returns_string(self):
        from orbit.orbit.screen import _detect_vision_model

        with patch("orbit.orbit.screen.requests.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=500)
            result = _detect_vision_model()
            assert isinstance(result, str)
            assert result == "llava"

    def test_detect_vision_model_finds_installed(self):
        from orbit.orbit.screen import _detect_vision_model

        with patch("orbit.orbit.screen.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"models": [{"name": "gemma3:4b"}]}
            mock_get.return_value = mock_resp
            result = _detect_vision_model()
            assert result == "gemma3:4b"

    def test_analyze_screenshot_returns_dict(self):
        from orbit.orbit.screen import analyze_screenshot

        result = analyze_screenshot(None)
        assert isinstance(result, dict)
        assert "text" in result

    def test_analyze_screenshot_nonexistent_file(self):
        from orbit.orbit.screen import analyze_screenshot

        result = analyze_screenshot("/nonexistent/path.png")
        assert isinstance(result, dict)
        assert "text" in result

    def test_analyze_screenshot_with_mock_ollama(self):
        from orbit.orbit.screen import analyze_screenshot

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
            path = f.name
        try:
            with patch("orbit.orbit.screen.requests.post") as mock_post:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"message": {"content": "A blue screen"}}
                mock_post.return_value = mock_resp
                result = analyze_screenshot(path, "describe this")
                assert isinstance(result, dict)
                assert result["text"] == "A blue screen"
                assert "image_b64" in result
        finally:
            os.unlink(path)

    def test_capture_and_analyze_returns_dict_with_keys(self):
        from orbit.orbit.screen import capture_and_analyze

        with patch("orbit.orbit.screen.capture_screen", return_value=None):
            result = capture_and_analyze()
            assert isinstance(result, dict)
            assert "text" in result
            assert "image_b64" in result
            assert "path" in result

    def test_capture_and_analyze_with_screenshot(self):
        from orbit.orbit.screen import capture_and_analyze

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
            path = f.name
        try:
            with (
                patch("orbit.orbit.screen.capture_screen", return_value=path),
                patch("orbit.orbit.screen.requests.post") as mock_post,
            ):
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"message": {"content": "analysis"}}
                mock_post.return_value = mock_resp
                result = capture_and_analyze()
                assert "path" in result
                assert result["path"] == path
        finally:
            os.unlink(path)

    def test_image_to_base64_returns_data_uri(self):
        from orbit.orbit.screen import _image_to_base64

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake image data")
            path = f.name
        try:
            result = _image_to_base64(path)
            assert result.startswith("data:image/png;base64,")
        finally:
            os.unlink(path)

    def test_image_to_base64_nonexistent_returns_empty(self):
        from orbit.orbit.screen import _image_to_base64

        result = _image_to_base64("/nonexistent/file.png")
        assert result == ""

    def test_cleanup_removes_file(self):
        from orbit.orbit.screen import cleanup

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        assert os.path.exists(path)
        cleanup(path)
        assert not os.path.exists(path)


# ---------------------------------------------------------------------------
# 3. Real-time Learning (realtime_learning.py)
# ---------------------------------------------------------------------------
class TestRealtimeLearning:
    """Tests for orbit.orbit.core.realtime_learning."""

    def test_record_feedback_no_crash(self):
        from orbit.orbit.core.realtime_learning import RealtimeLearner

        learner = RealtimeLearner()
        result = learner.record_feedback("test query", "test response", 0.8)
        assert result["success"] is True
        assert result["rating"] == 0.8
        assert result["total_entries"] == 1

    def test_get_stats_returns_proper_keys(self):
        from orbit.orbit.core.realtime_learning import RealtimeLearner

        learner = RealtimeLearner()
        stats = learner.get_stats()
        expected = {
            "total_feedback",
            "average_rating",
            "low_ratings",
            "high_ratings",
            "adaptation_count",
            "last_adaptation",
            "preferred_style",
            "top_patterns",
        }
        assert expected.issubset(stats.keys())

    def test_adaptation_count_increments_on_low_rating(self):
        from orbit.orbit.core.realtime_learning import RealtimeLearner

        learner = RealtimeLearner()
        learner.record_feedback("q1", "r1", 0.1)
        learner.record_feedback("q2", "r2", 0.2)
        stats = learner.get_stats()
        assert stats["adaptation_count"] == 2

    def test_adaptation_count_not_increments_on_high_rating(self):
        from orbit.orbit.core.realtime_learning import RealtimeLearner

        learner = RealtimeLearner()
        learner.record_feedback("q1", "r1", 0.9)
        learner.record_feedback("q2", "r2", 1.0)
        stats = learner.get_stats()
        assert stats["adaptation_count"] == 0

    def test_pattern_detector_load_restores_topic_scores(self):
        from orbit.orbit.core.realtime_learning import PatternDetector

        PatternDetector()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(
                {
                    "topic_scores": {"machine learning": 0.9, "web dev": 0.3},
                    "query_pattern_counts": {"machine learning": 10, "web dev": 5},
                    "response_pattern_counts": {},
                },
                f,
            )
            path = Path(f.name)
        try:
            new_detector = PatternDetector()
            new_detector.load(path)
            assert new_detector.topic_scores["machine learning"] == 0.9
            assert new_detector.topic_scores["web dev"] == 0.3
        finally:
            path.unlink()

    def test_pattern_detector_load_nonexistent_file(self):
        from orbit.orbit.core.realtime_learning import PatternDetector

        detector = PatternDetector()
        detector.load(Path("/nonexistent/file.json"))
        assert len(detector.topic_scores) == 0

    def test_reset_clears_data(self):
        from orbit.orbit.core.realtime_learning import RealtimeLearner

        learner = RealtimeLearner()
        learner.record_feedback("q1", "r1", 0.1)
        learner.record_feedback("q2", "r2", 0.9)
        learner.reset()
        stats = learner.get_stats()
        assert stats["total_feedback"] == 0
        assert stats["adaptation_count"] == 0
        assert stats["last_adaptation"] is None

    def test_get_adaptation_suggestion_returns_dict_for_high_score(self):
        from orbit.orbit.core.realtime_learning import RealtimeLearner

        learner = RealtimeLearner()
        for _ in range(6):
            learner.record_feedback("quantum physics basics", "great answer", 0.9)
        suggestion = learner.get_adaptation_suggestion("quantum physics basics")
        assert suggestion is not None
        assert "suggestions" in suggestion

    def test_get_adaptation_suggestion_returns_dict_for_low_score(self):
        from orbit.orbit.core.realtime_learning import RealtimeLearner

        learner = RealtimeLearner()
        for _ in range(6):
            learner.record_feedback("tricky edge case", "bad answer", 0.1)
        suggestion = learner.get_adaptation_suggestion("tricky edge case")
        assert suggestion is not None
        assert "suggestions" in suggestion

    def test_feedback_entry_to_dict(self):
        from orbit.orbit.core.realtime_learning import FeedbackEntry

        entry = FeedbackEntry("q", "r", 0.5, {"k": "v"})
        d = entry.to_dict()
        assert d["query"] == "q"
        assert d["response"] == "r"
        assert d["rating"] == 0.5
        assert "timestamp" in d

    def test_feedback_entry_from_dict(self):
        from orbit.orbit.core.realtime_learning import FeedbackEntry

        entry = FeedbackEntry.from_dict(
            {
                "query": "q",
                "response": "r",
                "rating": 0.7,
                "context": {},
                "timestamp": "2026-01-01T00:00:00",
            }
        )
        assert entry.rating == 0.7
        assert entry.timestamp == "2026-01-01T00:00:00"


# ---------------------------------------------------------------------------
# 4. Proactive Assistant (proactive_assistant.py)
# ---------------------------------------------------------------------------
class TestProactiveAssistant:
    """Tests for orbit.orbit.core.proactive_assistant."""

    def test_start_stop_lifecycle(self):
        from orbit.orbit.core.proactive_assistant import ProactiveAssistant

        pa = ProactiveAssistant()
        callback = MagicMock()
        pa.start(callback)
        assert pa._running is True
        assert pa._thread is not None
        pa.stop()
        assert pa._running is False

    def test_start_is_idempotent(self):
        from orbit.orbit.core.proactive_assistant import ProactiveAssistant

        pa = ProactiveAssistant()
        cb = MagicMock()
        pa.start(cb)
        first_thread = pa._thread
        pa.start(cb)
        assert pa._thread is first_thread
        pa.stop()

    def test_get_status_returns_proper_keys(self):
        from orbit.orbit.core.proactive_assistant import ProactiveAssistant

        pa = ProactiveAssistant()
        status = pa.get_status()
        expected = {
            "running",
            "reminders_sent",
            "max_per_session",
            "session_start",
            "last_reminder",
            "reminders",
        }
        assert expected.issubset(status.keys())

    def test_can_proact_respects_cooldown(self):
        from datetime import datetime, timedelta

        from orbit.orbit.core.proactive_assistant import (
            COOLDOWN_SEC,
            ProactiveAssistant,
        )

        pa = ProactiveAssistant()
        assert pa._can_proact() is True
        pa._last_proactive = datetime.now()  # noqa: DTZ005 — source uses naive
        assert pa._can_proact() is False
        pa._last_proactive = datetime.now() - timedelta(  # noqa: DTZ005
            seconds=COOLDOWN_SEC + 1
        )
        assert pa._can_proact() is True

    def test_reset_session_clears_counts(self):
        from orbit.orbit.core.proactive_assistant import ProactiveAssistant

        pa = ProactiveAssistant()
        pa._reminder_count = 5
        pa._reminders.append({"type": "test"})
        pa.reset_session()
        assert pa._reminder_count == 0
        assert len(pa._reminders) == 0
        assert pa._last_reminder_time is None

    def test_get_reminders_returns_list(self):
        from orbit.orbit.core.proactive_assistant import ProactiveAssistant

        pa = ProactiveAssistant()
        result = pa.get_reminders()
        assert isinstance(result, list)

    def test_generate_reminder_returns_dict_or_none(self):
        from orbit.orbit.core.proactive_assistant import ProactiveAssistant

        pa = ProactiveAssistant()
        with (
            patch.object(pa, "_get_system_message", return_value=None),
            patch.object(pa, "_get_news_message", return_value=None),
            patch.object(pa, "_get_task_message", return_value=None),
            patch.object(pa, "_get_time_message", return_value="Good morning!"),
            patch.object(pa, "_get_idle_message", return_value=None),
        ):
            result = pa._generate_reminder()
            assert result is not None
            assert isinstance(result, dict)
            assert "type" in result
            assert "timestamp" in result

    def test_generate_reminder_returns_none_when_all_empty(self):
        from orbit.orbit.core.proactive_assistant import ProactiveAssistant

        pa = ProactiveAssistant()
        with (
            patch.object(pa, "_get_system_message", return_value=None),
            patch.object(pa, "_get_news_message", return_value=None),
            patch.object(pa, "_get_task_message", return_value=None),
            patch.object(pa, "_get_time_message", return_value=None),
            patch.object(pa, "_get_idle_message", return_value=None),
        ):
            result = pa._generate_reminder()
            assert result is None

    def test_get_status_with_reminders(self):
        from orbit.orbit.core.proactive_assistant import ProactiveAssistant

        pa = ProactiveAssistant()
        pa._reminder_count = 3
        pa._reminders.append({"type": "time_based", "message": "test"})
        status = pa.get_status()
        assert status["reminders_sent"] == 3
        assert len(status["reminders"]) == 1

    def test_singleton(self):
        import orbit.orbit.core.proactive_assistant as mod
        from orbit.orbit.core.proactive_assistant import (
            get_proactive_assistant,
        )

        old = mod._proactive
        mod._proactive = None
        try:
            a = get_proactive_assistant()
            b = get_proactive_assistant()
            assert a is b
        finally:
            mod._proactive = old


# ---------------------------------------------------------------------------
# 5. MultiModal Agent (multimodal_agent.py)
# ---------------------------------------------------------------------------
class TestMultiModalAgent:
    """Tests for orbit.orbit.agents.multimodal_agent."""

    def test_analyze_screenshot_returns_dict(self):
        from orbit.orbit.agents.multimodal_agent import MultiModalAgent

        agent = MultiModalAgent()
        with patch("orbit.orbit.screen.capture_and_analyze") as mock_ca:
            mock_ca.return_value = {
                "text": "screen analysis",
                "image_b64": "abc",
                "path": "/tmp/x.png",
            }
            result = agent.analyze_screenshot()
            assert isinstance(result, dict)
            assert result["analysis"] == "screen analysis"

    def test_analyze_screenshot_error_handling(self):
        from orbit.orbit.agents.multimodal_agent import MultiModalAgent

        agent = MultiModalAgent()
        with patch(
            "orbit.orbit.screen.capture_and_analyze", side_effect=Exception("fail")
        ):
            result = agent.analyze_screenshot()
            assert result["status"] == "error"

    def test_ocr_image_returns_dict_with_text_key(self):
        from orbit.orbit.agents.multimodal_agent import MultiModalAgent

        agent = MultiModalAgent()
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake")
            path = f.name
        try:
            mock_pytesseract = MagicMock()
            mock_pytesseract.image_to_string.return_value = "Hello World"
            mock_image = MagicMock()
            with (
                patch.dict("sys.modules", {"pytesseract": mock_pytesseract}),
                patch("PIL.Image.open", return_value=mock_image),
            ):
                result = agent.ocr_image(path)
                assert isinstance(result, dict)
                assert "text" in result
                assert result["text"] == "Hello World"
        finally:
            os.unlink(path)

    def test_ocr_image_nonexistent_file(self):
        from orbit.orbit.agents.multimodal_agent import MultiModalAgent

        agent = MultiModalAgent()
        result = agent.ocr_image("/nonexistent/img.png")
        assert "error" in result

    def test_run_routes_to_analyze_image(self):
        from orbit.orbit.agents.multimodal_agent import MultiModalAgent

        agent = MultiModalAgent()
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake img")
            path = f.name
        try:
            with patch.object(agent, "analyze_image") as mock_ai:
                mock_ai.return_value = {"status": "analyzed", "analysis": "a cat"}
                agent._run(f"analyze {path}")
                mock_ai.assert_called_once_with(path)
        finally:
            os.unlink(path)

    def test_run_routes_to_screenshot(self):
        from orbit.orbit.agents.multimodal_agent import MultiModalAgent

        agent = MultiModalAgent()
        with patch.object(agent, "analyze_screenshot") as mock_as:
            mock_as.return_value = {"status": "analyzed", "analysis": "desktop"}
            agent._run("take a screenshot")
            mock_as.assert_called_once()

    def test_analyze_image_nonexistent(self):
        from orbit.orbit.agents.multimodal_agent import MultiModalAgent

        agent = MultiModalAgent()
        result = agent.analyze_image("/nonexistent/file.png")
        assert "error" in result

    def test_can_handle_keywords(self):
        from orbit.orbit.agents.multimodal_agent import MultiModalAgent

        agent = MultiModalAgent()
        assert agent.can_handle("analyze this image") is True
        assert agent.can_handle("take a screenshot") is True
        assert agent.can_handle("hello world") is False

    def test_singleton(self):
        import orbit.orbit.agents.multimodal_agent as mod
        from orbit.orbit.agents.multimodal_agent import get_multimodal_agent

        old = mod._instance
        mod._instance = None
        try:
            a = get_multimodal_agent()
            b = get_multimodal_agent()
            assert a is b
        finally:
            mod._instance = old


# ---------------------------------------------------------------------------
# 6. Wake Word (wake_word.py)
# ---------------------------------------------------------------------------
class TestWakeWord:
    """Tests for orbit.orbit.wake_word."""

    def _make_detector_no_oww(self):
        from orbit.orbit.wake_word import WakeWordDetector

        def _raise_import(*a, **kw):
            raise ImportError("openwakeword not installed")

        fake_oww = MagicMock()
        fake_oww.Model = _raise_import
        with (
            patch.dict("sys.modules", {"openwakeword": fake_oww}),
            patch("orbit.orbit.wake_word._check_pyaudio", return_value=False),
        ):
            return WakeWordDetector()

    def test_get_info_returns_oww_threshold_key(self):
        det = self._make_detector_no_oww()
        info = det.get_info()
        assert "oww_threshold" in info
        assert isinstance(info["oww_threshold"], float)

    def test_oww_threshold_configurable_via_env(self):
        with patch.dict(os.environ, {"WAKE_WORD_THRESHOLD": "0.75"}):
            import importlib

            import orbit.orbit.wake_word as mod

            importlib.reload(mod)
            try:
                assert mod.OWW_THRESHOLD == 0.75
            finally:
                importlib.reload(mod)

    def test_wake_word_detector_defaults(self):
        det = self._make_detector_no_oww()
        assert det.is_listening is False
        assert det._use_oww is False

    def test_start_stop_lifecycle(self):
        det = self._make_detector_no_oww()
        cb = MagicMock()
        det.start(cb)
        assert det.is_listening is True
        det.stop()
        assert det.is_listening is False

    def test_start_is_idempotent(self):
        det = self._make_detector_no_oww()
        cb = MagicMock()
        det.start(cb)
        first_thread = det._thread
        det.start(cb)
        assert det._thread is first_thread
        det.stop()

    def test_matches_wake_word(self):
        det = self._make_detector_no_oww()
        assert det._matches_wake_word("hey orbit what time is it") is True
        assert det._matches_wake_word("hello there") is False
        assert det._matches_wake_word("ORBIT help me") is True

    def test_get_info_completeness(self):
        det = self._make_detector_no_oww()
        info = det.get_info()
        expected = {
            "available",
            "engine",
            "wake_word",
            "variants",
            "oww_threshold",
            "calibrated_threshold",
            "listening",
        }
        assert expected.issubset(info.keys())

    def test_calibrate_threshold(self):
        det = self._make_detector_no_oww()
        base = det._calibrated_threshold
        for _ in range(25):
            det._calibrate_threshold(2000.0)
        assert det._calibrated_threshold >= base

    def test_singleton(self):
        import orbit.orbit.wake_word as mod
        from orbit.orbit.wake_word import get_wake_word_detector

        old = mod._detector
        mod._detector = None
        try:
            a = get_wake_word_detector()
            b = get_wake_word_detector()
            assert a is b
        finally:
            mod._detector = old
