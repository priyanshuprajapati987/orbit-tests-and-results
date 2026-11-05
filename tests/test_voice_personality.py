"""Tests for voice_personality module."""

import os

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")

from orbit.orbit.core.voice_personality import (
    EMOTION_KEYWORDS,
    EMOTION_VOICE_MAP,
    VoicePersonality,
    get_voice_personality,
)


class TestEmotionDetection:
    def test_detect_happy(self):
        vp = VoicePersonality()
        # Needs 2+ keywords to trigger (threshold in detect_emotion)
        assert vp.detect_emotion("I am so happy and glad today!") == "happy"

    def test_detect_sad(self):
        vp = VoicePersonality()
        assert vp.detect_emotion("This is so sad and terrible") == "sad"

    def test_detect_angry(self):
        vp = VoicePersonality()
        assert vp.detect_emotion("I am angry and frustrated") == "angry"

    def test_detect_default_neutral(self):
        vp = VoicePersonality()
        assert vp.detect_emotion("the weather is ok") == "default"

    def test_detect_single_keyword_returns_default(self):
        vp = VoicePersonality()
        # "happy" alone only scores 1, below threshold of 2
        assert vp.detect_emotion("happy") == "default"

    def test_detect_multiple_keywords(self):
        vp = VoicePersonality()
        assert vp.detect_emotion("I am happy and excited and glad") in (
            "happy",
            "excited",
        )


class TestVoiceConfig:
    def test_get_voice_config_default(self):
        vp = VoicePersonality()
        config = vp.get_voice_config()
        assert config["engine"] == "edge-tts"
        assert "voice" in config
        assert "speed" in config

    def test_get_voice_config_happy(self):
        vp = VoicePersonality()
        config = vp.get_voice_config("happy")
        assert config["emotion"] == "happy"
        assert config["voice"] == "en-US-JennyNeural"

    def test_get_voice_config_unknown(self):
        vp = VoicePersonality()
        config = vp.get_voice_config("unknown_emotion")
        assert config["emotion"] == "unknown_emotion"
        assert config["voice"] == EMOTION_VOICE_MAP["default"]["voice"]


class TestSetEmotion:
    def test_set_valid_emotion(self):
        vp = VoicePersonality()
        result = vp.set_emotion("happy")
        assert result["success"] is True
        assert result["emotion"] == "happy"

    def test_set_invalid_emotion(self):
        vp = VoicePersonality()
        result = vp.set_emotion("invalid_emotion")
        assert result["success"] is False
        assert "error" in result

    def test_set_emotion_records_history(self):
        vp = VoicePersonality()
        vp.reset()
        vp.set_emotion("calm")
        history = vp.get_history()
        assert len(history) == 1
        assert history[0]["emotion"] == "calm"

    def test_emotion_appears_in_stats(self):
        vp = VoicePersonality()
        vp.reset()
        vp.set_emotion("excited")
        stats = vp.get_stats()
        assert stats["current_emotion"] == "excited"
        assert stats["emotion_distribution"].get("excited", 0) >= 1


class TestAdaptTone:
    def test_adapt_tone_returns_config(self):
        vp = VoicePersonality()
        result = vp.adapt_tone("I am so happy!", "Great to hear!")
        assert "emotion" in result
        assert "voice_config" in result
        assert result["response"] == "Great to hear!"

    def test_adapt_tone_updates_current(self):
        vp = VoicePersonality()
        vp.reset()
        vp.adapt_tone("This is so sad and terrible", "I'm sorry")
        assert vp.get_stats()["current_emotion"] in ("sad", "default")

    def test_adapt_tone_records_history(self):
        vp = VoicePersonality()
        vp.reset()
        vp.adapt_tone("hello hey thanks", "Hi!")
        history = vp.get_history()
        assert len(history) >= 1


class TestHistoryAndStats:
    def test_history_limit(self):
        vp = VoicePersonality()
        vp.reset()
        for i in range(60):
            vp.set_emotion("happy")
        history = vp.get_history(limit=10)
        assert len(history) == 10

    def test_stats_structure(self):
        vp = VoicePersonality()
        stats = vp.get_stats()
        assert "enabled" in stats
        assert "current_emotion" in stats
        assert "total_interactions" in stats
        assert "emotion_distribution" in stats

    def test_reset_clears_state(self):
        vp = VoicePersonality()
        vp.set_emotion("angry")
        vp.reset()
        stats = vp.get_stats()
        assert stats["current_emotion"] == "default"
        assert stats["total_interactions"] == 0


class TestSingletonAndEnabled:
    def test_singleton(self):
        a = get_voice_personality()
        b = get_voice_personality()
        assert a is b

    def test_is_enabled(self):
        vp = VoicePersonality()
        assert isinstance(vp.is_enabled(), bool)

    def test_emotion_keywords_coverage(self):
        for emotion in EMOTION_VOICE_MAP:
            if emotion != "default":
                assert emotion in EMOTION_KEYWORDS, f"Missing keywords for {emotion}"
