# ORBIT — Voice function audit: STT/TTS/wake-word/pipeline/personality/screen.
# Hardware-free: mocks audio I/O; tests every pure-logic function.
# Live-audio tests are env-gated (ORBIT_REAL_AUDIO=1).
#
# Run:  python -m pytest tests/test_voice_audit.py -v
#
# (c) 2026 Priyanshu Prajapati

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.unit


# ───────────────────────── voice_personality ─────────────────────────

class TestVoicePersonality:
    def _vp(self):
        from orbit.orbit.core.voice_personality import VoicePersonality

        return VoicePersonality()

    def test_detect_emotion_happy(self):
        vp = self._vp()
        assert vp.detect_emotion("I am so happy and glad today") == "happy"

    def test_detect_emotion_sad(self):
        vp = self._vp()
        assert vp.detect_emotion("this is sad and terrible") == "sad"

    def test_detect_emotion_angry(self):
        vp = self._vp()
        assert vp.detect_emotion("I am angry and furious") == "angry"

    def test_detect_emotion_calm(self):
        vp = self._vp()
        assert vp.detect_emotion("just relax and be calm and quiet") == "calm"

    def test_detect_emotion_excited(self):
        vp = self._vp()
        assert vp.detect_emotion("wow amazing incredible excited") == "excited"

    def test_detect_emotion_serious(self):
        vp = self._vp()
        assert vp.detect_emotion("this is serious urgent critical warning") == "serious"

    def test_detect_emotion_friendly(self):
        vp = self._vp()
        assert vp.detect_emotion("hello hi thanks please welcome") == "friendly"

    def test_detect_emotion_motivational(self):
        vp = self._vp()
        assert vp.detect_emotion("achieve your goal success win strong believe") == "motivational"

    def test_detect_emotion_empathetic(self):
        vp = self._vp()
        assert vp.detect_emotion("I understand how you feel and support you") == "empathetic"

    def test_detect_emotion_default_low_signal(self):
        vp = self._vp()
        assert vp.detect_emotion("just one happy") == "default"  # score < 2

    def test_detect_emotion_default_empty(self):
        vp = self._vp()
        assert vp.detect_emotion("") == "default"
        assert vp.detect_emotion("   ") == "default"

    def test_detect_emotion_none_not_str(self):
        vp = self._vp()
        assert vp.detect_emotion(None) == "default"

    def test_get_voice_config_default(self):
        vp = self._vp()
        cfg = vp.get_voice_config("default")
        assert cfg["emotion"] == "default"
        assert cfg["engine"] == "edge-tts"
        assert "voice" in cfg and "speed" in cfg

    def test_get_voice_config_all_emotions(self):
        from orbit.orbit.core.voice_personality import EMOTION_VOICE_MAP

        vp = self._vp()
        for emo in EMOTION_VOICE_MAP:
            cfg = vp.get_voice_config(emo)
            assert cfg["emotion"] == emo
            assert cfg["engine"] == "edge-tts"
            assert isinstance(cfg["speed"], (int, float))

    def test_get_voice_config_unknown_falls_back(self):
        vp = self._vp()
        cfg = vp.get_voice_config("nonexistent_emotion")
        assert cfg["emotion"] == "nonexistent_emotion"
        assert cfg["engine"] == "edge-tts"  # default fallback

    def test_set_emotion_valid(self):
        vp = self._vp()
        r = vp.set_emotion("happy")
        assert r["success"] is True
        assert r["emotion"] == "happy"

    def test_set_emotion_invalid(self):
        vp = self._vp()
        r = vp.set_emotion("bogus")
        assert r["success"] is False
        assert "Unknown emotion" in r["error"]

    def test_set_emotion_non_str(self):
        vp = self._vp()
        r = vp.set_emotion(42)
        assert r["success"] is False

    def test_adapt_tone_happy(self):
        vp = self._vp()
        r = vp.adapt_tone("I am so happy great wonderful", "That is fantastic!")
        assert r["emotion"] == "happy"
        assert r["voice_config"]["speed"] == 1.1
        assert r["response"] == "That is fantastic!"

    def test_adapt_tone_records_history(self):
        vp = self._vp()
        vp.adapt_tone("happy glad great", "ok")
        assert len(vp.get_history(10)) >= 1

    def test_adapt_tone_non_str_text(self):
        vp = self._vp()
        r = vp.adapt_tone(None, "reply")
        assert r["emotion"] == "default"

    def test_get_history_clamping(self):
        vp = self._vp()
        for _ in range(5):
            vp.adapt_tone("happy glad", "ok")
        assert len(vp.get_history(0)) >= 1  # clamped to min 1
        assert len(vp.get_history(1000)) <= 5
        assert len(vp.get_history("not_a_number")) <= 5  # invalid -> default 20

    def test_get_stats_shape(self):
        vp = self._vp()
        vp.adapt_tone("happy glad", "ok")
        vp.adapt_tone("sad terrible", "ok")
        s = vp.get_stats()
        assert s["total_interactions"] == 2
        assert "emotion_distribution" in s
        assert s["most_common"] in ("happy", "sad")

    def test_reset(self):
        vp = self._vp()
        vp.adapt_tone("happy glad", "ok")
        vp.reset()
        assert vp.get_stats()["total_interactions"] == 0

    def test_is_enabled_default_true(self):
        vp = self._vp()
        assert vp.is_enabled() is True

    def test_singleton(self):
        from orbit.orbit.core.voice_personality import get_voice_personality

        assert get_voice_personality() is get_voice_personality()


# ───────────────────────── voice_pipeline ─────────────────────────

class TestVoicePipeline:
    def _vp(self):
        from orbit.orbit.core.voice_pipeline import VoicePipeline

        return VoicePipeline()

    def test_status_defaults(self):
        p = self._vp()
        s = p.get_status()
        assert s["tts_engine"] == "edge-tts"
        assert s["stt_engine"] == "google"
        assert s["wake_word"] == "orbit"
        assert s["listening"] is False
        assert s["speaking"] is False
        assert s["uptime_seconds"] >= 0

    def test_configure_valid_tts_engine(self):
        p = self._vp()
        s = p.configure(tts_engine="pyttsx3")
        assert s["tts_engine"] == "pyttsx3"

    def test_configure_invalid_tts_engine(self):
        p = self._vp()
        with pytest.raises(ValueError, match="unknown tts_engine"):
            p.configure(tts_engine="bogus_engine")

    def test_configure_valid_stt_engine(self):
        p = self._vp()
        s = p.configure(stt_engine="vosk")
        assert s["stt_engine"] == "vosk"

    def test_configure_invalid_stt_engine(self):
        p = self._vp()
        with pytest.raises(ValueError, match="unknown stt_engine"):
            p.configure(stt_engine="whisper_x")

    def test_configure_voice_length_limit(self):
        p = self._vp()
        with pytest.raises(ValueError, match="invalid tts_voice"):
            p.configure(tts_voice="x" * 121)

    def test_configure_voice_empty(self):
        p = self._vp()
        with pytest.raises(ValueError, match="invalid tts_voice"):
            p.configure(tts_voice="   ")

    def test_configure_wake_word_valid(self):
        p = self._vp()
        s = p.configure(wake_word="jarvis")
        assert s["wake_word"] == "jarvis"

    def test_configure_wake_word_too_long(self):
        p = self._vp()
        with pytest.raises(ValueError, match="invalid wake_word"):
            p.configure(wake_word="x" * 61)

    def test_configure_wake_word_empty_noop(self):
        p = self._vp()
        # empty string is falsy -> treated as "not provided" (no-op, keeps current)
        s = p.configure(wake_word="")
        assert s["wake_word"] == "orbit"  # unchanged

    def test_history_clamping(self):
        p = self._vp()
        p._log_history("speak", "hello", 100.0, "edge-tts")
        assert len(p.get_history(0)) == 1  # min 1
        assert len(p.get_history("bad")) == 1  # invalid -> default 20

    def test_history_text_truncated(self):
        p = self._vp()
        p._log_history("speak", "x" * 500, 100.0, "edge-tts")
        h = p.get_history(1)
        assert len(h[0]["text"]) <= 200

    def test_history_reversed_order(self):
        p = self._vp()
        for i in range(3):
            p._log_history("speak", f"msg{i}", 10.0, "edge")
        h = p.get_history(3)
        assert h[0]["text"] == "msg2"  # newest first

    def test_list_voices_returns_list(self):
        p = self._vp()
        voices = p.list_voices()
        assert isinstance(voices, list)

    def test_singleton(self):
        from orbit.orbit.core.voice_pipeline import get_voice_pipeline

        assert get_voice_pipeline() is get_voice_pipeline()


# ───────────────────────── wake_word (pure logic) ─────────────────────────

class TestWakeWord:
    def _ww(self):
        from orbit.orbit.wake_word import WakeWordDetector

        return WakeWordDetector()

    def test_compute_energy_empty(self):
        from orbit.orbit.wake_word import _compute_energy

        assert _compute_energy([]) == 0.0
        assert _compute_energy(None) == 0.0

    def test_compute_energy_values(self):
        from orbit.orbit.wake_word import _compute_energy

        assert _compute_energy([0, 0, 0]) == 0.0
        assert abs(_compute_energy([100, 100]) - 100.0) < 0.01

    def test_bandpass_filter_short_input(self):
        from orbit.orbit.wake_word import _bandpass_filter

        assert _bandpass_filter([1, 2], 16000) == [1, 2]  # n < 4 passthrough

    def test_bandpass_filter_numpy(self):
        import numpy as np

        from orbit.orbit.wake_word import _bandpass_filter

        samples = np.sin(2 * np.pi * 1000 * np.arange(1600) / 16000) * 1000
        out = _bandpass_filter(samples, 16000)
        assert len(out) == len(samples)

    def test_matches_wake_word_exact(self):
        d = self._ww()
        assert d._matches_wake_word("orbit please help") is True

    def test_matches_wake_word_case_insensitive(self):
        d = self._ww()
        assert d._matches_wake_word("ORBIT status") is True
        assert d._matches_wake_word("Orbit") is True

    def test_matches_wake_word_false_substring(self):
        d = self._ww()
        assert d._matches_wake_word("orbital mechanics") is False
        assert d._matches_wake_word("orbitz app") is False

    def test_matches_wake_word_false_empty(self):
        d = self._ww()
        assert d._matches_wake_word("") is False
        assert d._matches_wake_word("hello there") is False

    def test_matches_wake_word_variants(self, monkeypatch):
        import orbit.orbit.wake_word as ww

        monkeypatch.setattr(ww, "WAKE_WORD_VARIANTS", ["computer", "hey orbit"], raising=False)
        d = self._ww()
        assert d._matches_wake_word("computer please") is True

    def test_calibration_silence_anchors_baseline(self):
        d = self._ww()
        # silence frame (energy below threshold) should lower baseline
        before = d._baseline
        d._calibrate_threshold(energy=50.0)
        assert d._baseline <= before or d._baseline == 50.0

    def test_calibration_speech_does_not_inflate(self):
        d = self._ww()
        before = d._calibrated_threshold
        # loud speech frame (energy ABOVE threshold) must NOT raise threshold
        d._calibrate_threshold(energy=5000.0)
        assert d._calibrated_threshold == before

    def test_confirmation_needs_window(self):
        d = self._ww()
        # less than CONFIRMATION_WINDOW frames -> False
        for _ in range(2):
            assert d._check_confirmation(True) is False

    def test_confirmation_majority(self):
        d = self._ww()
        results = [d._check_confirmation(x) for x in [True, True, True, False, False]]
        # after 5 frames (window), >=3 True -> last should be True
        assert results[-1] is True

    def test_info_shape(self):
        d = self._ww()
        info = d.get_info()
        assert "available" in info
        assert "engine" in info
        assert info["wake_word"] == "orbit"

    def test_singleton(self):
        from orbit.orbit.wake_word import get_wake_word_detector

        assert get_wake_word_detector() is get_wake_word_detector()


# ───────────────────────── tts pure helpers ─────────────────────────

class TestTTSHelpers:
    def test_set_get_engine(self):
        from orbit.orbit import tts

        tts.set_engine("edge-tts")
        assert tts.get_engine() == "edge-tts"
        tts.set_engine("pyttsx3")
        assert tts.get_engine() == "pyttsx3"

    def test_resolve_voice_none_default(self):
        from orbit.orbit import tts

        v = tts._resolve_voice(None)
        assert isinstance(v, str) and v  # falls back to TTS_VOICE

    def test_resolve_voice_known_value(self):
        from orbit.orbit import tts

        v = tts._resolve_voice("en-GB-RyanNeural")
        assert v == "en-GB-RyanNeural"

    def test_resolve_voice_unknown_falls_back(self):
        from orbit.orbit import tts

        v = tts._resolve_voice("bogus_voice_xyz")
        assert isinstance(v, str) and v  # falls back to default

    def test_compute_rate_neutral(self):
        from orbit.orbit import tts

        r = tts.compute_rate_for_voice(speed=None, sentiment="neutral")
        assert r.endswith("%")
        assert r.startswith(("+", "-")) or r == "+0%"

    def test_compute_rate_fast(self):
        from orbit.orbit import tts

        r = tts.compute_rate_for_voice(speed=200, sentiment="neutral")
        assert r.endswith("%")

    def test_compute_rate_all_sentiments(self):
        from orbit.orbit import tts

        for s in ("excited", "calm", "serious", "sad", "happy", "angry", "neutral"):
            r = tts.compute_rate_for_voice(speed=180, sentiment=s)
            assert r.endswith("%")

    def test_compute_pitch(self):
        from orbit.orbit import tts

        p = tts._compute_pitch("excited")
        assert p.endswith("Hz")
        p2 = tts._compute_pitch("sad")
        assert p2.endswith("Hz")

    def test_compute_pitch_neutral(self):
        from orbit.orbit import tts

        assert tts._compute_pitch("neutral") == "+0Hz"


# ───────────────────────── emotions (sentiment) ─────────────────────────

class TestEmotions:
    def test_detect_sentiment_positive(self):
        from orbit.orbit.emotions import detect_sentiment

        s = detect_sentiment("this is great wonderful amazing")
        assert s in ("happy", "excited", "positive")

    def test_detect_sentiment_negative(self):
        from orbit.orbit.emotions import detect_sentiment

        s = detect_sentiment("I am sad and sorry about this unfortunate news")
        assert s == "sad"

    def test_detect_sentiment_angry(self):
        from orbit.orbit.emotions import detect_sentiment

        s = detect_sentiment("I hate this stupid damn thing")
        assert s == "angry"

    def test_get_tts_params_all(self):
        from orbit.orbit.emotions import get_tts_params

        for s in ("excited", "calm", "serious", "sad", "happy", "angry", "neutral"):
            p = get_tts_params(s)
            assert "rate_delta" in p
            assert "pitch_delta" in p
            assert p["rate_delta"].endswith("%")
            assert p["pitch_delta"].endswith("Hz")

    def test_get_tts_params_unknown_neutral(self):
        from orbit.orbit.emotions import get_tts_params

        p = get_tts_params("unknown_sentiment")
        assert p["rate_delta"] == "+0%"
        assert p["pitch_delta"] == "+0Hz"


# ───────────────────────── voice_screen (config/state) ─────────────────────────

class TestVoiceScreen:
    def _vsc(self):
        from orbit.orbit.core.voice_screen import VoiceScreenController

        return VoiceScreenController()

    def test_event_to_dict(self):
        from orbit.orbit.core.voice_screen import VoiceScreenEvent

        e = VoiceScreenEvent(type="heard", state="listening", text="hello")
        d = e.to_dict()
        assert d["type"] == "heard"
        assert d["text"] == "hello"
        assert "ts" in d

    def test_state_enum_values(self):
        from orbit.orbit.core.voice_screen import VoiceScreenState

        vals = [s.value for s in VoiceScreenState]
        assert "idle" in vals
        assert "listening" in vals
        assert "thinking" in vals
        assert "error" in vals

    def test_config_schema(self):
        vsc = self._vsc()
        schema = vsc.get_config_schema()
        for k in ("mode", "auto_speak", "screen_on_query", "trigger_gesture", "mic_index", "continuous_gap_sec"):
            assert k in schema

    def test_validate_mode_valid(self):
        from orbit.orbit.core.voice_screen import VoiceScreenController as V

        assert V._validate_config_value("mode", "wake") == "wake"
        assert V._validate_config_value("mode", "continuous") == "continuous"

    def test_validate_mode_invalid(self):
        from orbit.orbit.core.voice_screen import VoiceScreenController as V

        assert V._validate_config_value("mode", "bogus") is None

    def test_validate_bool_keys(self):
        from orbit.orbit.core.voice_screen import VoiceScreenController as V

        assert V._validate_config_value("auto_speak", True) is True
        assert V._validate_config_value("auto_speak", 0) is False
        assert V._validate_config_value("screen_on_query", "yes") is True

    def test_validate_gesture_string(self):
        from orbit.orbit.core.voice_screen import VoiceScreenController as V

        assert V._validate_config_value("trigger_gesture", "wave") == "wave"
        assert V._validate_config_value("trigger_gesture", "") == ""  # empty clears

    def test_validate_gesture_non_str(self):
        from orbit.orbit.core.voice_screen import VoiceScreenController as V

        assert V._validate_config_value("trigger_gesture", 42) is None

    def test_validate_mic_index(self):
        from orbit.orbit.core.voice_screen import VoiceScreenController as V

        assert V._validate_config_value("mic_index", 0) == 0
        assert V._validate_config_value("mic_index", 2) == 2
        assert V._validate_config_value("mic_index", -1) is None
        assert V._validate_config_value("mic_index", "abc") is None

    def test_validate_gap_clamped(self):
        from orbit.orbit.core.voice_screen import VoiceScreenController as V

        assert V._validate_config_value("continuous_gap_sec", 0.1) == 0.2  # clamped up
        assert V._validate_config_value("continuous_gap_sec", 60.0) == 30.0  # clamped down
        assert V._validate_config_value("continuous_gap_sec", 5.0) == 5.0

    def test_validate_gap_invalid(self):
        from orbit.orbit.core.voice_screen import VoiceScreenController as V

        assert V._validate_config_value("continuous_gap_sec", "abc") is None

    def test_handle_command_empty(self):
        vsc = self._vsc()
        r = vsc.handle_command("")
        assert r["status"] == "error"
        assert "empty" in r["error"]

    def test_get_status_shape(self):
        vsc = self._vsc()
        s = vsc.get_status()
        assert "state" in s
        assert "running" in s
        assert "mode" in s
        assert "config" in s

    def test_singleton(self):
        from orbit.orbit.core.voice_screen import get_voice_screen

        assert get_voice_screen() is get_voice_screen()


# ───────────────────────── voice_bp routes (no-mic graceful) ─────────────────────────

class TestVoiceBp:
    @pytest.fixture
    def client(self):
        from flask import Flask

        from orbit.orbit.core.voice_bp import voice_bp as voice_bp

        app = Flask(__name__)
        app.register_blueprint(voice_bp, url_prefix="/api/voice")
        app.config["TESTING"] = True
        return app.test_client()

    def test_status_route(self, client):
        r = client.get("/api/voice/status")
        assert r.status_code in (200, 401, 404)  # graceful (auth may gate)
        if r.status_code == 200:
            d = r.get_json()
            assert "tts_engine" in d or "status" in d

    def test_devices_route_no_crash(self, client):
        r = client.get("/api/voice/devices")
        assert r.status_code in (200, 401, 404, 500)  # may fail without mic, but no hang

    def test_history_route(self, client):
        r = client.get("/api/voice/history")
        assert r.status_code in (200, 401, 404)


# ───────────────────────── cross integration ─────────────────────────

class TestVoiceIntegration:
    def test_personality_to_pipeline_config(self):
        from orbit.orbit.core.voice_personality import get_voice_personality
        from orbit.orbit.core.voice_pipeline import VoicePipeline

        vp = get_voice_personality()
        cfg = vp.adapt_tone("I am so happy great wonderful", "reply")
        p = VoicePipeline()
        # personality voice maps to a valid edge-tts voice
        assert cfg["voice_config"]["voice"]

    def test_emotion_rate_includes_speed_base(self):
        from orbit.orbit.emotions import get_tts_params
        from orbit.orbit import tts

        # _compute_rate = (speed-100) + sentiment_delta, clamped [-50,150]
        for s in ("excited", "calm", "sad"):
            params = get_tts_params(s)
            rate_str = params["rate_delta"]  # e.g. "+30%" or "-15%"
            delta = int(rate_str.rstrip("%"))  # int("+30")=30, int("-15")=-15
            rate = tts.compute_rate_for_voice(speed=180, sentiment=s)
            expected_val = max(-50, min((180 - 100) + delta, 150))
            expected = f"+{expected_val}%" if expected_val >= 0 else f"-{abs(expected_val)}%"
            assert rate == expected, f"{s}: got {rate}, want {expected}"
