import unittest


class TestPerformanceOptimizerCore(unittest.TestCase):
    def setUp(self):
        from orbit.orbit.core.performance_optimizer import get_performance_optimizer

        self.opt = get_performance_optimizer()
        self.opt.reset()

    def test_01_import(self):
        from orbit.orbit.core.performance_optimizer import (
            get_performance_optimizer,
        )

        self.assertTrue(callable(get_performance_optimizer))

    def test_02_record_and_get_metrics(self):
        self.opt.record_metric("latency", "api_call", 1.5, "s", ["test"])
        self.opt.record_metric("latency", "db_query", 0.3, "s")
        self.opt.record_metric("memory", "heap_usage", 256, "MB")
        metrics = self.opt.get_metrics()
        self.assertEqual(len(metrics), 3)

    def test_03_metrics_filter_by_category(self):
        self.opt.record_metric("latency", "api_call", 1.5, "s")
        self.opt.record_metric("memory", "heap", 256, "MB")
        latencies = self.opt.get_metrics(category="latency")
        self.assertEqual(len(latencies), 1)
        self.assertEqual(latencies[0]["name"], "api_call")

    def test_04_record_metric_returns_entry(self):
        entry = self.opt.record_metric("cpu", "load", 0.75, "pct")
        self.assertIn("id", entry)
        self.assertEqual(entry["category"], "cpu")
        self.assertEqual(entry["value"], 0.75)

    def test_05_add_suggestion(self):
        s = self.opt.add_suggestion("Cache API", "Add Redis caching", "high", "latency")
        self.assertIn("id", s)
        self.assertEqual(s["title"], "Cache API")
        self.assertEqual(s["expected_impact"], "high")

    def test_06_get_suggestions_ordered_by_votes(self):
        s1 = self.opt.add_suggestion("S1", "First", "medium", "general")
        s2 = self.opt.add_suggestion("S2", "Second", "medium", "general")
        self.opt.vote_suggestion(s1["id"])
        self.opt.vote_suggestion(s1["id"])
        self.opt.vote_suggestion(s2["id"])
        suggestions = self.opt.get_suggestions()
        self.assertGreaterEqual(suggestions[0]["votes"], suggestions[1]["votes"])

    def test_07_vote_suggestion(self):
        s = self.opt.add_suggestion("Test", "Desc", "low", "general")
        ok = self.opt.vote_suggestion(s["id"])
        self.assertTrue(ok)
        self.assertEqual(self.opt.get_suggestions()[0]["votes"], 1)

    def test_08_vote_nonexistent(self):
        ok = self.opt.vote_suggestion("nonexistent")
        self.assertFalse(ok)

    def test_09_mark_implemented(self):
        s = self.opt.add_suggestion("Test", "Desc", "medium", "general")
        ok = self.opt.mark_implemented(s["id"])
        self.assertTrue(ok)
        self.assertTrue(self.opt.get_suggestions()[0]["implemented"])

    def test_10_get_stats(self):
        self.opt.record_metric("latency", "x", 1.0)
        self.opt.record_metric("memory", "y", 2.0)
        self.opt.add_suggestion("S1", "D", "high", "latency")
        self.opt.add_suggestion("S2", "D", "low", "memory")
        stats = self.opt.get_stats()
        self.assertEqual(stats["total_metrics"], 2)
        self.assertEqual(stats["total_suggestions"], 2)
        self.assertIn("latency", stats["categories"])

    def test_11_generate_auto_suggestions(self):
        for i in range(5):
            self.opt.record_metric("latency", f"slow_op_{i}", 2.5 + i, "s")
        self.opt.record_metric("memory", "quick", 0.1, "MB")
        suggestions = self.opt.generate_auto_suggestions()
        self.assertGreater(len(suggestions), 0)

    def test_12_auto_suggestions_empty_when_few_metrics(self):
        suggestions = self.opt.generate_auto_suggestions()
        self.assertEqual(len(suggestions), 0)

    def test_13_reset(self):
        self.opt.record_metric("latency", "x", 1.0)
        self.opt.add_suggestion("S1", "D", "medium", "general")
        self.opt.reset()
        self.assertEqual(len(self.opt.get_metrics()), 0)
        self.assertEqual(len(self.opt.get_suggestions()), 0)

    def test_14_singleton(self):
        from orbit.orbit.core.performance_optimizer import get_performance_optimizer

        self.assertIs(self.opt, get_performance_optimizer())

    def test_15_suggestions_filter_by_category(self):
        self.opt.add_suggestion("S1", "D", "high", "latency")
        self.opt.add_suggestion("S2", "D", "low", "memory")
        latency_sugs = self.opt.get_suggestions(category="latency")
        self.assertEqual(len(latency_sugs), 1)
        self.assertEqual(latency_sugs[0]["category"], "latency")


if __name__ == "__main__":
    unittest.main()
