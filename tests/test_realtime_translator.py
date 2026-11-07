"""Unit tests for orbit/orbit/core/realtime_translator.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.realtime_translator import RealtimeTranslator, get_translator, SUPPORTED


class TestRealtimeTranslator(unittest.TestCase):
    def setUp(self):
        self.t = RealtimeTranslator()

    def test_supported_languages(self):
        self.assertEqual(self.t.supported_languages(), SUPPORTED)
        self.assertIn("hi", self.t.supported_languages())

    def test_translate_success(self):
        resp = MagicMock()
        resp.ok = True
        resp.json.return_value = {"translatedText": "Hola"}
        with patch("requests.post", return_value=resp) as post:
            r = self.t.translate("hello", "es")
        self.assertEqual(r["translated"], "Hola")
        self.assertEqual(r["target"], "es")
        post.assert_called_once()

    def test_translate_failure_status(self):
        resp = MagicMock()
        resp.ok = False
        with patch("requests.post", return_value=resp):
            r = self.t.translate("hello", "es")
        self.assertEqual(r["translated"], "hello")
        self.assertIn("error", r)

    def test_translate_exception(self):
        with patch("requests.post", side_effect=RuntimeError("net down")):
            r = self.t.translate("hello", "fr")
        self.assertEqual(r["translated"], "hello")
        self.assertIn("error", r)

    def test_translate_custom_source(self):
        resp = MagicMock()
        resp.ok = True
        resp.json.return_value = {"translatedText": "bonjour"}
        with patch("requests.post", return_value=resp) as post:
            r = self.t.translate("hello", "fr", source="en")
        self.assertEqual(r["translated"], "bonjour")
        self.assertEqual(post.call_args.kwargs["json"]["source"], "en")

    def test_singleton(self):
        a = get_translator()
        b = get_translator()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
