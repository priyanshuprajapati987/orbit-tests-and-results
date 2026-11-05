import unittest


class TestPromptEvolverCore(unittest.TestCase):
    def setUp(self):
        from orbit.orbit.core.prompt_evolver import get_prompt_evolver

        self.ev = get_prompt_evolver()
        self.ev.reset()

    def test_01_import(self):
        from orbit.orbit.core.prompt_evolver import get_prompt_evolver

        self.assertTrue(callable(get_prompt_evolver))

    def test_02_register_variation(self):
        var = self.ev.register_variation(
            "summarize", "short prompt", "long prompt", ["test"]
        )
        self.assertIn("id", var)
        self.assertEqual(var["task"], "summarize")
        self.assertEqual(var["prompt_a"], "short prompt")

    def test_03_get_variations(self):
        self.ev.register_variation("t1", "a", "b")
        self.ev.register_variation("t2", "c", "d")
        vars = self.ev.get_variations()
        self.assertEqual(len(vars), 2)

    def test_04_get_variation_by_id(self):
        var = self.ev.register_variation("test", "a", "b")
        found = self.ev.get_variation(var["id"])
        self.assertIsNotNone(found)
        self.assertEqual(found["task"], "test")

    def test_05_get_variation_nonexistent(self):
        self.assertIsNone(self.ev.get_variation("nonexistent"))

    def test_06_record_trial(self):
        var = self.ev.register_variation("test", "a", "b")
        trial = self.ev.record_trial(var["id"], "A", 0.85, 120)
        self.assertIsNotNone(trial)
        self.assertEqual(trial["version"], "A")
        self.assertEqual(trial["score"], 0.85)

    def test_07_record_trial_nonexistent_variation(self):
        trial = self.ev.record_trial("nonexistent", "A", 0.5)
        self.assertIsNone(trial)

    def test_08_get_results_winner(self):
        var = self.ev.register_variation("test", "a", "b")
        self.ev.record_trial(var["id"], "A", 0.9, 100)
        self.ev.record_trial(var["id"], "A", 0.85, 110)
        self.ev.record_trial(var["id"], "B", 0.7, 90)
        results = self.ev.get_results(var["id"])
        self.assertEqual(results["winner"], "A")
        self.assertGreater(results["avg_score_a"], results["avg_score_b"])

    def test_09_get_results_tie(self):
        var = self.ev.register_variation("test", "a", "b")
        self.ev.record_trial(var["id"], "A", 0.8, 100)
        self.ev.record_trial(var["id"], "B", 0.8, 100)
        results = self.ev.get_results(var["id"])
        self.assertEqual(results["winner"], "tie")

    def test_10_get_stats(self):
        var = self.ev.register_variation("t1", "a", "b")
        self.ev.record_trial(var["id"], "A", 0.9)
        self.ev.record_trial(var["id"], "B", 0.8)
        self.ev.register_variation("t2", "c", "d")
        stats = self.ev.get_stats()
        self.assertEqual(stats["total_variations"], 2)
        self.assertEqual(stats["total_trials"], 2)
        self.assertEqual(stats["unique_tasks"], 2)

    def test_11_decide_variation(self):
        var = self.ev.register_variation("qa", "prompt_a", "prompt_b")
        self.ev.record_trial(var["id"], "A", 0.95)
        self.ev.record_trial(var["id"], "B", 0.6)
        decision = self.ev.decide_variation("qa")
        self.assertIsNotNone(decision)
        self.assertEqual(decision["version"], "A")

    def test_12_decide_variation_no_data(self):
        decision = self.ev.decide_variation("unknown")
        self.assertIsNone(decision)

    def test_13_get_results_nonexistent(self):
        self.assertIsNone(self.ev.get_results("nonexistent"))

    def test_14_reset(self):
        self.ev.register_variation("t", "a", "b")
        self.ev.record_trial(self.ev.get_variations()[0]["id"], "A", 0.5)
        self.ev.reset()
        self.assertEqual(len(self.ev.get_variations()), 0)
        self.assertEqual(self.ev.get_stats()["total_trials"], 0)

    def test_15_singleton(self):
        from orbit.orbit.core.prompt_evolver import get_prompt_evolver

        self.assertIs(self.ev, get_prompt_evolver())


if __name__ == "__main__":
    unittest.main()
