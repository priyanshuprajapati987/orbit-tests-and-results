"""
Legacy router adapter tests
===========================
Covers the Phase A sync facade (`orbit/orbit/core/llm/legacy_adapter.py`):
- Facade `generate()` returns plain `str` from the modern router on success.
- Falls back to the legacy `orbit.router.generate` when the modern router
  fails or raises.
- `extra_context` is forwarded into the modern `LLMRequest`.
- `get_status()` exposes the `online` + `tier` keys agents_api consumers need.
- `generate_offline` and tier/ollama delegates work.
- `/api/agents/status` still returns 200 with the facade wired in.

Run: python -m pytest tests/test_legacy_adapter.py -v
"""

import asyncio
import unittest
from unittest import mock

from orbit.orbit.core.llm import legacy_adapter as la
from orbit.orbit.core.llm.router import LLMResponse


class _FakeRouter:
    def __init__(self, response):
        self.response = response
        self.last_request = None

    def generate(self, request):
        self.last_request = request
        return _awaitable(self.response)


def _awaitable(value):
    async def _inner():
        return value

    return _inner()


class TestFacadeGenerate(unittest.TestCase):
    def test_returns_plain_str_on_success(self):
        fake = _FakeRouter(
            LLMResponse(
                content="modern answer",
                provider="ollama",
                model="m",
                latency_ms=5,
            )
        )
        with mock.patch.object(la, "get_router", return_value=fake):
            result = la.generate("hello")
        self.assertIsInstance(result, str)
        self.assertEqual(result, "modern answer")

    def test_task_type_maps_to_category(self):
        fake = _FakeRouter(
            LLMResponse(
                content="ok",
                provider="ollama",
                model="m",
                latency_ms=5,
            )
        )
        with mock.patch.object(la, "get_router", return_value=fake):
            la.generate("write a poem", task_type="writing")
        self.assertEqual(fake.last_request.category, "creative")

    def test_extra_context_forwarded_to_request(self):
        fake = _FakeRouter(
            LLMResponse(
                content="ok",
                provider="ollama",
                model="m",
                latency_ms=5,
            )
        )
        with mock.patch.object(la, "get_router", return_value=fake):
            la.generate("hi", extra_context="ctx snippet")
        self.assertEqual(fake.last_request.extra_context, "ctx snippet")

    def test_router_injects_extra_context_into_system_prompt(self):
        from orbit.orbit.core.llm.router import LLMRequest, LLMRouter

        router = LLMRouter()
        captured = {}

        async def fake_call(request, model=None):
            captured["system_prompt"] = router._effective_system_prompt(request)
            return LLMResponse(content="ok", provider="ollama", model="m", latency_ms=5)

        with mock.patch.object(router, "_call_ollama", side_effect=fake_call):
            asyncio.run(
                router._generate_with_failover(
                    LLMRequest(
                        prompt="hi",
                        system_prompt="base prompt",
                        extra_context="extra bit",
                        model="qwen2.5:14b",
                        force_offline=True,
                    )
                )
            )
        self.assertIn("extra bit", captured["system_prompt"])
        self.assertIn("base prompt", captured["system_prompt"])

    def test_router_effective_prompt_no_context(self):
        from orbit.orbit.core.llm.router import LLMRequest, LLMRouter

        router = LLMRouter()
        prompt = router._effective_system_prompt(
            LLMRequest(prompt="hi", system_prompt="base")
        )
        self.assertEqual(prompt, "base")
        self.assertIsNone(router._effective_system_prompt(LLMRequest(prompt="hi")))

    def test_history_timestamps_stripped(self):
        fake = _FakeRouter(
            LLMResponse(
                content="ok",
                provider="ollama",
                model="m",
                latency_ms=5,
            )
        )
        history = [
            {"role": "user", "content": "a", "timestamp": "t1"},
            {"role": "assistant", "content": "b", "timestamp": "t2"},
        ]
        with mock.patch.object(la, "get_router", return_value=fake):
            la.generate("hi", history=history)
        for msg in fake.last_request.history:
            self.assertNotIn("timestamp", msg)

    def test_falls_back_on_success_false(self):
        fake = _FakeRouter(
            LLMResponse(
                content="[Error: All LLM providers unavailable]",
                provider="none",
                model="m",
                latency_ms=0,
                success=False,
                error="boom",
            )
        )
        with (
            mock.patch.object(la, "get_router", return_value=fake),
            mock.patch.object(la, "_legacy_generate", return_value="legacy fallback"),
        ):
            result = la.generate("hi")
        self.assertEqual(result, "legacy fallback")

    def test_falls_back_on_modern_exception(self):
        with (
            mock.patch.object(la, "get_router", side_effect=RuntimeError("boom")),
            mock.patch.object(la, "_legacy_generate", return_value="legacy answer"),
        ):
            result = la.generate("hi")
        self.assertEqual(result, "legacy answer")

    def test_error_string_when_both_fail(self):
        fake = _FakeRouter(
            LLMResponse(
                content="[Error: All LLM providers unavailable]",
                provider="none",
                model="m",
                latency_ms=0,
                success=False,
                error="boom",
            )
        )
        with (
            mock.patch.object(la, "get_router", return_value=fake),
            mock.patch.object(
                la, "_legacy_generate", return_value="[Error: legacy down]"
            ),
        ):
            result = la.generate("hi")
        self.assertTrue(result.startswith("[Error"))

    def test_generate_offline_delegate(self):
        fake = _FakeRouter(
            LLMResponse(
                content="offline answer",
                provider="ollama",
                model="phi3",
                latency_ms=5,
            )
        )
        with mock.patch.object(la, "get_router", return_value=fake):
            result = la.generate_offline("hi")
        self.assertEqual(result, "offline answer")


class TestFacadeStatus(unittest.TestCase):
    def test_get_status_has_online_and_tier(self):
        fake = _FakeRouter(
            LLMResponse(
                content="ok",
                provider="ollama",
                model="m",
                latency_ms=5,
            )
        )
        fake.get_status = lambda: {
            "online": True,
            "provider_health": {
                "ollama": "available",
                "gemini": "unknown",
                "groq": "unknown",
                "cloudflare": "unknown",
            },
            "provider_stats": {},
        }
        with mock.patch.object(la, "get_router", return_value=fake):
            status = la.get_status()
        self.assertIn("online", status)
        self.assertIn("tier", status)
        self.assertIsInstance(status["online"], bool)


class TestFacadeLegacyFallback(unittest.TestCase):
    def test_legacy_generate_path(self):
        captured = {}

        def _fake_legacy(
            prompt,
            model=None,
            history=None,
            extra_context=None,
            system_prompt=None,
            force_offline=False,
            task_type=None,
            exp_id=None,
            var_id=None,
            start_time=None,
        ):
            captured["prompt"] = prompt
            captured["task_type"] = task_type
            return "from legacy"

        with (
            mock.patch.object(la, "get_router", side_effect=RuntimeError("down")),
            mock.patch(
                "orbit.orbit.core.llm.legacy_adapter._legacy_generate",
                side_effect=_fake_legacy,
            ),
        ):
            result = la.generate("hi", task_type="coding")
        self.assertEqual(result, "from legacy")
        self.assertEqual(captured["prompt"], "hi")
        self.assertEqual(captured["task_type"], "coding")


class TestFacadeAgentsApi(unittest.TestCase):
    def test_model_info_endpoint_200_with_facade(self):
        from flask import Flask

        from orbit.orbit.core.agents_api import agents_bp

        app = Flask(__name__)
        app.register_blueprint(agents_bp)
        app.config["TESTING"] = True
        client = app.test_client()

        resp = client.get("/model-info")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("online", data)
        self.assertIn("tier", data)
        self.assertIn("providers", data)

    def test_agents_endpoint_200(self):
        from flask import Flask

        from orbit.orbit.core.agents_api import agents_bp

        app = Flask(__name__)
        app.register_blueprint(agents_bp)
        app.config["TESTING"] = True
        client = app.test_client()

        resp = client.get("/agents")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("agents", resp.get_json())


class TestFacadeForceOffline(unittest.TestCase):
    def test_force_offline_sets_request_flag(self):
        fake = _FakeRouter(
            LLMResponse(content="ok", provider="ollama", model="m", latency_ms=5)
        )
        with mock.patch.object(la, "get_router", return_value=fake):
            la.generate("hi", force_offline=True)
        self.assertTrue(fake.last_request.force_offline)

    def test_model_passthrough_reaches_router(self):
        fake = _FakeRouter(
            LLMResponse(content="ok", provider="ollama", model="m", latency_ms=5)
        )
        with mock.patch.object(la, "get_router", return_value=fake):
            la.generate("hi", model="qwen3:8b")
        self.assertEqual(fake.last_request.model, "qwen3:8b")


class TestFacadeConcurrency(unittest.TestCase):
    def test_concurrent_calls_dont_corrupt_state(self):
        import threading

        results = []
        errors = []

        fake = _FakeRouter(
            LLMResponse(content="ok", provider="ollama", model="m", latency_ms=1)
        )

        def worker(i):
            try:
                results.append(la.generate(f"msg-{i}"))
            except Exception as e:
                errors.append(e)

        # Patch ONCE on the main thread. Entering mock.patch from 5 threads
        # concurrently races the save/restore of the original attribute (last
        # restorer wins) and leaked a MagicMock into la.get_router — every
        # later test in the session then got fake "ok" responses.
        real_get_router = la.get_router
        with mock.patch.object(la, "get_router", return_value=fake):
            threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)

        self.assertIs(
            la.get_router, real_get_router, "get_router patch leaked out of the test"
        )
        self.assertEqual(len(errors), 0, f"Errors in threads: {errors}")
        self.assertEqual(len(results), 5)
        for r in results:
            self.assertEqual(r, "ok")


class TestRunCoroFallback(unittest.TestCase):
    def test_run_coro_falls_back_on_running_loop(self):
        import concurrent.futures

        async def dummy():
            return 42

        async def runner():
            with concurrent.futures.ThreadPoolExecutor() as pool:
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(pool, la._run_coro, dummy())
            return result

        result = asyncio.run(runner())
        self.assertEqual(result, 42)

    def test_run_coro_raises_non_loop_error(self):
        async def dummy():
            return 42

        with mock.patch.object(la.asyncio, "run", side_effect=ValueError("other")):
            with self.assertRaises(ValueError):
                la._run_coro(dummy())


class TestCheckInternet(unittest.TestCase):
    def test_delegates_to_router(self):
        fake = _FakeRouter(
            LLMResponse(content="ok", provider="ollama", model="m", latency_ms=1)
        )
        fake._check_internet = lambda timeout=2: True
        with mock.patch.object(la, "get_router", return_value=fake):
            self.assertTrue(la.check_internet())


class TestExperimentIntercept(unittest.TestCase):
    def test_experiment_intercept_called_when_task_type_set(self):
        mock_fw = mock.MagicMock()
        mock_fw.route_prompt.return_value = ("rewritten", "exp1", "var1")
        with mock.patch.dict(
            "sys.modules",
            {
                "orbit.orbit.core.experimentation_framework": mock.MagicMock(
                    get_experimentation_framework=mock.MagicMock(return_value=mock_fw)
                )
            },
        ):
            prompt, exp_id, var_id = la._experiment_intercept("coding", "write code")
        self.assertEqual(prompt, "rewritten")
        self.assertEqual(exp_id, "exp1")
        self.assertEqual(var_id, "var1")

    def test_experiment_intercept_noop_when_task_type_none(self):
        prompt, exp_id, var_id = la._experiment_intercept(None, "hello")
        self.assertEqual(prompt, "hello")
        self.assertIsNone(exp_id)
        self.assertIsNone(var_id)

    def test_experiment_intercept_survives_framework_error(self):
        mock_fw = mock.MagicMock()
        mock_fw.route_prompt.side_effect = RuntimeError("boom")
        with mock.patch.dict(
            "sys.modules",
            {
                "orbit.orbit.core.experimentation_framework": mock.MagicMock(
                    get_experimentation_framework=mock.MagicMock(return_value=mock_fw)
                )
            },
        ):
            prompt, exp_id, var_id = la._experiment_intercept("coding", "hello")
        self.assertEqual(prompt, "hello")
        self.assertIsNone(exp_id)
        self.assertIsNone(var_id)

    def test_record_experiment_called_on_success(self):
        mock_fw = mock.MagicMock()
        with mock.patch.dict(
            "sys.modules",
            {
                "orbit.orbit.core.experimentation_framework": mock.MagicMock(
                    get_experimentation_framework=mock.MagicMock(return_value=mock_fw)
                )
            },
        ):
            la._record_experiment("exp1", "var1", 100.0, True)
        mock_fw.record_result.assert_called_once_with("exp1", "var1", 0.5, 100.0, True)

    def test_record_experiment_noop_when_no_var_id(self):
        mock_fw = mock.MagicMock()
        with mock.patch.dict(
            "sys.modules",
            {
                "orbit.orbit.core.experimentation_framework": mock.MagicMock(
                    get_experimentation_framework=mock.MagicMock(return_value=mock_fw)
                )
            },
        ):
            la._record_experiment("exp1", None, 100.0, True)
        mock_fw.record_result.assert_not_called()


if __name__ == "__main__":
    unittest.main()
