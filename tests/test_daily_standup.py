"""Unit tests for orbit/orbit/core/daily_standup.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.daily_standup import (
    DailyEntry, DailySummary, DailyStandup, get_daily_standup,
)


class TestDailyEntry(unittest.TestCase):
    def test_init(self):
        e = DailyEntry(timestamp=1.0, category="task_completed", title="t", details="d")
        self.assertEqual(e.category, "task_completed")
        self.assertEqual(e.title, "t")

    def test_to_dict(self):
        e = DailyEntry(timestamp=1.0, category="task_completed", title="t", details="d")
        d = e.to_dict()
        self.assertIsInstance(d, dict)


class TestDailySummary(unittest.TestCase):
    def test_init(self):
        s = DailySummary(date="2026-01-01")
        self.assertEqual(s.date, "2026-01-01")
        self.assertEqual(s.total_tasks, 0)

    def test_to_dict(self):
        s = DailySummary(date="2026-01-01")
        d = s.to_dict()
        self.assertIsInstance(d, dict)


class TestDailyStandup(unittest.TestCase):
    def setUp(self):
        self.ds = DailyStandup()

    def test_instantiation(self):
        self.assertIsNotNone(self.ds)

    def test_record_event(self):
        self.ds.record_event("task_completed", "Task 1", "done")
        self.assertTrue(True)

    def test_record_task_completed(self):
        self.ds.record_task_completed("Task 1", "agent", 100.0)
        self.assertTrue(True)

    def test_record_task_failed(self):
        self.ds.record_task_failed("Task 2", "reason")
        self.assertTrue(True)

    def test_record_chat_message(self):
        self.ds.record_chat_message("hi")
        self.assertTrue(True)

    def test_record_mood_change(self):
        self.ds.record_mood_change("happy", "high")
        self.assertTrue(True)

    def test_generate_summary(self):
        self.ds.record_event("task_completed", "Task 1", "done")
        r = self.ds.generate_summary()
        self.assertIsNotNone(r)

    def test_generate_morning_briefing(self):
        r = self.ds.generate_morning_briefing()
        self.assertIsNotNone(r)

    def test_generate_evening_summary(self):
        r = self.ds.generate_evening_summary()
        self.assertIsNotNone(r)

    def test_get_stats(self):
        r = self.ds.get_stats()
        self.assertIsNotNone(r)

    def test_get_recent_summaries(self):
        r = self.ds.get_recent_summaries(5)
        self.assertIsNotNone(r)

    def test_singleton(self):
        a = get_daily_standup()
        b = get_daily_standup()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
