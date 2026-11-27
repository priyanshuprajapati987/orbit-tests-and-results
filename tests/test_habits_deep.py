"""Deep tests for orbit/orbit/habits.py (Loop 17/3)."""

import json
import threading
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from orbit.orbit import habits as hb


class LoadSaveTests(unittest.TestCase):
    def setUp(self):
        self._orig = hb.HABITS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "habits.json"
        hb.HABITS_FILE = self._path
        self.addCleanup(setattr, hb, "HABITS_FILE", self._orig)

    def test_load_missing(self):
        self.assertEqual(hb._load(), [])

    def test_load_valid(self):
        self._path.write_text('[{"id":1}]', encoding="utf-8")
        self.assertEqual(hb._load(), [{"id": 1}])

    def test_load_corrupt(self):
        self._path.write_text("{bad", encoding="utf-8")
        self.assertEqual(hb._load(), [])

    def test_save_success(self):
        ok = hb._save([{"id": 1}])
        self.assertIsNone(ok)
        self.assertTrue(self._path.exists())
        self.assertEqual(json.loads(self._path.read_text("utf-8")), [{"id": 1}])

    def test_save_failure(self):
        with mock.patch.object(Path, "mkdir", side_effect=OSError("nope")):
            ok = hb._save([{"id": 1}])
        self.assertFalse(ok)


class NextIdTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(hb._next_id([]), 1)

    def test_max_plus_one(self):
        self.assertEqual(hb._next_id([{"id": 3}, {"id": 7}]), 8)


class AddTests(unittest.TestCase):
    def setUp(self):
        self._orig = hb.HABITS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "habits.json"
        hb.HABITS_FILE = self._path
        self.addCleanup(setattr, hb, "HABITS_FILE", self._orig)

    def test_add_basic(self):
        h = hb.add("exercise", "daily", ["health"])
        self.assertEqual(h["name"], "exercise")
        self.assertEqual(h["frequency"], "daily")
        self.assertEqual(h["tags"], ["health"])
        self.assertEqual(h["streak"], 0)
        self.assertEqual(h["best_streak"], 0)
        self.assertEqual(h["log"], [])
        self.assertIn("id", h)
        self.assertIn("created", h)
        self.assertEqual(len(hb._load()), 1)

    def test_add_default_frequency_and_tags(self):
        h = hb.add("read")
        self.assertEqual(h["frequency"], "daily")
        self.assertEqual(h["tags"], [])

    def test_add_tags_none(self):
        h = hb.add("x", tags=None)
        self.assertEqual(h["tags"], [])

    def test_add_id_increments(self):
        hb.add("a")
        h2 = hb.add("b")
        self.assertEqual(h2["id"], 2)


class GetAllTests(unittest.TestCase):
    def setUp(self):
        self._orig = hb.HABITS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "habits.json"
        hb.HABITS_FILE = self._path
        self.addCleanup(setattr, hb, "HABITS_FILE", self._orig)
        hb.add("a")
        hb.add("b")

    def test_get_all(self):
        self.assertEqual(len(hb.get_all()), 2)


class LogTests(unittest.TestCase):
    def setUp(self):
        self._orig = hb.HABITS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "habits.json"
        hb.HABITS_FILE = self._path
        self.addCleanup(setattr, hb, "HABITS_FILE", self._orig)
        self.h = hb.add("exercise")

    def test_log_today(self):
        self.assertTrue(hb.log(self.h["id"]))
        self.assertIn(date.today().isoformat(), hb.get_all()[0]["log"])

    def test_log_specific_date(self):
        self.assertTrue(hb.log(self.h["id"], "2026-01-01"))
        self.assertIn("2026-01-01", hb.get_all()[0]["log"])

    def test_log_duplicate_returns_false(self):
        hb.log(self.h["id"], "2026-01-01")
        self.assertFalse(hb.log(self.h["id"], "2026-01-01"))

    def test_log_unknown_habit(self):
        self.assertFalse(hb.log(99999))

    def test_log_recalc_streak(self):
        hb.log(self.h["id"], date.today().isoformat())
        h = hb.get_all()[0]
        self.assertEqual(h["streak"], 1)
        self.assertEqual(h["best_streak"], 1)

    def test_log_streak_multiple_days(self):
        from datetime import timedelta
        today = date.today()
        for i in range(3):
            hb.log(self.h["id"], (today - timedelta(days=i)).isoformat())
        h = hb.get_all()[0]
        self.assertEqual(h["streak"], 3)
        self.assertEqual(h["best_streak"], 3)


class UnlogTests(unittest.TestCase):
    def setUp(self):
        self._orig = hb.HABITS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "habits.json"
        hb.HABITS_FILE = self._path
        self.addCleanup(setattr, hb, "HABITS_FILE", self._orig)
        self.h = hb.add("exercise")
        hb.log(self.h["id"], "2026-01-01")

    def test_unlog_success(self):
        self.assertTrue(hb.unlog(self.h["id"], "2026-01-01"))
        self.assertNotIn("2026-01-01", hb.get_all()[0]["log"])

    def test_unlog_default_today(self):
        hb.log(self.h["id"])  # log today
        self.assertTrue(hb.unlog(self.h["id"]))  # unlog today
        self.assertNotIn(date.today().isoformat(), hb.get_all()[0]["log"])

    def test_unlog_not_logged(self):
        self.assertFalse(hb.unlog(self.h["id"], "2020-01-01"))

    def test_unlog_unknown_habit(self):
        self.assertFalse(hb.unlog(99999, "2026-01-01"))

    def test_unlog_recalc_streak(self):
        from datetime import timedelta
        today = date.today()
        hb.log(self.h["id"], today.isoformat())
        hb.log(self.h["id"], (today - timedelta(days=1)).isoformat())
        hb.unlog(self.h["id"], today.isoformat())
        h = hb.get_all()[0]
        self.assertEqual(h["streak"], 0)


class RecalcStreakTests(unittest.TestCase):
    def test_empty_logs(self):
        h = {"log": [], "frequency": "daily", "streak": 0, "best_streak": 0}
        hb._recalc_streak(h)
        self.assertEqual(h["streak"], 0)

    def test_daily_streak(self):
        today = date.today()
        h = {"log": [today.isoformat(), (today - __import__("datetime").timedelta(days=1)).isoformat()],
             "frequency": "daily", "streak": 0, "best_streak": 0}
        hb._recalc_streak(h)
        self.assertEqual(h["streak"], 2)

    def test_daily_broken(self):
        today = date.today()
        h = {"log": [today.isoformat(), (today - __import__("datetime").timedelta(days=2)).isoformat()],
             "frequency": "daily", "streak": 0, "best_streak": 0}
        hb._recalc_streak(h)
        self.assertEqual(h["streak"], 1)

    def test_weekly_frequency(self):
        today = date.today()
        h = {"log": [today.isoformat(), (today - __import__("datetime").timedelta(days=3)).isoformat()],
             "frequency": "weekly", "streak": 0, "best_streak": 0}
        hb._recalc_streak(h)
        # weekly: decrements by 1 each day but doesn't break on missing days
        # streak counts logged days in the window
        self.assertGreaterEqual(h["streak"], 1)

    def test_best_streak_updated(self):
        today = date.today()
        h = {"log": [today.isoformat()], "frequency": "daily",
             "streak": 0, "best_streak": 5}
        hb._recalc_streak(h)
        self.assertEqual(h["streak"], 1)
        self.assertEqual(h["best_streak"], 5)  # not lowered

    def test_best_streak_increased(self):
        today = date.today()
        h = {"log": [today.isoformat()], "frequency": "daily",
             "streak": 0, "best_streak": 0}
        hb._recalc_streak(h)
        self.assertEqual(h["best_streak"], 1)

    def test_invalid_date_in_logs(self):
        h = {"log": ["not-a-date"], "frequency": "daily", "streak": 0,
             "best_streak": 0}
        # floor computation: date.fromisoformat raises -> floor = check - 365 days
        hb._recalc_streak(h)
        self.assertEqual(h["streak"], 0)

    def test_index_error_floor(self):
        h = {"log": [], "frequency": "daily", "streak": 0, "best_streak": 0}
        hb._recalc_streak(h)
        self.assertEqual(h["streak"], 0)

    def test_guard_cap(self):
        # many logs but guard prevents infinite loop
        today = date.today()
        logs = [(today - timedelta(days=i)).isoformat() for i in range(100)]
        h = {"log": logs, "frequency": "weekly", "streak": 0, "best_streak": 0}
        hb._recalc_streak(h)
        self.assertGreaterEqual(h["streak"], 1)


class DeleteTests(unittest.TestCase):
    def setUp(self):
        self._orig = hb.HABITS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "habits.json"
        hb.HABITS_FILE = self._path
        self.addCleanup(setattr, hb, "HABITS_FILE", self._orig)
        self.h = hb.add("exercise")

    def test_delete_success(self):
        self.assertTrue(hb.delete(self.h["id"]))
        self.assertEqual(hb.get_all(), [])

    def test_delete_missing(self):
        self.assertFalse(hb.delete(99999))

    def test_delete_does_not_save_when_missing(self):
        with mock.patch.object(hb, "_save") as sv:
            hb.delete(99999)
        sv.assert_not_called()


class TodayStatusTests(unittest.TestCase):
    def setUp(self):
        self._orig = hb.HABITS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "habits.json"
        hb.HABITS_FILE = self._path
        self.addCleanup(setattr, hb, "HABITS_FILE", self._orig)
        self.h = hb.add("exercise")

    def test_not_done(self):
        items = hb.today_status()
        self.assertEqual(len(items), 1)
        self.assertFalse(items[0]["done"])
        self.assertEqual(items[0]["name"], "exercise")
        self.assertEqual(items[0]["frequency"], "daily")
        self.assertEqual(items[0]["total"], 0)
        self.assertIn("id", items[0])
        self.assertIn("streak", items[0])
        self.assertIn("best_streak", items[0])

    def test_done(self):
        hb.log(self.h["id"])
        items = hb.today_status()
        self.assertTrue(items[0]["done"])
        self.assertEqual(items[0]["total"], 1)


class WeekProgressTests(unittest.TestCase):
    def setUp(self):
        self._orig = hb.HABITS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "habits.json"
        hb.HABITS_FILE = self._path
        self.addCleanup(setattr, hb, "HABITS_FILE", self._orig)
        self.h = hb.add("exercise")

    def test_empty(self):
        wp = hb.week_progress()
        self.assertEqual(len(wp), 7)
        self.assertTrue(all(v == 0 for v in wp.values()))

    def test_with_log(self):
        today = date.today().isoformat()
        hb.log(self.h["id"], today)
        wp = hb.week_progress()
        self.assertEqual(wp[today], 1)

    def test_sorted_keys(self):
        wp = hb.week_progress()
        keys = list(wp.keys())
        self.assertEqual(keys, sorted(keys))


class FormatListTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(hb.format_list([]), "✅ Koi habits nahi hai. 'add habit' bolo naya habit banane ke liye.")

    def test_none_loads_all(self):
        with mock.patch.object(hb, "get_all", return_value=[]):
            self.assertEqual(hb.format_list(None), "✅ Koi habits nahi hai. 'add habit' bolo naya habit banane ke liye.")

    def test_with_habits(self):
        h = {"id": 1, "name": "exercise", "frequency": "daily", "log": [],
             "streak": 3, "best_streak": 5}
        out = hb.format_list([h])
        self.assertIn("✅ **Your Habits:**", out)
        self.assertIn("1. #1 ⬜ **exercise** [daily] 🔥3d", out)

    def test_done_status(self):
        today = date.today().isoformat()
        h = {"id": 1, "name": "ex", "frequency": "daily", "log": [today],
             "streak": 0, "best_streak": 0}
        out = hb.format_list([h])
        self.assertIn("1. #1 ✅ **ex** [daily]", out)

    def test_no_streak_no_fire(self):
        h = {"id": 1, "name": "ex", "frequency": "daily", "log": [],
             "streak": 0, "best_streak": 0}
        out = hb.format_list([h])
        self.assertNotIn("🔥", out)

    def test_cap_15(self):
        habits = [{"id": i, "name": f"h{i}", "frequency": "daily", "log": [],
                   "streak": 0, "best_streak": 0} for i in range(20)]
        out = hb.format_list(habits)
        self.assertEqual(out.count("#"), 15)


class FormatTodayTests(unittest.TestCase):
    def setUp(self):
        self._orig = hb.HABITS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "habits.json"
        hb.HABITS_FILE = self._path
        self.addCleanup(setattr, hb, "HABITS_FILE", self._orig)

    def test_empty(self):
        self.assertEqual(hb.format_today(), "✅ Aaj ke liye koi habits nahi hai.")

    def test_with_done_and_pending(self):
        h = hb.add("exercise")
        hb.add("read")
        hb.log(h["id"])
        out = hb.format_today()
        self.assertIn("✅ **Today's Habits:**", out)
        self.assertIn("Done (1):", out)
        self.assertIn("Pending (1):", out)
        self.assertIn("✅ #", out)
        self.assertIn("⬜ #", out)

    def test_all_pending(self):
        hb.add("exercise")
        out = hb.format_today()
        self.assertIn("Pending (1):", out)
        self.assertNotIn("Done", out)

    def test_all_done(self):
        h = hb.add("exercise")
        hb.log(h["id"])
        out = hb.format_today()
        self.assertIn("Done (1):", out)
        self.assertNotIn("Pending", out)


if __name__ == "__main__":
    unittest.main()
