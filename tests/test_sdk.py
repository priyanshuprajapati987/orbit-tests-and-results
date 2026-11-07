"""Unit tests for orbit/orbit/sdk.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.sdk import OrbitClient


class TestOrbitClient(unittest.TestCase):
    def test_init_defaults(self):
        c = OrbitClient()
        self.assertEqual(c.base_url, "http://127.0.0.1:5000")
        self.assertEqual(c.headers, {})

    def test_init_strips_trailing_slash(self):
        c = OrbitClient(base_url="http://x:8000/")
        self.assertEqual(c.base_url, "http://x:8000")

    def test_init_with_api_key(self):
        c = OrbitClient(api_key="secret")
        self.assertEqual(c.headers, {"X-API-Key": "secret"})

    def test_health(self):
        resp = MagicMock()
        resp.json.return_value = {"status": "ok"}
        with patch("orbit.sdk.requests.get", return_value=resp) as get:
            c = OrbitClient()
            r = c.health()
        self.assertEqual(r, {"status": "ok"})
        get.assert_called_once_with("http://127.0.0.1:5000/api/health", headers={})

    def test_chat_without_session(self):
        resp = MagicMock()
        resp.json.return_value = {"reply": "hi"}
        with patch("orbit.sdk.requests.post", return_value=resp) as post:
            c = OrbitClient()
            r = c.chat("hello")
        self.assertEqual(r, {"reply": "hi"})
        post.assert_called_once_with("http://127.0.0.1:5000/api/chat", json={"message": "hello"}, headers={})

    def test_chat_with_session(self):
        resp = MagicMock()
        resp.json.return_value = {"reply": "hi"}
        with patch("orbit.sdk.requests.post", return_value=resp) as post:
            c = OrbitClient()
            r = c.chat("hello", session_id="s1")
        post.assert_called_once_with("http://127.0.0.1:5000/api/chat", json={"message": "hello", "session_id": "s1"}, headers={})

    def test_docs(self):
        resp = MagicMock()
        resp.json.return_value = {"title": "docs"}
        with patch("orbit.sdk.requests.get", return_value=resp) as get:
            c = OrbitClient()
            r = c.docs()
        self.assertEqual(r, {"title": "docs"})
        get.assert_called_once_with("http://127.0.0.1:5000/api/docs", headers={})


if __name__ == "__main__":
    unittest.main()
