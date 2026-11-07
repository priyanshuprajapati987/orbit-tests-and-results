"""Unit tests for orbit/orbit/core/meeting_transcriber.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.meeting_transcriber import MeetingTranscriber, get_meeting_transcriber


class TestMeetingTranscriber(unittest.TestCase):
    def setUp(self):
        self.t = MeetingTranscriber()

    def test_no_whisper(self):
        with patch.dict(sys.modules, {"whisper": None}):
            r = self.t.transcribe("audio.wav")
        self.assertIn("error", r)
        self.assertEqual(r["text"], "")

    def test_whisper_transcribe(self):
        whisper_mod = MagicMock()
        model = MagicMock()
        model.transcribe.return_value = {"text": "hello world", "segments": [{"id": 1}]}
        whisper_mod.load_model.return_value = model
        with patch.dict(sys.modules, {"whisper": whisper_mod}):
            t = MeetingTranscriber()
            r = t.transcribe("audio.wav")
        self.assertEqual(r["text"], "hello world")
        self.assertEqual(len(r["segments"]), 1)

    def test_whisper_transcribe_error(self):
        whisper_mod = MagicMock()
        model = MagicMock()
        model.transcribe.side_effect = RuntimeError("bad audio")
        whisper_mod.load_model.return_value = model
        with patch.dict(sys.modules, {"whisper": whisper_mod}):
            t = MeetingTranscriber()
            r = t.transcribe("audio.wav")
        self.assertIn("error", r)
        self.assertEqual(r["text"], "")

    def test_singleton(self):
        a = get_meeting_transcriber()
        b = get_meeting_transcriber()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
