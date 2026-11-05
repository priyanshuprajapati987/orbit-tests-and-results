"""Tests for true token streaming (perceived-zero-latency chat).

- Router ``stream_generate`` yields tokens from a streaming provider (Ollama SSE).
- ``/chat/stream`` emits real ``token`` SSE events + a final ``complete`` event
  (previously it buffered the whole response and emitted a single chunk).
"""

import asyncio
import json
import unittest
import unittest.mock
from unittest.mock import AsyncMock

from flask import Flask

from orbit.orbit.core import conversation_engine as ce
from orbit.orbit.core.llm.router import LLMRequest, get_router


class _FakeResp:
    status_code = 200

    def iter_lines(self, decode_unicode=True):
        # Ollama SSE: one JSON object per line.
        return iter(
            [
                '{"message": {"content": "Hello "}}',
                '{"message": {"content": "world"}}',
            ]
        )


class TestRouterStreaming(unittest.TestCase):
    def test_stream_generate_yields_tokens(self):
        captured = []

        async def collect():
            async for piece in get_router().stream_generate(LLMRequest(prompt="hi")):
                captured.append(piece)

        with unittest.mock.patch("requests.post", return_value=_FakeResp()):
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(collect())
            finally:
                loop.close()

        self.assertEqual(captured, ["Hello ", "world"])


class _FakeEngine:
    async def stream_process(
        self,
        message,
        history=None,
        system_prompt=None,
        force_offline=False,
        skip_cache=False,
        model=None,
    ):
        yield {"token": "Hello "}
        yield {"token": "world"}
        yield {
            "done": {
                "content": "Hello world",
                "state": "complete",
                "query_type": "general",
                "complexity": "simple",
                "provider": "stream",
                "model": "stream",
                "latency_ms": 1.0,
                "confidence": 0.5,
                "token_estimate": 2,
                "used_cache": False,
                "error": None,
            }
        }


class TestChatStreamEndpoint(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        from orbit.orbit.core.chat_api import chat_bp

        self.app.register_blueprint(chat_bp)
        self.client = self.app.test_client()
        self._patcher = unittest.mock.patch.object(
            ce, "get_engine", lambda *a, **k: _FakeEngine()
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_stream_endpoint_emits_tokens_then_complete(self):
        resp = self.client.post("/chat/stream", json={"message": "tell me a joke"})
        self.assertEqual(resp.status_code, 200)
        events = []
        for raw in resp.data.decode().split("\n\n"):
            raw = raw.strip()
            if not raw.startswith("data:"):
                continue
            payload_str = raw[len("data:") :].strip()
            if payload_str == "[DONE]":
                continue
            events.append(json.loads(payload_str))

        types = [e["type"] for e in events]
        # Two token events followed by one complete event.
        self.assertEqual(types.count("token"), 2)
        self.assertIn("complete", types)
        token_data = "".join(e["data"] for e in events if e["type"] == "token")
        self.assertEqual(token_data, "Hello world")
        complete = next(e for e in events if e["type"] == "complete")
        self.assertEqual(complete["data"]["content"], "Hello world")

    def test_stream_endpoint_requires_message(self):
        resp = self.client.post("/chat/stream", json={})
        self.assertEqual(resp.status_code, 400)


class _FakeEngineError:
    async def stream_process(
        self,
        message,
        history=None,
        system_prompt=None,
        force_offline=False,
        skip_cache=False,
        model=None,
    ):
        yield {"token": "partial "}
        yield {
            "done": {
                "content": "[Engine error: boom]",
                "state": "error",
                "query_type": "general",
                "complexity": "simple",
                "provider": "none",
                "model": "none",
                "latency_ms": 1.0,
                "confidence": 0.0,
                "token_estimate": 0,
                "used_cache": False,
                "error": "boom",
            }
        }


class TestChatStreamError(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        from orbit.orbit.core.chat_api import chat_bp

        self.app.register_blueprint(chat_bp)
        self.client = self.app.test_client()
        self._patcher = unittest.mock.patch.object(
            ce, "get_engine", lambda *a, **k: _FakeEngineError()
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_error_completion_emits_error_event_not_complete(self):
        resp = self.client.post("/chat/stream", json={"message": "tell me a joke"})
        self.assertEqual(resp.status_code, 200)
        events = []
        for raw in resp.data.decode().split("\n\n"):
            raw = raw.strip()
            if not raw.startswith("data:"):
                continue
            payload_str = raw[len("data:") :].strip()
            if payload_str == "[DONE]":
                continue
            events.append(json.loads(payload_str))

        types = [e["type"] for e in events]
        # A failed generation must surface as a distinct `error` event (not
        # `complete`) so the client doesn't store it as a successful answer.
        self.assertIn("error", types)
        self.assertNotIn("complete", types)
        error = next(e for e in events if e["type"] == "error")
        self.assertEqual(error["data"]["error"], "boom")


class _Resp:
    content = "fallback answer"
    success = True


class TestStreamFailover(unittest.TestCase):
    def setUp(self):
        self.router = get_router()
        self._patcher = unittest.mock.patch.object(
            self.router,
            "_stream_order",
            return_value=[("openrouter", "m"), ("ollama", "om")],
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def _collect(self, gen):
        out = []

        async def run():
            async for p in gen:
                out.append(p)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(run())
        finally:
            loop.close()
        return out

    def test_fallback_to_generate_when_all_streams_dead(self):
        async def dead(*a, **k):
            raise RuntimeError("dead provider")
            yield  # unreachable; marks this as an async generator

        with (
            unittest.mock.patch.object(self.router, "_stream_openrouter", dead),
            unittest.mock.patch.object(self.router, "_stream_ollama", dead),
            unittest.mock.patch.object(
                self.router, "generate", new=AsyncMock(return_value=_Resp())
            ),
        ):
            result = self._collect(self.router.stream_generate(LLMRequest(prompt="hi")))

        self.assertEqual(result, ["fallback answer"])

    def test_mid_stream_failure_stops_without_duplicate(self):
        async def partial_then_fail(*a, **k):
            yield "Hello "
            raise RuntimeError("mid-stream died")

        gen = AsyncMock(return_value=_Resp())
        with (
            unittest.mock.patch.object(
                self.router, "_stream_openrouter", partial_then_fail
            ),
            unittest.mock.patch.object(
                self.router, "_stream_ollama", partial_then_fail
            ),
            unittest.mock.patch.object(self.router, "generate", new=gen),
        ):
            result = self._collect(self.router.stream_generate(LLMRequest(prompt="hi")))

        # Only the partial content is emitted; no re-stream / no fallback dup.
        self.assertEqual(result, ["Hello "])
        gen.assert_not_called()

    def test_successful_stream_returns_immediately(self):
        async def ok(*a, **k):
            yield "a"
            yield "b"

        gen = AsyncMock(return_value=_Resp())
        with (
            unittest.mock.patch.object(self.router, "_stream_openrouter", ok),
            unittest.mock.patch.object(self.router, "_stream_ollama", ok),
            unittest.mock.patch.object(self.router, "generate", new=gen),
        ):
            result = self._collect(self.router.stream_generate(LLMRequest(prompt="hi")))

        self.assertEqual(result, ["a", "b"])
        gen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
