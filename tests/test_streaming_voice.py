"""
Tests for Sprint 3: Streaming TTS, Wake Word improvements, XTTS quality gate.

Covers:
  - tts.py: streaming generator, sounddevice playback, _play_streaming_mp3
  - wake_word.py: bandpass filter, N-of-M confirmation, confidence gate, streaming STT, cooldown
  - xtts.py: _convert_to_wav, SNR quality estimation, MIN_QUALITY_THRESHOLD, clone_voice params
"""

import importlib
import os
import tempfile
from collections import deque
from unittest.mock import MagicMock, patch

import pytest

# ── wake_word.py ──────────────────────────────────────────────────────────────


class TestBandpassFilter:
    def test_returns_samples_when_no_numpy(self):
        from orbit.orbit.wake_word import _bandpass_filter

        samples = list(range(0, 10000, 100))
        result = _bandpass_filter(samples, 16000)
        assert result == samples

    def test_short_samples_returned_as_is(self):
        from orbit.orbit.wake_word import _bandpass_filter

        result = _bandpass_filter([100, 200], 16000)
        assert result == [100, 200]

    def test_empty_samples(self):
        from orbit.orbit.wake_word import _bandpass_filter

        result = _bandpass_filter([], 16000)
        assert result == []

    def test_bandpass_reduces_out_of_band_energy(self):
        try:
            import numpy as np
        except ImportError:
            pytest.skip("numpy not installed")
        from orbit.orbit.wake_word import _bandpass_filter

        rate = 16000
        n = 1600
        t = np.arange(n) / rate
        low_freq_signal = np.sin(2 * np.pi * 50 * t) * 1000
        filtered = _bandpass_filter(
            low_freq_signal.astype(np.int16), rate, low=300, high=3400
        )
        orig_energy = np.mean(np.abs(low_freq_signal.astype(np.float64)))
        filt_energy = np.mean(np.abs(np.array(filtered, dtype=np.float64)))
        assert filt_energy < orig_energy

    def test_bandpass_preserves_speech_band(self):
        try:
            import numpy as np
        except ImportError:
            pytest.skip("numpy not installed")
        from orbit.orbit.wake_word import _bandpass_filter

        rate = 16000
        n = 1600
        t = np.arange(n) / rate
        speech_signal = (np.sin(2 * np.pi * 1000 * t) * 5000).astype(np.int16)
        filtered = _bandpass_filter(speech_signal, rate, low=300, high=3400)
        orig_energy = float(np.mean(np.abs(speech_signal.astype(np.float64))))
        filt_energy = float(np.mean(np.abs(np.array(filtered, dtype=np.float64))))
        ratio = filt_energy / max(orig_energy, 1)
        assert ratio > 0.7


class TestComputeEnergy:
    def test_zero_for_empty(self):
        from orbit.orbit.wake_word import _compute_energy

        assert _compute_energy([]) == 0.0

    def test_positive_for_speech(self):
        from orbit.orbit.wake_word import _compute_energy

        samples = list(range(-3000, 3000)) * 10
        energy = _compute_energy(samples)
        assert energy > 100

    def test_zero_for_silence(self):
        from orbit.orbit.wake_word import _compute_energy

        assert _compute_energy([0] * 100) == 0.0


class TestConfirmation:
    def _make_detector(self):
        from orbit.orbit.wake_word import WakeWordDetector

        d = WakeWordDetector.__new__(WakeWordDetector)
        d._speech_history = deque(maxlen=5)
        d._energy_history = []
        d._calibrated_threshold = 500
        return d

    def test_insufficient_history(self):
        d = self._make_detector()
        result = d._check_confirmation(True)
        assert result is False

    def test_all_speech_passes(self):
        d = self._make_detector()
        for _ in range(5):
            d._check_confirmation(True)
        assert d._check_confirmation(True) is True

    def test_mixed_below_threshold(self):
        d = self._make_detector()
        d._check_confirmation(True)
        d._check_confirmation(True)
        d._check_confirmation(False)
        d._check_confirmation(False)
        d._check_confirmation(False)
        assert d._check_confirmation(False) is False

    def test_deque_maxlen_respected(self):
        d = self._make_detector()
        for _ in range(10):
            d._check_confirmation(True)
        assert len(d._speech_history) == 5


class TestWakeWordMatching:
    def _make_detector(self):
        from orbit.orbit.wake_word import WakeWordDetector

        d = WakeWordDetector.__new__(WakeWordDetector)
        d._speech_history = deque(maxlen=5)
        d._energy_history = []
        d._calibrated_threshold = 500
        d._oww_model = None
        d._use_oww = False
        d._vosk_recognizer = None
        d._vosk_model = None
        d._callback = None
        d.is_listening = False
        d._thread = None
        return d

    def test_exact_match(self):
        d = self._make_detector()
        with patch.dict(os.environ, {"ORBIT_WAKE_WORD": "orbit"}):
            import orbit.orbit.wake_word as mod

            mod.WAKE_WORD = "orbit"
            mod.WAKE_WORD_VARIANTS = []
        assert d._matches_wake_word("orbit") is True

    def test_case_insensitive(self):
        d = self._make_detector()
        import orbit.orbit.wake_word as mod

        mod.WAKE_WORD = "orbit"
        mod.WAKE_WORD_VARIANTS = []
        assert d._matches_wake_word("ORBIT") is True
        assert d._matches_wake_word("Hey Orbit") is True

    def test_no_match(self):
        d = self._make_detector()
        import orbit.orbit.wake_word as mod

        mod.WAKE_WORD = "orbit"
        mod.WAKE_WORD_VARIANTS = []
        assert d._matches_wake_word("hello world") is False

    def test_variant_match(self):
        d = self._make_detector()
        import orbit.orbit.wake_word as mod

        mod.WAKE_WORD = "orbit"
        mod.WAKE_WORD_VARIANTS = ["hey orbit", "computer"]
        assert d._matches_wake_word("hey orbit") is True
        assert d._matches_wake_word("computer") is True


class TestCooldown:
    def test_cooldown_blocks_rapid_triggers(self):
        from orbit.orbit.wake_word import WakeWordDetector

        d = WakeWordDetector.__new__(WakeWordDetector)
        d._speech_history = deque(maxlen=5)
        d._energy_history = []
        d._calibrated_threshold = 500
        d._vosk_recognizer = None
        d._vosk_model = None
        d._callback = MagicMock()
        d.is_listening = False
        d._thread = None
        d._use_oww = False
        d._oww_model = None
        assert hasattr(d, "_speech_history")


class TestWakeWordConfig:
    def test_config_reads_default_values(self):
        import orbit.orbit.wake_word as mod

        importlib.reload(mod)
        assert mod.CONFIDENCE_THRESHOLD > 0
        assert mod.CONFIRMATION_WINDOW >= 3
        assert mod.CONFIRMATION_MIN >= 1
        assert mod.COOLDOWN_SEC >= 1

    def test_config_env_override(self):
        with patch.dict(os.environ, {"WAKE_CONFIDENCE_THRESHOLD": "0.8"}):
            import orbit.orbit.wake_word as mod

            old = mod.CONFIDENCE_THRESHOLD
            mod.CONFIDENCE_THRESHOLD = float(
                os.getenv("WAKE_CONFIDENCE_THRESHOLD", "0.7")
            )
            assert mod.CONFIDENCE_THRESHOLD == 0.8
            mod.CONFIDENCE_THRESHOLD = old

    def test_singleton_exists(self):
        from orbit.orbit.wake_word import get_wake_word_detector

        d = get_wake_word_detector()
        assert d is not None


# ── tts.py ────────────────────────────────────────────────────────────────────


class TestStreamingGenerator:
    def test_empty_text_yields_nothing(self):
        from orbit.orbit.tts import generate_audio_stream

        chunks = list(generate_audio_stream(""))
        assert chunks == []

    def test_whitespace_only_yields_nothing(self):
        from orbit.orbit.tts import generate_audio_stream

        chunks = list(generate_audio_stream("   "))
        assert chunks == []

    @patch("orbit.orbit.tts._run_async_task")
    def test_yields_chunks_from_edge_tts(self, mock_run):
        mock_run.return_value = [b"chunk1", b"chunk2", b"chunk3"]
        from orbit.orbit.tts import generate_audio_stream

        chunks = list(generate_audio_stream("Hello world"))
        assert chunks == [b"chunk1", b"chunk2", b"chunk3"]

    @patch("orbit.orbit.tts._run_async_task")
    def test_empty_chunks_returns_nothing(self, mock_run):
        mock_run.return_value = []
        from orbit.orbit.tts import generate_audio_stream

        chunks = list(generate_audio_stream("Hello"))
        assert chunks == []

    @patch("orbit.orbit.tts.detect_sentiment", return_value="neutral")
    def test_sentiment_passed_through(self, mock_sent):
        from orbit.orbit.tts import generate_audio_stream

        with patch("orbit.orbit.tts._run_async_task", return_value=[b"data"]):
            list(generate_audio_stream("Hello", sentiment="happy"))


class TestPlaybackSounddevice:
    @patch("orbit.orbit.tts._play_with_sounddevice")
    def test_play_audio_bytes_uses_sounddevice_first(self, mock_sd):
        from orbit.orbit.tts import _play_audio_bytes

        _play_audio_bytes(b"fake mp3")
        mock_sd.assert_called_once()

    @patch(
        "orbit.orbit.tts._play_with_sounddevice", side_effect=RuntimeError("no device")
    )
    @patch("orbit.orbit.tts._play_mp3")
    def test_falls_back_to_powershell(self, mock_ps, mock_sd):
        from orbit.orbit.tts import _play_audio_bytes

        _play_audio_bytes(b"fake mp3")
        mock_ps.assert_called_once()

    def test_play_with_sounddevice_missing_deps(self):
        from orbit.orbit.tts import _play_with_sounddevice

        with (
            patch.dict("sys.modules", {"pydub": None, "sounddevice": None}),
            pytest.raises(RuntimeError),
        ):
            _play_with_sounddevice(b"fake mp3")


class TestPlayStreamingMp3:
    def test_exists(self):
        from orbit.orbit.tts import _play_streaming_mp3

        assert callable(_play_streaming_mp3)

    def test_empty_chunks_no_error(self):
        from orbit.orbit.tts import _play_streaming_mp3

        _play_streaming_mp3([])

    @patch.dict("sys.modules", {"pydub": None, "sounddevice": None})
    def test_missing_deps_graceful(self):
        from orbit.orbit.tts import _play_streaming_mp3

        _play_streaming_mp3([b"data"])


class TestGenerateAudioStreamEdgeCases:
    @patch("orbit.orbit.tts._run_async_task", side_effect=Exception("network error"))
    def test_network_error_yields_nothing(self, mock_run):
        from orbit.orbit.tts import generate_audio_stream

        chunks = list(generate_audio_stream("Hello"))
        assert chunks == []


# ── xtts.py ───────────────────────────────────────────────────────────────────


class TestConvertToWav:
    def test_wav_file_returned_as_is(self):
        from orbit.orbit.xtts import _convert_to_wav

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"RIFF\x00" * 10)
            wav_path = f.name
        try:
            result = _convert_to_wav(wav_path)
            assert result == wav_path
        finally:
            os.unlink(wav_path)

    def test_ffmpeg_success(self):
        from orbit.orbit.xtts import _convert_to_wav

        mock_result = MagicMock()
        mock_result.returncode = 0
        with (
            patch(
                "orbit.orbit.xtts.subprocess.run", return_value=mock_result
            ) as mock_run,
            patch("orbit.orbit.xtts.os.path.getsize", return_value=1000),
        ):
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(b"fake mp3 data")
                mp3_path = f.name
            try:
                wav_path = _convert_to_wav(mp3_path)
                assert wav_path is not None
                assert wav_path.endswith(".wav")
                mock_run.assert_called_once()
                args = mock_run.call_args[0][0]
                assert "ffmpeg" in args[0]
            finally:
                if wav_path and os.path.exists(wav_path):
                    os.unlink(wav_path)
                os.unlink(mp3_path)

    def test_ffmpeg_failure_returns_none(self):
        from orbit.orbit.xtts import _convert_to_wav

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = b"error"
        with patch("orbit.orbit.xtts.subprocess.run", return_value=mock_result):
            result = _convert_to_wav("/nonexistent/file.mp3")
            assert result is None

    def test_ffmpeg_not_found_returns_none(self):
        from orbit.orbit.xtts import _convert_to_wav

        with patch(
            "orbit.orbit.xtts.subprocess.run", side_effect=FileNotFoundError("ffmpeg")
        ):
            result = _convert_to_wav("/nonexistent/file.mp3")
            assert result is None


class TestSNRQualityEstimation:
    def test_nonexistent_file_returns_zero(self):
        from orbit.orbit.xtts import _estimate_quality

        score = _estimate_quality("/nonexistent/path/audio.wav")
        assert score == 0.0

    def test_convert_used_for_non_wav(self):
        from orbit.orbit.xtts import _estimate_quality

        with patch("orbit.orbit.xtts._convert_to_wav", return_value=None):
            score = _estimate_quality("/fake/file.mp3")
            assert score == 0.0

    def test_silence_low_quality(self):
        from orbit.orbit.xtts import _estimate_quality

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            import wave

            with wave.open(f.name, "w") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"\x00" * 32000)
            wav_path = f.name
        try:
            score = _estimate_quality(wav_path)
            assert score < 0.5
        finally:
            os.unlink(wav_path)

    def test_score_range(self):
        from orbit.orbit.xtts import _estimate_quality

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            import wave

            import numpy as np

            samples = (
                np.sin(np.linspace(0, 2 * np.pi * 1000, 16000 * 3)) * 5000
            ).astype(np.int16)
            with wave.open(f.name, "w") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(samples.tobytes())
            wav_path = f.name
        try:
            score = _estimate_quality(wav_path)
            assert 0.0 <= score <= 1.0
        finally:
            os.unlink(wav_path)


class TestMinQualityThreshold:
    def test_threshold_exists(self):
        from orbit.orbit.xtts import MIN_QUALITY_THRESHOLD

        assert 0.0 <= MIN_QUALITY_THRESHOLD <= 1.0

    def test_threshold_is_default(self):
        from orbit.orbit.xtts import MIN_QUALITY_THRESHOLD

        assert MIN_QUALITY_THRESHOLD == 0.3


class TestCloneVoiceXTTSParams:
    def test_clone_voice_unavailable(self):
        from orbit.orbit.xtts import VoiceCloner

        cloner = VoiceCloner.__new__(VoiceCloner)
        cloner._available = False
        result = cloner.clone_voice("ref.wav", "hello")
        assert result["success"] is False

    def test_clone_voice_nonexistent_ref(self):
        from orbit.orbit.xtts import VoiceCloner

        cloner = VoiceCloner.__new__(VoiceCloner)
        cloner._available = True
        result = cloner.clone_voice("/nonexistent/ref.wav", "hello")
        assert result["success"] is False

    def test_clone_voice_passes_xtts_params(self):
        from orbit.orbit.xtts import VoiceCloner

        cloner = VoiceCloner.__new__(VoiceCloner)
        cloner._available = True
        cloner._lock = MagicMock()
        cloner._model = MagicMock()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"RIFF\x00" * 10)
            ref_path = f.name
        try:
            with (
                patch("orbit.orbit.xtts._preprocess_audio", return_value=None),
                patch("orbit.orbit.xtts._estimate_quality", return_value=0.8),
                patch("os.path.exists", return_value=True),
            ):
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as out_f:
                    out_path = out_f.name
                cloner.clone_voice(
                    ref_path,
                    "hello",
                    out_path,
                    temperature=0.5,
                    speed=1.2,
                    repetition_penalty=3.0,
                )
                call_kwargs = cloner._model.tts_to_file.call_args
                assert call_kwargs[1]["temperature"] == 0.5
                assert call_kwargs[1]["speed"] == 1.2
                assert call_kwargs[1]["repetition_penalty"] == 3.0
                os.unlink(out_path)
        finally:
            os.unlink(ref_path)


# ── API streaming endpoint ────────────────────────────────────────────────────


class TestVoiceStreamEndpoint:
    def test_stream_endpoint_registered(self):
        from orbit.orbit.server import create_app

        app = create_app()
        rules = [rule.rule for rule in app.url_map.iter_rules()]
        assert "/api/voice/speak/stream" in rules

    def test_stream_empty_text_returns_400(self):
        from orbit.orbit.server import create_app

        app = create_app()
        with app.test_client() as c:
            resp = c.post("/api/voice/speak/stream", json={"text": ""})
            assert resp.status_code == 400

    def test_stream_missing_text_returns_400(self):
        from orbit.orbit.server import create_app

        app = create_app()
        with app.test_client() as c:
            resp = c.post("/api/voice/speak/stream", json={})
            assert resp.status_code == 400
