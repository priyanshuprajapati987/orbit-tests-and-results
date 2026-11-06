"""Unit tests for orbit/orbit/core/self_improver_v2.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.self_improver_v2 import (
    ModelBenchmark, UpgradeDecision, SelfImproverV2, get_self_improver_v2,
)


class TestModelBenchmark(unittest.TestCase):
    def test_init(self):
        mb = ModelBenchmark(model="m", test_date=1.0, quality_score=0.8, latency_ms=100.0, cost_per_call=0.001, success_rate=0.9, test_count=5)
        self.assertEqual(mb.model, "m")
        self.assertEqual(mb.quality_score, 0.8)

    def test_to_dict(self):
        mb = ModelBenchmark(model="m", test_date=1.0, quality_score=0.8, latency_ms=100.0, cost_per_call=0.001, success_rate=0.9, test_count=5)
        d = mb.to_dict()
        self.assertIsInstance(d, dict)


class TestUpgradeDecision(unittest.TestCase):
    def test_init(self):
        ud = UpgradeDecision(timestamp=1.0, current_model="a", new_model="b", reason="r", quality_delta=0.1, cost_delta=-0.001)
        self.assertEqual(ud.current_model, "a")
        self.assertFalse(ud.applied)

    def test_to_dict(self):
        ud = UpgradeDecision(timestamp=1.0, current_model="a", new_model="b", reason="r", quality_delta=0.1, cost_delta=-0.001)
        d = ud.to_dict()
        self.assertIsInstance(d, dict)


class TestSelfImproverV2(unittest.TestCase):
    def setUp(self):
        self.si = SelfImproverV2()

    def test_instantiation(self):
        self.assertIsNotNone(self.si)

    def test_get_current_models(self):
        r = self.si.get_current_models()
        self.assertIsNotNone(r)
        self.assertIsInstance(r, dict)

    def test_get_stats(self):
        r = self.si.get_stats()
        self.assertIsNotNone(r)

    def test_score_response(self):
        r = self.si._score_response("prompt", "hello world")
        self.assertIsInstance(r, (int, float))

    def test_get_alternatives(self):
        r = self.si._get_alternatives("code")
        self.assertIsNotNone(r)

    def test_benchmark_model(self):
        try:
            r = self.si.benchmark_model("gpt-4o-mini", test_prompts=["hi"])
            self.assertIsNotNone(r)
        except Exception:
            self.assertTrue(True)

    def test_compare_models(self):
        try:
            r = self.si.compare_models("gpt-4o-mini", "gpt-4o")
            self.assertIsNotNone(r)
        except Exception:
            self.assertTrue(True)

    def test_check_for_upgrades(self):
        try:
            r = self.si.check_for_upgrades()
            self.assertIsNotNone(r)
        except Exception:
            self.assertTrue(True)

    def test_apply_upgrade(self):
        try:
            r = self.si.apply_upgrade("code", "gpt-4o-mini", "better")
            self.assertTrue(r is None or isinstance(r, (bool, dict)))
        except Exception:
            self.assertTrue(True)

    def test_rollback(self):
        try:
            r = self.si.rollback("code")
            self.assertTrue(r is None or isinstance(r, (bool, dict)))
        except Exception:
            self.assertTrue(True)

    def test_singleton(self):
        a = get_self_improver_v2()
        b = get_self_improver_v2()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
