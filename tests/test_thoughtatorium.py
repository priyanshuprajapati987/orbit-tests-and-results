"""Unit tests for orbit/orbit/core/thoughtatorium.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

import orbit.core.thoughtatorium as tt
from orbit.core.thoughtatorium import spark


class TestSparkNoMaterial(unittest.TestCase):
    def test_no_fragments(self):
        with patch("orbit.core.thoughtatorium.run_llm_sync") as rl, \
             patch("orbit.core.companion_memory.get_companion_memory", side_effect=RuntimeError("no")):
            r = spark()
        self.assertFalse(r["ok"])
        self.assertIn("not enough material", r["error"])
        rl.assert_not_called()

    def test_single_fragment_not_enough(self):
        with patch("orbit.core.companion_memory.get_companion_memory") as gcm, \
             patch("orbit.core.dream_synthesis._gather_fragments", side_effect=RuntimeError("no")):
            gcm.return_value.timeline.return_value = [{"text": "only one"}]
            r = spark()
        self.assertFalse(r["ok"])
        self.assertIn("not enough material", r["error"])

    def test_both_sources_fail(self):
        with patch("orbit.core.companion_memory.get_companion_memory", side_effect=RuntimeError("x")), \
             patch("orbit.core.dream_synthesis._gather_fragments", side_effect=RuntimeError("y")):
            r = spark()
        self.assertFalse(r["ok"])


class TestSparkSuccess(unittest.TestCase):
    def _run(self, use_cache=True):
        with patch("orbit.core.companion_memory.get_companion_memory") as gcm, \
             patch("orbit.core.dream_synthesis._gather_fragments") as gg, \
             patch("orbit.core.thoughtatorium.run_llm_sync") as rl, \
             patch("orbit.core.llm.router.get_router") as gr, \
             patch("orbit.core.llm.router.LLMRequest") as lreq:
            gcm.return_value.timeline.return_value = [
                {"text": "a1"}, {"text": "a2"}, {"text": "a3"},
            ]
            gg.return_value = ["b1", "b2"]
            resp = MagicMock()
            resp.content = "  Insight about life.  "
            resp.success = True
            rl.return_value = resp
            gr.return_value.generate.return_value = "req-obj"
            r = spark(use_cache=use_cache)
            return r, rl, gr, lreq, gcm, gg

    def test_success_insight(self):
        r, rl, gr, lreq, gcm, gg = self._run()
        self.assertTrue(r["ok"])
        self.assertEqual(r["insight"], "Insight about life.")
        self.assertEqual(len(r["seeds"]), 2)

    def test_llm_called_with_offline_request(self):
        r, rl, gr, lreq, gcm, gg = self._run()
        lreq.assert_called_once()
        kwargs = lreq.call_args.kwargs
        self.assertTrue(kwargs["force_offline"])
        self.assertEqual(kwargs["max_tokens"], 220)
        self.assertIn("You are ORBIT's background mind", kwargs["prompt"])

    def test_use_cache_false_propagates(self):
        r, rl, gr, lreq, gcm, gg = self._run(use_cache=False)
        self.assertFalse(lreq.call_args.kwargs["use_cache"])

    def test_shuffled_pick_max_4(self):
        # 5 fragments total -> pick = min(4, 5) = 4
        r, rl, gr, lreq, gcm, gg = self._run()
        # seeds is pick[:2] so always 2
        self.assertEqual(len(r["seeds"]), 2)

    def test_seeds_subset_of_fragments(self):
        r, rl, gr, lreq, gcm, gg = self._run()
        all_frags = {"a1", "a2", "a3", "b1", "b2"}
        for s in r["seeds"]:
            self.assertIn(s, all_frags)


class TestSparkFailure(unittest.TestCase):
    def _base_patches(self):
        gcm = patch("orbit.core.companion_memory.get_companion_memory")
        gg = patch("orbit.core.dream_synthesis._gather_fragments")
        return gcm, gg

    def test_llm_returns_failed(self):
        gcm_p, gg_p = self._base_patches()
        gcm = gcm_p.start()
        gg = gg_p.start()
        gcm.return_value.timeline.return_value = [{"text": "x"}, {"text": "y"}]
        gg.return_value = []
        try:
            with patch("orbit.core.thoughtatorium.run_llm_sync") as rl, \
                 patch("orbit.core.llm.router.get_router") as gr, \
                 patch("orbit.core.llm.router.LLMRequest"):
                resp = MagicMock()
                resp.success = False
                resp.content = ""
                rl.return_value = resp
                r = spark()
            self.assertFalse(r["ok"])
            self.assertEqual(r["error"], "insight failed")
        finally:
            gcm_p.stop()
            gg_p.stop()

    def test_llm_empty_content(self):
        gcm_p, gg_p = self._base_patches()
        gcm = gcm_p.start()
        gg = gg_p.start()
        gcm.return_value.timeline.return_value = [{"text": "x"}, {"text": "y"}]
        gg.return_value = []
        try:
            with patch("orbit.core.thoughtatorium.run_llm_sync") as rl, \
                 patch("orbit.core.llm.router.get_router") as gr, \
                 patch("orbit.core.llm.router.LLMRequest"):
                resp = MagicMock()
                resp.success = True
                resp.content = "   "
                rl.return_value = resp
                r = spark()
            self.assertFalse(r["ok"])
            self.assertEqual(r["error"], "insight failed")
        finally:
            gcm_p.stop()
            gg_p.stop()

    def test_llm_raises(self):
        gcm_p, gg_p = self._base_patches()
        gcm = gcm_p.start()
        gg = gg_p.start()
        gcm.return_value.timeline.return_value = [{"text": "x"}, {"text": "y"}]
        gg.return_value = []
        try:
            with patch("orbit.core.thoughtatorium.run_llm_sync", side_effect=RuntimeError("llm down")), \
                 patch("orbit.core.llm.router.get_router") as gr, \
                 patch("orbit.core.llm.router.LLMRequest"):
                r = spark()
            self.assertFalse(r["ok"])
            self.assertEqual(r["error"], "insight failed")
        finally:
            gcm_p.stop()
            gg_p.stop()

    def test_router_generate_raises(self):
        gcm_p, gg_p = self._base_patches()
        gcm = gcm_p.start()
        gg = gg_p.start()
        gcm.return_value.timeline.return_value = [{"text": "x"}, {"text": "y"}]
        gg.return_value = []
        try:
            with patch("orbit.core.thoughtatorium.run_llm_sync") as rl, \
                 patch("orbit.core.llm.router.get_router", side_effect=RuntimeError("router")), \
                 patch("orbit.core.llm.router.LLMRequest"):
                r = spark()
            self.assertFalse(r["ok"])
            self.assertEqual(r["error"], "insight failed")
        finally:
            gcm_p.stop()
            gg_p.stop()


if __name__ == "__main__":
    unittest.main()
