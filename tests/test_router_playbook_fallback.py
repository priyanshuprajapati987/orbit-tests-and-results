"""Router battle-chain playbook fallback (2026-10-06 claim-closure round).

Playbook routes must never dead-end on dead online providers — every
non-empty battle chain guarantees a validated local ollama last-resort.
Before the fix, facts/general chains filtered down to a single 404-ing
Groq route = "All providers unavailable" while local Ollama sat idle
(ground-truth rerun hit 25/103 because of this).
"""

import os
import unittest
from unittest import mock

_KEYS = (
    "OPENROUTER_API_KEY",
    "GROQ_API_KEY",
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "CLOUDFLARE_API_KEY",
)


class TestPlaybookChainFallback(unittest.TestCase):
    @staticmethod
    def _chain(category, installed, online=True, keys=None):
        from orbit.orbit.core.llm.router import LLMRouter

        env = dict(keys) if keys is not None else {
            "OPENROUTER_API_KEY": "sk-test",
            "GROQ_API_KEY": "gsk-test",
            "GEMINI_API_KEY": "AIza-test",
            "OPENAI_API_KEY": "sk-oai-test",
            "CLOUDFLARE_API_KEY": "cf-test",
        }
        with mock.patch.dict(os.environ, env, clear=False), mock.patch.object(
            LLMRouter, "_installed_ollama_models", return_value=installed
        ):
            return LLMRouter()._get_battle_optimized_chain(category, online)

    def test_every_nonempty_chain_ends_with_ollama(self):
        for cat in ("facts", "general", "reasoning", "coding", "creative", "math"):
            chain = self._chain(cat, ["qwen3:8b"])
            if not chain:
                continue  # empty -> orchestrator plan fallback (plans end in ollama)
            self.assertEqual(chain[-1][0], "ollama", f"{cat}: {chain}")

    def test_keyless_dead_end_gains_local_fallback(self):
        # groq key present (facts playbook route survives) but the playbook
        # has no ollama entry — chain must gain validated local fallback,
        # not exhaust at the 404-ing groq route
        env = {k: "" for k in _KEYS}
        env["GROQ_API_KEY"] = "gsk-test"
        chain = self._chain("facts", ["qwen3:8b"], keys=env)
        self.assertTrue(chain, chain)
        self.assertEqual(chain[-1], ("ollama", "qwen3:8b"), chain)

    def test_offline_chain_only_ollama_entries(self):
        chain = self._chain("general", ["qwen3:8b"], online=False)
        if chain:
            self.assertTrue(all(p == "ollama" for p, _ in chain), chain)

    def test_substitutes_installed_model_when_playbook_model_missing(self):
        # playbook ollama entries like qwen2.5 are often uninstalled — the
        # chain must substitute an actually-installed model, not a 404 name
        chain = self._chain("reasoning", ["qwen3:8b", "deepseek-r1:14b"])
        ollama_entries = [m for p, m in chain if p == "ollama"]
        self.assertTrue(ollama_entries, chain)
        self.assertTrue(
            all(m in ("qwen3:8b", "deepseek-r1:14b") for m in ollama_entries),
            chain,
        )


if __name__ == "__main__":
    unittest.main()
