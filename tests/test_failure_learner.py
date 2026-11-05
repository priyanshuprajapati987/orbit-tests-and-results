import unittest


class TestFailureLearnerCore(unittest.TestCase):
    def setUp(self):
        from orbit.orbit.core.failure_learner import get_failure_learner

        self.fl = get_failure_learner()
        self.fl.reset()

    def test_01_import(self):
        from orbit.orbit.core.failure_learner import get_failure_learner

        self.assertTrue(callable(get_failure_learner))

    def test_02_log_failure(self):
        f = self.fl.log_failure(
            "COD", "parse_json", "JSONDecodeError", "input: {...}", "high"
        )
        self.assertIn("id", f)
        self.assertEqual(f["agent"], "COD")
        self.assertEqual(f["severity"], "high")
        self.assertFalse(f["resolved"])

    def test_03_get_failures(self):
        self.fl.log_failure("TAS", "read_file", "FileNotFoundError")
        self.fl.log_failure("RES", "search_web", "TimeoutError")
        failures = self.fl.get_failures()
        self.assertEqual(len(failures), 2)

    def test_04_get_failures_filter_by_agent(self):
        self.fl.log_failure("COD", "t1", "error1")
        self.fl.log_failure("TAS", "t2", "error2")
        cod_failures = self.fl.get_failures(agent="COD")
        self.assertEqual(len(cod_failures), 1)
        self.assertEqual(cod_failures[0]["agent"], "COD")

    def test_05_get_failures_filter_by_severity(self):
        self.fl.log_failure("COD", "t1", "e1", severity="high")
        self.fl.log_failure("TAS", "t2", "e2", severity="low")
        high = self.fl.get_failures(severity="high")
        self.assertEqual(len(high), 1)

    def test_06_add_solution(self):
        f = self.fl.log_failure("COD", "parse", "JSONDecodeError")
        sol = self.fl.add_solution(
            f["id"], "Use try/except", "try: json.loads(...)\nexcept: None"
        )
        self.assertIsNotNone(sol)
        self.assertEqual(sol["agent"], "COD")
        self.assertEqual(sol["description"], "Use try/except")

    def test_07_add_solution_marks_failure_resolved(self):
        f = self.fl.log_failure("COD", "parse", "Error")
        self.fl.add_solution(f["id"], "Fix", "patch")
        failures = self.fl.get_failures()
        self.assertTrue(any(f.get("resolved") for f in failures if f["id"] == f["id"]))

    def test_08_add_solution_nonexistent_failure(self):
        sol = self.fl.add_solution("nonexistent", "desc", "fix")
        self.assertIsNone(sol)

    def test_09_get_solutions(self):
        f1 = self.fl.log_failure("COD", "t1", "e1")
        f2 = self.fl.log_failure("TAS", "t2", "e2")
        self.fl.add_solution(f1["id"], "Fix1", "patch1")
        self.fl.add_solution(f2["id"], "Fix2", "patch2")
        solutions = self.fl.get_solutions()
        self.assertEqual(len(solutions), 2)

    def test_10_apply_solution(self):
        f = self.fl.log_failure("COD", "t", "e")
        sol = self.fl.add_solution(f["id"], "Fix", "patch")
        ok = self.fl.apply_solution(sol["id"])
        self.assertTrue(ok)
        self.assertEqual(self.fl.get_solutions()[0]["applied_count"], 1)

    def test_11_rate_solution(self):
        f = self.fl.log_failure("COD", "t", "e")
        sol = self.fl.add_solution(f["id"], "Fix", "patch")
        ok = self.fl.rate_solution(sol["id"], 4.5)
        self.assertTrue(ok)
        self.assertAlmostEqual(self.fl.get_solutions()[0]["rating"], 4.5)

    def test_12_rate_solution_invalid_rating(self):
        f = self.fl.log_failure("COD", "t", "e")
        sol = self.fl.add_solution(f["id"], "Fix", "patch")
        self.assertFalse(self.fl.rate_solution(sol["id"], 6))

    def test_13_get_stats(self):
        f = self.fl.log_failure("COD", "t1", "e1")
        self.fl.log_failure("TAS", "t2", "e2")
        self.fl.add_solution(f["id"], "Fix", "patch")
        stats = self.fl.get_stats()
        self.assertEqual(stats["total_failures"], 2)
        self.assertEqual(stats["resolved_failures"], 1)
        self.assertEqual(stats["total_solutions"], 1)
        self.assertEqual(stats["unique_agents"], 2)

    def test_14_share_solution(self):
        f = self.fl.log_failure("COD", "parse", "Error")
        sol = self.fl.add_solution(f["id"], "Fix", "patch")
        shared = self.fl.share_solution(sol["id"])
        self.assertIsNotNone(shared)
        self.assertIn("shared_solution", shared)
        self.assertEqual(shared["shared_solution"]["agent"], "COD")

    def test_15_share_solution_nonexistent(self):
        self.assertIsNone(self.fl.share_solution("nonexistent"))

    def test_16_find_similar_failures(self):
        self.fl.log_failure("COD", "parse_json", "JSONDecodeError: invalid syntax")
        self.fl.log_failure("TAS", "read_file", "FileNotFoundError")
        self.fl.log_failure("RES", "json_api", "JSONDecodeError: unexpected token")
        matches = self.fl.find_similar_failures("JSONDecodeError")
        self.assertEqual(len(matches), 2)

    def test_17_reset(self):
        self.fl.log_failure("COD", "t", "e")
        self.fl.reset()
        self.assertEqual(len(self.fl.get_failures()), 0)
        self.assertEqual(len(self.fl.get_solutions()), 0)

    def test_18_singleton(self):
        from orbit.orbit.core.failure_learner import get_failure_learner

        self.assertIs(self.fl, get_failure_learner())


if __name__ == "__main__":
    unittest.main()
