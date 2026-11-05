import os
import pathlib
import tempfile
import unittest
import unittest.mock
import wave

import numpy as np

from orbit.orbit import xtts


def make_wav(path, seconds, amplitude, noise=0.0, rate=22050):
    n = int(seconds * rate)
    t = np.arange(n) / rate
    sig = amplitude * np.sin(2 * np.pi * 220 * t)
    if noise:
        sig = sig + noise * np.random.randn(n)
    sig = np.clip(sig, -1, 1)
    data = (sig * 32767).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(data.tobytes())


class TestVoiceCloneSelection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.good = os.path.join(self.tmp, "good.wav")
        make_wav(self.good, 6.0, 0.3, noise=0.001)
        # Noisier than `good` so it deterministically ranks below it (SNR metric).
        self.good2 = os.path.join(self.tmp, "good2.wav")
        make_wav(self.good2, 6.0, 0.3, noise=0.2)
        # Too short -> dropped by the duration gate regardless of quality formula.
        self.short = os.path.join(self.tmp, "short.wav")
        make_wav(self.short, 0.5, 0.3)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- _select_best_references gating ---

    def test_select_drops_below_threshold(self):
        sel = xtts._select_best_references([self.good, self.short], max_refs=3)
        self.assertEqual([s["path"] for s in sel], [self.good])

    def test_select_empty_when_all_bad(self):
        self.assertEqual(xtts._select_best_references([self.short], max_refs=3), [])

    def test_select_sorts_by_quality(self):
        sel = xtts._select_best_references([self.good2, self.good], max_refs=3)
        # Both samples must survive the gate, the clean one must rank first,
        # and the result must be sorted strictly best-first.
        self.assertEqual(len(sel), 2)
        self.assertEqual(sel[0]["path"], self.good)
        qs = [s["quality"] for s in sel]
        self.assertEqual(qs, sorted(qs, reverse=True))

    def test_select_caps_at_max_refs(self):
        refs = [self.good, self.good2, self.good, self.good2]
        sel = xtts._select_best_references(refs, max_refs=1)
        self.assertEqual(len(sel), 1)

    def test_select_skips_missing_files(self):
        sel = xtts._select_best_references(
            [self.good, "does_not_exist.wav"], max_refs=3
        )
        self.assertEqual([s["path"] for s in sel], [self.good])

    # --- clone_from_text integration (model unavailable -> quality gate first) ---

    def _make_cloner(self):
        with unittest.mock.patch.object(
            xtts.VoiceCloner, "_init_model", lambda self: None
        ):
            return xtts.VoiceCloner()

    def test_clone_from_text_rejects_all_bad(self):
        bad_dir = os.path.join(self.tmp, "bad")
        os.makedirs(bad_dir, exist_ok=True)
        import shutil

        shutil.copy(self.short, os.path.join(bad_dir, "short.wav"))
        with unittest.mock.patch.object(
            xtts, "CLONING_SAMPLES_DIR", pathlib.Path(bad_dir)
        ):
            vc = self._make_cloner()
            res = vc.clone_from_text("hello")
            self.assertFalse(res["success"])
            self.assertIn("No usable", res["error"])

    def test_clone_from_text_passes_gate_then_model_unavailable(self):
        with unittest.mock.patch.object(
            xtts, "CLONING_SAMPLES_DIR", pathlib.Path(self.tmp)
        ):
            vc = self._make_cloner()
            res = vc.clone_from_text("hello")
            self.assertFalse(res["success"])
            self.assertIn("not available", res["error"].lower())


if __name__ == "__main__":
    unittest.main()
