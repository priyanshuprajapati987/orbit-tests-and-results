"""Unit tests for orbit/orbit/core/calendar_optimizer.py."""

import os
import sys
import unittest
from datetime import datetime, timedelta

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.calendar_optimizer import CalendarOptimizer, get_calendar_optimizer


class TestCalendarOptimizer(unittest.TestCase):
    def setUp(self):
        self.o = CalendarOptimizer()

    def test_empty_busy_returns_slots(self):
        slots = self.o.suggest_slots([], duration_min=30, days=1)
        self.assertGreater(len(slots), 0)
        self.assertLessEqual(len(slots), 10)

    def test_max_10_slots(self):
        slots = self.o.suggest_slots([], duration_min=30, days=7)
        self.assertLessEqual(len(slots), 10)

    def test_overlaps_true(self):
        now = datetime.now()
        start = now.replace(hour=10, minute=0, second=0, microsecond=0)
        end = start + timedelta(minutes=30)
        busy = [{"start": start.isoformat(), "end": end.isoformat()}]
        self.assertTrue(self.o._overlaps(start, end, busy))

    def test_overlaps_false(self):
        now = datetime.now()
        start = now.replace(hour=10, minute=0, second=0, microsecond=0)
        end = start + timedelta(minutes=30)
        busy = [{"start": (start + timedelta(hours=2)).isoformat(),
                 "end": (start + timedelta(hours=3)).isoformat()}]
        self.assertFalse(self.o._overlaps(start, end, busy))

    def test_busy_slot_reduces_availability(self):
        now = datetime.now()
        day = now.replace(hour=9, minute=0, second=0, microsecond=0)
        busy = [{"start": day.isoformat(), "end": (day + timedelta(hours=8)).isoformat()}]
        # block entire first day (9-17)
        slots_day0 = [s for s in self.o.suggest_slots(busy, duration_min=30, days=1)]
        # all 9-16 slots blocked → should be empty
        self.assertEqual(slots_day0, [])

    def test_duration_min_param(self):
        slots = self.o.suggest_slots([], duration_min=60, days=1)
        self.assertGreater(len(slots), 0)

    def test_days_param(self):
        slots1 = self.o.suggest_slots([], duration_min=30, days=1)
        slots7 = self.o.suggest_slots([], duration_min=30, days=7)
        self.assertGreaterEqual(len(slots7), len(slots1))

    def test_singleton(self):
        a = get_calendar_optimizer()
        b = get_calendar_optimizer()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
