"""Deep coverage tests for orbit/orbit/wake_word.py (633 lines).

Targets the lines the existing test_wake_word.py misses: tuning load/persist,
bandpass/energy helpers, OWW init + listen loops, energy listen loop with
cooldown, streaming/quick STT, N-of-M confirmation gates, _process_frame
decision tree, _open_mic pyaudio/sounddevice backends, training data
generation + info, and availability checks. Audio/model/network is mocked.
"""

import json
import os
import struct
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

import numpy as np  # noqa: E402

from orbit.orbit import wake_word as ww  # noqa: E402


class WakeBase(unittest.TestCase):
    _GLOBALS = ("OWW_THRESHOLD", "ENERGY_THRESHOLD", "CONFIDENCE_THRESHOLD",
                "CONFIRMATION_MIN", "WAKE_WORD", "WAKE_WORD_VARIANTS")

    def setUp(self):
        self._saved = {k: getattr(ww, k) for k in self._GLOBALS}

        def _restore():
            for k, v in self._saved.items():
                setattr(ww, k, v)

        self.addCleanup(_restore)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    @staticmethod
    def make_detector(**attrs):
        det = ww.WakeWordDetector()  # openwakeword absent -> ImportError path
        for k, v in attrs.items():
            setattr(det, k, v)
        return det


# ---------------------------------------------------------------------------
# _tuning_file (37-43) + _load_tuning (46-70) + apply_tuning (76-109)
# ---------------------------------------------------------------------------


class TestTuning(WakeBase):
    def test_tuning_file_falls_back_on_import_error(self):
        with patch("orbit.orbit.core.runtime_paths.orbit_data_dir",
                   side_effect=RuntimeError("no runtime")):
            self.assertEqual(ww._tuning_file(),
                             os.path.join("orbit_data", "wake_tuning.json"))

    def test_tuning_file_uses_runtime_dir(self):
        with patch("orbit.orbit.core.runtime_paths.orbit_data_dir",
                   return_value=self.dir):
            self.assertEqual(ww._tuning_file(),
                             str(self.dir / "wake_tuning.json"))

    def _write_tuning(self, cfg):
        p = self.dir / "wake_tuning.json"
        p.write_text(json.dumps(cfg), encoding="utf-8")
        return str(p)

    def test_load_tuning_applies_values(self):
        path = self._write_tuning({
            "oww_threshold": 0.66, "energy_threshold": 1234,
            "confidence_threshold": 0.88, "confirmation_min": 4,
        })
        with patch.object(ww, "_tuning_file", return_value=path):
            with self.assertLogs(ww.logger, level="INFO") as cm:
                ww._load_tuning()
        self.assertEqual(ww.OWW_THRESHOLD, 0.66)
        self.assertEqual(ww.ENERGY_THRESHOLD, 1234)
        self.assertEqual(ww.CONFIDENCE_THRESHOLD, 0.88)
        self.assertEqual(ww.CONFIRMATION_MIN, 4)
        self.assertTrue(any("Wake tuning loaded" in l for l in cm.output))

    def test_load_tuning_env_vars_win(self):
        path = self._write_tuning({"oww_threshold": 0.66,
                                   "energy_threshold": 1234})
        env = {"WAKE_WORD_THRESHOLD": "0.9", "WAKE_ENERGY_THRESHOLD": "77"}
        with patch.object(ww, "_tuning_file", return_value=path), \
             patch.dict(os.environ, env):
            ww._load_tuning()
        self.assertEqual(ww.OWW_THRESHOLD, 0.5)      # env set -> untouched
        self.assertEqual(ww.ENERGY_THRESHOLD, 500)  # env set -> untouched

    def test_load_tuning_missing_file_silent(self):
        with patch.object(ww, "_tuning_file",
                          return_value=str(self.dir / "nope.json")):
            ww._load_tuning()  # FileNotFoundError -> pass, no raise

    def test_load_tuning_corrupt_file_debug_logged(self):
        p = self.dir / "wake_tuning.json"
        p.write_text("{not json", encoding="utf-8")
        with patch.object(ww, "_tuning_file", return_value=str(p)), \
             self.assertLogs(ww.logger, level="DEBUG") as cm:
            ww._load_tuning()
        self.assertTrue(any("Wake tuning load failed" in l
                            for l in cm.output))

    def test_apply_tuning_updates_and_persists(self):
        with patch.object(ww, "_tuning_file",
                          return_value=str(self.dir / "t.json")):
            out = ww.apply_tuning(oww_threshold=0.61, energy_threshold=999,
                                  confidence_threshold=0.77,
                                  confirmation_min=2)
        self.assertEqual(out, {"oww_threshold": 0.61, "energy_threshold": 999,
                               "confidence_threshold": 0.77,
                               "confirmation_min": 2})
        saved = json.loads((self.dir / "t.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["oww_threshold"], 0.61)
        self.assertEqual(saved["confirmation_min"], 2)

    def test_apply_tuning_clamps_confirmation_min(self):
        with patch.object(ww, "_tuning_file",
                          return_value=str(self.dir / "t.json")):
            out = ww.apply_tuning(confirmation_min=0)
        self.assertEqual(out["confirmation_min"], 1)  # max(1, 0)
        with patch.object(ww, "_tuning_file",
                          return_value=str(self.dir / "t.json")):
            out = ww.apply_tuning(confirmation_min=-5)
        self.assertEqual(out["confirmation_min"], 1)

    def test_apply_tuning_persist_failure_still_applies(self):
        with patch("orbit.orbit.core.runtime_paths.atomic_write_json",
                   side_effect=OSError("read-only fs")), \
             patch.object(ww, "_tuning_file",
                          return_value=str(self.dir / "t.json")), \
             self.assertLogs(ww.logger, level="WARNING") as cm:
            out = ww.apply_tuning(oww_threshold=0.42)
        self.assertEqual(out["oww_threshold"], 0.42)  # in-memory applied
        self.assertTrue(any("persist failed" in l for l in cm.output))

    def test_apply_tuning_no_args_returns_current(self):
        before = ww.OWW_THRESHOLD
        with patch.object(ww, "_tuning_file",
                          return_value=str(self.dir / "t.json")):
            out = ww.apply_tuning()
        self.assertEqual(out["oww_threshold"], before)
        self.assertEqual(out["energy_threshold"], ww.ENERGY_THRESHOLD)


# ---------------------------------------------------------------------------
# _bandpass_filter (112-129) + _compute_energy (132-136)
# ---------------------------------------------------------------------------


class TestAudioHelpers(WakeBase):
    def test_too_few_samples_untouched(self):
        samples = np.array([1, 2, 3], dtype=np.int16)
        out = ww._bandpass_filter(samples, 16000)
        self.assertIs(out, samples)

    def test_in_band_signal_preserved_out_band_attenuated(self):
        rate = 16000
        t = np.arange(rate) / rate
        speech = (8000 * np.sin(2 * np.pi * 1000 * t)).astype(np.int16)
        hiss = (8000 * np.sin(2 * np.pi * 7000 * t)).astype(np.int16)
        out_speech = ww._bandpass_filter(speech, rate)
        out_hiss = ww._bandpass_filter(hiss, rate)
        self.assertEqual(out_speech.dtype, np.int16)
        # 1 kHz (in band) keeps its energy; 7 kHz (out of band) is cut to ~10%
        self.assertGreater(np.abs(out_speech).mean(),
                           np.abs(out_hiss).mean() * 5)

    def test_numpy_import_error_returns_raw(self):
        samples = np.array([1, 2, 3, 4], dtype=np.int16)
        with patch.dict(sys.modules, {"numpy": None}):
            out = ww._bandpass_filter(samples, 16000)
        self.assertIs(out, samples)

    def test_generic_error_returns_raw(self):
        # list has no .astype -> Exception -> raw return
        samples = [1, 2, 3, 4]
        out = ww._bandpass_filter(samples, 16000)
        self.assertIs(out, samples)

    def test_compute_energy_empty(self):
        self.assertEqual(ww._compute_energy([]), 0.0)
        self.assertEqual(ww._compute_energy(None), 0.0)

    def test_compute_energy_mean_abs(self):
        self.assertEqual(ww._compute_energy([3, -4, 0]), (3 + 4 + 0) / 3)


# ---------------------------------------------------------------------------
# _init_oww (156-166) + _calibrate_threshold (168-175) +
# _matches_wake_word (177-189) + confirmations (191-209)
# ---------------------------------------------------------------------------


class TestDetectionGuts(WakeBase):
    def test_oww_init_success(self):
        fake = types.ModuleType("openwakeword")
        model_obj = MagicMock(name="oww")
        fake.Model = MagicMock(return_value=model_obj)
        det = ww.WakeWordDetector.__new__(ww.WakeWordDetector)
        det._oww_model = None
        det._use_oww = False
        with patch.dict(sys.modules, {"openwakeword": fake}):
            with self.assertLogs(ww.logger, level="INFO") as cm:
                det._init_oww()
        self.assertTrue(det._use_oww)
        self.assertIs(det._oww_model, model_obj)
        self.assertTrue(any("OpenWakeWord initialized" in l for l in cm.output))

    def test_oww_init_import_error_falls_back(self):
        det = ww.WakeWordDetector.__new__(ww.WakeWordDetector)
        det._oww_model = None
        det._use_oww = False
        with patch.dict(sys.modules, {"openwakeword": None}):
            with self.assertLogs(ww.logger, level="INFO") as cm:
                det._init_oww()
        self.assertFalse(det._use_oww)
        self.assertTrue(any("using energy-based detection" in l
                            for l in cm.output))

    def test_oww_init_generic_failure_warns(self):
        fake = types.ModuleType("openwakeword")
        fake.Model = MagicMock(side_effect=RuntimeError("weights missing"))
        det = ww.WakeWordDetector.__new__(ww.WakeWordDetector)
        det._oww_model = None
        det._use_oww = False
        with patch.dict(sys.modules, {"openwakeword": fake}):
            with self.assertLogs(ww.logger, level="WARNING") as cm:
                det._init_oww()
        self.assertFalse(det._use_oww)
        self.assertTrue(any("OpenWakeWord init failed" in l for l in cm.output))

    def test_calibrate_adapts_only_below_threshold(self):
        det = self.make_detector()
        det._calibrated_threshold = 500
        det._baseline = 500
        det._calibrate_threshold(200)  # silence -> baseline drifts down
        self.assertLess(det._baseline, 500)
        self.assertGreaterEqual(det._calibrated_threshold, ww.ENERGY_THRESHOLD)
        # speech frame must NOT inflate threshold above itself
        keep = det._calibrated_threshold
        det._calibrate_threshold(99999)
        self.assertEqual(det._calibrated_threshold, keep)

    def test_matches_whole_word_only(self):
        det = self.make_detector()
        with patch.object(ww, "WAKE_WORD", "orbit"), \
             patch.object(ww, "WAKE_WORD_VARIANTS", []):
            self.assertTrue(det._matches_wake_word("Hey ORBIT!"))
            self.assertTrue(det._matches_wake_word("please orbit now"))
            self.assertFalse(det._matches_wake_word("orbital mechanics"))
            self.assertFalse(det._matches_wake_word("orbitz"))
            self.assertFalse(det._matches_wake_word("nothing here"))

    def test_matches_variants(self):
        det = self.make_detector()
        # .strip() only removes whitespace — trailing commas stay in the
        # variant, so feed whitespace-only padding here.
        with patch.object(ww, "WAKE_WORD", "orbit"), \
             patch.object(ww, "WAKE_WORD_VARIANTS", [" hey jarvis ", ""]):
            self.assertTrue(det._matches_wake_word("wake up hey jarvis"))
            self.assertFalse(det._matches_wake_word("jarvis is a name"))
            # empty/whitespace variant must be skipped, not crash
            self.assertFalse(det._matches_wake_word(""))

    def test_speech_confirmation_n_of_m(self):
        det = self.make_detector()
        # window not yet full -> False
        for _ in range(ww.CONFIRMATION_WINDOW - 1):
            self.assertFalse(det._check_confirmation(True))
        self.assertTrue(det._check_confirmation(True))  # full window, sum>=min

    def test_speech_confirmation_rejects_sparse(self):
        det = self.make_detector()
        results = []
        for i in range(ww.CONFIRMATION_WINDOW):
            results.append(det._check_confirmation(i == 0))  # 1 hit of 5
        self.assertFalse(results[-1])

    def test_match_confirmation_n_of_m(self):
        det = self.make_detector()
        for _ in range(ww.CONFIRMATION_WINDOW - 1):
            self.assertFalse(det._check_match_confirmation(True))
        self.assertTrue(det._check_match_confirmation(True))

    def test_match_confirmation_rejects_single_spurious(self):
        det = self.make_detector()
        results = []
        for i in range(ww.CONFIRMATION_WINDOW):
            results.append(det._check_match_confirmation(i == 2))
        self.assertFalse(results[-1])


# ---------------------------------------------------------------------------
# start/stop (211-230) + _init_vosk (232-247) + _listen_loop (249-253)
# ---------------------------------------------------------------------------


class TestLifecycle(WakeBase):
    def test_start_sets_up_and_second_start_noop(self):
        det = self.make_detector()
        det._energy_history.append(1.0)
        fake_thread = MagicMock(name="thread")
        with patch.object(ww.threading, "Thread", return_value=fake_thread) as T, \
             patch.object(det, "_init_vosk") as iv, \
             patch.object(ww.logger, "info"):
            det.start(lambda: None)
            det.start(lambda: None)  # already listening -> return
        self.assertTrue(det.is_listening)
        T.assert_called_once()
        iv.assert_called_once()
        self.assertIs(det._thread, fake_thread)
        fake_thread.start.assert_called_once()
        self.assertEqual(det._energy_history, [])  # cleared on start
        det.stop()

    def test_stop_joins_and_clears_vosk(self):
        det = self.make_detector()
        fake_thread = MagicMock(name="thread")
        det._thread = fake_thread
        det.is_listening = True
        det._vosk_recognizer = object()
        with patch.object(ww.logger, "info"):
            det.stop()
        self.assertFalse(det.is_listening)
        fake_thread.join.assert_called_once_with(timeout=2)
        self.assertIsNone(det._vosk_recognizer)

    def test_stop_without_thread(self):
        det = self.make_detector()
        det._thread = None
        with patch.object(ww.logger, "info"):
            det.stop()
        self.assertFalse(det.is_listening)

    def _config_patch(self, create_model=True):
        model_dir = self.dir / "vosk_model"
        model_dir.mkdir(exist_ok=True)
        if create_model:
            (model_dir / "model").write_bytes(b"x")
        return patch.multiple(
            "orbit.orbit.config",
            VOSK_MODEL_DIR=str(model_dir),
            VOSK_MODEL_NAME="model",
        )

    def test_init_vosk_missing_model_returns(self):
        det = self.make_detector()
        with self._config_patch(create_model=False):
            det._init_vosk()
        self.assertIsNone(det._vosk_recognizer)

    def test_init_vosk_success(self):
        det = self.make_detector()
        fake = types.ModuleType("vosk")
        fake.Model = MagicMock(return_value=MagicMock(name="vmodel"))
        rec = MagicMock(name="rec")
        fake.KaldiRecognizer = MagicMock(return_value=rec)
        with self._config_patch(), \
             patch.dict(sys.modules, {"vosk": fake}), \
             self.assertLogs(ww.logger, level="INFO") as cm:
            det._init_vosk()
        self.assertIs(det._vosk_recognizer, rec)
        self.assertTrue(any("Vosk recognizer initialized" in l
                            for l in cm.output))

    def test_init_vosk_failure_warns_and_clears(self):
        det = self.make_detector()
        fake = types.ModuleType("vosk")
        fake.Model = MagicMock(side_effect=RuntimeError("bad model"))
        with self._config_patch(), \
             patch.dict(sys.modules, {"vosk": fake}), \
             self.assertLogs(ww.logger, level="WARNING") as cm:
            det._init_vosk()
        self.assertIsNone(det._vosk_recognizer)
        self.assertTrue(any("Vosk init failed" in l for l in cm.output))

    def test_init_vosk_model_cached_reuses(self):
        det = self.make_detector()
        existing = MagicMock(name="cached")
        det._vosk_model = existing
        fake = types.ModuleType("vosk")
        fake.Model = MagicMock()
        fake.KaldiRecognizer = MagicMock(return_value=MagicMock())
        with self._config_patch(), patch.dict(sys.modules, {"vosk": fake}):
            det._init_vosk()
        fake.Model.assert_not_called()  # reused cached model

    def test_listen_loop_dispatches_oww(self):
        det = self.make_detector(_use_oww=True)
        with patch.object(det, "_oww_listen_loop") as oww, \
             patch.object(det, "_energy_listen_loop") as energy:
            det._listen_loop()
        oww.assert_called_once()
        energy.assert_not_called()

    def test_listen_loop_dispatches_energy(self):
        det = self.make_detector(_use_oww=False)
        with patch.object(det, "_oww_listen_loop") as oww, \
             patch.object(det, "_energy_listen_loop") as energy:
            det._listen_loop()
        energy.assert_called_once()
        oww.assert_not_called()


# ---------------------------------------------------------------------------
# _oww_listen_loop (255-275) + _energy_listen_loop (277-300)
# ---------------------------------------------------------------------------


class TestListenLoops(WakeBase):
    def test_oww_loop_detects_and_cools_down(self):
        det = self.make_detector(_use_oww=True)
        det._oww_model = MagicMock()
        det._oww_model.predict.return_value = {"hey_orbit": 0.9}
        det.is_listening = True
        det._callback = MagicMock()
        close = MagicMock()

        def read(n):
            det.is_listening = False  # single frame then stop
            return b"\x00\x00" * n

        with patch.object(ww, "_open_mic", return_value=(read, close)) as om, \
             patch.object(ww.time, "sleep") as sleep:
            det._oww_listen_loop()
        det._callback.assert_called_once()
        sleep.assert_called_once_with(ww.COOLDOWN_SEC)
        close.assert_called_once()
        om.assert_called_once_with(1280)

    def test_oww_loop_below_threshold_no_callback(self):
        det = self.make_detector(_use_oww=True)
        det._oww_model = MagicMock()
        det._oww_model.predict.return_value = {"hey_orbit": 0.1}
        det.is_listening = True
        det._callback = MagicMock()
        close = MagicMock()

        def read(n):
            det.is_listening = False
            return b"\x00\x00" * n

        with patch.object(ww, "_open_mic", return_value=(read, close)), \
             patch.object(ww.time, "sleep"):
            det._oww_listen_loop()
        det._callback.assert_not_called()
        close.assert_called_once()

    def test_oww_loop_error_falls_back_to_energy(self):
        det = self.make_detector(_use_oww=True)
        with patch.object(ww, "_open_mic",
                          side_effect=RuntimeError("mic busy")), \
             patch.object(det, "_energy_listen_loop") as energy, \
             self.assertLogs(ww.logger, level="ERROR") as cm:
            det._oww_listen_loop()
        energy.assert_called_once()
        self.assertTrue(any("OWW listen loop error" in l for l in cm.output))

    def _loud_frame(self, n=1024, freq=1000, rate=16000):
        t = np.arange(n) / rate
        vals = (8000 * np.sin(2 * np.pi * freq * t)).astype(np.int16)
        return struct.pack(f"<{n}h", *vals)

    def test_energy_loop_triggers_callback(self):
        det = self.make_detector()
        det.is_listening = True
        det._callback = MagicMock()
        close = MagicMock()
        frame = self._loud_frame()

        def read(n):
            det.is_listening = False
            return frame

        with patch.object(ww, "_open_mic", return_value=(read, close)) as om, \
             patch.object(det, "_process_frame", return_value=True) as pf, \
             patch.object(ww.time, "monotonic", return_value=100.0), \
             patch.object(ww.time, "sleep") as sleep:
            det._energy_listen_loop()
        det._callback.assert_called_once()
        sleep.assert_called_once_with(ww.COOLDOWN_SEC)
        close.assert_called_once()
        om.assert_called_once_with(1024)
        pf.assert_called_once()

    def test_energy_loop_cooldown_blocks_retrigger(self):
        det = self.make_detector()
        det.is_listening = True
        det._callback = MagicMock()
        close = MagicMock()
        frame = self._loud_frame()

        def read(n):
            det.is_listening = False
            return frame

        # monotonic 0.5 -> 0.5 - 0 < COOLDOWN -> trigger suppressed
        with patch.object(ww, "_open_mic", return_value=(read, close)), \
             patch.object(det, "_process_frame", return_value=True), \
             patch.object(ww.time, "monotonic", return_value=0.5), \
             patch.object(ww.time, "sleep"):
            det._energy_listen_loop()
        det._callback.assert_not_called()

    def test_energy_loop_error_logged(self):
        det = self.make_detector()
        with patch.object(ww, "_open_mic",
                          side_effect=RuntimeError("no device")), \
             self.assertLogs(ww.logger, level="ERROR") as cm:
            det._energy_listen_loop()
        self.assertTrue(any("Energy listen loop error" in l
                            for l in cm.output))


# ---------------------------------------------------------------------------
# _streaming_stt (302-320) + _process_frame (322-349) + _quick_stt (351-368)
# ---------------------------------------------------------------------------


class TestSttAndFrame(WakeBase):
    def test_streaming_stt_none_recognizer_stays_none(self):
        det = self.make_detector(_vosk_recognizer=None)
        with patch.object(det, "_init_vosk",
                          side_effect=lambda: None):  # still None after init
            self.assertIsNone(det._streaming_stt(b"\x00\x00"))

    def test_streaming_stt_final_result(self):
        rec = MagicMock()
        rec.AcceptWaveform.return_value = True
        rec.FinalResult.return_value = json.dumps({"text": "hey orbit"})
        det = self.make_detector(_vosk_recognizer=rec)
        self.assertEqual(det._streaming_stt(b"\x00\x00"), "hey orbit")

    def test_streaming_stt_partial_result(self):
        rec = MagicMock()
        rec.AcceptWaveform.return_value = False
        rec.PartialResult.return_value = json.dumps({"partial": "hey or"})
        det = self.make_detector(_vosk_recognizer=rec)
        self.assertEqual(det._streaming_stt(b"\x00\x00"), "hey or")

    def test_streaming_stt_empty_text(self):
        rec = MagicMock()
        rec.AcceptWaveform.return_value = True
        rec.FinalResult.return_value = json.dumps({})
        det = self.make_detector(_vosk_recognizer=rec)
        self.assertEqual(det._streaming_stt(b"\x00\x00"), "")

    def test_streaming_stt_exception_returns_none(self):
        rec = MagicMock()
        rec.AcceptWaveform.side_effect = RuntimeError("kaldi died")
        det = self.make_detector(_vosk_recognizer=rec)
        self.assertIsNone(det._streaming_stt(b"\x00\x00"))

    def _fill_speech(self, det, n=None):
        for _ in range(n or ww.CONFIRMATION_WINDOW):
            det._process_frame(1000.0, b"\x00\x00")

    def test_process_frame_not_speech_short_circuits(self):
        det = self.make_detector()
        det._calibrated_threshold = 500
        det._baseline = 500
        with patch.object(det, "_streaming_stt") as stt:
            self.assertFalse(det._process_frame(10.0, b"\x00\x00"))
        stt.assert_not_called()  # no STT call for silence

    def test_process_frame_full_detection_path(self):
        det = self.make_detector()
        det._calibrated_threshold = 500
        det._baseline = 500
        with patch.object(det, "_streaming_stt",
                          return_value="hey orbit please"):
            results = [det._process_frame(1000.0, b"\x00\x00")
                       for _ in range(ww.CONFIRMATION_WINDOW)]
        self.assertFalse(any(results[:-1]))  # window fills first
        self.assertTrue(results[-1])         # 5th frame confirms
        # histories cleared on accept
        self.assertEqual(len(det._speech_history), 0)
        self.assertEqual(len(det._match_history), 0)

    def test_process_frame_match_not_yet_confirmed(self):
        det = self.make_detector()
        det._calibrated_threshold = 500
        det._baseline = 500
        with patch.object(det, "_streaming_stt",
                          return_value="orbit"):
            # only 2 matches -> match confirmation incomplete
            self.assertFalse(det._process_frame(1000.0, b"\x00\x00"))
            self.assertFalse(det._process_frame(1000.0, b"\x00\x00"))

    def test_process_frame_no_match_returns_false(self):
        det = self.make_detector()
        det._calibrated_threshold = 500
        det._baseline = 500
        with patch.object(det, "_streaming_stt", return_value="hello world"):
            for _ in range(ww.CONFIRMATION_WINDOW):
                self.assertFalse(det._process_frame(1000.0, b"\x00\x00"))

    def test_process_frame_confidence_gate(self):
        det = self.make_detector()
        det._calibrated_threshold = 500
        det._baseline = 500
        # confidence = min(1, energy/threshold) == 1.0 when energy>threshold;
        # raise the gate above 1.0 to exercise the reject branch.
        with patch.object(det, "_streaming_stt", return_value="orbit"), \
             patch.object(ww, "CONFIDENCE_THRESHOLD", 1.5):
            results = [det._process_frame(1000.0, b"\x00\x00")
                       for _ in range(ww.CONFIRMATION_WINDOW)]
        self.assertFalse(any(results))

    def test_quick_stt_missing_model_dir(self):
        det = self.make_detector(_vosk_model=None)
        with patch.multiple("orbit.orbit.config",
                            VOSK_MODEL_DIR=str(self.dir / "missing"),
                            VOSK_MODEL_NAME="m"):
            self.assertIsNone(det._quick_stt(b"\x00\x00"))

    def test_quick_stt_vosk_unavailable(self):
        det = self.make_detector(_vosk_model=None)
        with patch.multiple("orbit.orbit.config",
                            VOSK_MODEL_DIR=str(self.dir),
                            VOSK_MODEL_NAME="m"), \
             patch.dict(sys.modules, {"vosk": None}):
            self.assertIsNone(det._quick_stt(b"\x00\x00"))

    def test_quick_stt_success(self):
        det = self.make_detector(_vosk_model=None)
        model_dir = self.dir / "vm"
        model_dir.mkdir()
        (model_dir / "m").write_bytes(b"x")
        fake = types.ModuleType("vosk")
        fake.Model = MagicMock(return_value=MagicMock(name="m"))
        rec = MagicMock()
        rec.AcceptWaveform.return_value = True
        rec.FinalResult.return_value = json.dumps({"text": "orbit"})
        fake.KaldiRecognizer = MagicMock(return_value=rec)
        with patch.multiple("orbit.orbit.config",
                            VOSK_MODEL_DIR=str(model_dir),
                            VOSK_MODEL_NAME="m"), \
             patch.dict(sys.modules, {"vosk": fake}):
            self.assertEqual(det._quick_stt(b"\x00\x00"), "orbit")
        fake.Model.assert_called_once()

    def test_quick_stt_malformed_json_returns_none(self):
        det = self.make_detector(_vosk_model=MagicMock())
        model_dir = self.dir / "vm2"
        model_dir.mkdir()
        (model_dir / "m").write_bytes(b"x")
        fake = types.ModuleType("vosk")
        rec = MagicMock()
        rec.AcceptWaveform.return_value = True
        rec.FinalResult.return_value = "not-json"
        fake.KaldiRecognizer = MagicMock(return_value=rec)
        with patch.multiple("orbit.orbit.config",
                            VOSK_MODEL_DIR=str(model_dir),
                            VOSK_MODEL_NAME="m"), \
             patch.dict(sys.modules, {"vosk": fake}):
            self.assertIsNone(det._quick_stt(b"\x00\x00"))


# ---------------------------------------------------------------------------
# is_available / get_info (370-386) + _check_pyaudio/_check_sounddevice
# ---------------------------------------------------------------------------


class TestAvailability(WakeBase):
    def test_is_available_via_oww(self):
        det = self.make_detector(_use_oww=True)
        with patch.object(ww, "_check_pyaudio", return_value=False), \
             patch.object(ww, "_check_sounddevice", return_value=False):
            self.assertTrue(det.is_available())

    def test_is_available_via_audio_backends(self):
        det = self.make_detector(_use_oww=False)
        with patch.object(ww, "_check_pyaudio", return_value=True), \
             patch.object(ww, "_check_sounddevice", return_value=False):
            self.assertTrue(det.is_available())
        with patch.object(ww, "_check_pyaudio", return_value=False), \
             patch.object(ww, "_check_sounddevice", return_value=True):
            self.assertTrue(det.is_available())

    def test_is_unavailable_with_nothing(self):
        det = self.make_detector(_use_oww=False)
        with patch.object(ww, "_check_pyaudio", return_value=False), \
             patch.object(ww, "_check_sounddevice", return_value=False):
            self.assertFalse(det.is_available())

    def test_get_info_shape(self):
        det = self.make_detector(_use_oww=False)
        det.is_listening = True
        with patch.object(det, "is_available", return_value=True):
            info = det.get_info()
        self.assertTrue(info["available"])
        self.assertEqual(info["engine"], "energy")
        self.assertEqual(info["wake_word"], ww.WAKE_WORD)
        self.assertIn("oww_threshold", info)
        self.assertIn("confirmation_window", info)
        self.assertTrue(info["listening"])

    def test_check_pyaudio(self):
        with patch.dict(sys.modules, {"pyaudio": MagicMock()}):
            self.assertTrue(ww._check_pyaudio())
        with patch.dict(sys.modules, {"pyaudio": None}):
            self.assertFalse(ww._check_pyaudio())

    def test_check_sounddevice(self):
        with patch.dict(sys.modules, {"sounddevice": MagicMock()}):
            self.assertTrue(ww._check_sounddevice())
        with patch.dict(sys.modules, {"sounddevice": None}):
            self.assertFalse(ww._check_sounddevice())

    def test_check_sounddevice_generic_exception(self):
        # `except Exception` branch (line 403): a NON-ImportError during import
        # must still yield False (e.g. portaudio raising at import time).
        real_import = __import__

        def fake_import(name, *a, **k):
            if name == "sounddevice":
                raise RuntimeError("portaudio exploded")
            return real_import(name, *a, **k)

        with patch("builtins.__import__", side_effect=fake_import):
            self.assertFalse(ww._check_sounddevice())


# ---------------------------------------------------------------------------
# _open_mic (407-463)
# ---------------------------------------------------------------------------


class TestOpenMic(unittest.TestCase):
    def _fake_pyaudio(self, raise_on_read=False):
        mod = types.ModuleType("pyaudio")
        mod.paInt16 = 8

        class Stream:
            def __init__(self):
                self.stopped = False
                self.closed = False
                self.terminated = False

            def read(self, n, exception_on_overflow=False):
                if raise_on_read:
                    raise RuntimeError("overflow")
                return b"\x00\x00" * n

            def stop_stream(self):
                self.stopped = True

            def close(self):
                self.closed = True

        class Pa:
            def __init__(self):
                self.stream = Stream()

            def open(self, **kw):
                self.kw = kw
                return self.stream

            def terminate(self):
                self.stream.terminated = True

        pa = Pa()
        mod.PyAudio = lambda: pa
        return mod, pa

    def test_pyaudio_backend_read_and_close(self):
        mod, pa = self._fake_pyaudio()
        with patch.dict(sys.modules, {"pyaudio": mod}):
            read, close = ww._open_mic(512)
            data = read(16)
            close()
        self.assertEqual(len(data), 32)  # 16 int16 frames
        self.assertTrue(pa.stream.stopped)
        self.assertTrue(pa.stream.closed)
        self.assertTrue(pa.stream.terminated)

    def test_pyaudio_close_swallows_errors(self):
        mod, pa = self._fake_pyaudio()

        class BadStream:
            def read(self, n, exception_on_overflow=False):
                return b"\x00\x00" * n

            def stop_stream(self):
                raise RuntimeError("already stopped")

        pa.stream = BadStream()
        with patch.dict(sys.modules, {"pyaudio": mod}):
            read, close = ww._open_mic(512)
            close()  # must not raise

    def test_pyaudio_failure_falls_back_to_sounddevice(self):
        sd = types.ModuleType("sounddevice")

        class RawStream:
            def __init__(self, **kw):
                self.kw = kw
                self.started = False
                self.stopped = False
                self.closed = False

            def start(self):
                self.started = True

            def read(self, n):
                return b"\x00\x00" * n

            def stop(self):
                self.stopped = True

            def close(self):
                self.closed = True

        holder = {}

        def make_raw(**kw):
            s = RawStream(**kw)
            holder["s"] = s
            return s

        sd.RawInputStream = make_raw
        with patch.dict(sys.modules, {"pyaudio": None, "sounddevice": sd}):
            read, close = ww._open_mic(256)
            data = read(8)
            close()
        self.assertEqual(len(data), 16)
        self.assertTrue(holder["s"].started)
        self.assertTrue(holder["s"].stopped)
        self.assertTrue(holder["s"].closed)

    def test_sounddevice_close_swallows_errors(self):
        sd = types.ModuleType("sounddevice")

        class BadStream:
            def start(self):
                pass

            def read(self, n):
                return b"\x00\x00" * n

            def stop(self):
                raise RuntimeError("nope")

        sd.RawInputStream = lambda **kw: BadStream()
        with patch.dict(sys.modules, {"pyaudio": None, "sounddevice": sd}):
            read, close = ww._open_mic(256)
            close()  # must not raise

    def test_neither_backend_raises(self):
        with patch.dict(sys.modules, {"pyaudio": None, "sounddevice": None}):
            with self.assertRaises(ImportError):
                ww._open_mic(256)


# ---------------------------------------------------------------------------
# get_wake_word_detector singleton (466-473)
# ---------------------------------------------------------------------------


class TestSingleton(WakeBase):
    def test_get_wake_word_detector_cached(self):
        sentinel = object()
        with patch.object(ww, "_detector", None), \
             patch.object(ww, "WakeWordDetector",
                          return_value=sentinel) as ctor:
            a = ww.get_wake_word_detector()
            b = ww.get_wake_word_detector()
        self.assertIs(a, sentinel)
        self.assertIs(a, b)
        ctor.assert_called_once()


# ---------------------------------------------------------------------------
# generate_wake_word_data (479-602) + get_training_data_info (605-633)
# ---------------------------------------------------------------------------


class TestTrainingData(WakeBase):
    def test_generates_positive_negative_and_metadata(self):
        out = ww.generate_wake_word_data(
            wake_phrase="hey orbit", output_dir=str(self.dir),
            num_samples=4, sample_rate=8000, duration_sec=0.1,
        )
        pos = list((self.dir / "positive").glob("*.wav"))
        neg = list((self.dir / "negative").glob("*.wav"))
        self.assertEqual(len(pos), 2)  # 4 // 2
        self.assertEqual(len(neg), 2)
        self.assertEqual(out["positive_samples"], 2)
        self.assertEqual(out["negative_samples"], 2)
        self.assertEqual(out["wake_phrase"], "hey orbit")
        meta = json.loads((self.dir / "metadata.json").read_text("utf-8"))
        self.assertEqual(meta["sample_rate"], 8000)
        # WAVs are real and readable
        import wave as _wave
        with _wave.open(str(pos[0]), "rb") as wf:
            self.assertEqual(wf.getframerate(), 8000)

    def test_default_output_dir_uses_runtime_paths(self):
        with patch("orbit.orbit.core.runtime_paths.orbit_data_dir",
                   return_value=self.dir):
            out = ww.generate_wake_word_data(num_samples=2,
                                             sample_rate=8000,
                                             duration_sec=0.1)
        self.assertEqual(out["output_dir"], str(self.dir / "wake_training"))
        self.assertTrue((self.dir / "wake_training" / "metadata.json")
                        .exists())

    def test_save_failure_counts_zero_and_logs(self):
        # per-sample except branches (569-570, 581-582): make `random`
        # (imported inside the function) explode on both loops' first call.
        import types as _t
        fake_rng = _t.ModuleType("random")
        fake_rng.uniform = MagicMock(side_effect=RuntimeError("rng dead"))
        fake_rng.choice = MagicMock(side_effect=RuntimeError("rng dead"))
        with patch.dict(sys.modules, {"random": fake_rng}), \
             self.assertLogs(ww.logger, level="DEBUG") as cm:
            out = ww.generate_wake_word_data(output_dir=str(self.dir),
                                             num_samples=4,
                                             sample_rate=8000,
                                             duration_sec=0.1)
        self.assertEqual(out["positive_samples"], 0)
        self.assertEqual(out["negative_samples"], 0)
        logs = "\n".join(cm.output)
        self.assertIn("Failed to generate positive sample", logs)
        self.assertIn("Failed to generate negative sample", logs)
        # metadata still written
        self.assertTrue((self.dir / "metadata.json").exists())

    def test_num_samples_floor_division(self):
        out = ww.generate_wake_word_data(output_dir=str(self.dir / "odd"),
                                         num_samples=3, sample_rate=8000,
                                         duration_sec=0.1)
        self.assertEqual(out["positive_samples"], 1)  # 3 // 2
        self.assertEqual(out["negative_samples"], 1)

    def _write_meta(self, meta, raw=None):
        out_path = self.dir / "wake_training"
        out_path.mkdir(exist_ok=True)
        content = raw if raw is not None else json.dumps(meta)
        (out_path / "metadata.json").write_text(content, encoding="utf-8")
        return out_path

    def test_info_missing_metadata(self):
        with patch("orbit.orbit.core.runtime_paths.orbit_data_dir",
                   return_value=self.dir):
            out = ww.get_training_data_info()
        self.assertFalse(out["exists"])
        self.assertIn("No training data", out["message"])

    def test_info_counts_actual_files(self):
        out_path = self._write_meta({
            "wake_phrase": "orbit", "sample_rate": 16000,
            "duration_sec": 2.0, "created": "2026-01-01T00:00:00",
        })
        (out_path / "positive").mkdir()
        (out_path / "negative").mkdir()
        (out_path / "positive" / "a.wav").write_bytes(b"x")
        (out_path / "positive" / "b.wav").write_bytes(b"x")
        (out_path / "negative" / "c.wav").write_bytes(b"x")
        with patch("orbit.orbit.core.runtime_paths.orbit_data_dir",
                   return_value=self.dir):
            out = ww.get_training_data_info()
        self.assertTrue(out["exists"])
        self.assertEqual(out["positive_samples"], 2)
        self.assertEqual(out["negative_samples"], 1)
        self.assertEqual(out["wake_phrase"], "orbit")
        self.assertEqual(out["sample_rate"], 16000)

    def test_info_non_dict_metadata_returns_empty(self):
        self._write_meta(None, raw="[]")
        with patch("orbit.orbit.core.runtime_paths.orbit_data_dir",
                   return_value=self.dir):
            out = ww.get_training_data_info()
        self.assertEqual(out, {})

    def test_info_corrupted_metadata(self):
        self._write_meta(None, raw="{broken")
        with patch("orbit.orbit.core.runtime_paths.orbit_data_dir",
                   return_value=self.dir):
            out = ww.get_training_data_info()
        self.assertFalse(out["exists"])
        self.assertEqual(out["message"], "Metadata corrupted")

    def test_info_without_subdirs_counts_zero(self):
        self._write_meta({"wake_phrase": "orbit"})
        with patch("orbit.orbit.core.runtime_paths.orbit_data_dir",
                   return_value=self.dir):
            out = ww.get_training_data_info()
        self.assertTrue(out["exists"])
        self.assertEqual(out["positive_samples"], 0)
        self.assertEqual(out["negative_samples"], 0)


# ---------------------------------------------------------------------------
# Integration: energy loop + real _process_frame pipeline
# ---------------------------------------------------------------------------


class TestEnergyLoopIntegration(WakeBase):
    def test_five_confirmed_frames_trigger_callback(self):
        det = self.make_detector()
        det._calibrated_threshold = ww.ENERGY_THRESHOLD
        det._baseline = ww.ENERGY_THRESHOLD
        det.is_listening = True
        det._callback = MagicMock()
        close = MagicMock()
        frames = {"n": 0}
        rate, n = 16000, 1024
        t = np.arange(n) / rate
        loud = struct.pack(f"<{n}h",
                           *((8000 * np.sin(2 * np.pi * 1000 * t))
                             .astype(np.int16)))

        def read(size):
            frames["n"] += 1
            if frames["n"] >= ww.CONFIRMATION_WINDOW:
                det.is_listening = False
            return loud

        with patch.object(ww, "_open_mic", return_value=(read, close)), \
             patch.object(det, "_streaming_stt",
                          return_value="hey orbit"), \
             patch.object(ww.time, "monotonic", return_value=100.0), \
             patch.object(ww.time, "sleep"):
            det._energy_listen_loop()
        self.assertEqual(frames["n"], ww.CONFIRMATION_WINDOW)
        det._callback.assert_called_once()


if __name__ == "__main__":
    unittest.main()
