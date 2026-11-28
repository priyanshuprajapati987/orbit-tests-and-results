"""Deep tests for orbit/orbit/core/llm/providers.py (Loop 20/2)."""

import os
import unittest
from unittest import mock

from orbit.orbit.core.llm import providers as prv
from orbit.orbit.core.llm.router import LLMRequest, LLMResponse


class LLMProviderAbstractTests(unittest.TestCase):
    def test_cannot_instantiate_abstract(self):
        with self.assertRaises(TypeError):
            prv.LLMProvider()


class OllamaProviderTests(unittest.TestCase):
    def test_init_defaults(self):
        p = prv.OllamaProvider()
        self.assertEqual(p.url, "http://127.0.0.1:11434")
        self.assertIsNone(p.api_key)

    def test_init_custom_url(self):
        p = prv.OllamaProvider(url="http://x:1234")
        self.assertEqual(p.url, "http://x:1234")

    def test_is_available_success(self):
        p = prv.OllamaProvider()
        resp = mock.MagicMock(status_code=200)
        with mock.patch("requests.get", return_value=resp):
            self.assertTrue(p.is_available())

    def test_is_available_fail(self):
        p = prv.OllamaProvider()
        with mock.patch("requests.get", side_effect=Exception("boom")):
            self.assertFalse(p.is_available())

    def test_is_available_non_200(self):
        p = prv.OllamaProvider()
        resp = mock.MagicMock(status_code=500)
        with mock.patch("requests.get", return_value=resp):
            self.assertFalse(p.is_available())

    def test_get_models_success(self):
        p = prv.OllamaProvider()
        resp = mock.MagicMock(status_code=200)
        resp.json.return_value = {"models": [{"name": "llama3"}, {"name": "qwen"}]}
        with mock.patch("requests.get", return_value=resp):
            self.assertEqual(p.get_models(), ["llama3", "qwen"])

    def test_get_models_fail_returns_available_models(self):
        p = prv.OllamaProvider()
        with mock.patch("requests.get", side_effect=Exception("boom")), \
                mock.patch("orbit.orbit.core.llm.providers.AVAILABLE_MODELS",
                           ["m1", "m2"], create=True):
            # AVAILABLE_MODELS imported from ..config inside method
            with mock.patch("orbit.orbit.core.config.AVAILABLE_MODELS", ["m1", "m2"]):
                self.assertEqual(p.get_models(), ["m1", "m2"])

    def test_get_models_non_200_returns_available(self):
        p = prv.OllamaProvider()
        resp = mock.MagicMock(status_code=404)
        with mock.patch("requests.get", return_value=resp), \
                mock.patch("orbit.orbit.core.config.AVAILABLE_MODELS", ["fallback"]):
            self.assertEqual(p.get_models(), ["fallback"])

    def test_pull_model_success(self):
        p = prv.OllamaProvider()
        resp = mock.MagicMock(status_code=200)
        with mock.patch("requests.post", return_value=resp):
            self.assertTrue(p.pull_model("llama3"))

    def test_pull_model_fail(self):
        p = prv.OllamaProvider()
        with mock.patch("requests.post", side_effect=Exception("boom")):
            self.assertFalse(p.pull_model("llama3"))

    def test_pull_model_non_200(self):
        p = prv.OllamaProvider()
        resp = mock.MagicMock(status_code=404)
        with mock.patch("requests.post", return_value=resp):
            self.assertFalse(p.pull_model("llama3"))

    def test_generate_with_circuit_breaker_open(self):
        import asyncio
        p = prv.OllamaProvider()
        with mock.patch("orbit.orbit.core.llm.providers.get_circuit_breaker") as gcb, \
                mock.patch("orbit.orbit.core.llm.router.get_router") as gr:
            cb = mock.MagicMock()
            cb.call.side_effect = prv.CircuitBreakerOpenError("x", 0.0)
            gcb.return_value = cb
            router = mock.MagicMock()
            gr.return_value = router
            req = LLMRequest(prompt="hi")
            r = asyncio.run(p.generate(req))
        self.assertIsNone(r)

    def test_generate_success(self):
        import asyncio
        p = prv.OllamaProvider()
        resp = mock.MagicMock(content="hello")
        with mock.patch("orbit.orbit.core.llm.providers.get_circuit_breaker") as gcb, \
                mock.patch("orbit.orbit.core.llm.router.get_router") as gr:
            cb = mock.MagicMock()
            cb.call = mock.AsyncMock(return_value=resp)
            gcb.return_value = cb
            router = mock.MagicMock()
            gr.return_value = router
            req = LLMRequest(prompt="hi")
            r = asyncio.run(p.generate(req))
        self.assertIs(r, resp)
        cb.call.assert_called_once_with(router._call_ollama, req)

    def test_generate_offline(self):
        import asyncio
        p = prv.OllamaProvider()
        resp = mock.MagicMock(content="offline result")
        with mock.patch("orbit.orbit.core.llm.router.get_router") as gr:
            router = mock.MagicMock()
            router.generate = mock.AsyncMock(return_value=resp)
            gr.return_value = router
            r = asyncio.run(p.generate_offline("hi", "m"))
        self.assertEqual(r, "offline result")
        req = router.generate.call_args.args[0]
        self.assertEqual(req.prompt, "hi")
        self.assertEqual(req.model, "m")
        self.assertTrue(req.force_offline)


class OpenRouterProviderTests(unittest.TestCase):
    def test_init(self):
        p = prv.OpenRouterProvider(api_key="key123")
        self.assertEqual(p.api_key, "key123")
        self.assertEqual(p.base_url, "http://127.0.0.1:20128/v1")
        # env override
        with mock.patch.dict(os.environ, {"OPENROUTER_BASE_URL": "http://x/v1"}):
            p2 = prv.OpenRouterProvider(api_key="k")
        self.assertEqual(p2.base_url, "http://x/v1")

    def test_is_available(self):
        p = prv.OpenRouterProvider(api_key="key")
        self.assertTrue(p.is_available())
        p2 = prv.OpenRouterProvider(api_key=None)
        self.assertFalse(p2.is_available())
        p3 = prv.OpenRouterProvider(api_key="")
        self.assertFalse(p3.is_available())
        p4 = prv.OpenRouterProvider(api_key="your_openrouter_api_key_here")
        self.assertFalse(p4.is_available())

    def test_get_models(self):
        p = prv.OpenRouterProvider(api_key="k")
        models = p.get_models()
        self.assertGreater(len(models), 0)
        self.assertIn("google/gemini-2.0-flash-exp:free", models)

    def test_generate_no_api_key(self):
        import asyncio
        p = prv.OpenRouterProvider(api_key=None)
        req = LLMRequest(prompt="hi")
        r = asyncio.run(p.generate(req))
        self.assertIsNone(r)

    def test_generate_placeholder_key(self):
        import asyncio
        p = prv.OpenRouterProvider(api_key="your_openrouter_api_key_here")
        req = LLMRequest(prompt="hi")
        r = asyncio.run(p.generate(req))
        self.assertIsNone(r)

    def test_generate_success(self):
        import asyncio
        p = prv.OpenRouterProvider(api_key="realkey")
        resp = mock.MagicMock(content="hello")
        with mock.patch("orbit.orbit.core.llm.providers.get_circuit_breaker") as gcb, \
                mock.patch("orbit.orbit.core.llm.router.get_router") as gr:
            cb = mock.MagicMock()
            cb.call = mock.AsyncMock(return_value=resp)
            gcb.return_value = cb
            router = mock.MagicMock()
            gr.return_value = router
            req = LLMRequest(prompt="hi", model="m", system_prompt="sp", history=[{"a": 1}])
            r = asyncio.run(p.generate(req))
        self.assertIs(r, resp)
        # model uses request.model
        cb.call.assert_called_once()
        call_args = cb.call.call_args
        self.assertEqual(call_args.args[1], req)
        self.assertEqual(call_args.args[2], "m")

    def test_generate_circuit_breaker_open(self):
        import asyncio
        p = prv.OpenRouterProvider(api_key="realkey")
        with mock.patch("orbit.orbit.core.llm.providers.get_circuit_breaker") as gcb, \
                mock.patch("orbit.orbit.core.llm.router.get_router") as gr:
            cb = mock.MagicMock()
            cb.call.side_effect = prv.CircuitBreakerOpenError("x", 0.0)
            gcb.return_value = cb
            gr.return_value = mock.MagicMock()
            req = LLMRequest(prompt="hi")
            r = asyncio.run(p.generate(req))
        self.assertIsNone(r)

    def test_generate_with_routing(self):
        import asyncio
        p = prv.OpenRouterProvider(api_key="realkey")
        resp = mock.MagicMock(content="routed")
        with mock.patch.object(p, "generate", mock.AsyncMock(return_value=resp)) as gen:
            r = asyncio.run(p.generate_with_routing("hi", model="m", system_prompt="sp",
                                                    history=[{"a": 1}]))
            self.assertEqual(r, "routed")
            req = gen.call_args.args[0]
            self.assertEqual(req.prompt, "hi")
            self.assertEqual(req.model, "m")
            self.assertEqual(req.system_prompt, "sp")
            self.assertEqual(req.history, [{"a": 1}])

    def test_generate_with_routing_no_response(self):
        import asyncio
        p = prv.OpenRouterProvider(api_key="realkey")
        with mock.patch.object(p, "generate", mock.AsyncMock(return_value=None)):
            r = asyncio.run(p.generate_with_routing("hi"))
        self.assertIsNone(r)


class OpenAIProviderTests(unittest.TestCase):
    def test_init_with_key(self):
        p = prv.OpenAIProvider(api_key="sk-123")
        self.assertEqual(p.api_key, "sk-123")

    def test_init_from_env(self):
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "env-key"}):
            p = prv.OpenAIProvider()
        self.assertEqual(p.api_key, "env-key")

    def test_init_no_key(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            p = prv.OpenAIProvider()
        self.assertEqual(p.api_key, "")

    def test_is_available(self):
        p = prv.OpenAIProvider(api_key="k")
        self.assertTrue(p.is_available())
        p2 = prv.OpenAIProvider(api_key="")
        self.assertFalse(p2.is_available())

    def test_get_models(self):
        p = prv.OpenAIProvider(api_key="k")
        with mock.patch("orbit.orbit.core.config.ASTRA_MODEL", "gpt-5"):
            models = p.get_models()
        self.assertIn("gpt-5", models)

    def test_generate_no_key(self):
        import asyncio
        p = prv.OpenAIProvider(api_key="")
        req = LLMRequest(prompt="hi")
        r = asyncio.run(p.generate(req))
        self.assertIsNone(r)

    def test_generate_success(self):
        import asyncio
        p = prv.OpenAIProvider(api_key="sk")
        resp = mock.MagicMock(content="hi")
        with mock.patch("orbit.orbit.core.llm.providers.get_circuit_breaker") as gcb, \
                mock.patch("orbit.orbit.core.llm.router.get_router") as gr, \
                mock.patch("orbit.orbit.core.config.ASTRA_MODEL", "gpt-5"):
            cb = mock.MagicMock()
            cb.call = mock.AsyncMock(return_value=resp)
            gcb.return_value = cb
            router = mock.MagicMock()
            gr.return_value = router
            req = LLMRequest(prompt="hi")
            r = asyncio.run(p.generate(req))
        self.assertIs(r, resp)
        cb.call.assert_called_once()
        # model defaults to ASTRA_MODEL
        self.assertEqual(cb.call.call_args.args[2], "gpt-5")

    def test_generate_with_model(self):
        import asyncio
        p = prv.OpenAIProvider(api_key="sk")
        resp = mock.MagicMock(content="hi")
        with mock.patch("orbit.orbit.core.llm.providers.get_circuit_breaker") as gcb, \
                mock.patch("orbit.orbit.core.llm.router.get_router") as gr, \
                mock.patch("orbit.orbit.core.config.ASTRA_MODEL", "gpt-5"):
            cb = mock.MagicMock()
            cb.call = mock.AsyncMock(return_value=resp)
            gcb.return_value = cb
            gr.return_value = mock.MagicMock()
            req = LLMRequest(prompt="hi", model="gpt-4o")
            asyncio.run(p.generate(req))
        self.assertEqual(cb.call.call_args.args[2], "gpt-4o")

    def test_generate_circuit_breaker_open(self):
        import asyncio
        p = prv.OpenAIProvider(api_key="sk")
        with mock.patch("orbit.orbit.core.llm.providers.get_circuit_breaker") as gcb, \
                mock.patch("orbit.orbit.core.llm.router.get_router") as gr, \
                mock.patch("orbit.orbit.core.config.ASTRA_MODEL", "gpt-5"):
            cb = mock.MagicMock()
            cb.call.side_effect = prv.CircuitBreakerOpenError("x", 0.0)
            gcb.return_value = cb
            gr.return_value = mock.MagicMock()
            req = LLMRequest(prompt="hi")
            r = asyncio.run(p.generate(req))
        self.assertIsNone(r)


class GeminiProviderTests(unittest.TestCase):
    def test_init(self):
        p = prv.GeminiProvider(api_key="key")
        self.assertEqual(p.api_key, "key")
        self.assertEqual(p.base_url, "https://generativelanguage.googleapis.com/v1beta/models")

    def test_is_available(self):
        p = prv.GeminiProvider(api_key="key")
        self.assertTrue(p.is_available())
        p2 = prv.GeminiProvider(api_key=None)
        self.assertFalse(p2.is_available())
        p3 = prv.GeminiProvider(api_key="")
        self.assertFalse(p3.is_available())
        p4 = prv.GeminiProvider(api_key="your_gemini_api_key_here")
        self.assertFalse(p4.is_available())

    def test_get_models(self):
        p = prv.GeminiProvider(api_key="k")
        models = p.get_models()
        self.assertEqual(len(models), 3)

    def test_generate_no_key(self):
        import asyncio
        p = prv.GeminiProvider(api_key=None)
        req = LLMRequest(prompt="hi")
        r = asyncio.run(p.generate(req))
        self.assertIsNone(r)

    def test_generate_placeholder_key(self):
        import asyncio
        p = prv.GeminiProvider(api_key="your_gemini_api_key_here")
        req = LLMRequest(prompt="hi")
        r = asyncio.run(p.generate(req))
        self.assertIsNone(r)

    def test_generate_success_default_model(self):
        import asyncio
        p = prv.GeminiProvider(api_key="key")
        resp = mock.MagicMock(content="hi")
        with mock.patch("orbit.orbit.core.llm.providers.get_circuit_breaker") as gcb, \
                mock.patch("orbit.orbit.core.llm.router.get_router") as gr:
            cb = mock.MagicMock()
            cb.call = mock.AsyncMock(return_value=resp)
            gcb.return_value = cb
            router = mock.MagicMock()
            gr.return_value = router
            req = LLMRequest(prompt="hi")
            r = asyncio.run(p.generate(req))
        self.assertIs(r, resp)
        # default model = gemini-2.0-flash-exp (free)
        self.assertEqual(cb.call.call_args.args[2], "gemini-2.0-flash-exp")

    def test_generate_success_model_override(self):
        import asyncio
        p = prv.GeminiProvider(api_key="key")
        resp = mock.MagicMock(content="hi")
        with mock.patch("orbit.orbit.core.llm.providers.get_circuit_breaker") as gcb, \
                mock.patch("orbit.orbit.core.llm.router.get_router") as gr:
            cb = mock.MagicMock()
            cb.call = mock.AsyncMock(return_value=resp)
            gcb.return_value = cb
            gr.return_value = mock.MagicMock()
            req = LLMRequest(prompt="hi", model="gemini-1.5-pro")
            asyncio.run(p.generate(req))
        self.assertEqual(cb.call.call_args.args[2], "gemini-1.5-pro")

    def test_generate_success_model_free_cheap_best(self):
        import asyncio
        p = prv.GeminiProvider(api_key="key")
        resp = mock.MagicMock(content="hi")
        # When request.model is None/falsy, defaults to models["free"]
        with mock.patch("orbit.orbit.core.llm.providers.get_circuit_breaker") as gcb, \
                mock.patch("orbit.orbit.core.llm.router.get_router") as gr:
            cb = mock.MagicMock()
            cb.call = mock.AsyncMock(return_value=resp)
            gcb.return_value = cb
            gr.return_value = mock.MagicMock()
            req = LLMRequest(prompt="hi", model=None)
            asyncio.run(p.generate(req))
        self.assertEqual(cb.call.call_args.args[2], "gemini-2.0-flash-exp")

    def test_generate_circuit_breaker_open(self):
        import asyncio
        p = prv.GeminiProvider(api_key="key")
        with mock.patch("orbit.orbit.core.llm.providers.get_circuit_breaker") as gcb, \
                mock.patch("orbit.orbit.core.llm.router.get_router") as gr:
            cb = mock.MagicMock()
            cb.call.side_effect = prv.CircuitBreakerOpenError("x", 0.0)
            gcb.return_value = cb
            gr.return_value = mock.MagicMock()
            req = LLMRequest(prompt="hi")
            r = asyncio.run(p.generate(req))
        self.assertIsNone(r)

    def test_generate_with_flash(self):
        import asyncio
        p = prv.GeminiProvider(api_key="key")
        resp = mock.MagicMock(content="flash result")
        with mock.patch.object(p, "generate", mock.AsyncMock(return_value=resp)) as gen:
            r = asyncio.run(p.generate_with_flash("hi", system_prompt="sp",
                                                  history=[{"a": 1}]))
            self.assertEqual(r, "flash result")
            req = gen.call_args.args[0]
            self.assertEqual(req.prompt, "hi")
            self.assertEqual(req.system_prompt, "sp")
            self.assertEqual(req.history, [{"a": 1}])

    def test_generate_with_flash_no_response(self):
        import asyncio
        p = prv.GeminiProvider(api_key="key")
        with mock.patch.object(p, "generate", mock.AsyncMock(return_value=None)):
            r = asyncio.run(p.generate_with_flash("hi"))
        self.assertIsNone(r)


class PortkeyProviderTests(unittest.TestCase):
    def test_init(self):
        p = prv.PortkeyProvider(api_key="k", gateway_url="http://x/v1")
        self.assertEqual(p.api_key, "k")
        self.assertEqual(p.gateway_url, "http://x/v1")
        self.assertIsNone(p._client)
        # default gateway_url
        p2 = prv.PortkeyProvider(api_key="k")
        self.assertEqual(p2.gateway_url, "http://localhost:20128/v1")

    def test_is_available_success(self):
        p = prv.PortkeyProvider(api_key="k")
        resp = mock.MagicMock(status_code=200)
        httpx = mock.MagicMock()
        httpx.get.return_value = resp
        with mock.patch.dict("sys.modules", {"httpx": httpx}):
            self.assertTrue(p.is_available())
        httpx.get.assert_called_once()

    def test_is_available_fail(self):
        p = prv.PortkeyProvider(api_key="k")
        httpx = mock.MagicMock()
        httpx.get.side_effect = Exception("boom")
        with mock.patch.dict("sys.modules", {"httpx": httpx}):
            self.assertFalse(p.is_available())

    def test_is_available_non_200(self):
        p = prv.PortkeyProvider(api_key="k")
        resp = mock.MagicMock(status_code=404)
        httpx = mock.MagicMock()
        httpx.get.return_value = resp
        with mock.patch.dict("sys.modules", {"httpx": httpx}):
            self.assertFalse(p.is_available())

    def test_get_models_success_dict(self):
        p = prv.PortkeyProvider(api_key="k")
        resp = mock.MagicMock(status_code=200)
        resp.json.return_value = {"data": [{"id": "m1"}, {"id": "m2"}]}
        httpx = mock.MagicMock()
        httpx.get.return_value = resp
        with mock.patch.dict("sys.modules", {"httpx": httpx}):
            self.assertEqual(p.get_models(), ["m1", "m2"])

    def test_get_models_success_list(self):
        p = prv.PortkeyProvider(api_key="k")
        resp = mock.MagicMock(status_code=200)
        resp.json.return_value = ["m1", "m2"]
        httpx = mock.MagicMock()
        httpx.get.return_value = resp
        with mock.patch.dict("sys.modules", {"httpx": httpx}):
            self.assertEqual(p.get_models(), ["m1", "m2"])

    def test_get_models_non_200_returns_defaults(self):
        p = prv.PortkeyProvider(api_key="k")
        resp = mock.MagicMock(status_code=404)
        httpx = mock.MagicMock()
        httpx.get.return_value = resp
        with mock.patch.dict("sys.modules", {"httpx": httpx}):
            models = p.get_models()
        self.assertIn("gpt-4o-mini", models)

    def test_get_models_exception_returns_defaults(self):
        p = prv.PortkeyProvider(api_key="k")
        httpx = mock.MagicMock()
        httpx.get.side_effect = Exception("boom")
        with mock.patch.dict("sys.modules", {"httpx": httpx}), \
                mock.patch.object(prv, "logger") as lg:
            models = p.get_models()
        self.assertIn("gpt-4o-mini", models)
        lg.exception.assert_called_once()

    def test_get_models_dict_non_dict_items(self):
        p = prv.PortkeyProvider(api_key="k")
        resp = mock.MagicMock(status_code=200)
        resp.json.return_value = {"data": ["m1", "m2"]}
        httpx = mock.MagicMock()
        httpx.get.return_value = resp
        with mock.patch.dict("sys.modules", {"httpx": httpx}):
            self.assertEqual(p.get_models(), ["m1", "m2"])

    def test_generate_success(self):
        import asyncio
        p = prv.PortkeyProvider(api_key="k")
        resp = mock.MagicMock(content="hi")
        with mock.patch("orbit.orbit.core.llm.providers.get_circuit_breaker") as gcb, \
                mock.patch("orbit.orbit.core.llm.router.get_router") as gr:
            cb = mock.MagicMock()
            cb.call = mock.AsyncMock(return_value=resp)
            gcb.return_value = cb
            router = mock.MagicMock()
            gr.return_value = router
            req = LLMRequest(prompt="hi")
            r = asyncio.run(p.generate(req))
        self.assertIs(r, resp)
        cb.call.assert_called_once_with(router._call_portkey, req,
                                       p.gateway_url, "k")

    def test_generate_circuit_breaker_open(self):
        import asyncio
        p = prv.PortkeyProvider(api_key="k")
        with mock.patch("orbit.orbit.core.llm.providers.get_circuit_breaker") as gcb, \
                mock.patch("orbit.orbit.core.llm.router.get_router") as gr:
            cb = mock.MagicMock()
            cb.call.side_effect = prv.CircuitBreakerOpenError("x", 0.0)
            gcb.return_value = cb
            gr.return_value = mock.MagicMock()
            req = LLMRequest(prompt="hi")
            r = asyncio.run(p.generate(req))
        self.assertIsNone(r)


if __name__ == "__main__":
    unittest.main()
