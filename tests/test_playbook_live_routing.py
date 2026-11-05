"""Playbook live-routing (Tier 1.1 — 2026-10-17).

The optimization playbooks are consulted FIRST by `_run_failover_chain`,
but their key gate used to be a bare ``os.getenv`` lookup. Three gaps made
"reasoning/facts route online when available" silently false:

1. A BYOK key saved at runtime in the provider vault never enabled a
   playbook route (the orchestrator plan saw it, the playbook path did
   not — and the playbook path wins the ``if battle_chain:`` branch).
2. A keyless local OmniRouter gateway (the only online provider in
   keyless envs) was dropped for the same reason.
3. The classifier/legacy categories say ``code`` while the playbook
   registry says ``coding`` — live code queries never hit the coding
   playbook at all.

Plus: callers that preset ``system_prompt`` (most agents) skipped
classification entirely, so ``request.category`` stayed None and the
chain fell back to the "general" playbook for every query type.
"""

import os
import unittest
from unittest import mock

_KEY_ENV = (
    "OPENROUTER_API_KEY",
    "GROQ_API_KEY",
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "CLOUDFLARE_API_TOKEN",
)


def _chain(category, installed=None, online=True, env=None, vault=None, gateway=False):
    from orbit.orbit.core.llm.router import LLMRouter

    if installed is None:
        from orbit.orbit.core.config import DEFAULT_OLLAMA_MODEL

        installed = (DEFAULT_OLLAMA_MODEL, "qwen3:8b")
    env = dict(env) if env is not None else {k: "" for k in _KEY_ENV}

    def _vault(provider):
        if isinstance(vault, dict):
            return vault.get(provider)
        return vault

    with mock.patch.dict(os.environ, env, clear=False), mock.patch(
        "orbit.orbit.core.provider_keys.get_provider_key", side_effect=_vault
    ), mock.patch(
        "orbit.orbit.core.llm.orchestrator._gateway_reachable", return_value=gateway
    ), mock.patch.object(
        LLMRouter, "_installed_ollama_models", return_value=list(installed)
    ):
        return LLMRouter()._get_battle_optimized_chain(category, online)


class TestVaultAndGatewayRouting(unittest.TestCase):
    def test_vault_key_routes_online_without_env_key(self):
        # All env keys blank, but a runtime-saved vault key must flip the
        # playbook's openrouter route on (the core Tier-1.1 promise).
        chain = _chain("reasoning", vault={"openrouter": "sk-vault-live"})
        self.assertTrue(chain, chain)
        self.assertEqual(chain[0], ("openrouter", "deepseek/deepseek-r1"), chain)
        self.assertEqual(chain[-1][0], "ollama", chain)

    def test_keyless_gateway_reachable_routes_online(self):
        # No keys anywhere, but the local OmniRouter gateway answers —
        # reasoning must prefer the online gateway over local ollama.
        chain = _chain("reasoning", vault=None, gateway=True)
        self.assertTrue(chain, chain)
        self.assertEqual(chain[0], ("openrouter", "deepseek/deepseek-r1"), chain)
        self.assertEqual(chain[-1][0], "ollama", chain)

    def test_keyless_gateway_down_stays_local_only(self):
        chain = _chain("reasoning", vault=None, gateway=False)
        self.assertTrue(chain, chain)
        self.assertTrue(all(p == "ollama" for p, _ in chain), chain)

    def test_all_dead_category_without_local_entry_falls_to_plan(self):
        # facts' playbook has no ollama route; with every online provider
        # dead the chain is [] on purpose -> _run_failover_chain falls back
        # to the orchestrator plan (which guarantees its own ollama leg).
        self.assertEqual(_chain("facts", vault=None, gateway=False), [])

    def test_placeholder_env_key_is_not_a_key(self):
        env = {k: "" for k in _KEY_ENV}
        env["OPENROUTER_API_KEY"] = "your_openrouter_api_key_here"
        chain = _chain("reasoning", env=env, gateway=False)
        self.assertTrue(chain, chain)
        self.assertFalse(any(p == "openrouter" for p, _ in chain), chain)

    def test_calltime_env_key_enables_provider(self):
        env = {k: "" for k in _KEY_ENV}
        env["OPENROUTER_API_KEY"] = "sk-live-exported"
        chain = _chain("reasoning", env=env, gateway=False)
        self.assertTrue(chain, chain)
        self.assertEqual(chain[0][0], "openrouter", chain)

    def test_offline_ignores_vault_and_gateway(self):
        chain = _chain(
            "reasoning",
            online=False,
            vault={"openrouter": "sk-vault-live"},
            gateway=True,
        )
        self.assertTrue(chain, chain)
        self.assertTrue(all(p == "ollama" for p, _ in chain), chain)

    def test_empty_playbook_falls_back_to_plan(self):
        # "fast" has no playbook -> [] -> _run_failover_chain uses the plan
        self.assertEqual(_chain("fast", gateway=True), [])


class TestCodeCategoryAlias(unittest.TestCase):
    def test_classifier_code_reaches_coding_playbook(self):
        # Without the code->coding alias, PLAYBOOKS.get("code") misses and
        # the chain is [] (silent fallback to the generic plan).
        env = {k: "sk-live-1" for k in _KEY_ENV}
        chain = _chain("code", env=env, gateway=False)
        self.assertTrue(chain, chain)
        self.assertEqual(chain[0], ("openrouter", "qwen/qwen3-coder"), chain)

    def test_gt_style_coding_category_still_works(self):
        env = {k: "sk-live-1" for k in _KEY_ENV}
        chain = _chain("coding", env=env, gateway=False)
        self.assertEqual(chain[0], ("openrouter", "qwen/qwen3-coder"), chain)


class TestPresetSystemPromptClassification(unittest.TestCase):
    def test_category_resolved_even_with_preset_system_prompt(self):
        from orbit.orbit.core.llm.router import LLMRequest, LLMResponse, LLMRouter

        captured = {}

        async def _failover(request):
            captured["request"] = request
            return LLMResponse(
                content="ok", provider="test", model="m", latency_ms=1, success=True
            )

        async def _reflect(request, response):
            return response

        req = LLMRequest(
            prompt=(
                "Why does the sky appear blue? Think through the physics "
                "step by step before answering."
            ),
            system_prompt="AGENT STATION PROMPT",
            use_cache=False,
        )
        with mock.patch.object(LLMRouter, "_generate_with_failover", side_effect=_failover), mock.patch.object(
            LLMRouter, "_maybe_reflect", side_effect=_reflect
        ), mock.patch.object(LLMRouter, "_audit_call", return_value=None), mock.patch(
            "orbit.orbit.core.kill_switch.get_trust_manager",
            return_value=mock.Mock(can_act=lambda *a, **kw: {"allowed": True}),
        ):
            import asyncio

            resp = asyncio.run(LLMRouter().generate(req))

        self.assertTrue(resp.success)
        self.assertIsNotNone(captured.get("request"))
        # classified -> playbook categories work for preset-SP requests
        self.assertEqual(req.category, "reasoning")
        # caller's system prompt must NOT be overwritten
        self.assertEqual(req.system_prompt, "AGENT STATION PROMPT")
        self.assertIsNotNone(getattr(req, "_cached_plan", None))

    def test_missing_system_prompt_still_injected(self):
        from orbit.orbit.core.llm.router import LLMRequest, LLMResponse, LLMRouter

        async def _failover(request):
            return LLMResponse(
                content="ok", provider="test", model="m", latency_ms=1, success=True
            )

        async def _reflect(request, response):
            return response

        req = LLMRequest(prompt="capital of france?", use_cache=False)
        with mock.patch.object(LLMRouter, "_generate_with_failover", side_effect=_failover), mock.patch.object(
            LLMRouter, "_maybe_reflect", side_effect=_reflect
        ), mock.patch.object(LLMRouter, "_audit_call", return_value=None), mock.patch(
            "orbit.orbit.core.kill_switch.get_trust_manager",
            return_value=mock.Mock(can_act=lambda *a, **kw: {"allowed": True}),
        ):
            import asyncio

            asyncio.run(LLMRouter().generate(req))

        self.assertEqual(req.category, "facts")
        self.assertTrue(req.system_prompt)
        self.assertNotEqual(req.system_prompt, "AGENT STATION PROMPT")


class TestLocalModelPreference(unittest.TestCase):
    def test_quality_local_preferred_over_small_default(self):
        # Both installed: the playbook wants a quality local model — qwen3:8b
        # must win over a small/fast DEFAULT_OLLAMA_MODEL (qwen3:1.7b in .env).
        chain = _chain(
            "reasoning",
            installed=("qwen3:1.7b", "qwen3:8b"),
            gateway=False,
        )
        self.assertEqual(chain[-1], ("ollama", "qwen3:8b"), chain)

    def test_default_used_when_quality_model_missing(self):
        # Only the default installed -> substitution still lands on it.
        chain = _chain(
            "reasoning",
            installed=("qwen3:1.7b",),
            gateway=False,
        )
        self.assertEqual(chain[-1], ("ollama", "qwen3:1.7b"), chain)

    def test_hardware_tested_model_beats_small_default(self):
        # qwen3:8b not installed (unpulled / OOM environment): the
        # Phase-1 hardware-tested llama3.2 must win over the 1.7b default.
        chain = _chain(
            "reasoning",
            installed=("llama3.2:latest", "qwen3:1.7b"),
            gateway=False,
        )
        self.assertEqual(chain[-1], ("ollama", "llama3.2:latest"), chain)

    def test_guarantee_leg_uses_quality_preference(self):
        # facts has no local route; guarantee appends the quality model when
        # at least one online provider survived.
        env = {k: "sk-live-1" for k in _KEY_ENV}
        chain = _chain(
            "facts",
            installed=("qwen3:1.7b", "qwen3:8b"),
            env=env,
            gateway=False,
        )
        self.assertTrue(chain, chain)
        self.assertEqual(chain[-1], ("ollama", "qwen3:8b"), chain)


if __name__ == "__main__":
    unittest.main()
