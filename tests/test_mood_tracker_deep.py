"""Deep tests for orbit/orbit/core/mood_tracker.py (Loop 18/4)."""

import json
import threading
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from orbit.orbit.core import mood_tracker as mt


class InitLoadTests(unittest.TestCase):
    def _tmp(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d) / "mood"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def test_init_creates_dir(self):
        d = self._tmp()
        with mock.patch("orbit.orbit.core.mood_tracker.DATA_DIR", d):
            m = mt.MoodTracker()
        self.assertTrue(hasattr(m, "_lock"))
        self.assertEqual(m._entries, [])

    def test_load_valid_list(self):
        d = self._tmp()
        f = d / "mood_entries.json"
        f.write_text('[{"id":"1","score":5,"category":"happy","timestamp":"2026-01-01T10:00:00+00:00","productivity":0,"note":""}]',
                    encoding="utf-8")
        with mock.patch("orbit.orbit.core.mood_tracker.DATA_DIR", d):
            m = mt.MoodTracker()
        self.assertEqual(len(m._entries), 1)

    def test_load_null_shape(self):
        d = self._tmp()
        f = d / "mood_entries.json"
        f.write_text("null", encoding="utf-8")
        with mock.patch("orbit.orbit.core.mood_tracker.DATA_DIR", d):
            m = mt.MoodTracker()
        self.assertEqual(m._entries, [])

    def test_load_corrupt(self):
        d = self._tmp()
        f = d / "mood_entries.json"
        f.write_text("{bad", encoding="utf-8")
        with mock.patch("orbit.orbit.core.mood_tracker.DATA_DIR", d):
            m = mt.MoodTracker()
        self.assertEqual(m._entries, [])

    def test_load_missing(self):
        d = self._tmp()
        with mock.patch("orbit.orbit.core.mood_tracker.DATA_DIR", d):
            m = mt.MoodTracker()
        self.assertEqual(m._entries, [])

    def test_save_success(self):
        d = self._tmp()
        m = mt.MoodTracker.__new__(mt.MoodTracker)
        m._mood_file = d / "mood_entries.json"
        m._lock = threading.Lock()
        m._entries = [{"id": "1", "score": 5}]
        m._save()
        self.assertTrue(m._mood_file.exists())
        data = json.loads if False else None
        import json
        self.assertEqual(json.loads(m._mood_file.read_text("utf-8")), [{"id": "1", "score": 5}])

    def test_save_failure(self):
        d = self._tmp()
        m = mt.MoodTracker.__new__(mt.MoodTracker)
        m._mood_file = d / "mood_entries.json"
        m._lock = threading.Lock()
        m._entries = [{"id": "1"}]
        with mock.patch("builtins.open", side_effect=OSError("boom")), \
                mock.patch.object(mt, "logger") as lg:
            m._save()
        lg.error.assert_called_once()


class LogMoodTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.mood_tracker.DATA_DIR", self._d):
            self.m = mt.MoodTracker()

    def test_log_basic(self):
        e = self.m.log_mood(5, "happy", note="hi", productivity=3)
        self.assertEqual(e["score"], 5)
        self.assertEqual(e["category"], "happy")
        self.assertEqual(e["note"], "hi")
        self.assertEqual(e["productivity"], 3)
        self.assertIn("id", e)
        self.assertIn("timestamp", e)
        self.assertEqual(len(self.m._entries), 1)

    def test_score_clamp_low(self):
        e = self.m.log_mood(0, "happy")
        self.assertEqual(e["score"], 1)

    def test_score_clamp_high(self):
        e = self.m.log_mood(99, "happy")
        self.assertEqual(e["score"], 10)

    def test_score_invalid_type(self):
        e = self.m.log_mood("abc", "happy")
        self.assertEqual(e["score"], 5)

    def test_productivity_clamp(self):
        e = self.m.log_mood(5, "happy", productivity=99)
        self.assertEqual(e["productivity"], 10)
        e2 = self.m.log_mood(5, "happy", productivity=-5)
        self.assertEqual(e2["productivity"], 0)

    def test_productivity_invalid(self):
        e = self.m.log_mood(5, "happy", productivity="x")
        self.assertEqual(e["productivity"], 0)

    def test_unknown_category_defaults_happy(self):
        e = self.m.log_mood(5, "nope")
        self.assertEqual(e["category"], "happy")

    def test_cap_5000(self):
        self.m._entries = [{"id": str(i)} for i in range(5000)]
        self.m.log_mood(5, "happy")
        self.assertEqual(len(self.m._entries), 5000)

    def test_log_returns_entry(self):
        e = self.m.log_mood(7, "focused")
        self.assertEqual(e["score"], 7)
        self.assertEqual(e["category"], "focused")

    def test_timestamp_utc(self):
        e = self.m.log_mood(5, "happy")
        self.assertIn("+", e["timestamp"])  # UTC isoformat has +00:00


class GetHistoryTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.mood_tracker.DATA_DIR", self._d):
            self.m = mt.MoodTracker()
        for i in range(5):
            self.m.log_mood(i + 1, "happy")

    def test_default_limit_30(self):
        r = self.m.get_history()
        self.assertEqual(len(r), 5)

    def test_limit(self):
        r = self.m.get_history(2)
        self.assertEqual(len(r), 2)
        # reversed
        self.assertEqual(r[0]["score"], 5)
        self.assertEqual(r[1]["score"], 4)

    def test_limit_larger_than_entries(self):
        r = self.m.get_history(100)
        self.assertEqual(len(r), 5)


class GetTodayTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.mood_tracker.DATA_DIR", self._d):
            self.m = mt.MoodTracker()

    def test_none_when_empty(self):
        self.assertIsNone(self.m.get_today())

    def test_returns_last_today_entry(self):
        self.m.log_mood(5, "happy")
        self.m.log_mood(7, "focused")
        r = self.m.get_today()
        self.assertEqual(r["score"], 7)

    def test_ignores_yesterday(self):
        # inject an entry with yesterday's timestamp
        from datetime import datetime, timedelta, timezone
        yest = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        self.m._entries.append({"id": "old", "score": 9, "category": "happy",
                                "timestamp": yest, "productivity": 0, "note": ""})
        self.m.log_mood(5, "happy")
        r = self.m.get_today()
        self.assertEqual(r["score"], 5)


class GetPatternsTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.mood_tracker.DATA_DIR", self._d):
            self.m = mt.MoodTracker()

    def test_empty(self):
        r = self.m.get_patterns()
        self.assertEqual(r["average_mood"], 0)
        self.assertEqual(r["mood_by_day_of_week"], {})
        self.assertIsNone(r["most_common_category"])
        self.assertEqual(r["mood_productivity_correlation"],
                         {"high_mood_avg": 0, "low_mood_avg": 0})
        self.assertEqual(r["streak_data"], 0)

    def test_with_entries(self):
        self.m.log_mood(8, "happy", productivity=5)
        self.m.log_mood(4, "tired", productivity=2)
        r = self.m.get_patterns()
        self.assertEqual(r["average_mood"], 6.0)
        self.assertIn("most_common_category", r)
        self.assertEqual(r["mood_productivity_correlation"]["high_mood_avg"], 5.0)
        self.assertEqual(r["mood_productivity_correlation"]["low_mood_avg"], 2.0)
        self.assertGreaterEqual(r["streak_data"], 1)

    def test_most_common_category(self):
        self.m.log_mood(5, "happy")
        self.m.log_mood(5, "happy")
        self.m.log_mood(5, "tired")
        r = self.m.get_patterns()
        self.assertEqual(r["most_common_category"], "happy")

    def test_high_mood_no_productivity(self):
        self.m.log_mood(9, "happy", productivity=0)
        r = self.m.get_patterns()
        self.assertEqual(r["mood_productivity_correlation"]["high_mood_avg"], 0)

    def test_low_mood_no_productivity(self):
        self.m.log_mood(3, "tired", productivity=0)
        r = self.m.get_patterns()
        self.assertEqual(r["mood_productivity_correlation"]["low_mood_avg"], 0)

    def test_mood_by_day(self):
        self.m.log_mood(7, "focused")
        r = self.m.get_patterns()
        self.assertIsInstance(r["mood_by_day_of_week"], dict)
        self.assertGreater(len(r["mood_by_day_of_week"]), 0)

    def test_streak_multiple_days(self):
        from datetime import datetime, timedelta, timezone
        # inject entries for yesterday and today
        yest = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        self.m._entries.append({"id": "y", "score": 5, "category": "happy",
                                "timestamp": yest, "productivity": 0, "note": ""})
        self.m.log_mood(5, "happy")
        r = self.m.get_patterns()
        self.assertEqual(r["streak_data"], 2)


class WeeklyReportTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.mood_tracker.DATA_DIR", self._d):
            self.m = mt.MoodTracker()

    def test_empty(self):
        r = self.m.get_weekly_report()
        self.assertEqual(r["total_entries"], 0)
        self.assertEqual(r["average_mood"], 0)
        self.assertEqual(r["categories"], {})
        self.assertEqual(r["productivity_avg"], 0)
        self.assertIsNone(r["best_day"])
        self.assertEqual(r["mood_trend"], [])

    def test_with_entries(self):
        self.m.log_mood(8, "happy", productivity=5)
        self.m.log_mood(4, "tired", productivity=2)
        r = self.m.get_weekly_report()
        self.assertEqual(r["total_entries"], 2)
        self.assertEqual(r["average_mood"], 6.0)
        self.assertIn("happy", r["categories"])
        self.assertEqual(r["productivity_avg"], 3.5)
        self.assertIsNotNone(r["best_day"])
        self.assertEqual(len(r["mood_trend"]), 2)

    def test_best_day_selection(self):
        # two entries same day
        self.m.log_mood(9, "happy")
        self.m.log_mood(9, "happy")
        r = self.m.get_weekly_report()
        self.assertIsNotNone(r["best_day"])

    def test_productivity_avg_zero_when_none(self):
        self.m.log_mood(5, "happy", productivity=0)
        r = self.m.get_weekly_report()
        self.assertEqual(r["productivity_avg"], 0)


class ToneSuggestionTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.mood_tracker.DATA_DIR", self._d):
            self.m = mt.MoodTracker()

    def test_no_today_returns_default(self):
        from orbit.orbit.config import TITLE
        self.assertEqual(self.m.get_tone_suggestion(),
                         f"{TITLE}, at your service.")

    def test_tired_suggestion(self):
        from orbit.orbit.config import TITLE
        self.m.log_mood(3, "tired")
        self.assertEqual(self.m.get_tone_suggestion(),
                         f"{TITLE}, I'll keep it brief. You need rest.")

    def test_unknown_category_default(self):
        from orbit.orbit.config import TITLE
        # force an entry with unknown category by direct append
        self.m._entries.append({"id": "x", "score": 5, "category": "nope",
                                "timestamp": __import__("datetime").datetime.now(
                                    __import__("datetime").timezone.utc).isoformat(),
                                "productivity": 0, "note": ""})
        self.assertEqual(self.m.get_tone_suggestion(),
                         f"{TITLE}, at your service.")


class SingletonTests(unittest.TestCase):
    def setUp(self):
        self._saved = mt._instance
        mt._instance = None
        self.addCleanup(setattr, mt, "_instance", self._saved)

    def test_creates(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.mood_tracker.DATA_DIR", d):
            a = mt.get_mood_tracker()
        self.assertIsInstance(a, mt.MoodTracker)
        self.assertIs(mt._instance, a)

    def test_reuses(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.mood_tracker.DATA_DIR", d):
            a = mt.get_mood_tracker()
            b = mt.get_mood_tracker()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
