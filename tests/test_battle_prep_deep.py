"""Deep tests for orbit/orbit/core/battle_prep.py (Loop 12/1).

Covers every statement:
  * ``pick_random_task`` / ``pick_random_skill`` — membership in the
    constant lists (patch random.choice to make deterministic).
  * ``run_battle_test`` — empty-ish task counts, exception path,
    success/failure classification (reply starting with ``[Error``),
    elapsed timing fields, pass_rate/avg_time/total_time math, tasks
    clamped to ``len(BATTLE_TASKS)``.
  * ``judge_score`` — every branch of the three scoring tiers
    (pass_rate 80/60/<60, avg_response_time 2/5/10/>10, avg_len
    50-500/<50/>500) + perfection bonus + grade letters (S/A/B/C/D).
  * ``battle_mode_prompt`` — returns one of the prompts (patch
    random.choice).
"""

import unittest
from unittest import mock

from orbit.orbit.core import battle_prep as bp


class PickRandomTests(unittest.TestCase):
    def test_pick_random_task_in_list(self):
        with mock.patch.object(bp.random, "choice", return_value="X") as rc:
            self.assertEqual(bp.pick_random_task(), "X")
        rc.assert_called_once_with(bp.BATTLE_TASKS)

    def test_pick_random_skill_in_list(self):
        with mock.patch.object(bp.random, "choice", return_value="Y") as rc:
            self.assertEqual(bp.pick_random_skill(), "Y")
        rc.assert_called_once_with(bp.SKILLS)


class RunBattleTestTests(unittest.TestCase):
    def _assistant(self, reply="ok", raise_on=None):
        m = mock.MagicMock()
        if raise_on:
            m.process.side_effect = raise_on
        else:
            m.process.return_value = reply
        return m

    def test_zero_tasks(self):
        a = self._assistant()
        r = bp.run_battle_test(a, tasks=0)
        self.assertEqual(r["total_tasks"], 0)
        self.assertEqual(r["passed"], 0)
        self.assertEqual(r["failed"], 0)
        self.assertEqual(r["pass_rate"], 0)
        self.assertEqual(r["avg_response_time"], 0)
        self.assertEqual(r["results"], [])
        # random.sample called with min(0, len)
        a.process.assert_not_called()

    def test_tasks_clamped_to_list_length(self):
        a = self._assistant(reply="ok")
        with mock.patch.object(bp.random, "sample",
                               return_value=bp.BATTLE_TASKS[:3]):
            r = bp.run_battle_test(a, tasks=1000)
        self.assertEqual(r["total_tasks"], 3)

    def test_success_classification(self):
        a = self._assistant(reply="hello world")
        with mock.patch.object(bp.random, "sample",
                               return_value=[bp.BATTLE_TASKS[0]]):
            r = bp.run_battle_test(a, tasks=1)
        self.assertEqual(r["passed"], 1)
        self.assertEqual(r["failed"], 0)
        self.assertEqual(r["pass_rate"], 100.0)
        self.assertTrue(r["results"][0]["success"])
        self.assertIsNone(r["results"][0]["error"])
        self.assertGreaterEqual(r["results"][0]["response_time"], 0)
        self.assertEqual(r["results"][0]["response_len"], 11)

    def test_error_prefix_classified_failure(self):
        a = self._assistant(reply="[Error] boom")
        with mock.patch.object(bp.random, "sample",
                               return_value=[bp.BATTLE_TASKS[0]]):
            r = bp.run_battle_test(a, tasks=1)
        self.assertEqual(r["passed"], 0)
        self.assertFalse(r["results"][0]["success"])

    def test_empty_reply_classified_failure(self):
        a = self._assistant(reply="")
        with mock.patch.object(bp.random, "sample",
                               return_value=[bp.BATTLE_TASKS[0]]):
            r = bp.run_battle_test(a, tasks=1)
        self.assertFalse(r["results"][0]["success"])

    def test_none_reply_classified_failure(self):
        a = self._assistant(reply=None)
        with mock.patch.object(bp.random, "sample",
                               return_value=[bp.BATTLE_TASKS[0]]):
            r = bp.run_battle_test(a, tasks=1)
        self.assertFalse(r["results"][0]["success"])
        self.assertEqual(r["results"][0]["response_len"], 0)

    def test_exception_path(self):
        a = self._assistant(raise_on=RuntimeError("kaboom"))
        with mock.patch.object(bp.random, "sample",
                               return_value=[bp.BATTLE_TASKS[0]]):
            r = bp.run_battle_test(a, tasks=1)
        self.assertEqual(r["passed"], 0)
        self.assertEqual(r["failed"], 1)
        self.assertFalse(r["results"][0]["success"])
        self.assertEqual(r["results"][0]["error"], "kaboom")
        self.assertEqual(r["results"][0]["response_len"], 0)
        self.assertGreaterEqual(r["results"][0]["response_time"], 0)

    def test_multi_task_mix(self):
        a = mock.MagicMock()
        a.process.side_effect = ["ok", "[Error] x", "fine"]
        tasks = bp.BATTLE_TASKS[:3]
        with mock.patch.object(bp.random, "sample", return_value=tasks):
            r = bp.run_battle_test(a, tasks=3)
        self.assertEqual(r["total_tasks"], 3)
        self.assertEqual(r["passed"], 2)
        self.assertEqual(r["failed"], 1)
        self.assertEqual(r["pass_rate"], 66.7)
        self.assertGreaterEqual(r["total_time"], 0)
        self.assertAlmostEqual(
            r["avg_response_time"],
            sum(x["response_time"] for x in r["results"]) / 3, places=2)


class JudgeScoreTests(unittest.TestCase):
    def _result(self, pass_rate=100, avg_time=1.0, avg_len=100,
                total=3, passed=3):
        return {
            "pass_rate": pass_rate,
            "avg_response_time": avg_time,
            "results": [{"response_len": avg_len} for _ in range(total)],
            "total_tasks": total,
            "passed": passed,
        }

    def test_perfect_score_s_grade(self):
        j = bp.judge_score(self._result(pass_rate=100, avg_time=1.0,
                                        avg_len=100, total=3, passed=3))
        self.assertEqual(j["score"], 100)
        self.assertEqual(j["max_score"], 100)
        self.assertEqual(j["percentage"], 100.0)
        self.assertEqual(j["grade"], "S")
        self.assertIn("Task completion: Excellent", j["feedback"])
        self.assertIn("Speed: Lightning fast", j["feedback"])
        self.assertIn("Conciseness: Perfect", j["feedback"])
        self.assertIn("Perfection: All tasks passed", j["feedback"])

    def test_pass_rate_60_tier(self):
        j = bp.judge_score(self._result(pass_rate=60, avg_time=3.0,
                                        avg_len=10, total=2, passed=1))
        self.assertEqual(j["score"], 30 + 20 + 10)  # no perfection
        self.assertIn("Task completion: Good", j["feedback"])
        self.assertIn("Speed: Fast", j["feedback"])
        self.assertIn("Conciseness: Too brief", j["feedback"])
        self.assertNotIn("Perfection: All tasks passed", j["feedback"])
        self.assertEqual(j["grade"], "C")

    def test_pass_rate_below_60_tier(self):
        j = bp.judge_score(self._result(pass_rate=40, avg_time=7.0,
                                        avg_len=600, total=2, passed=1))
        self.assertEqual(j["score"], 10 + 10 + 5)
        self.assertIn("Task completion: Needs improvement", j["feedback"])
        self.assertIn("Speed: Acceptable", j["feedback"])
        self.assertIn("Conciseness: Verbose", j["feedback"])
        self.assertEqual(j["grade"], "D")

    def test_speed_slow_no_speed_points(self):
        j = bp.judge_score(self._result(pass_rate=100, avg_time=15.0,
                                        avg_len=100, total=1, passed=1))
        self.assertNotIn("Speed: Lightning fast", j["feedback"])
        self.assertNotIn("Speed: Fast", j["feedback"])
        self.assertNotIn("Speed: Acceptable", j["feedback"])
        self.assertIn("Speed: Slow", j["feedback"])
        # 40 + 0 + 20 + 10 = 70 -> B
        self.assertEqual(j["score"], 70)
        self.assertEqual(j["grade"], "B")

    def test_speed_5_boundary(self):
        j = bp.judge_score(self._result(pass_rate=100, avg_time=5.0,
                                        avg_len=100, total=1, passed=1))
        self.assertIn("Speed: Fast", j["feedback"])

    def test_speed_10_boundary(self):
        j = bp.judge_score(self._result(pass_rate=100, avg_time=10.0,
                                        avg_len=100, total=1, passed=1))
        self.assertIn("Speed: Acceptable", j["feedback"])

    def test_pass_rate_80_boundary(self):
        j = bp.judge_score(self._result(pass_rate=80, avg_time=1.0,
                                        avg_len=100, total=1, passed=1))
        self.assertIn("Task completion: Excellent", j["feedback"])

    def test_pass_rate_60_boundary(self):
        j = bp.judge_score(self._result(pass_rate=60, avg_time=1.0,
                                        avg_len=100, total=1, passed=1))
        self.assertIn("Task completion: Good", j["feedback"])

    def test_empty_results_avg_len_zero(self):
        r = {
            "pass_rate": 0,
            "avg_response_time": 0,
            "results": [],
            "total_tasks": 0,
            "passed": 0,
        }
        j = bp.judge_score(r)
        # avg_len = 0 -> <50 -> "Too brief" (10 pts)
        self.assertIn("Conciseness: Too brief", j["feedback"])
        # total_tasks 0 != passed 0? 0==0 True -> perfection bonus
        self.assertIn("Perfection: All tasks passed", j["feedback"])

    def test_grade_a(self):
        # 80-89 -> A
        j = bp.judge_score(self._result(pass_rate=100, avg_time=3.0,
                                        avg_len=10, total=1, passed=0))
        # 40+20+10 = 70 -> actually B; force 80 by passing all tasks
        j2 = bp.judge_score(self._result(pass_rate=100, avg_time=1.0,
                                         avg_len=10, total=1, passed=1))
        # 40+30+10+10 = 90 -> S. Use 60 pass_rate to get A band:
        j3 = bp.judge_score(self._result(pass_rate=60, avg_time=1.0,
                                         avg_len=100, total=1, passed=0))
        # 30+30+20 = 80 -> A
        self.assertEqual(j3["score"], 80)
        self.assertEqual(j3["grade"], "A")


class BattleModePromptTests(unittest.TestCase):
    def test_returns_one_of_prompts(self):
        with mock.patch.object(bp.random, "choice", return_value="X"):
            self.assertEqual(bp.battle_mode_prompt(), "X")

    def test_prompts_count(self):
        # random.choice called with the 5-prompt list
        with mock.patch.object(bp.random, "choice") as rc:
            bp.battle_mode_prompt()
        self.assertEqual(len(rc.call_args.args[0]), 5)


if __name__ == "__main__":
    unittest.main()
