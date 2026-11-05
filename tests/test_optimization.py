"""Competitive optimization engine tests: threshold classification + report building."""

import unittest

from orbit.orbit.core.optimization import (
    MAJOR_THRESHOLD,
    TARGETED_THRESHOLD,
    CompetitiveOptimizer,
    generate_optimization_report,
    get_optimizer,
)


def _round(cat, winner="jarvus", composite=0.8, opponent_error=False):
    return {
        "prompt": f"{cat} prompt #{abs(hash((cat, winner, composite)) % 10000)}",
        "composite": {"winner": winner, "total": composite},
        "opponent_error": opponent_error,
        "jarvus": {"latency_ms": 800.0},
        "accuracy_score": 0.4,
    }


def _category(cat, rounds):
    return {
        cat: {
            "prompts": [r["prompt"] for r in rounds],
            "results": rounds,
            "win_rate": 0.0,
            "voids": 0,
        }
    }


def _payload(cats):
    return {
        "categories": cats,
        "summary": {"opponent": "MockOpponent", "overall_win_rate": None},
    }


class TestOptimizerClassify(unittest.TestCase):
    def setUp(self):
        self.opt = CompetitiveOptimizer()

    def test_threshold_values(self):
        self.assertAlmostEqual(MAJOR_THRESHOLD, 0.40)
        self.assertAlmostEqual(TARGETED_THRESHOLD, 0.60)

    def test_classify_major(self):
        self.assertEqual(self.opt.classify(0.20), "MAJOR")
        self.assertEqual(self.opt.classify(MAJOR_THRESHOLD - 0.01), "MAJOR")

    def test_classify_targeted(self):
        self.assertEqual(self.opt.classify(0.5), "TARGETED")
        self.assertEqual(self.opt.classify(0.55), "TARGETED")

    def test_classify_maintenance(self):
        self.assertEqual(self.opt.classify(0.9), "MAINTENANCE")
        self.assertEqual(self.opt.classify(TARGETED_THRESHOLD), "MAINTENANCE")

    def test_recommend_known_category(self):
        rec = self.opt.recommend("reasoning", 0.3)
        self.assertEqual(rec["severity"], "MAJOR")
        self.assertIn("actions", rec)
        self.assertIn("suggested_routes", rec)
        self.assertTrue(rec["actions"])

    def test_recommend_unknown_category(self):
        rec = self.opt.recommend("nope", 0.5)
        self.assertIn("actions", rec)

    def test_singleton(self):
        self.assertIs(get_optimizer(), get_optimizer())


class TestOptimizerReport(unittest.TestCase):
    def test_analyze_battle_win_rate(self):
        opt = CompetitiveOptimizer()
        cats = _category(
            "facts",
            [_round("facts"), _round("facts"), _round("facts", winner="opponent")],
        )
        rows = opt.analyze_battle(cats)
        self.assertEqual(rows[0]["valid"], 3)
        self.assertAlmostEqual(rows[0]["win_rate"], round(2 / 3, 4))

    def test_analyze_battle_voids_excluded(self):
        opt = CompetitiveOptimizer()
        cats = _category(
            "facts",
            [_round("facts"), _round("facts", winner="void", opponent_error=True)],
        )
        rows = opt.analyze_battle(cats)
        self.assertEqual(rows[0]["valid"], 1)
        self.assertEqual(rows[0]["voids"], 1)
        self.assertAlmostEqual(rows[0]["win_rate"], 1.0)

    def test_weak_prompts_top_n(self):
        opt = CompetitiveOptimizer()
        rounds = [_round("facts", composite=0.9 - i * 0.02) for i in range(15)]
        weak = opt.weak_prompts(_category("facts", rounds))
        self.assertLessEqual(len(weak), 10)
        self.assertEqual(weak[0]["composite"], min(w["composite"] for w in weak))

    def test_generate_report(self):
        cats = _category(
            "reasoning", [_round("reasoning"), _round("reasoning", winner="opponent")]
        )
        report = generate_optimization_report(_payload(cats))
        self.assertIn("report_date", report)
        self.assertAlmostEqual(report["overall_win_rate"], 0.5)
        self.assertEqual(report["overall_severity"], "TARGETED")
        self.assertIn("weak_prompts", report)
        self.assertIn("verdict", report)
        self.assertEqual(report["categories"][0]["category"], "reasoning")

    def test_generate_report_empty_rounds(self):
        report = generate_optimization_report(_payload(_category("facts", [])))
        self.assertEqual(report["total_complete"], 0)
        self.assertEqual(report["overall_win_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
