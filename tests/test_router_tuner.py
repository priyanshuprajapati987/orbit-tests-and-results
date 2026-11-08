"""Unit tests for orbit/orbit/core/router_tuner.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.router_tuner import RouterTuner, get_router_tuner, _score


class TestScore(unittest.TestCase):
    def test_success_fast(self):
        self.assertAlmostEqual(_score(500.0, True), 1.0, places=2)

    def test_success_slow(self):
        self.assertAlmostEqual(_score(5000.0, True), 0.1, places=2)

    def test_failure(self):
        self.assertEqual(_score(100.0, False), 0.0)

    def test_zero_latency(self):
        self.assertAlmostEqual(_score(0.0, True), 1.0, places=2)

    def test_min_floor(self):
        self.assertEqual(_score(100000.0, True), 0.05)


class TestRouterTuner(unittest.TestCase):
    def setUp(self):
        self.t = RouterTuner()

    def test_record_ignored_empty(self):
        self.t.record("", "prov", 100, True)
        self.t.record("qt", "", 100, True)
        self.assertEqual(self.t.stats(), {})

    def test_record_updates(self):
        self.t.record("chat", "groq", 500, True)
        s = self.t.stats()
        self.assertIn("chat", s)
        self.assertIn("groq", s["chat"])
        self.assertEqual(s["chat"]["groq"]["calls"], 1)
        self.assertGreater(s["chat"]["groq"]["score"], 0)

    def test_record_failure_score_zero(self):
        self.t.record("chat", "groq", 100, False)
        s = self.t.stats()
        self.assertEqual(s["chat"]["groq"]["score"], 0.0)

    def test_optimize_chain_empty(self):
        self.assertEqual(self.t.optimize_chain("chat", []), [])

    def test_optimize_chain_unseen_mid_priority(self):
        chain = [("provA", "m1"), ("provB", "m2")]
        out = self.t.optimize_chain("chat", chain)
        # both unseen -> both 0.5 -> stable sort? sorted reverse; ties keep original order in python stable sort
        self.assertEqual(len(out), 2)

    def test_optimize_chain_reorders(self):
        self.t.record("chat", "slow", 5000, True)
        self.t.record("chat", "fast", 100, True)
        chain = [("slow", "m1"), ("fast", "m2")]
        out = self.t.optimize_chain("chat", chain)
        self.assertEqual(out[0][0], "fast")

    def test_optimize_chain_does_not_mutate_input(self):
        chain = [("a", "m")]
        out = self.t.optimize_chain("chat", chain)
        self.assertEqual(chain, [("a", "m")])

    def test_stats_empty(self):
        self.assertEqual(self.t.stats(), {})

    def test_reset(self):
        self.t.record("chat", "groq", 100, True)
        self.t.reset()
        self.assertEqual(self.t.stats(), {})

    def test_thread_safety_smoke(self):
        import threading
        def worker():
            for _ in range(50):
                self.t.record("chat", "groq", 200, True)
        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        s = self.t.stats()
        self.assertEqual(s["chat"]["groq"]["calls"], 200)

    def test_singleton(self):
        a = get_router_tuner()
        b = get_router_tuner()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
