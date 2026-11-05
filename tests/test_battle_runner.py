"""
Tests for the real-ChatGPT battle infra (Day 33 PM):
  * OPPONENT_OPENAI_KEY forces the ACTUAL ChatGPT backend
  * core/battle.py prompt loading + summarize + payload
  * POST /api/benchmark/battle endpoint (engine mocked -> deterministic)
"""

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import orbit.orbit.core.benchmark as bm


def _fake_result(
    prompt, winner="jarvus", provider="mock", model="gpt-4o-mini", latency=50.0
):
    return {
        "prompt": prompt,
        "jarvus": {"text": "answer", "latency_ms": latency, "model_used": "test"},
        "opponent": {
            "text": "other",
            "latency_ms": latency * 2,
            "model": model,
            "provider": provider,
        },
        "accuracy_score": 0.5,
        "context_retention": 0.6,
        "composite": {"total": 0.7 if winner == "jarvus" else 0.3, "winner": winner},
    }


class TestOpponentKeyResolution(unittest.TestCase):
    def setUp(self):
        self._saved = {
            k: os.environ.get(k)
            for k in (
                "OPPONENT_OPENAI_KEY",
                "OPPONENT_OPENAI_MODEL",
                "OPPONENT_API_KEY",
                "OPPONENT_MODEL",
                "OPPONENT_BASE_URL",
                "OPENAI_API_KEY",
                "GROQ_API_KEY",
                "CEREBRAS_API_KEY",
                "GEMINI_API_KEY",
            )
        }
        for k in self._saved:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_forces_actual_chatgpt_backend(self):
        os.environ["OPPONENT_OPENAI_KEY"] = "sk-real-openai-key"
        opp = bm.ChatGPTOpponent()
        self.assertTrue(opp.is_available())
        self.assertEqual(opp.provider_name(), "openai")
        self.assertTrue(opp.base_url.startswith("https://api.openai.com"))
        self.assertEqual(opp.model, "gpt-6-astra")

    def test_opponent_openai_model_override(self):
        os.environ["OPPONENT_OPENAI_KEY"] = "sk-real-openai-key"
        os.environ["OPPONENT_OPENAI_MODEL"] = "gpt-4o"
        opp = bm.ChatGPTOpponent()
        self.assertEqual(opp.model, "gpt-4o")

    def test_beats_generic_and_fallback_keys(self):
        os.environ["OPPONENT_OPENAI_KEY"] = "sk-real-openai-key"
        os.environ["OPPONENT_API_KEY"] = "sk-other-provider"
        os.environ["GROQ_API_KEY"] = "gsk-groq-key"
        opp = bm.ChatGPTOpponent()
        self.assertEqual(opp.provider_name(), "openai")

    def test_placeholder_key_rejected(self):
        os.environ["OPPONENT_OPENAI_KEY"] = "your_orbit_api_key_here"
        opp = bm.ChatGPTOpponent()
        self.assertFalse(opp.is_available())

    def test_missing_key_falls_through_to_openai(self):
        os.environ.pop("OPPONENT_OPENAI_KEY", None)
        os.environ["OPENAI_API_KEY"] = "sk-real-openai-key"
        opp = bm.ChatGPTOpponent()
        self.assertTrue(opp.is_available())
        self.assertEqual(opp.provider_name(), "openai")


class TestBattleModule(unittest.TestCase):
    def test_load_prompts_full(self):
        from orbit.orbit.core.battle import load_prompts

        cats = load_prompts()
        self.assertEqual(
            set(cats),
            {"reasoning", "coding", "creative", "facts", "math", "multi_turn"},
        )
        self.assertEqual(len(cats["math"]), 20)
        self.assertEqual(len(cats["multi_turn"]), 20)
        self.assertTrue(all(isinstance(p, list) for p in cats["multi_turn"]))
        self.assertTrue(all(len(p) >= 3 for p in cats["multi_turn"]))

    def test_load_prompts_quick_and_category(self):
        from orbit.orbit.core.battle import load_prompts

        cats = load_prompts(quick=True)
        self.assertTrue(all(len(ps) == 5 for ps in cats.values()))
        only = load_prompts(category="coding", n=3)
        self.assertEqual(list(only), ["coding"])
        self.assertEqual(len(only["coding"]), 3)

    def test_load_prompts_bad_category(self):
        from orbit.orbit.core.battle import load_prompts

        with self.assertRaises(ValueError):
            load_prompts(category="nope")

    def test_summarize_counts_and_voids(self):
        from orbit.orbit.core.battle import summarize

        results = {
            "math": {
                "prompts": ["a", "b", "c"],
                "results": [
                    _fake_result("a", "jarvus"),
                    _fake_result("b", "jarvus"),
                    {
                        "prompt": "c",
                        "opponent_error": True,
                        "composite": {"winner": "void"},
                    },
                ],
                "win_rate": 1.0,
                "voids": 1,
            },
            "coding": {
                "prompts": ["d", "e"],
                "results": [
                    _fake_result("d", "opponent", provider="openai"),
                    _fake_result("e", "opponent", provider="openai"),
                ],
                "win_rate": 0.0,
                "voids": 0,
            },
        }
        s = summarize(results)
        self.assertEqual(s["total_wins"], 2)
        self.assertEqual(s["total_complete"], 4)
        self.assertEqual(s["overall_win_rate"], 0.5)
        by_cat = {c["category"]: c for c in s["categories"]}
        self.assertEqual(by_cat["math"]["voids"], 1)
        self.assertTrue(by_cat["math"]["pass"])
        self.assertFalse(by_cat["coding"]["pass"])
        self.assertIn("gpt-4o-mini", s["opponent"])

    def test_build_payload_and_save(self):
        from orbit.orbit.core.battle import build_payload, save_battle

        results = {
            "custom": {
                "prompts": ["x"],
                "results": [_fake_result("x")],
                "win_rate": 1.0,
                "voids": 0,
            }
        }
        payload = build_payload(results, quick=True, elapsed_seconds=3.5)
        self.assertEqual(payload["quick"], True)
        self.assertEqual(payload["elapsed_seconds"], 3.5)
        self.assertIn("summary", payload)
        with tempfile.TemporaryDirectory() as td:
            p = save_battle(payload, str(Path(td) / "b.json"))
            saved = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(saved["summary"]["overall_win_rate"], 1.0)


class TestBattleAPI(unittest.TestCase):
    def setUp(self):
        from orbit.orbit.server import create_app

        self.app = create_app()
        self.client = self.app.test_client()
        self._tmp = tempfile.TemporaryDirectory()
        self._file = str(Path(self._tmp.name) / "battle_test.json")

    def tearDown(self):
        self._tmp.cleanup()

    @mock.patch("orbit.orbit.core.battle.get_benchmark_engine")
    def test_battle_endpoint_with_custom_prompts(self, m_engine):
        async def _fake_compare(prompt, **kw):
            return _fake_result(prompt)

        m_engine.return_value.compare_single.side_effect = _fake_compare
        r = self.client.post(
            "/api/benchmark/battle",
            json={
                "prompts": ["2+2", "write a haiku"],
                "filepath": self._file,
                "system_prompt": "be concise",
            },
        )
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        data = r.get_json()
        self.assertEqual(data["summary"]["total_complete"], 2)
        self.assertEqual(data["summary"]["overall_win_rate"], 1.0)
        self.assertTrue(Path(self._file).exists())

    def test_battle_endpoint_requires_prompts_list(self):
        r = self.client.post("/api/benchmark/battle", json={"prompts": "nope"})
        self.assertEqual(r.status_code, 400)

    def test_battle_last_empty(self):
        import orbit.orbit.core.battle as bm

        orig = bm.DEFAULT_BATTLE_FILE
        bm.DEFAULT_BATTLE_FILE = bm.BATTLE_DIR / "nonexistent_battle_file.json"
        try:
            r = self.client.get("/api/benchmark/battle/last")
            self.assertEqual(r.status_code, 404)
        finally:
            bm.DEFAULT_BATTLE_FILE = orig


class TestGroundTruthAPI(unittest.TestCase):
    def setUp(self):
        from orbit.orbit.server import create_app

        self.app = create_app()
        self.client = self.app.test_client()

    def test_ground_truth_status(self):
        r = self.client.get("/api/benchmark/ground-truth/status")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertGreaterEqual(data["total"], 90)
        self.assertIn("facts", data["items"])

    def test_ground_truth_last_empty(self):
        import orbit.orbit.core.ground_truth as gt

        self._orig_file = gt.DEFAULT_GT_FILE
        gt.DEFAULT_GT_FILE = gt.GT_DIR / "test_ground_truth_absent.json"
        try:
            if gt.DEFAULT_GT_FILE.exists():
                gt.DEFAULT_GT_FILE.unlink()
            r = self.client.get("/api/benchmark/ground-truth/last")
            self.assertEqual(r.status_code, 404)
        finally:
            gt.DEFAULT_GT_FILE = self._orig_file

    @mock.patch("orbit.orbit.core.llm.router.get_router")
    def test_ground_truth_run(self, m_router):
        async def _fake(req):
            from orbit.orbit.core.llm.router import LLMResponse

            return LLMResponse(
                content="The capital is Canberra.",
                provider="mock",
                model="m",
                latency_ms=5,
                success=True,
            )

        m_router.return_value.generate.side_effect = _fake
        with tempfile.TemporaryDirectory() as td:
            out = str(Path(td) / "gt.json")
            r = self.client.post(
                "/api/benchmark/ground-truth/run",
                json={"category": "facts", "n": 2, "filepath": out},
            )
            self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
            data = r.get_json()
            self.assertEqual(data["summary"]["total"], 2)
            self.assertTrue(Path(data["saved_to"]).exists())

    def test_ground_truth_run_bad_prompts(self):
        r = self.client.post(
            "/api/benchmark/ground-truth/run", json={"prompts": "nope"}
        )
        self.assertEqual(r.status_code, 400)


class TestOptimizeAPI(unittest.TestCase):
    def setUp(self):
        from orbit.orbit.server import create_app

        self.app = create_app()
        self.client = self.app.test_client()

    def test_optimize_with_payload(self):
        cats = {
            "facts": {
                "prompts": ["a"],
                "results": [_fake_result("a", "jarvus")],
                "win_rate": 1.0,
                "voids": 0,
            }
        }
        r = self.client.post(
            "/api/benchmark/optimize",
            json={"payload": {"categories": cats, "summary": {"opponent": "Mock"}}},
        )
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        data = r.get_json()
        self.assertEqual(data["overall_win_rate"], 1.0)
        self.assertEqual(data["overall_severity"], "MAINTENANCE")
        self.assertEqual(data["categories"][0]["category"], "facts")

    def test_optimize_bad_file(self):
        r = self.client.post(
            "/api/benchmark/optimize", json={"battle_file": "nope.json"}
        )
        self.assertEqual(r.status_code, 400)

    def test_optimize_last_empty(self):
        import orbit.orbit.core.battle as bm

        orig = bm.DEFAULT_BATTLE_FILE
        bm.DEFAULT_BATTLE_FILE = bm.BATTLE_DIR / "nonexistent_battle_file.json"
        try:
            r = self.client.get("/api/benchmark/optimize/last")
            self.assertEqual(r.status_code, 404)
        finally:
            bm.DEFAULT_BATTLE_FILE = orig


class TestJarvusErrorHandling(unittest.TestCase):
    """JARVUS generation failures must be recorded as errors, not opponent wins,
    and must be excluded from the win-rate denominator (SUCCESS != FAILURE)."""

    def test_jarvus_error_marks_status(self):
        async def _run():
            engine = bm.BenchmarkEngine()
            captured = {}

            async def _fake_orbit(p, **kw):
                captured.update(kw)

            with (
                mock.patch.object(engine, "_run_orbit", _fake_orbit),
                mock.patch.object(
                    engine,
                    "_run_chatgpt",
                    return_value={"text": "ok", "latency_ms": 10},
                ),
            ):
                res = await engine.compare_single(
                    "who wrote romeo and juliet", local=True
                )
            self.assertTrue(res.get("jarvus_error"))
            self.assertEqual(res.get("status"), "error")
            self.assertEqual(res.get("composite", {}).get("winner"), "error")
            # system_prompt must flow through as None so the router applies the
            # category-aware prompt (FACTS_PROMPT), not the explanation prompt.
            self.assertIsNone(captured.get("system_prompt"))

        asyncio.run(_run())

    def test_jarvus_error_excluded_from_summary(self):
        from orbit.orbit.core.battle import summarize

        res = {
            "prompt": "x",
            "jarvus_error": True,
            "status": "error",
            "composite": {"winner": "error"},
        }
        all_results = {
            "facts": {
                "prompts": ["x"],
                "results": [res],
                "win_rate": 0.0,
                "voids": 0,
                "jarvus_errors": 1,
            }
        }
        s = summarize(all_results)
        self.assertEqual(s["total_complete"], 0)
        self.assertEqual(s["categories"][0]["jarvus_errors"], 1)


class TestRoutingFallback(unittest.TestCase):
    """FACTS/SEARCH must degrade to local Ollama when cloud keys are dead
    (was the cause of the 3/5 facts errors in the baseline battle)."""

    def test_facts_and_search_chains_end_in_ollama(self):
        from orbit.orbit.core.llm.orchestrator import ProviderOrchestrator, QueryType

        self.assertEqual(ProviderOrchestrator.ROUTES[QueryType.FACTS][-1][0], "ollama")
        self.assertEqual(ProviderOrchestrator.ROUTES[QueryType.SEARCH][-1][0], "ollama")

    def test_degenerate_opponent_detection(self):
        # Opponent "User Safety: safe" stubs must be voided, not scored as wins.
        self.assertTrue(bm._is_degenerate_opponent("User Safety: safe"))
        self.assertTrue(
            bm._is_degenerate_opponent("I'm sorry, but I can't help with that.")
        )
        # Real short answers must NOT be voided.
        self.assertFalse(bm._is_degenerate_opponent("Canberra"))
        self.assertFalse(bm._is_degenerate_opponent("56"))
        self.assertFalse(bm._is_degenerate_opponent("The derivative of x^2 is 2x."))


if __name__ == "__main__":
    unittest.main()
