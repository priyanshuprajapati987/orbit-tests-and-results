"""Tests for ORBIT self-improving system.

Verifies the feedback -> lesson -> retrieval loop: negative feedback is turned
into reusable lessons (deduped per agent+task type), agents can pull an
applicable context hint at runtime, and lesson efficacy is tracked.
"""

import tempfile
import unittest

from orbit.orbit.core.self_improvement import SelfImprovement


class TestSelfImprovementLoop(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.si = SelfImprovement(storage_file=f"{self.tmp}/si.json")

    def test_negative_feedback_creates_lesson(self):
        self.si.add_feedback(
            "COD", "debug", "x", "y", 0.1, comment="Always check None before deref"
        )
        lessons = self.si.get_lessons("COD", "debug")
        self.assertEqual(len(lessons), 1)
        self.assertIn("None", lessons[0]["guidance"])
        self.assertEqual(lessons[0]["failure_count"], 1)

    def test_positive_feedback_no_lesson(self):
        self.si.add_feedback("COD", "debug", "x", "y", 0.95)
        self.assertEqual(self.si.get_lessons("COD"), [])

    def test_lesson_dedup_increments_count(self):
        self.si.add_feedback("COD", "debug", "x", "y", 0.1, comment="check None")
        self.si.add_feedback("COD", "debug", "x", "y", 0.2, comment="check None")
        lessons = self.si.get_lessons("COD", "debug")
        self.assertEqual(len(lessons), 1)
        self.assertEqual(lessons[0]["failure_count"], 2)

    def test_improvement_context_returns_hint(self):
        self.si.add_feedback(
            "COD", "debug", "x", "y", 0.1, comment="check None before deref"
        )
        ctx = self.si.get_improvement_context("COD", "debug")
        self.assertIn("prompt_hint", ctx)
        self.assertIn("None", ctx["prompt_hint"])
        self.assertEqual(len(ctx["lessons"]), 1)

    def test_improvement_context_empty_when_no_lessons(self):
        ctx = self.si.get_improvement_context("ZZZ", "nope")
        self.assertEqual(ctx["prompt_hint"], "")
        self.assertEqual(ctx["lessons"], [])

    def test_record_lesson_applied_tracks_success(self):
        self.si.add_feedback("COD", "debug", "x", "y", 0.1, comment="check None")
        lesson_id = self.si.get_lessons("COD", "debug")[0]["id"]
        ok = self.si.record_lesson_applied(lesson_id, success=True)
        self.assertTrue(ok)
        lesson = self.si.get_lessons("COD", "debug")[0]
        self.assertEqual(lesson["success_count"], 1)
        self.assertEqual(lesson["failure_count"], 1)

    def test_record_lesson_applied_unknown_returns_false(self):
        self.assertFalse(self.si.record_lesson_applied("nope", success=True))

    def test_lessons_persisted(self):
        self.si.add_feedback("COD", "debug", "x", "y", 0.1, comment="check None")
        reloaded = SelfImprovement(storage_file=f"{self.tmp}/si.json")
        self.assertEqual(len(reloaded.get_lessons("COD", "debug")), 1)

    def test_stats_includes_lessons(self):
        self.si.add_feedback("COD", "debug", "x", "y", 0.1, comment="check None")
        self.assertEqual(self.si.get_stats()["total_lessons"], 1)


if __name__ == "__main__":
    unittest.main()
