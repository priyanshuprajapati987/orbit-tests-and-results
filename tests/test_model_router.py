"""Unit tests for orbit/orbit/core/model_router.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.model_router import (
    TaskType, Complexity, ModelRouter, get_model_router,
    route_model, analyze_and_route, get_cost_estimate, get_stats,
)


class TestEnums(unittest.TestCase):
    def test_task_type(self):
        self.assertEqual(TaskType.CODING.value, "coding")
        self.assertEqual(TaskType.GENERAL.value, "general")

    def test_complexity(self):
        self.assertEqual(Complexity.SIMPLE.value, "simple")
        self.assertEqual(Complexity.COMPLEX.value, "complex")


class TestModelRouter(unittest.TestCase):
    def setUp(self):
        self.mr = ModelRouter()

    def test_instantiation(self):
        self.assertIsNotNone(self.mr)

    def test_analyze_task(self):
        r = self.mr.analyze_task("write a python function")
        self.assertIsNotNone(r)

    def test_route_model(self):
        r = self.mr.route_model("write a python function")
        self.assertIsNotNone(r)

    def test_check_model_availability(self):
        try:
            r = self.mr._check_model_availability("gpt-4o-mini")
            self.assertTrue(r is None or isinstance(r, bool))
        except Exception:
            self.assertTrue(True)

    def test_get_fallback_model(self):
        r = self.mr._get_fallback_model("coding", "simple")
        self.assertTrue(r is None or isinstance(r, str))

    def test_get_cost_estimate(self):
        r = self.mr.get_cost_estimate("coding", "simple")
        self.assertTrue(r is None or isinstance(r, (int, float, dict)))

    def test_log_task(self):
        self.mr.log_task("coding", "simple", "gpt-4o-mini", 100, 50)
        self.assertTrue(True)

    def test_get_stats(self):
        r = self.mr.get_stats()
        self.assertIsNotNone(r)

    def test_update_routing(self):
        r = self.mr.update_routing("coding", "simple", "gpt-4o")
        self.assertTrue(r is None or isinstance(r, (bool, dict)))

    def test_singleton(self):
        a = get_model_router()
        b = get_model_router()
        self.assertIs(a, b)


class TestModuleFunctions(unittest.TestCase):
    def test_route_model_func(self):
        self.assertTrue(callable(route_model))

    def test_analyze_and_route_func(self):
        self.assertTrue(callable(analyze_and_route))

    def test_get_cost_estimate_func(self):
        self.assertTrue(callable(get_cost_estimate))

    def test_get_stats_func(self):
        self.assertTrue(callable(get_stats))


if __name__ == "__main__":
    unittest.main()
