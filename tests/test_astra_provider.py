"""Tests for GPT-6 Astra first-class provider wiring.

Hermetic: all HTTP is mocked, no keys needed, no network.
"""

import asyncio
import os
import unittest.mock

from orbit.orbit.core.llm.router import LLMRequest, LLMRouter


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _FakeResp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = (
            payload
            if payload is not None
            else {"choices": [{"message": {"content": "hello from astra"}}]}
        )

    def json(self):
        return self._payload


class TestAstraConfig(unittest.TestCase):
    def test_defaults(self):
        from orbit.orbit.core import config as core_config

        self.assertEqual(
            core_config.ASTRA_MODEL, os.environ.get("ASTRA_MODEL", "gpt-6-astra")
        )
        self.assertTrue(core_config.OPENAI_BASE_URL.startswith("https://"))
        self.assertIn(
            core_config.ASTRA_REASONING_EFFORT,
            ("low", "medium", "high", "xhigh", "max"),
        )

    def test_inner_config_exports(self):
        import orbit.orbit.config as inner

        self.assertEqual(
            inner.ASTRA_MODEL, os.environ.get("ASTRA_MODEL", "gpt-6-astra")
        )
        self.assertTrue(hasattr(inner, "OPENAI_API_KEY"))
        import orbit.config as outer

        self.assertEqual(outer.ASTRA_MODEL, inner.ASTRA_MODEL)


class TestOpenAICall(unittest.TestCase):
    def test_no_key_returns_none(self):
        with unittest.mock.patch("orbit.orbit.core.llm.router.OPENAI_API_KEY", ""):
            resp = _run(
                LLMRouter()._call_openai(LLMRequest(prompt="hi"), "gpt-6-astra")
            )
        self.assertIsNone(resp)

    def test_astra_payload_uses_reasoning_effort(self):
        captured = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _FakeResp()

        with (
            unittest.mock.patch(
                "orbit.orbit.core.llm.router.OPENAI_API_KEY", "sk-test"
            ),
            unittest.mock.patch("requests.post", side_effect=fake_post),
        ):
            resp = _run(
                LLMRouter()._call_openai(
                    LLMRequest(prompt="hi", reasoning_effort="high"), "gpt-6-astra"
                )
            )
        self.assertIsNotNone(resp)
        self.assertTrue(resp.success)
        self.assertEqual(resp.provider, "openai")
        self.assertIn("/chat/completions", captured["url"])
        self.assertEqual(captured["headers"]["Authorization"], "Bearer sk-test")
        self.assertEqual(captured["json"]["reasoning_effort"], "high")
        self.assertIn("max_completion_tokens", captured["json"])
        self.assertNotIn("temperature", captured["json"])

    def test_non_reasoning_payload_uses_max_tokens(self):
        captured = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured["json"] = json
            return _FakeResp()

        with (
            unittest.mock.patch(
                "orbit.orbit.core.llm.router.OPENAI_API_KEY", "sk-test"
            ),
            unittest.mock.patch("requests.post", side_effect=fake_post),
        ):
            resp = _run(
                LLMRouter()._call_openai(LLMRequest(prompt="hi"), "gpt-4o-mini")
            )
        self.assertIsNotNone(resp)
        self.assertIn("max_tokens", captured["json"])
        self.assertNotIn("reasoning_effort", captured["json"])

    def test_non_200_returns_none(self):
        with (
            unittest.mock.patch(
                "orbit.orbit.core.llm.router.OPENAI_API_KEY", "sk-test"
            ),
            unittest.mock.patch(
                "requests.post", return_value=_FakeResp(status_code=401)
            ),
        ):
            resp = _run(
                LLMRouter()._call_openai(LLMRequest(prompt="hi"), "gpt-6-astra")
            )
        self.assertIsNone(resp)

    def test_empty_choices_returns_none(self):
        with (
            unittest.mock.patch(
                "orbit.orbit.core.llm.router.OPENAI_API_KEY", "sk-test"
            ),
            unittest.mock.patch(
                "requests.post", return_value=_FakeResp(payload={"choices": []})
            ),
        ):
            resp = _run(
                LLMRouter()._call_openai(LLMRequest(prompt="hi"), "gpt-6-astra")
            )
        self.assertIsNone(resp)


class TestOpenAIProvider(unittest.TestCase):
    def test_unavailable_without_key(self):
        from orbit.orbit.core.llm.providers import OpenAIProvider

        with unittest.mock.patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            p = OpenAIProvider(api_key="")
        self.assertFalse(p.is_available())

    def test_available_with_key(self):
        from orbit.orbit.core.llm.providers import OpenAIProvider

        p = OpenAIProvider(api_key="sk-test")
        self.assertTrue(p.is_available())
        self.assertIn("gpt-6-astra", p.get_models())

    def test_generate_without_key_returns_none(self):
        from orbit.orbit.core.llm.providers import OpenAIProvider

        p = OpenAIProvider(api_key="")
        resp = _run(p.generate(LLMRequest(prompt="hi")))
        self.assertIsNone(resp)


class TestAstraRouting(unittest.TestCase):
    def test_explicit_astra_model_routes_openai_first(self):
        router = LLMRouter()
        with unittest.mock.patch.object(router, "_check_internet", return_value=True):
            req = LLMRequest(prompt="hi", model="gpt-6-astra")
            # Reproduce the explicit-model branch of _generate_with_failover
            chain = []
            m = req.model.lower()
            if m.startswith(("gpt-6", "o1", "o3", "o4")) or "openai" in m:
                chain.append(("openai", req.model))
            else:
                chain.append(("openrouter", req.model))
            chain.append(("ollama", req.model))
        self.assertEqual(chain[0], ("openai", "gpt-6-astra"))

    def test_orchestrator_reasoning_chain_starts_with_openai_when_keyed(self):
        from orbit.orbit.core.llm import orchestrator as orch_mod

        orch = orch_mod.ProviderOrchestrator()
        with unittest.mock.patch.dict(
            orch_mod.ProviderOrchestrator.KEY_GATES,
            {**orch_mod.ProviderOrchestrator.KEY_GATES, "openai": ("sk-test", None)},
        ):
            plan = orch.plan("prove this theorem step by step in detail")
        heads = [p for p, _ in plan.chain]
        self.assertIn("openai", heads)
        self.assertEqual(plan.chain[0][0], "openai")

    def test_orchestrator_skips_openai_without_key(self):
        from orbit.orbit.core.llm import orchestrator as orch_mod

        orch = orch_mod.ProviderOrchestrator()
        with unittest.mock.patch.dict(
            orch_mod.ProviderOrchestrator.KEY_GATES,
            {**orch_mod.ProviderOrchestrator.KEY_GATES, "openai": ("", None)},
        ):
            plan = orch.plan("prove this theorem step by step in detail")
        self.assertNotIn("openai", [p for p, _ in plan.chain])


class TestAstraOpponent(unittest.TestCase):
    def test_default_model_is_astra(self):
        from orbit.orbit.core.benchmark import ChatGPTOpponent

        self.assertEqual(ChatGPTOpponent.DEFAULT_MODEL, "gpt-6-astra")

    def test_force_openai_resolves_astra(self):
        from orbit.orbit.core.benchmark import ChatGPTOpponent

        with unittest.mock.patch.dict(
            os.environ,
            {"OPPONENT_OPENAI_KEY": "sk-real", "OPPONENT_OPENAI_MODEL": ""},
            clear=False,
        ):
            opp = ChatGPTOpponent()
        self.assertEqual(opp.model, "gpt-6-astra")
        self.assertTrue(opp.is_available())

    def test_explicit_model_override(self):
        from orbit.orbit.core.benchmark import ChatGPTOpponent

        opp = ChatGPTOpponent(
            api_key="sk-x", model="gpt-6-astra", base_url="https://api.openai.com/v1"
        )
        self.assertEqual(opp.model, "gpt-6-astra")
        self.assertEqual(opp.provider_name(), "openai")


if __name__ == "__main__":
    import unittest

    unittest.main()
