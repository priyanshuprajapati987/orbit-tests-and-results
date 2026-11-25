"""Deep coverage tests for orbit/orbit/tts.py (515 lines, multi-engine TTS).

Targets the lines the existing streaming/voice tests miss: _run_async_task
branches, pyttsx3 engine paths, voice/rate/pitch resolution, speak routing,
edge-tts async generators, playback fallbacks (sounddevice / PowerShell /
WAV), XTTS routing and offline speech. All network/audio is mocked.
"""

import asyncio
import os
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# numpy's C extension can only be loaded ONCE per process. The tests below
# swap sys.modules via patch.dict(), which evicts anything imported inside
# the window on exit — so numpy must already be fully imported beforehand,
# otherwise the second test re-loads _multiarray_umath and dies with
# "cannot load module more than once per process".
import numpy  # noqa: F401

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.orbit import tts as tts_mod
from orbit.orbit.config import TTS_SPEED, TTS_VOICE, TTS_VOICES


async def _coro_ok(value=42):
    return value


async def _coro_boom():
    raise ValueError("async boom")


class TtsBase(unittest.TestCase):
    """Save/restore every mutable module global the tests touch."""

    _GLOBALS = (
        "_current_engine",
        "_voice_map",
        "_pyttsx3_engine",
        "_pyttsx3_base_rate",
        "_pydub_ffmpeg_configured",
        "_EDGE_TTS_AVAILABLE",
    )

    def setUp(self):
        self._saved = {k: getattr(tts_mod, k) for k in self._GLOBALS}

        def _restore():
            for k, v in self._saved.items():
                setattr(tts_mod, k, v)

        self.addCleanup(_restore)


# ---------------------------------------------------------------------------
# _run_async_task (lines 39-65): thread path when a loop is running
# ---------------------------------------------------------------------------


class TestRunAsyncTask(TtsBase):
    def test_no_running_loop_runs_directly(self):
        self.assertEqual(tts_mod._run_async_task(_coro_ok(7)), 7)

    def test_no_loop_exception_propagates(self):
        with self.assertRaises(ValueError):
            tts_mod._run_async_task(_coro_boom())

    def test_running_loop_uses_thread_path(self):
        async def inside():
            # current thread has a running loop -> thread fallback must be used
            return tts_mod._run_async_task(_coro_ok(11))

        self.assertEqual(asyncio.run(inside()), 11)

    def test_running_loop_exception_propagates(self):
        async def inside():
            return tts_mod._run_async_task(_coro_boom())

        with self.assertRaises(ValueError):
            asyncio.run(inside())

    def test_running_loop_timeout_returns_none(self):
        # A fake thread that never finishes exercises the 30s-timeout branch.
        class FakeThread:
            def __init__(self, target=None, daemon=None):
                self._target = target

            def start(self):
                pass

            def join(self, timeout=None):
                pass

            def is_alive(self):
                return True

        async def inside():
            with patch.object(tts_mod.threading, "Thread", FakeThread):
                with self.assertLogs(tts_mod.logger, level="WARNING") as cm:
                    result = tts_mod._run_async_task(_coro_ok(1))
                return result, cm.output

        result, logs = asyncio.run(inside())
        self.assertIsNone(result)
        self.assertTrue(any("timed out" in line for line in logs))


# ---------------------------------------------------------------------------
# pyttsx3 engine (77-87) + get_voices (101-108)
# ---------------------------------------------------------------------------


class TestPyttsx3AndVoices(TtsBase):
    def _fake_pyttsx3(self, engine):
        mod = types.ModuleType("pyttsx3")
        mod.init = lambda: engine
        return mod

    def test_cached_engine_returned(self):
        fake = object()
        tts_mod._pyttsx3_engine = fake
        self.assertIs(tts_mod._get_pyttsx3(), fake)

    def test_init_success_caches_engine(self):
        # full-suite isolation: an earlier test file may have warmed the
        # real pyttsx3 engine into the cache — start from a clean slate
        tts_mod._pyttsx3_engine = None
        engine = MagicMock(name="pyttsx3-engine")
        with patch.dict(sys.modules, {"pyttsx3": self._fake_pyttsx3(engine)}):
            got = tts_mod._get_pyttsx3()
        self.assertIs(got, engine)
        self.assertIs(tts_mod._pyttsx3_engine, engine)  # cached

    def test_init_failure_returns_none(self):
        tts_mod._pyttsx3_engine = None
        with patch.dict(sys.modules, {"pyttsx3": None}):  # import raises
            self.assertIsNone(tts_mod._get_pyttsx3())
        self.assertIsNone(tts_mod._pyttsx3_engine)

    def test_online_voices_from_config(self):
        voices = tts_mod.get_voices(offline=False)
        self.assertEqual(voices, list(TTS_VOICES.items()))

    def test_default_arg_uses_offline_mode_flag(self):
        with patch.object(tts_mod, "OFFLINE_MODE", False):
            self.assertEqual(tts_mod.get_voices(), list(TTS_VOICES.items()))

    def test_offline_uses_pyttsx3_engine(self):
        v1 = types.SimpleNamespace(name="Anna", id="id-anna")
        v2 = types.SimpleNamespace(name="Bo", id="id-bo")
        engine = MagicMock()
        engine.getProperty.return_value = [v1, v2]
        with patch.object(tts_mod, "_get_pyttsx3", return_value=engine):
            got = tts_mod.get_voices(offline=True)
        self.assertEqual(got, [("Anna", "id-anna"), ("Bo", "id-bo")])
        engine.getProperty.assert_called_once_with("voices")

    def test_offline_engine_unavailable_falls_back_to_config(self):
        with patch.object(tts_mod, "_get_pyttsx3", return_value=None):
            got = tts_mod.get_voices(offline=True)
        self.assertEqual(got, list(TTS_VOICES.items()))


# ---------------------------------------------------------------------------
# _resolve_voice (111-120)
# ---------------------------------------------------------------------------


class TestResolveVoice(TtsBase):
    def test_none_gives_default(self):
        self.assertEqual(tts_mod._resolve_voice(None), TTS_VOICE)

    def test_display_name_maps_to_voice_id(self):
        display = "Jenny (US Female) \U0001f338"
        self.assertEqual(tts_mod._resolve_voice(display), "en-US-JennyNeural")

    def test_voice_id_passes_through(self):
        self.assertEqual(
            tts_mod._resolve_voice("en-US-GuyNeural"), "en-US-GuyNeural"
        )

    def test_value_with_empty_map_returns_itself(self):
        # line 118-119: in TTS_VOICES.values() but not in the (cached) map
        tts_mod._voice_map = {}
        self.assertEqual(tts_mod._resolve_voice("en-US-GuyNeural"),
                         "en-US-GuyNeural")

    def test_unknown_falls_back_to_default(self):
        tts_mod._voice_map = {}
        self.assertEqual(tts_mod._resolve_voice("no-such-voice"), TTS_VOICE)


# ---------------------------------------------------------------------------
# _compute_rate / _compute_pitch (123-159)
# ---------------------------------------------------------------------------


class TestRateAndPitch(TtsBase):
    def test_rate_sentiment_none_defaults_neutral(self):
        self.assertEqual(tts_mod._compute_rate(100, None), "+0%")

    def test_rate_uses_tts_speed_when_speed_none(self):
        expected = f"+{TTS_SPEED - 100}%"
        self.assertEqual(tts_mod._compute_rate(None, "neutral"), expected)

    def test_rate_positive_sentiment_adds_delta(self):
        # excited: +30%, speed 180 -> 80 + 30 = 110
        self.assertEqual(tts_mod._compute_rate(180, "excited"), "+110%")

    def test_rate_negative_sentiment_subtracts_delta(self):
        # calm: -15%, speed 100 -> 0 - 15 = -15
        self.assertEqual(tts_mod._compute_rate(100, "calm"), "-15%")

    def test_rate_clamped_high(self):
        self.assertEqual(tts_mod._compute_rate(10000, "neutral"), "+150%")

    def test_rate_clamped_low(self):
        self.assertEqual(tts_mod._compute_rate(-10000, "neutral"), "-50%")

    def test_rate_malformed_delta_treated_as_zero(self):
        with patch.object(tts_mod, "get_tts_params",
                          return_value={"rate_delta": "not-a-number"}):
            self.assertEqual(tts_mod._compute_rate(100, "x"), "+0%")

    def test_pitch_sentiment_none_defaults_neutral(self):
        self.assertEqual(tts_mod._compute_pitch(None), "+0Hz")

    def test_pitch_positive(self):
        self.assertEqual(tts_mod._compute_pitch("excited"), "+10Hz")

    def test_pitch_negative(self):
        self.assertEqual(tts_mod._compute_pitch("sad"), "-10Hz")

    def test_pitch_clamped_high(self):
        with patch.object(tts_mod, "get_tts_params",
                          return_value={"pitch_delta": "+900Hz"}):
            self.assertEqual(tts_mod._compute_pitch("x"), "+50Hz")

    def test_pitch_clamped_low(self):
        with patch.object(tts_mod, "get_tts_params",
                          return_value={"pitch_delta": "-900Hz"}):
            self.assertEqual(tts_mod._compute_pitch("x"), "-50Hz")

    def test_pitch_malformed_delta_treated_as_zero(self):
        with patch.object(tts_mod, "get_tts_params",
                          return_value={"pitch_delta": "junk"}):
            self.assertEqual(tts_mod._compute_pitch("x"), "+0Hz")

    def test_public_rate_helper_delegates(self):
        self.assertEqual(
            tts_mod.compute_rate_for_voice(100, "neutral"),
            tts_mod._compute_rate(100, "neutral"),
        )


# ---------------------------------------------------------------------------
# speak() routing (167-205)
# ---------------------------------------------------------------------------


class TestSpeak(TtsBase):
    def test_empty_text_is_noop(self):
        self.assertIsNone(tts_mod.speak(""))
        self.assertIsNone(tts_mod.speak("   "))

    def test_offline_mode_routes_to_offline(self):
        with patch.object(tts_mod, "OFFLINE_MODE", True), \
             patch.object(tts_mod, "_speak_offline") as off:
            tts_mod.speak("hello there")
        off.assert_called_once_with("hello there", None, None)

    def test_kokoro_engine_routes_to_xtts(self):
        tts_mod.set_engine("kokoro")
        with patch.object(tts_mod, "_speak_xtts") as xt:
            tts_mod.speak("hi", voice="bm_george", speed=150)
        xt.assert_called_once_with("hi", "bm_george", 150)

    def test_xtts_engine_routes_to_xtts(self):
        tts_mod.set_engine("xtts")
        with patch.object(tts_mod, "_speak_xtts") as xt:
            tts_mod.speak("hi")
        xt.assert_called_once()

    def test_edge_happy_path_runs_async_task(self):
        tts_mod.set_engine("edge-tts")
        with patch.object(tts_mod, "_run_async_task",
                          return_value=b"mp3") as run, \
             patch.object(tts_mod, "_speak_offline") as off:
            tts_mod.speak("good morning")
        run.assert_called_once()
        off.assert_not_called()

    def test_sentiment_detected_when_not_given(self):
        tts_mod.set_engine("edge-tts")
        with patch.object(tts_mod, "detect_sentiment",
                          return_value="sad") as det, \
             patch.object(tts_mod, "_run_async_task", return_value=b"x"):
            tts_mod.speak("this is awful")
        det.assert_called_once_with("this is awful")

    def test_edge_failure_falls_back_offline(self):
        tts_mod.set_engine("edge-tts")
        with patch.object(tts_mod, "_run_async_task",
                          side_effect=RuntimeError("no network")), \
             patch.object(tts_mod, "_speak_offline") as off:
            tts_mod.speak("fallback please", speed=150, sentiment="happy")
        off.assert_called_once_with("fallback please", 150, "happy")

    def test_voice_personality_adapts_voice(self):
        tts_mod.set_engine("edge-tts")
        vp = MagicMock()
        vp.adapt_tone.return_value = {"voice": "en-US-GuyNeural"}
        with patch("orbit.orbit.core.voice_personality.get_voice_personality",
                   return_value=vp), \
             patch.object(tts_mod, "_resolve_voice",
                          return_value="en-US-GuyNeural") as res, \
             patch.object(tts_mod, "_run_async_task", return_value=b"x"):
            tts_mod.speak("hello")
        vp.adapt_tone.assert_called_once_with("", "hello")
        res.assert_called_once_with("en-US-GuyNeural")

    def test_voice_personality_failure_is_swallowed(self):
        tts_mod.set_engine("edge-tts")
        with patch("orbit.orbit.core.voice_personality.get_voice_personality",
                   side_effect=RuntimeError("vp down")), \
             patch.object(tts_mod, "_run_async_task", return_value=b"x") as run:
            tts_mod.speak("still works")  # must not raise
        run.assert_called_once()


# ---------------------------------------------------------------------------
# generate_audio (208-231) + edge-tts async generators (234-256)
# ---------------------------------------------------------------------------


class TestGenerateAudio(TtsBase):
    def test_empty_text_returns_empty_bytes(self):
        self.assertEqual(tts_mod.generate_audio("  "), (b"", "audio/mpeg"))

    def test_sentiment_detected_when_missing(self):
        with patch.object(tts_mod, "detect_sentiment",
                          return_value="happy") as det, \
             patch.object(tts_mod, "_run_async_task", return_value=b"mp3"):
            tts_mod.generate_audio("yay!")
        det.assert_called_once_with("yay!")

    def test_success_returns_audio(self):
        with patch.object(tts_mod, "_run_async_task",
                          return_value=b"ID3data") as run:
            data, mime = tts_mod.generate_audio("hello")
        self.assertEqual(data, b"ID3data")
        self.assertEqual(mime, "audio/mpeg")
        run.assert_called_once()

    def test_failure_returns_empty_bytes(self):
        with patch.object(tts_mod, "_run_async_task",
                          side_effect=RuntimeError("edge down")):
            data, mime = tts_mod.generate_audio("hello")
        self.assertEqual(data, b"")
        self.assertEqual(mime, "audio/mpeg")


class _FakeCommunicate:
    def __init__(self, text, voice=None, rate=None, pitch=None):
        self.text = text

    async def stream(self):
        yield {"type": "audio", "data": b"aa"}
        yield {"type": "metadata", "data": {"offset": 0}}
        yield {"type": "audio", "data": b""}
        yield {"type": "audio", "data": b"bb"}


def _fake_edge_tts():
    return types.SimpleNamespace(Communicate=_FakeCommunicate)


class TestEdgeTtsAsync(TtsBase):
    def test_generate_raises_when_not_available(self):
        with patch.object(tts_mod, "_EDGE_TTS_AVAILABLE", False):
            with self.assertRaises(ImportError):
                asyncio.run(tts_mod._generate_edge_tts("x", "v", "+0%"))

    def test_generate_collects_only_audio_chunks(self):
        with patch.object(tts_mod, "_EDGE_TTS_AVAILABLE", True), \
             patch.object(tts_mod, "edge_tts", _fake_edge_tts()):
            out = asyncio.run(
                tts_mod._generate_edge_tts("x", "v", "+0%"))
        self.assertEqual(out, b"aabb")

    def test_stream_raises_when_not_available(self):
        with patch.object(tts_mod, "_EDGE_TTS_AVAILABLE", False):
            async def collect():
                return [c async for c in
                        tts_mod._generate_edge_tts_stream("x", "v", "+0%")]

            with self.assertRaises(ImportError):
                asyncio.run(collect())

    def test_stream_yields_nonempty_audio_only(self):
        async def collect():
            return [c async for c in
                    tts_mod._generate_edge_tts_stream("x", "v", "+0%")]

        with patch.object(tts_mod, "_EDGE_TTS_AVAILABLE", True), \
             patch.object(tts_mod, "edge_tts", _fake_edge_tts()):
            chunks = asyncio.run(collect())
        self.assertEqual(chunks, [b"aa", b"bb"])


# ---------------------------------------------------------------------------
# _collect_stream_chunks (285-290) + _speak_async (293-298)
# ---------------------------------------------------------------------------


class TestStreamHelperAndSpeakAsync(TtsBase):
    def test_collect_stream_chunks_gathers_all(self):
        async def gen():
            yield b"1"
            yield b"2"
            yield b"3"

        out = asyncio.run(tts_mod._collect_stream_chunks(gen()))
        self.assertEqual(out, [b"1", b"2", b"3"])

    def test_speak_async_plays_when_audio(self):
        with patch.object(tts_mod, "_generate_edge_tts",
                          new=AsyncMock(return_value=b"mp3")), \
             patch.object(tts_mod, "_play_audio_bytes") as play:
            out = asyncio.run(tts_mod._speak_async("hi", "v", "+0%"))
        self.assertEqual(out, b"mp3")
        play.assert_called_once_with(b"mp3")

    def test_speak_async_skips_play_when_empty(self):
        with patch.object(tts_mod, "_generate_edge_tts",
                          new=AsyncMock(return_value=b"")), \
             patch.object(tts_mod, "_play_audio_bytes") as play:
            out = asyncio.run(tts_mod._speak_async("hi", "v", "+0%"))
        self.assertEqual(out, b"")
        play.assert_not_called()


# ---------------------------------------------------------------------------
# _play_audio_bytes fallbacks (301-319)
# ---------------------------------------------------------------------------


class TestPlayAudioBytes(TtsBase):
    def test_sounddevice_success_short_circuits(self):
        with patch.object(tts_mod, "_play_with_sounddevice") as sd, \
             patch.object(tts_mod, "_play_mp3") as mp3:
            tts_mod._play_audio_bytes(b"mp3")
        sd.assert_called_once_with(b"mp3")
        mp3.assert_not_called()

    def test_import_error_falls_back_to_powershell(self):
        with patch.object(tts_mod, "_play_with_sounddevice",
                          side_effect=ImportError("no pydub")), \
             patch.object(tts_mod, "_play_mp3") as mp3:
            tts_mod._play_audio_bytes(b"mp3")
        mp3.assert_called_once()
        self.assertTrue(mp3.call_args.args[0].endswith(".mp3"))

    def test_generic_failure_falls_back_to_powershell(self):
        with patch.object(tts_mod, "_play_with_sounddevice",
                          side_effect=RuntimeError("device busy")), \
             patch.object(tts_mod, "_play_mp3") as mp3:
            tts_mod._play_audio_bytes(b"mp3")
        mp3.assert_called_once()

    def test_temp_file_removed_after_playback(self):
        with patch.object(tts_mod, "_play_with_sounddevice",
                          side_effect=ImportError), \
             patch.object(tts_mod, "_play_mp3"), \
             patch.object(tts_mod.os, "unlink") as unlink:
            tts_mod._play_audio_bytes(b"mp3")
        unlink.assert_called_once()

    def test_unlink_failure_logged_not_raised(self):
        with patch.object(tts_mod, "_play_with_sounddevice",
                          side_effect=ImportError), \
             patch.object(tts_mod, "_play_mp3"), \
             patch.object(tts_mod.os, "unlink",
                          side_effect=OSError("locked")):
            with self.assertLogs(tts_mod.logger, level="ERROR") as cm:
                tts_mod._play_audio_bytes(b"mp3")
        self.assertTrue(any("clean up" in line for line in cm.output))


# ---------------------------------------------------------------------------
# _ensure_pydub_ffmpeg (325-340)
# ---------------------------------------------------------------------------


class TestEnsurePydubFfmpeg(TtsBase):
    def test_already_configured_returns_immediately(self):
        tts_mod._pydub_ffmpeg_configured = True
        tts_mod._ensure_pydub_ffmpeg()  # must not raise / import
        self.assertTrue(tts_mod._pydub_ffmpeg_configured)

    def test_sets_converter_from_imageio_ffmpeg(self):
        tts_mod._pydub_ffmpeg_configured = False
        pydub = types.ModuleType("pydub")
        pydub.AudioSegment = type("AudioSegment", (), {"converter": None})
        utils = types.ModuleType("pydub.utils")
        utils.which = lambda name: None  # ffmpeg not in PATH
        pydub.utils = utils
        imageio = types.ModuleType("imageio_ffmpeg")
        imageio.get_ffmpeg_exe = lambda: "C:/fake/ffmpeg.exe"
        with patch.dict(sys.modules,
                        {"pydub": pydub, "pydub.utils": utils,
                         "imageio_ffmpeg": imageio}):
            tts_mod._ensure_pydub_ffmpeg()
        self.assertEqual(pydub.AudioSegment.converter, "C:/fake/ffmpeg.exe")
        self.assertTrue(tts_mod._pydub_ffmpeg_configured)

    def test_pydub_missing_is_swallowed(self):
        tts_mod._pydub_ffmpeg_configured = False
        with patch.dict(sys.modules, {"pydub": None}):
            tts_mod._ensure_pydub_ffmpeg()  # ImportError -> pass
        self.assertTrue(tts_mod._pydub_ffmpeg_configured)


# ---------------------------------------------------------------------------
# _play_with_sounddevice (343-362)
# ---------------------------------------------------------------------------


class TestPlayWithSounddevice(TtsBase):
    def _fakes(self, channels=1, samples=(100, 200, 300), raise_from_mp3=None):
        class FakeSegment:
            def __init__(self):
                self.channels = channels
                self.frame_rate = 22050

            def get_array_of_samples(self):
                return list(samples)

        pydub = types.ModuleType("pydub")
        seg = FakeSegment()

        def from_mp3(src):
            if raise_from_mp3:
                raise raise_from_mp3
            return seg

        pydub.AudioSegment = type("AS", (), {"from_mp3": staticmethod(from_mp3)})
        sd = types.ModuleType("sounddevice")
        sd.play = MagicMock(name="sd.play")
        sd.wait = MagicMock(name="sd.wait")
        return pydub, sd

    def test_mono_playback(self):
        pydub, sd = self._fakes(channels=1)
        with patch.dict(sys.modules, {"pydub": pydub, "sounddevice": sd}), \
             patch.object(tts_mod, "_ensure_pydub_ffmpeg"):
            tts_mod._play_with_sounddevice(b"mp3")
        sd.play.assert_called_once()
        sd.wait.assert_called_once()

    def test_stereo_samples_reshaped(self):
        pydub, sd = self._fakes(channels=2, samples=(1, 2, 3, 4, 5, 6))
        with patch.dict(sys.modules, {"pydub": pydub, "sounddevice": sd}), \
             patch.object(tts_mod, "_ensure_pydub_ffmpeg"):
            tts_mod._play_with_sounddevice(b"mp3")
        arg = sd.play.call_args.args[0]
        self.assertEqual(arg.shape, (3, 2))  # 6 samples -> (3, 2)

    def test_import_error_raises_runtime_error(self):
        with patch.dict(sys.modules, {"pydub": None}):
            with self.assertRaises(RuntimeError):
                tts_mod._play_with_sounddevice(b"mp3")

    def test_decode_failure_logs_and_raises(self):
        pydub, sd = self._fakes(raise_from_mp3=ValueError("bad mp3"))
        with patch.dict(sys.modules, {"pydub": pydub, "sounddevice": sd}):
            with self.assertLogs(tts_mod.logger, level="WARNING") as cm:
                with self.assertRaises(ValueError):
                    tts_mod._play_with_sounddevice(b"mp3")
        self.assertTrue(any("sounddevice playback failed" in line
                            for line in cm.output))


# ---------------------------------------------------------------------------
# _play_streaming_mp3 (365-404)
# ---------------------------------------------------------------------------


class TestPlayStreamingMp3(TtsBase):
    def _fakes(self, decode_results=None):
        """decode_results: list of outcomes per from_mp3 call (obj or exc)."""
        calls = {"n": 0}

        class FakeSeg:
            channels = 1
            frame_rate = 22050

            def get_array_of_samples(self):
                return [1, 2]

            def __add__(self, other):
                return self

        def from_mp3(src):
            idx = calls["n"]
            calls["n"] += 1
            outcome = decode_results[idx] if decode_results else True
            if isinstance(outcome, Exception):
                raise outcome
            return FakeSeg()

        pydub = types.ModuleType("pydub")
        pydub.AudioSegment = type("AS", (), {"from_mp3": staticmethod(from_mp3)})
        sd = types.ModuleType("sounddevice")
        sd.play = MagicMock(name="sd.play")
        sd.wait = MagicMock(name="sd.wait")
        return pydub, sd, calls

    def test_all_chunks_decode_and_play(self):
        pydub, sd, _ = self._fakes(decode_results=[True, True])
        with patch.dict(sys.modules, {"pydub": pydub, "sounddevice": sd}), \
             patch.object(tts_mod, "_ensure_pydub_ffmpeg"):
            tts_mod._play_streaming_mp3([b"aa", b"bb"])
        sd.play.assert_called_once()
        sd.wait.assert_called_once()

    def test_undecodable_chunk_is_skipped(self):
        pydub, sd, calls = self._fakes(
            decode_results=[ValueError("partial"), True])
        with patch.dict(sys.modules, {"pydub": pydub, "sounddevice": sd}), \
             patch.object(tts_mod, "_ensure_pydub_ffmpeg"):
            tts_mod._play_streaming_mp3([b"aa", b"bb"])
        self.assertEqual(calls["n"], 2)  # both attempted
        sd.play.assert_called_once()  # second one played

    def test_no_decodable_chunks_no_play(self):
        pydub, sd, _ = self._fakes(
            decode_results=[ValueError("junk"), ValueError("junk2")])
        with patch.dict(sys.modules, {"pydub": pydub, "sounddevice": sd}), \
             patch.object(tts_mod, "_ensure_pydub_ffmpeg"):
            tts_mod._play_streaming_mp3([b"aa", b"bb"])
        sd.play.assert_not_called()

    def test_play_failure_logged_not_raised(self):
        pydub, sd, _ = self._fakes(decode_results=[True])
        sd.play.side_effect = RuntimeError("device gone")
        with patch.dict(sys.modules, {"pydub": pydub, "sounddevice": sd}), \
             patch.object(tts_mod, "_ensure_pydub_ffmpeg"):
            with self.assertLogs(tts_mod.logger, level="ERROR") as cm:
                tts_mod._play_streaming_mp3([b"aa"])  # must not raise
        self.assertTrue(any("Streaming playback failed" in line
                            for line in cm.output))

    def test_import_error_returns_silently(self):
        with patch.dict(sys.modules, {"pydub": None}):
            tts_mod._play_streaming_mp3([b"aa"])  # warning + return


# ---------------------------------------------------------------------------
# _play_wav_fallback (441-457)
# ---------------------------------------------------------------------------


class TestPlayWavFallback(TtsBase):
    def test_success_plays_float_samples(self):
        class FakeAudio:
            raw_data = b"\x01\x00\x02\x00"  # 2 int16 samples
            frame_rate = 16000

        pydub = types.ModuleType("pydub")
        pydub.AudioSegment = type(
            "AS", (), {"from_mp3": staticmethod(lambda p: FakeAudio())})
        sd = types.ModuleType("sounddevice")
        sd.play = MagicMock(name="sd.play")
        sd.wait = MagicMock(name="sd.wait")
        with patch.dict(sys.modules, {"pydub": pydub, "sounddevice": sd}):
            tts_mod._play_wav_fallback("/tmp/x.mp3")
        sd.play.assert_called_once()
        sd.wait.assert_called_once()

    def test_import_error_logged(self):
        with patch.dict(sys.modules, {"pydub": None}):
            with self.assertLogs(tts_mod.logger, level="ERROR") as cm:
                tts_mod._play_wav_fallback("/tmp/x.mp3")
        self.assertTrue(any("not available" in line for line in cm.output))

    def test_decode_failure_logged(self):
        pydub = types.ModuleType("pydub")

        def boom(p):
            raise ValueError("not mp3")

        pydub.AudioSegment = type("AS", (), {"from_mp3": staticmethod(boom)})
        with patch.dict(sys.modules, {"pydub": pydub}):
            with self.assertLogs(tts_mod.logger, level="ERROR") as cm:
                tts_mod._play_wav_fallback("/tmp/x.mp3")  # must not raise
        self.assertTrue(any("playback failed" in line for line in cm.output))


# ---------------------------------------------------------------------------
# _speak_xtts (460-488)
# ---------------------------------------------------------------------------


class TestSpeakXtts(TtsBase):
    def _cloner(self, available=True, speak_raises=False):
        cl = MagicMock(name="cloner")
        cl.is_available.return_value = available
        if speak_raises:
            cl.speak.side_effect = RuntimeError("xtts broke")
        return cl

    def _patch_cloner(self, cl):
        return patch("orbit.orbit.xtts.get_voice_cloner", return_value=cl)

    def test_unavailable_falls_back_offline(self):
        cl = self._cloner(available=False)
        with self._patch_cloner(cl), \
             patch.object(tts_mod, "_speak_offline") as off:
            tts_mod._speak_xtts("hello")
        off.assert_called_once_with("hello")
        cl.speak.assert_not_called()

    def test_valid_voice_and_default_speed(self):
        cl = self._cloner()
        with self._patch_cloner(cl), \
             patch.object(tts_mod, "_speak_offline") as off:
            tts_mod._speak_xtts("hello", voice="bm_george")
        cl.speak.assert_called_once_with("hello", voice="bm_george",
                                         speed=1.0)
        off.assert_not_called()

    def test_unknown_voice_replaced_with_default(self):
        cl = self._cloner()
        with self._patch_cloner(cl):
            tts_mod._speak_xtts("hello", voice="not-a-kokoro-voice")
        self.assertEqual(cl.speak.call_args.kwargs["voice"], "bm_george")

    def test_none_voice_replaced_with_default(self):
        cl = self._cloner()
        with self._patch_cloner(cl):
            tts_mod._speak_xtts("hello", voice=None)
        self.assertEqual(cl.speak.call_args.kwargs["voice"], "bm_george")

    def test_speed_converted_from_wpm(self):
        cl = self._cloner()
        with self._patch_cloner(cl):
            tts_mod._speak_xtts("hello", voice="bm_george", speed=90)
        self.assertAlmostEqual(cl.speak.call_args.kwargs["speed"], 0.5)

    def test_exception_falls_back_offline(self):
        cl = self._cloner(speak_raises=True)
        with self._patch_cloner(cl), \
             patch.object(tts_mod, "_speak_offline") as off:
            tts_mod._speak_xtts("hello", voice="bm_george")
        off.assert_called_once_with("hello")


# ---------------------------------------------------------------------------
# _speak_offline (491-506) + stop() (509-515)
# ---------------------------------------------------------------------------


class TestSpeakOfflineAndStop(TtsBase):
    def _engine(self, base_rate=200, say_raises=False):
        eng = MagicMock(name="offline-engine")
        eng.getProperty.return_value = base_rate
        if say_raises:
            eng.say.side_effect = RuntimeError("say failed")
        return eng

    def test_no_engine_returns_silently(self):
        with patch.object(tts_mod, "_get_pyttsx3", return_value=None):
            self.assertIsNone(tts_mod._speak_offline("hi"))

    def test_base_rate_cached_and_restored(self):
        eng = self._engine(base_rate=200)
        tts_mod._pyttsx3_base_rate = None
        with patch.object(tts_mod, "_get_pyttsx3", return_value=eng):
            tts_mod._speak_offline("hi")  # speed None -> base rate
        self.assertEqual(tts_mod._pyttsx3_base_rate, 200)
        eng.setProperty.assert_called_with("rate", 200)
        eng.say.assert_called_once_with("hi")
        eng.runAndWait.assert_called_once()

    def test_speed_scales_rate(self):
        eng = self._engine(base_rate=200)
        tts_mod._pyttsx3_base_rate = 200
        with patch.object(tts_mod, "_get_pyttsx3", return_value=eng):
            tts_mod._speak_offline("hi", speed=180)
        eng.setProperty.assert_called_with("rate", 360)  # 200 * 180/100

    def test_say_failure_logged(self):
        eng = self._engine(say_raises=True)
        tts_mod._pyttsx3_base_rate = 200
        with patch.object(tts_mod, "_get_pyttsx3", return_value=eng):
            with self.assertLogs(tts_mod.logger, level="ERROR") as cm:
                tts_mod._speak_offline("hi")  # must not raise
        self.assertTrue(any("pyttsx3 speech failed" in line
                            for line in cm.output))

    def test_stop_calls_sounddevice_stop(self):
        sd = types.ModuleType("sounddevice")
        sd.stop = MagicMock(name="sd.stop")
        with patch.dict(sys.modules, {"sounddevice": sd}):
            tts_mod.stop()
        sd.stop.assert_called_once()

    def test_stop_failure_logged(self):
        with patch.dict(sys.modules, {"sounddevice": None}):
            with self.assertLogs(tts_mod.logger, level="ERROR") as cm:
                tts_mod.stop()  # must not raise
        self.assertTrue(any("Failed to stop" in line for line in cm.output))


if __name__ == "__main__":
    unittest.main()
