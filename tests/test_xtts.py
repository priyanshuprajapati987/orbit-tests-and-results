"""Deep coverage tests for orbit/orbit/xtts.py (626 lines, XTTS voice cloning).

Targets the uncovered lines: _convert_to_wav ffmpeg branches, _preprocess_audio
(normalize/trim/too-short/too-long/silent), _estimate_quality gates, reference
selection, VoiceCloner init/clone/retry/speak/multi-ref/sample CRUD,
analyze_reference_audio duration branches + recommendation tiers, and
analyze_all_references aggregation. All model/subprocess/network is mocked;
audio fixtures are real WAVs generated on the fly.
"""

import io
import os
import sys
import tempfile
import threading
import unittest
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

import numpy as np  # noqa: E402  (must import before any patch.dict window)

from orbit.orbit import xtts as xt  # noqa: E402


def _write_wav(path, rate=22050, seconds=2.0, amplitude=8000, noise=0):
    """Write a real int16 WAV: sine tone (+ optional uniform noise)."""
    n = int(rate * seconds)
    t = np.arange(n) / rate
    sig = amplitude * np.sin(2 * np.pi * 220 * t)
    if noise:
        rng = np.random.default_rng(0)
        sig = sig + rng.integers(-noise, noise + 1, n)
    data = np.clip(sig, -32768, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(data.tobytes())
    return str(path)


def _write_silent_wav(path, rate=22050, seconds=2.0):
    n = int(rate * seconds)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * n)
    return str(path)


def _real_wav_bytes(rate=8000, seconds=0.5, amplitude=8000):
    """Valid WAV bytes in memory (for tts_to_file side effects)."""
    n = int(rate * seconds)
    t = np.arange(n) / rate
    data = (amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(data.tobytes())
    return buf.getvalue()


class XttsBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def make_cloner(self, available=True, model=None):
        """VoiceCloner without running __init__ (no TTS import needed)."""
        cl = xt.VoiceCloner.__new__(xt.VoiceCloner)
        cl.name = "voice_cloning"
        cl._model = model if model is not None else MagicMock(name="tts-model")
        cl._lock = threading.Lock()
        cl._available = available
        return cl

    @staticmethod
    def writing_tts(model, payload=b"RIFF-fake-wav"):
        """Make tts_to_file actually create its target file (getsize needs it)."""

        def _tts_to_file(**kw):
            Path(kw["file_path"]).write_bytes(payload)

        model.tts_to_file.side_effect = _tts_to_file
        return model


# ---------------------------------------------------------------------------
# _convert_to_wav (29-56)
# ---------------------------------------------------------------------------


class TestConvertToWav(XttsBase):
    def test_wav_passthrough_no_ffmpeg(self):
        p = str(self.dir / "a.wav")
        with patch.object(xt.subprocess, "run") as run:
            self.assertEqual(xt._convert_to_wav(p), p)
        run.assert_not_called()

    def test_non_wav_ffmpeg_success(self):
        src = str(self.dir / "a.mp3")
        Path(src).write_bytes(b"mp3")
        result = MagicMock(returncode=0, stderr=b"")
        with patch.object(xt.subprocess, "run", return_value=result) as run, \
             patch.object(xt.os.path, "getsize", return_value=1024):
            out = xt._convert_to_wav(src)
        self.assertTrue(out.endswith(".wav"))
        self.assertNotEqual(out, src)
        run.assert_called_once()
        os.unlink(out)  # temp file cleanup

    def test_ffmpeg_nonzero_returncode_returns_none(self):
        src = str(self.dir / "a.mp3")
        Path(src).write_bytes(b"mp3")
        result = MagicMock(returncode=1, stderr=b"bad input")
        with patch.object(xt.subprocess, "run", return_value=result), \
             patch.object(xt.os.path, "getsize", return_value=0), \
             patch.object(xt.os, "unlink") as unlink, \
             self.assertLogs(xt.logger, level="WARNING") as cm:
            self.assertIsNone(xt._convert_to_wav(src))
        unlink.assert_called_once()
        self.assertTrue(any("ffmpeg conversion failed" in l for l in cm.output))

    def test_ffmpeg_zero_return_but_empty_output_returns_none(self):
        src = str(self.dir / "a.mp3")
        Path(src).write_bytes(b"mp3")
        result = MagicMock(returncode=0, stderr=b"")
        with patch.object(xt.subprocess, "run", return_value=result), \
             patch.object(xt.os.path, "getsize", return_value=0), \
             patch.object(xt.os, "unlink"), \
             self.assertLogs(xt.logger, level="WARNING"):
            self.assertIsNone(xt._convert_to_wav(src))

    def test_unlink_failure_during_cleanup_swallowed(self):
        src = str(self.dir / "a.mp3")
        Path(src).write_bytes(b"mp3")
        result = MagicMock(returncode=1, stderr=b"x")
        with patch.object(xt.subprocess, "run", return_value=result), \
             patch.object(xt.os.path, "getsize", return_value=0), \
             patch.object(xt.os, "unlink", side_effect=OSError("locked")):
            self.assertIsNone(xt._convert_to_wav(src))  # must not raise

    def test_ffmpeg_missing_file_not_found(self):
        src = str(self.dir / "a.mp3")
        Path(src).write_bytes(b"mp3")
        with patch.object(xt.subprocess, "run",
                          side_effect=FileNotFoundError("ffmpeg")), \
             self.assertLogs(xt.logger, level="WARNING") as cm:
            self.assertIsNone(xt._convert_to_wav(src))
        self.assertTrue(any("ffmpeg not found" in l for l in cm.output))

    def test_ffmpeg_generic_error(self):
        src = str(self.dir / "a.mp3")
        Path(src).write_bytes(b"mp3")
        with patch.object(xt.subprocess, "run",
                          side_effect=OSError("boom")), \
             self.assertLogs(xt.logger, level="WARNING") as cm:
            self.assertIsNone(xt._convert_to_wav(src))
        self.assertTrue(any("ffmpeg conversion error" in l for l in cm.output))


# ---------------------------------------------------------------------------
# _preprocess_audio (59-126)
# ---------------------------------------------------------------------------


class TestPreprocessAudio(XttsBase):
    def test_good_signal_produces_new_wav(self):
        src = _write_wav(self.dir / "good.wav", seconds=3.0)
        out = xt._preprocess_audio(src)
        self.assertIsNotNone(out)
        self.assertNotEqual(out, src)
        with wave.open(out, "rb") as wf:
            self.assertGreaterEqual(wf.getnframes() / wf.getframerate(),
                                    xt.MIN_CLONE_DURATION_SEC)
        os.unlink(out)

    def test_empty_samples_returns_none(self):
        # WAV with a valid header but zero frames.
        src = str(self.dir / "empty.wav")
        with wave.open(src, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(22050)
        self.assertIsNone(xt._preprocess_audio(src))

    def test_silent_audio_returns_none(self):
        src = _write_silent_wav(self.dir / "silent.wav", seconds=2.0)
        self.assertIsNone(xt._preprocess_audio(src))

    def test_too_short_returns_none(self):
        src = _write_wav(self.dir / "short.wav", seconds=0.4)
        self.assertIsNone(xt._preprocess_audio(src))

    def test_long_audio_trimmed_to_optimal(self):
        src = _write_wav(self.dir / "long.wav", seconds=25.0, amplitude=9000)
        out = xt._preprocess_audio(src)
        self.assertIsNotNone(out)
        with wave.open(out, "rb") as wf:
            dur = wf.getnframes() / wf.getframerate()
        self.assertLessEqual(dur, xt.MAX_CLONE_DURATION_SEC + 0.1)
        self.assertGreaterEqual(dur, xt.OPTIMAL_CLONE_DURATION_SEC - 0.1)
        os.unlink(out)

    def test_tiny_sample_rate_window_clamped(self):
        # rate*0.02 < 1 -> window = 1 branch (line 84-85).
        # Constant DC signal: a 220Hz sine at 40Hz sample rate aliases to
        # exactly 0 (220/40 = 5.5 -> sin(11*pi*k)), so use a flat tone.
        rate, secs = 40, 3.0
        n = int(rate * secs)
        data = np.full(n, 6000, dtype=np.int16)
        src = str(self.dir / "lowrate.wav")
        with wave.open(src, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(data.tobytes())
        out = xt._preprocess_audio(src)
        self.assertIsNotNone(out)
        os.unlink(out)

    def test_convert_failure_falls_back_to_raw_path(self):
        src = _write_wav(self.dir / "raw.wav", seconds=3.0)
        with patch.object(xt, "_convert_to_wav", return_value=None):
            out = xt._preprocess_audio(src)
        self.assertIsNotNone(out)  # processed the original path
        os.unlink(out)

    def test_unreadable_file_logs_and_returns_none(self):
        bad = str(self.dir / "bad.wav")
        Path(bad).write_bytes(b"not a wave at all")
        with self.assertLogs(xt.logger, level="WARNING") as cm:
            self.assertIsNone(xt._preprocess_audio(bad))
        self.assertTrue(any("preprocessing failed" in l for l in cm.output))

    def test_tmp_convert_cleaned_up_on_success(self):
        src = _write_wav(self.dir / "ok.wav", seconds=3.0)
        with patch.object(xt, "_convert_to_wav",
                          return_value=str(self.dir / "conv.wav")) as conv, \
             patch.object(xt.os, "unlink") as unlink:
            # _convert_to_wav returned a DIFFERENT path -> cleanup branch
            out = xt._preprocess_audio(src)
        # convert target doesn't exist -> wave.open raises -> except branch
        self.assertIsNone(out)
        unlink.assert_called_once()

    def test_tmp_convert_cleaned_up_on_failure(self):
        src = _write_wav(self.dir / "ok2.wav", seconds=3.0)
        conv_target = str(self.dir / "conv2.wav")
        with patch.object(xt, "_convert_to_wav",
                          return_value=conv_target) as conv, \
             patch.object(xt.os, "unlink") as unlink, \
             self.assertLogs(xt.logger, level="WARNING"):
            self.assertIsNone(xt._preprocess_audio(src))
        unlink.assert_called_once()
        conv.assert_called_once_with(src)


# ---------------------------------------------------------------------------
# _estimate_quality (156-207)
# ---------------------------------------------------------------------------


class TestEstimateQuality(XttsBase):
    def test_good_speech_scores_high(self):
        src = _write_wav(self.dir / "good.wav", seconds=3.0, amplitude=9000)
        q = xt._estimate_quality(src)
        self.assertGreaterEqual(q, xt.MIN_QUALITY_THRESHOLD)

    def test_empty_frames_returns_zero(self):
        src = str(self.dir / "empty.wav")
        with wave.open(src, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(22050)
        self.assertEqual(xt._estimate_quality(src), 0.0)

    def test_zero_length_samples_returns_zero(self):
        # np.frombuffer on empty frames -> len 0 branch
        src = str(self.dir / "empty2.wav")
        with wave.open(src, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(22050)
            wf.writeframes(b"")
        self.assertEqual(xt._estimate_quality(src), 0.0)

    def test_too_short_returns_floor(self):
        src = _write_wav(self.dir / "short.wav", seconds=0.3, amplitude=9000)
        self.assertEqual(xt._estimate_quality(src), 0.1)

    def test_too_long_returns_floor(self):
        src = _write_wav(self.dir / "long.wav", seconds=35.0, amplitude=9000)
        self.assertEqual(xt._estimate_quality(src), 0.1)

    def test_silent_returns_floor(self):
        src = _write_silent_wav(self.dir / "silent.wav")
        self.assertEqual(xt._estimate_quality(src), 0.1)

    def test_noisy_low_snr_scores_below_clean(self):
        clean = _write_wav(self.dir / "clean.wav", seconds=3.0,
                           amplitude=12000, noise=0)
        noisy = _write_wav(self.dir / "noisy.wav", seconds=3.0,
                           amplitude=300, noise=800)
        self.assertGreater(xt._estimate_quality(clean),
                           xt._estimate_quality(noisy))

    def test_corrupt_file_returns_zero(self):
        bad = str(self.dir / "bad.wav")
        Path(bad).write_bytes(b"junk")
        with self.assertLogs(xt.logger, level="DEBUG"):
            self.assertEqual(xt._estimate_quality(bad), 0.0)

    def test_noise_power_zero_uses_full_snr_score(self):
        # Constant signal -> residual ~0 -> else branch snr_score = 1.0
        rate, secs = 8000, 2.0
        n = int(rate * secs)
        data = np.full(n, 5000, dtype=np.int16)
        src = str(self.dir / "const.wav")
        with wave.open(src, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(data.tobytes())
        q = xt._estimate_quality(src)
        self.assertGreater(q, 0.3)


# ---------------------------------------------------------------------------
# _select_best_references (129-153)
# ---------------------------------------------------------------------------


class TestSelectBestReferences(XttsBase):
    def test_missing_files_skipped(self):
        self.assertEqual(
            xt._select_best_references(["", None, str(self.dir / "nope.wav")]),
            [],
        )

    def test_preprocess_failure_skipped(self):
        good = _write_wav(self.dir / "g.wav", seconds=3.0)
        with patch.object(xt, "_preprocess_audio", return_value=None):
            self.assertEqual(xt._select_best_references([good]), [])

    def test_below_quality_floor_skipped(self):
        good = _write_wav(self.dir / "g.wav", seconds=3.0)
        with patch.object(xt, "_preprocess_audio",
                          return_value=good), \
             patch.object(xt, "_estimate_quality", return_value=0.1), \
             self.assertLogs(xt.logger, level="DEBUG") as cm:
            self.assertEqual(xt._select_best_references([good]), [])
        self.assertTrue(any("below quality floor" in l for l in cm.output))

    def test_sorted_descending_and_capped(self):
        a = _write_wav(self.dir / "a.wav", seconds=3.0)
        b = _write_wav(self.dir / "b.wav", seconds=3.0)
        c = _write_wav(self.dir / "c.wav", seconds=3.0)
        quality = {a: 0.9, b: 0.5, c: 0.7}
        with patch.object(xt, "_preprocess_audio",
                          side_effect=lambda p: p), \
             patch.object(xt, "_estimate_quality",
                          side_effect=lambda p: quality[p]):
            out = xt._select_best_references([a, b, c], max_refs=2)
        self.assertEqual([o["path"] for o in out], [a, c])
        self.assertEqual(out[0]["quality"], 0.9)

    def test_returns_original_path_not_preprocessed(self):
        a = _write_wav(self.dir / "a.wav", seconds=3.0)
        with patch.object(xt, "_preprocess_audio",
                          return_value=str(self.dir / "pp.wav")), \
             patch.object(xt, "_estimate_quality", return_value=0.8):
            out = xt._select_best_references([a])
        self.assertEqual(out[0]["path"], a)


# ---------------------------------------------------------------------------
# VoiceCloner._init_model (218-228)
# ---------------------------------------------------------------------------


class TestInitModel(XttsBase):
    def test_import_error_marks_unavailable(self):
        import types as _t
        cl = xt.VoiceCloner.__new__(xt.VoiceCloner)
        cl._model = None
        cl._lock = threading.Lock()
        cl._available = False
        with patch.dict(sys.modules, {"TTS": None, "TTS.api": None}):
            with self.assertLogs(xt.logger, level="INFO") as cm:
                cl._init_model()
        self.assertFalse(cl._available)
        self.assertTrue(any("not available" in l for l in cm.output))

    def test_load_success_sets_available(self):
        import types as _t
        fake_model = object()
        api = _t.ModuleType("TTS.api")
        api.TTS = MagicMock(return_value=fake_model)
        pkg = _t.ModuleType("TTS")
        pkg.api = api
        cl = xt.VoiceCloner.__new__(xt.VoiceCloner)
        cl._model = None
        cl._lock = threading.Lock()
        cl._available = False
        with patch.dict(sys.modules, {"TTS": pkg, "TTS.api": api}):
            with self.assertLogs(xt.logger, level="INFO") as cm:
                cl._init_model()
        self.assertTrue(cl._available)
        self.assertIs(cl._model, fake_model)
        self.assertTrue(any("XTTS v2 loaded" in l for l in cm.output))

    def test_load_failure_logs_warning(self):
        import types as _t
        api = _t.ModuleType("TTS.api")
        api.TTS = MagicMock(side_effect=RuntimeError("cuda gone"))
        pkg = _t.ModuleType("TTS")
        pkg.api = api
        cl = xt.VoiceCloner.__new__(xt.VoiceCloner)
        cl._model = None
        cl._lock = threading.Lock()
        cl._available = False
        with patch.dict(sys.modules, {"TTS": pkg, "TTS.api": api}):
            with self.assertLogs(xt.logger, level="WARNING") as cm:
                cl._init_model()
        self.assertFalse(cl._available)
        self.assertTrue(any("load failed" in l for l in cm.output))


# ---------------------------------------------------------------------------
# clone_voice (230-290) + clone_from_text (292-308)
# ---------------------------------------------------------------------------


class TestCloneVoice(XttsBase):
    def test_unavailable_returns_error(self):
        cl = self.make_cloner(available=False)
        out = cl.clone_voice("ref.wav", "hi")
        self.assertFalse(out["success"])
        self.assertIn("not available", out["error"])

    def test_missing_reference_returns_error(self):
        cl = self.make_cloner()
        out = cl.clone_voice(str(self.dir / "nope.wav"), "hi")
        self.assertFalse(out["success"])
        self.assertIn("not found", out["error"])

    def test_success_first_attempt(self):
        ref = _write_wav(self.dir / "ref.wav", seconds=3.0)
        out_file = str(self.dir / "out.wav")
        model = self.writing_tts(MagicMock())
        cl = self.make_cloner(model=model)
        with patch.object(xt, "_estimate_quality", return_value=0.8):
            out = cl.clone_voice(ref, "hello", output_path=out_file)
        self.assertTrue(out["success"])
        self.assertEqual(out["output"], out_file)
        self.assertEqual(out["attempt"], 0)
        self.assertEqual(out["quality_score"], 0.8)
        self.assertGreater(out["size"], 0)
        model.tts_to_file.assert_called_once()

    def test_default_output_path_used(self):
        ref = _write_wav(self.dir / "ref.wav", seconds=3.0)
        model = self.writing_tts(MagicMock())
        cl = self.make_cloner(model=model)
        with patch.object(xt, "_estimate_quality", return_value=0.8):
            out = cl.clone_voice(ref, "hello", output_path=None)
        self.assertTrue(out["success"])
        self.assertTrue(out["output"].endswith("orbit_cloned.wav"))

    def test_retry_then_success(self):
        ref = _write_wav(self.dir / "ref.wav", seconds=3.0)
        out_file = str(self.dir / "out.wav")
        model = MagicMock()
        calls = {"n": 0}

        def _tts(**kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("transient")
            Path(kw["file_path"]).write_bytes(b"x")

        model.tts_to_file.side_effect = _tts
        cl = self.make_cloner(model=model)
        with patch.object(xt, "_estimate_quality", return_value=0.8), \
             self.assertLogs(xt.logger, level="WARNING") as cm:
            out = cl.clone_voice(ref, "hello", output_path=out_file)
        self.assertTrue(out["success"])
        self.assertEqual(out["attempt"], 1)
        self.assertTrue(any("attempt 1 failed" in l for l in cm.output))

    def test_all_attempts_fail_returns_last_error(self):
        ref = _write_wav(self.dir / "ref.wav", seconds=3.0)
        model = MagicMock()
        model.tts_to_file.side_effect = RuntimeError("always broken")
        cl = self.make_cloner(model=model)
        with patch.object(xt, "_estimate_quality", return_value=0.8), \
             self.assertLogs(xt.logger, level="ERROR") as cm:
            out = cl.clone_voice(ref, "hello", max_retries=1,
                                 output_path=str(self.dir / "o.wav"))
        self.assertFalse(out["success"])
        self.assertEqual(out["error"], "always broken")
        self.assertEqual(model.tts_to_file.call_count, 2)  # 1 + 1 retry
        self.assertTrue(any("failed after 2 attempts" in l for l in cm.output))

    def test_low_quality_reference_warns(self):
        ref = _write_wav(self.dir / "ref.wav", seconds=3.0)
        cl = self.make_cloner(model=self.writing_tts(MagicMock()))
        with patch.object(xt, "_estimate_quality", return_value=0.1), \
             self.assertLogs(xt.logger, level="WARNING") as cm:
            out = cl.clone_voice(ref, "hello",
                                 output_path=str(self.dir / "o.wav"))
        self.assertTrue(out["success"])  # warning only, not a failure
        self.assertTrue(any("quality too low" in l for l in cm.output))


class TestCloneFromText(XttsBase):
    def test_no_samples_returns_error(self):
        cl = self.make_cloner()
        with patch.object(xt, "CLONING_SAMPLES_DIR", self.dir):
            out = cl.clone_from_text("hi")
        self.assertFalse(out["success"])
        self.assertIn("No voice samples", out["error"])

    def test_no_usable_samples_returns_error(self):
        cl = self.make_cloner()
        wav = _write_wav(self.dir / "s.wav", seconds=3.0)
        with patch.object(xt, "CLONING_SAMPLES_DIR", self.dir), \
             patch.object(xt, "_select_best_references", return_value=[]):
            out = cl.clone_from_text("hi")
        self.assertFalse(out["success"])
        self.assertIn("below quality threshold", out["error"])

    def test_delegates_to_clone_voice_with_best(self):
        cl = self.make_cloner()
        _write_wav(self.dir / "s.wav", seconds=3.0)
        with patch.object(xt, "CLONING_SAMPLES_DIR", self.dir), \
             patch.object(xt, "_select_best_references",
                          return_value=[{"path": "/best.wav",
                                         "quality": 0.9}]), \
             patch.object(cl, "clone_voice",
                          return_value={"success": True}) as cv:
            out = cl.clone_from_text("hi", output_path="o.wav",
                                     language="fr", max_retries=3)
        cv.assert_called_once_with("/best.wav", "hi", "o.wav", "fr", 3)
        self.assertTrue(out["success"])


# ---------------------------------------------------------------------------
# speak (310-354)
# ---------------------------------------------------------------------------


class TestSpeak(XttsBase):
    def test_unavailable_returns_false(self):
        cl = self.make_cloner(available=False)
        self.assertFalse(cl.speak("hi"))

    def test_no_samples_returns_false(self):
        cl = self.make_cloner()
        with patch.object(xt, "CLONING_SAMPLES_DIR", self.dir):
            self.assertFalse(cl.speak("hi"))

    def test_no_best_reference_returns_false(self):
        cl = self.make_cloner()
        _write_wav(self.dir / "s.wav", seconds=3.0)
        with patch.object(xt, "CLONING_SAMPLES_DIR", self.dir), \
             patch.object(xt, "_select_best_references", return_value=[]):
            self.assertFalse(cl.speak("hi"))

    @staticmethod
    def _wav_writing_tts():
        model = MagicMock()

        def _tts(**kw):
            Path(kw["file_path"]).write_bytes(_real_wav_bytes())

        model.tts_to_file.side_effect = _tts
        return model

    def test_success_generates_and_plays(self):
        cl = self.make_cloner(model=self._wav_writing_tts())
        _write_wav(self.dir / "s.wav", seconds=3.0)
        sd = MagicMock(name="sd")
        with patch.object(xt, "CLONING_SAMPLES_DIR", self.dir), \
             patch.object(xt, "_select_best_references",
                          return_value=[{"path": "/ref.wav"}]), \
             patch.dict(sys.modules, {"sounddevice": sd}):
            self.assertTrue(cl.speak("hello"))
        sd.play.assert_called_once()
        sd.wait.assert_called_once()

    def test_play_failure_still_returns_true(self):
        # inner play try/except swallows -> True (line 334-346)
        cl = self.make_cloner(model=self._wav_writing_tts())
        _write_wav(self.dir / "s.wav", seconds=3.0)
        with patch.object(xt, "CLONING_SAMPLES_DIR", self.dir), \
             patch.object(xt, "_select_best_references",
                          return_value=[{"path": "/ref.wav"}]), \
             patch.dict(sys.modules, {"sounddevice": None}):
            self.assertTrue(cl.speak("hello"))

    def test_generation_failure_returns_false(self):
        cl = self.make_cloner()
        cl._model.tts_to_file.side_effect = RuntimeError("model broke")
        _write_wav(self.dir / "s.wav", seconds=3.0)
        with patch.object(xt, "CLONING_SAMPLES_DIR", self.dir), \
             patch.object(xt, "_select_best_references",
                          return_value=[{"path": "/ref.wav"}]), \
             self.assertLogs(xt.logger, level="ERROR") as cm:
            self.assertFalse(cl.speak("hello"))
        self.assertTrue(any("XTTS speak failed" in l for l in cm.output))


# ---------------------------------------------------------------------------
# clone_with_multiple_refs (356-403)
# ---------------------------------------------------------------------------


class TestMultiRef(XttsBase):
    def test_unavailable(self):
        cl = self.make_cloner(available=False)
        out = cl.clone_with_multiple_refs(["a.wav"], "hi")
        self.assertFalse(out["success"])
        self.assertIn("not available", out["error"])

    def test_empty_refs(self):
        cl = self.make_cloner()
        out = cl.clone_with_multiple_refs([], "hi")
        self.assertFalse(out["success"])
        self.assertIn("No reference audios", out["error"])

    def test_all_refs_fail_quality_gate(self):
        cl = self.make_cloner()
        with patch.object(xt, "_select_best_references", return_value=[]):
            out = cl.clone_with_multiple_refs(["a.wav", "b.wav"], "hi")
        self.assertFalse(out["success"])
        self.assertIn("quality gate", out["error"])

    def test_success_with_multiple_refs(self):
        refs = [_write_wav(self.dir / f"r{i}.wav", seconds=3.0)
                for i in range(2)]
        out_file = str(self.dir / "out.wav")
        model = self.writing_tts(MagicMock())
        cl = self.make_cloner(model=model)
        with patch.object(xt, "_estimate_quality", return_value=0.7):
            out = cl.clone_with_multiple_refs(refs, "hi",
                                              output_path=out_file)
        self.assertTrue(out["success"])
        self.assertEqual(out["refs_used"], 2)
        self.assertEqual(out["quality_score"], 0.7)
        # speaker_wav passed as LIST of paths
        self.assertIsInstance(model.tts_to_file.call_args.kwargs["speaker_wav"],
                              list)

    def test_default_output_path(self):
        refs = [_write_wav(self.dir / "r.wav", seconds=3.0)]
        model = self.writing_tts(MagicMock())
        cl = self.make_cloner(model=model)
        with patch.object(xt, "_estimate_quality", return_value=0.7):
            out = cl.clone_with_multiple_refs(refs, "hi")
        self.assertTrue(out["success"])
        self.assertTrue(out["output"].endswith("orbit_cloned_multi.wav"))

    def test_model_failure_returns_error(self):
        refs = [_write_wav(self.dir / "r.wav", seconds=3.0)]
        model = MagicMock()
        model.tts_to_file.side_effect = RuntimeError("oom")
        cl = self.make_cloner(model=model)
        with patch.object(xt, "_estimate_quality", return_value=0.7), \
             self.assertLogs(xt.logger, level="ERROR") as cm:
            out = cl.clone_with_multiple_refs(refs, "hi",
                                              output_path=str(self.dir / "o.wav"))
        self.assertFalse(out["success"])
        self.assertEqual(out["error"], "oom")
        self.assertTrue(any("Multi-ref voice cloning failed" in l
                            for l in cm.output))


# ---------------------------------------------------------------------------
# sample CRUD (405-444) + module helpers (449-468)
# ---------------------------------------------------------------------------


class TestSampleCrud(XttsBase):
    def test_save_missing_audio(self):
        cl = self.make_cloner()
        out = cl.save_sample(str(self.dir / "nope.wav"), "x")
        self.assertFalse(out["success"])
        self.assertIn("not found", out["error"])

    def test_save_success(self):
        cl = self.make_cloner()
        src = _write_wav(self.dir / "src.wav", seconds=3.0)
        with patch.object(xt, "CLONING_SAMPLES_DIR", self.dir):
            out = cl.save_sample(src, "mysample")
        self.assertTrue(out["success"])
        self.assertTrue(Path(out["path"]).exists())
        self.assertEqual(out["name"], "mysample")
        self.assertIn("quality", out)

    def test_save_copy_failure(self):
        cl = self.make_cloner()
        src = _write_wav(self.dir / "src.wav", seconds=3.0)
        with patch.object(xt, "CLONING_SAMPLES_DIR", self.dir), \
             patch("shutil.copy2", side_effect=OSError("disk full")):
            out = cl.save_sample(src, "x")
        self.assertFalse(out["success"])
        self.assertIn("disk full", out["error"])

    def test_list_samples_with_quality(self):
        cl = self.make_cloner()
        _write_wav(self.dir / "b.wav", seconds=3.0, amplitude=9000)
        _write_wav(self.dir / "a.wav", seconds=3.0, amplitude=9000)
        with patch.object(xt, "CLONING_SAMPLES_DIR", self.dir):
            samples = cl.list_samples()
        self.assertEqual(len(samples), 2)
        self.assertEqual([s["name"] for s in samples], ["a", "b"])  # sorted
        self.assertIn("quality", samples[0])
        self.assertIn("size", samples[0])

    def test_delete_existing(self):
        cl = self.make_cloner()
        _write_wav(self.dir / "gone.wav", seconds=0.5)
        with patch.object(xt, "CLONING_SAMPLES_DIR", self.dir):
            out = cl.delete_sample("gone")
        self.assertTrue(out["success"])
        self.assertEqual(out["deleted"], "gone")
        self.assertFalse((self.dir / "gone.wav").exists())

    def test_delete_missing(self):
        cl = self.make_cloner()
        with patch.object(xt, "CLONING_SAMPLES_DIR", self.dir):
            out = cl.delete_sample("ghost")
        self.assertFalse(out["success"])
        self.assertIn("not found", out["error"])

    def test_is_available(self):
        self.assertTrue(self.make_cloner(available=True).is_available())
        self.assertFalse(self.make_cloner(available=False).is_available())

    def test_get_info(self):
        cl = self.make_cloner()
        _write_wav(self.dir / "s.wav", seconds=3.0)
        with patch.object(xt, "CLONING_SAMPLES_DIR", self.dir):
            info = cl.get_info()
        self.assertTrue(info["available"])
        self.assertEqual(info["model"], xt.XTTS_MODEL)
        self.assertEqual(info["sample_count"], 1)
        self.assertEqual(info["min_duration_sec"], xt.MIN_CLONE_DURATION_SEC)
        self.assertEqual(info["optimal_duration_sec"],
                         xt.OPTIMAL_CLONE_DURATION_SEC)


class TestModuleHelpers(XttsBase):
    def test_get_available_voices_is_a_copy(self):
        v1 = xt.get_available_voices()
        v1["Hacked"] = "x"
        self.assertNotIn("Hacked", xt.get_available_voices())
        self.assertEqual(xt.get_available_voices(), dict(xt.DEFAULT_VOICES))

    def test_get_voice_cloner_singleton(self):
        sentinel = object()
        with patch.object(xt, "_cloner", None), \
             patch.object(xt, "VoiceCloner", return_value=sentinel) as ctor:
            a = xt.get_voice_cloner()
            b = xt.get_voice_cloner()
        self.assertIs(a, sentinel)
        self.assertIs(a, b)  # cached
        ctor.assert_called_once()


# ---------------------------------------------------------------------------
# analyze_reference_audio (474-601)
# ---------------------------------------------------------------------------


class TestAnalyzeReferenceAudio(XttsBase):
    def test_empty_frames_error(self):
        src = str(self.dir / "empty.wav")
        with wave.open(src, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(22050)
        self.assertEqual(xt.analyze_reference_audio(src),
                         {"error": "empty file"})

    def test_zero_frames_reports_empty_file(self):
        # readframes on a zero-frame WAV -> falsy `frames` -> "empty file"
        src = str(self.dir / "z.wav")
        with wave.open(src, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(22050)
            wf.writeframes(b"")
        self.assertEqual(xt.analyze_reference_audio(src),
                         {"error": "empty file"})

    def test_duration_branches(self):
        cases = [
            (0.3, "Too short"),
            (0.8, "Short"),
            (4.0, "Optimal"),
            (20.0, "Long"),
            (45.0, "Very long"),
        ]
        for secs, expect in cases:
            with self.subTest(seconds=secs):
                src = _write_wav(self.dir / f"d{secs}.wav", seconds=secs,
                                 amplitude=9000)
                r = xt.analyze_reference_audio(src)
                self.assertIn(expect, r["details"]["duration_note"])

    def test_full_report_shape_and_scores(self):
        src = _write_wav(self.dir / "good.wav", seconds=3.0, amplitude=12000)
        r = xt.analyze_reference_audio(src)
        for key in ("path", "duration_sec", "sample_rate", "channels",
                    "bit_depth", "scores", "details", "recommendation"):
            self.assertIn(key, r)
        for key in ("duration", "energy", "snr", "clipping",
                    "speech_activity", "overall"):
            self.assertIn(key, r["scores"])
        self.assertGreaterEqual(r["scores"]["overall"], 0.0)
        self.assertLessEqual(r["scores"]["overall"], 1.0)
        self.assertEqual(r["bit_depth"], 16)

    def test_recommendation_matches_overall_tier(self):
        src = _write_wav(self.dir / "good.wav", seconds=3.0, amplitude=12000)
        r = xt.analyze_reference_audio(src)
        overall = r["scores"]["overall"]
        expected = (
            "Excellent" if overall >= 0.8
            else "Good" if overall >= 0.6
            else "Fair — consider re-recording" if overall >= 0.4
            else "Poor — re-record in quiet environment"
        )
        self.assertEqual(r["recommendation"], expected)

    def test_clipped_audio_gets_clipping_penalty(self):
        # Square-ish signal pinned at max -> clipped_percent > 0
        rate, secs = 8000, 2.0
        n = int(rate * secs)
        data = np.full(n, 32767, dtype=np.int16)
        src = str(self.dir / "clip.wav")
        with wave.open(src, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(data.tobytes())
        r = xt.analyze_reference_audio(src)
        self.assertGreater(r["details"]["clipped_percent"], 0.0)
        self.assertEqual(r["scores"]["clipping"], 0.0)  # >1% clipped

    def test_corrupt_file_returns_error_string(self):
        bad = str(self.dir / "bad.wav")
        Path(bad).write_bytes(b"garbage")
        r = xt.analyze_reference_audio(bad)
        self.assertIn("error", r)
        self.assertNotIn("scores", r)

    def test_import_error_branch(self):
        # numpy unavailable -> ImportError handler (line 598-599)
        src = _write_wav(self.dir / "g.wav", seconds=1.0)
        real_import = __import__

        def fake_import(name, *a, **k):
            if name == "numpy":
                raise ImportError("no numpy")
            return real_import(name, *a, **k)

        with patch("builtins.__import__", side_effect=fake_import):
            r = xt.analyze_reference_audio(src)
        self.assertEqual(r, {"error": "numpy not installed"})


# ---------------------------------------------------------------------------
# analyze_all_references (604-626)
# ---------------------------------------------------------------------------


class TestAnalyzeAllReferences(XttsBase):
    def test_empty_dir_message(self):
        with patch.object(xt, "CLONING_SAMPLES_DIR", self.dir):
            out = xt.analyze_all_references()
        self.assertEqual(out["samples"], [])
        self.assertIn("No reference audio found", out["message"])

    def test_aggregates_scores_and_best_sample(self):
        _write_wav(self.dir / "good.wav", seconds=3.0, amplitude=12000)
        _write_wav(self.dir / "ok.wav", seconds=3.0, amplitude=4000)
        with patch.object(xt, "CLONING_SAMPLES_DIR", self.dir):
            out = xt.analyze_all_references()
        self.assertEqual(out["count"], 2)
        self.assertEqual(len(out["samples"]), 2)
        self.assertGreater(out["average_quality"], 0.0)
        self.assertIn("scores", out["best_sample"])
        self.assertIn(out["cloning_readiness"],
                      ("Ready", "Needs better samples", "Record new samples"))

    def test_error_entries_excluded_from_average(self):
        _write_wav(self.dir / "good.wav", seconds=3.0, amplitude=12000)
        (self.dir / "junk.wav").write_bytes(b"not wave")
        with patch.object(xt, "CLONING_SAMPLES_DIR", self.dir):
            out = xt.analyze_all_references()
        self.assertEqual(out["count"], 2)  # both listed
        scored = [s for s in out["samples"] if "scores" in s]
        self.assertEqual(len(scored), 1)  # junk has no scores

    def test_all_error_results_average_zero(self):
        (self.dir / "junk.wav").write_bytes(b"not wave")
        with patch.object(xt, "CLONING_SAMPLES_DIR", self.dir):
            out = xt.analyze_all_references()
        self.assertEqual(out["average_quality"], 0)
        # best = max over empty `scores` -> the error entry itself (score 0)
        self.assertNotIn("scores", out["best_sample"])
        self.assertEqual(out["cloning_readiness"], "Record new samples")

    def test_mp3_files_included(self):
        (self.dir / "song.mp3").write_bytes(b"ID3notreally")
        with patch.object(xt, "CLONING_SAMPLES_DIR", self.dir):
            out = xt.analyze_all_references()
        self.assertEqual(out["count"], 1)


if __name__ == "__main__":
    unittest.main()
