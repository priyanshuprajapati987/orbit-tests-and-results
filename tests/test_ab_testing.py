"""Unit tests for orbit/orbit/core/ab_testing.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.ab_testing import ABTestingFramework, get_ab_testing


class TestABTestingFramework(unittest.TestCase):
    def setUp(self):
        self.ab = ABTestingFramework()

    def test_init(self):
        self.assertEqual(self.ab.experiments, {})

    def test_create_experiment(self):
        self.ab.create_experiment("exp1", ["A", "B"], split=0.3)
        self.assertIn("exp1", self.ab.experiments)
        self.assertEqual(self.ab.experiments["exp1"]["variants"], ["A", "B"])
        self.assertEqual(self.ab.experiments["exp1"]["split"], 0.3)
        self.assertEqual(self.ab.experiments["exp1"]["results"], {"A": 0, "B": 0})

    def test_create_default_split(self):
        self.ab.create_experiment("e", ["X", "Y"])
        self.assertEqual(self.ab.experiments["e"]["split"], 0.5)

    def test_assign_variant_deterministic(self):
        self.ab.create_experiment("e", ["A", "B"])
        r1 = self.ab.assign_variant("e", "user1")
        r2 = self.ab.assign_variant("e", "user1")
        self.assertEqual(r1, r2)
        self.assertIn(r1, ["A", "B"])

    def test_assign_variant_unknown_raises(self):
        with self.assertRaises(TypeError):
            self.ab.assign_variant("nope", "user1")

    def test_record_result_success(self):
        self.ab.create_experiment("e", ["A", "B"])
        self.ab.record_result("e", "A", True)
        self.assertEqual(self.ab.experiments["e"]["results"]["A"], 1)

    def test_record_result_failure_no_increment(self):
        self.ab.create_experiment("e", ["A", "B"])
        self.ab.record_result("e", "A", False)
        self.assertEqual(self.ab.experiments["e"]["results"]["A"], 0)

    def test_record_result_unknown_experiment(self):
        self.ab.record_result("nope", "A", True)  # no crash

    def test_record_result_unknown_variant(self):
        self.ab.create_experiment("e", ["A", "B"])
        self.ab.record_result("e", "Z", True)  # no crash, no increment

    def test_get_results(self):
        self.ab.create_experiment("e", ["A", "B"])
        r = self.ab.get_results("e")
        self.assertIn("variants", r)
        self.assertEqual(r["results"], {"A": 0, "B": 0})

    def test_get_results_unknown(self):
        self.assertEqual(self.ab.get_results("nope"), {})

    def test_singleton(self):
        a = get_ab_testing()
        b = get_ab_testing()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
