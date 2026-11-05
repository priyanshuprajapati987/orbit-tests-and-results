"""Tests for ORBIT wake-word detection (accuracy + confirmation pipeline).

These exercise the detection logic without needing a microphone: the audio
frames are synthetic and STT is stubbed, so the test verifies the matching /
confirmation / confidence gating end-to-end.
"""

import unittest
from collections import deque
from unittest import mock

from orbit.orbit import wake_word


class TestWakeWordMatching(unittest.TestCase):
    def setUp(self):
        self.d = wake_word.WakeWordDetector()

    def test_matches_default_word(self):
        self.assertTrue(self.d._matches_wake_word("hey orbit"))
        self.assertTrue(self.d._matches_wake_word("ORBIT please listen"))
        self.assertFalse(self.d._matches_wake_word("hello world"))

    def test_matches_variants(self):
        wake_word.WAKE_WORD_VARIANTS = ["hey jarvis", "computer"]
        try:
            self.assertTrue(self.d._matches_wake_word("hey jarvis"))
            self.assertTrue(self.d._matches_wake_word("computer on"))
            self.assertFalse(self.d._matches_wake_word("television off"))
        finally:
            wake_word.WAKE_WORD_VARIANTS = []

    def test_no_match_substring_false_accept(self):
        # "orbital"/"orbitz" must NOT trigger the "orbit" wake word.
        self.assertFalse(self.d._matches_wake_word("orbital station"))
        self.assertFalse(self.d._matches_wake_word("please orbitz me"))
        # But a real whole-word "orbit" still matches.
        self.assertTrue(self.d._matches_wake_word("hey orbit"))
        self.assertTrue(self.d._matches_wake_word("ORBIT please listen"))


class TestConfirmation(unittest.TestCase):
    def setUp(self):
        self.d = wake_word.WakeWordDetector()

    def test_confirmation_requires_min_frames(self):
        self.d._speech_history = deque([1, 1, 0, 1, 0], maxlen=5)
        self.assertTrue(self.d._check_confirmation(True))  # -> sum 4 >= 3
        self.d._speech_history = deque([0, 0, 0, 0, 0], maxlen=5)
        self.assertFalse(self.d._check_confirmation(True))  # -> sum 1 < 3


class TestProcessFrame(unittest.TestCase):
    def setUp(self):
        self.d = wake_word.WakeWordDetector()
        self.d._vosk_recognizer = None  # force stubbed STT path

    def _feed(self, n, energy=2000, text="hey orbit"):
        """Feed n high-energy frames with stubbed STT returning `text`."""
        with mock.patch.object(self.d, "_streaming_stt", return_value=text):
            last = False
            for _ in range(n):
                last = self.d._process_frame(energy, b"\x00" * 1024)
            return last

    def test_detects_after_confirmation(self):
        # Calibration detects speech ONSET (energy above the silence-anchored
        # baseline). Feed a silence baseline, then a rising-energy speech burst
        # and assert the wake word is detected at least once (on success the
        # speech-history is cleared, so it can re-confirm within the same burst).
        with mock.patch.object(self.d, "_streaming_stt", return_value=""):
            for _ in range(3):
                self.d._process_frame(10, b"\x00" * 1024)  # baseline -> low threshold
        detected = False
        with mock.patch.object(self.d, "_streaming_stt", return_value="hey orbit"):
            for i in range(10):
                if self.d._process_frame(1000 + i * 1000, b"\x00" * 1024):
                    detected = True
                    break
        self.assertTrue(detected)  # confirmed + match -> detected

    def test_no_detect_when_text_mismatches(self):
        self.assertFalse(self._feed(5, text="hello there"))

    def test_no_detect_when_stt_unavailable(self):
        self.assertFalse(self._feed(5, text=None))

    def test_single_spurious_match_does_not_trigger(self):
        # High-energy speech with only ONE frame containing the wake word must
        # NOT trigger: match-level N-of-M confirmation is required, so a single
        # spurious 'orbit' (e.g. from background TV) is rejected.
        self.d._calibrate_threshold(10)  # establish a low silence baseline
        energies = [2000] * 10
        texts = ["hello there"] * 10
        texts[5] = "hey orbit"  # single spurious match among speech
        detected = False
        for e, t in zip(energies, texts):
            with mock.patch.object(self.d, "_streaming_stt", return_value=t):
                if self.d._process_frame(e, b"\x00" * 1024):
                    detected = True
                    break
        self.assertFalse(detected)

    def test_genuine_burst_detects(self):
        # A real wake-word utterance spanning several frames MUST trigger.
        self.d._calibrate_threshold(10)
        detected = False
        with mock.patch.object(self.d, "_streaming_stt", return_value="hey orbit"):
            for e in [2000, 2000, 2000, 2000, 2000]:
                if self.d._process_frame(e, b"\x00" * 1024):
                    detected = True
                    break
        self.assertTrue(detected)

    def test_silence_relaxes_threshold(self):
        # Low-energy frames must not trigger and should not raise.
        for _ in range(3):
            self.assertFalse(self.d._process_frame(10, b"\x00" * 1024))

    def test_get_info_shape(self):
        info = self.d.get_info()
        self.assertIn("engine", info)
        self.assertIn("listening", info)
        self.assertIn("confidence_threshold", info)


class TestMatchConfirmation(unittest.TestCase):
    def setUp(self):
        self.d = wake_word.WakeWordDetector()

    def test_match_confirmation_requires_min_frames(self):
        self.d._match_history = deque([1, 1, 0, 1, 0], maxlen=5)
        self.assertTrue(self.d._check_match_confirmation(True))  # sum 4 >= 3
        self.d._match_history = deque([1, 0, 0, 0, 0], maxlen=5)
        self.assertFalse(self.d._check_match_confirmation(True))  # sum 1 < 3


if __name__ == "__main__":
    unittest.main()
