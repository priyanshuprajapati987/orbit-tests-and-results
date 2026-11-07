"""Unit tests for orbit/orbit/core/consensus_engine.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

import orbit.core.consensus_engine as ce
from orbit.core.consensus_engine import ConsensusEngine, get_consensus_engine


class TestConsensusEngine(unittest.TestCase):
    def test_empty_providers(self):
        e = ConsensusEngine([])
        r = e.query("q")
        self.assertIsNone(r["answer"])
        self.assertEqual(r["consensus"], 0.0)
        self.assertEqual(r["responses"], [])

    def test_majority(self):
        e = ConsensusEngine([lambda p: "yes", lambda p: "yes", lambda p: "no"])
        r = e.query("q")
        self.assertEqual(r["answer"], "yes")
        self.assertAlmostEqual(r["consensus"], 2 / 3, places=2)

    def test_unanimous(self):
        e = ConsensusEngine([lambda p: "ok", lambda p: "ok"])
        r = e.query("q")
        self.assertEqual(r["answer"], "ok")
        self.assertEqual(r["consensus"], 1.0)

    def test_no_majority_picks_longest(self):
        e = ConsensusEngine([lambda p: "a", lambda p: "b", lambda p: "a much longer response"])
        r = e.query("q")
        self.assertEqual(r["answer"], "a much longer response")
        self.assertAlmostEqual(r["consensus"], 1 / 3, places=2)

    def test_provider_exception_skipped(self):
        def bad(p):
            raise RuntimeError("fail")

        e = ConsensusEngine([bad, lambda p: "ok"])
        r = e.query("q")
        self.assertEqual(r["answer"], "ok")
        self.assertEqual(r["responses"], ["ok"])

    def test_all_providers_fail(self):
        def bad(p):
            raise RuntimeError("fail")

        e = ConsensusEngine([bad, bad])
        r = e.query("q")
        self.assertIsNone(r["answer"])
        self.assertEqual(r["consensus"], 0.0)

    def test_responses_passed_prompt(self):
        seen = []

        def p(prompt):
            seen.append(prompt)
            return "r"

        e = ConsensusEngine([p])
        e.query("hello")
        self.assertEqual(seen, ["hello"])

    def test_singleton_no_providers(self):
        ce._engine = None
        a = get_consensus_engine()
        b = get_consensus_engine()
        self.assertIs(a, b)
        self.assertEqual(a.providers, [])

    def test_singleton_with_providers_first_call(self):
        ce._engine = None
        a = get_consensus_engine([lambda p: "x"])
        self.assertEqual(len(a.providers), 1)
        ce._engine = None  # cleanup


if __name__ == "__main__":
    unittest.main()
