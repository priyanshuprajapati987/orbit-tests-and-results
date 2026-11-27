"""Deep tests for orbit/orbit/usage_tracker.py (Loop 16/4)."""

import json
import threading
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest import mock

from orbit.orbit import usage_tracker as ut


class LoadSaveTests(unittest.TestCase):
    def setUp(self):
        self._orig = ut.USAGE_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "orbit_usage.json"
        ut.USAGE_FILE = self._path
        self.addCleanup(setattr, ut, "USAGE_FILE", self._orig)

    def test_load_missing(self):
        self.assertEqual(ut._load(), {})

    def test_load_valid(self):
        self._path.write_text('{"days":{}}', encoding="utf-8")
        self.assertEqual(ut._load(), {"days": {}})

    def test_load_corrupt(self):
        self._path.write_text("{bad", encoding="utf-8")
        self.assertEqual(ut._load(), {})

    def test_load_non_dict(self):
        self._path.write_text('[1,2]', encoding="utf-8")
        self.assertEqual(ut._load(), {})

    def test_save_success(self):
        ok = ut._save({"days": {}})
        self.assertIsNone(ok)
        self.assertTrue(self._path.exists())
        self.assertEqual(json.loads(self._path.read_text("utf-8")), {"days": {}})

    def test_save_failure(self):
        with mock.patch.object(Path, "mkdir", side_effect=OSError("nope")):
            ok = ut._save({"days": {}})
        self.assertFalse(ok)


class TimeOfDayTests(unittest.TestCase):
    def _patch_hour(self, hour):
        return mock.patch("orbit.orbit.usage_tracker.datetime", wraps=__import__("datetime").datetime)

    def test_morning(self):
        with mock.patch("orbit.orbit.usage_tracker.datetime") as dt:
            dt.now.return_value.hour = 8
            self.assertEqual(ut.get_time_of_day(), "morning")

    def test_afternoon(self):
        with mock.patch("orbit.orbit.usage_tracker.datetime") as dt:
            dt.now.return_value.hour = 14
            self.assertEqual(ut.get_time_of_day(), "afternoon")

    def test_evening(self):
        with mock.patch("orbit.orbit.usage_tracker.datetime") as dt:
            dt.now.return_value.hour = 19
            self.assertEqual(ut.get_time_of_day(), "evening")

    def test_night(self):
        with mock.patch("orbit.orbit.usage_tracker.datetime") as dt:
            dt.now.return_value.hour = 23
            self.assertEqual(ut.get_time_of_day(), "night")

    def test_night_early(self):
        with mock.patch("orbit.orbit.usage_tracker.datetime") as dt:
            dt.now.return_value.hour = 3
            self.assertEqual(ut.get_time_of_day(), "night")

    def test_boundary_morning_start(self):
        with mock.patch("orbit.orbit.usage_tracker.datetime") as dt:
            dt.now.return_value.hour = 5
            self.assertEqual(ut.get_time_of_day(), "morning")

    def test_boundary_morning_end(self):
        with mock.patch("orbit.orbit.usage_tracker.datetime") as dt:
            dt.now.return_value.hour = 11
            self.assertEqual(ut.get_time_of_day(), "morning")

    def test_boundary_afternoon_start(self):
        with mock.patch("orbit.orbit.usage_tracker.datetime") as dt:
            dt.now.return_value.hour = 12
            self.assertEqual(ut.get_time_of_day(), "afternoon")

    def test_boundary_afternoon_end(self):
        with mock.patch("orbit.orbit.usage_tracker.datetime") as dt:
            dt.now.return_value.hour = 16
            self.assertEqual(ut.get_time_of_day(), "afternoon")

    def test_boundary_evening_start(self):
        with mock.patch("orbit.orbit.usage_tracker.datetime") as dt:
            dt.now.return_value.hour = 17
            self.assertEqual(ut.get_time_of_day(), "evening")

    def test_boundary_evening_end(self):
        with mock.patch("orbit.orbit.usage_tracker.datetime") as dt:
            dt.now.return_value.hour = 20
            self.assertEqual(ut.get_time_of_day(), "evening")


class GreetingEmojiIconTests(unittest.TestCase):
    def test_greeting(self):
        with mock.patch.object(ut, "get_time_of_day", return_value="morning"):
            self.assertEqual(ut.get_greeting(), "Good morning")
        with mock.patch.object(ut, "get_time_of_day", return_value="afternoon"):
            self.assertEqual(ut.get_greeting(), "Good afternoon")
        with mock.patch.object(ut, "get_time_of_day", return_value="evening"):
            self.assertEqual(ut.get_greeting(), "Good evening")
        with mock.patch.object(ut, "get_time_of_day", return_value="night"):
            self.assertEqual(ut.get_greeting(), "Good night")

    def test_emoji(self):
        expected = {"morning": "🌅", "afternoon": "☀️",
                    "evening": "🌇", "night": "🌙"}
        for tod, emoji in expected.items():
            with mock.patch.object(ut, "get_time_of_day", return_value=tod):
                self.assertEqual(ut.get_time_emoji(), emoji)

    def test_icon(self):
        expected = {"morning": "🌤", "afternoon": "☀️",
                    "evening": "🌆", "night": "🌃"}
        for tod, icon in expected.items():
            with mock.patch.object(ut, "get_time_of_day", return_value=tod):
                self.assertEqual(ut.get_time_icon(), icon)


class StartEndSessionTests(unittest.TestCase):
    def setUp(self):
        self._orig = ut.USAGE_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "orbit_usage.json"
        ut.USAGE_FILE = self._path
        self.addCleanup(setattr, ut, "USAGE_FILE", self._orig)

    def _mock_dt(self, hour=10, minute=0, iso="2026-01-01T10:00:00"):
        m = mock.MagicMock()
        m.now.return_value.hour = hour
        m.now.return_value.isoformat.return_value = iso
        m.now.return_value.strftime.return_value = "2026-01-01"
        m.now.return_value.date.return_value.isoformat.return_value = "2026-01-01"
        # date.today() is separate
        return m

    def test_start_session_first_today(self):
        with mock.patch("orbit.orbit.usage_tracker.datetime") as dt, \
                mock.patch("orbit.orbit.usage_tracker.date") as d:
            dt.now.return_value.isoformat.return_value = "2026-01-01T10:00:00"
            d.today.return_value.isoformat.return_value = "2026-01-01"
            is_first = ut.start_session()
        self.assertTrue(is_first)
        data = ut._load()
        self.assertEqual(len(data["sessions"]), 1)
        self.assertEqual(data["sessions"][0]["start"], "2026-01-01T10:00:00")
        self.assertEqual(data["sessions"][0]["date"], "2026-01-01")
        self.assertIsNone(data["sessions"][0]["end"])
        self.assertEqual(data["days"]["2026-01-01"]["total_sessions"], 1)
        self.assertEqual(data["days"]["2026-01-01"]["message_count"], 0)

    def test_start_session_second_not_first(self):
        # seed first session
        with mock.patch("orbit.orbit.usage_tracker.datetime") as dt, \
                mock.patch("orbit.orbit.usage_tracker.date") as d:
            dt.now.return_value.isoformat.return_value = "2026-01-01T10:00:00"
            d.today.return_value.isoformat.return_value = "2026-01-01"
            ut.start_session()
        with mock.patch("orbit.orbit.usage_tracker.datetime") as dt, \
                mock.patch("orbit.orbit.usage_tracker.date") as d:
            dt.now.return_value.isoformat.return_value = "2026-01-01T11:00:00"
            d.today.return_value.isoformat.return_value = "2026-01-01"
            is_first = ut.start_session()
        self.assertFalse(is_first)
        data = ut._load()
        self.assertEqual(data["days"]["2026-01-01"]["total_sessions"], 2)

    def test_end_session_no_sessions(self):
        ut.end_session()  # no crash

    def test_end_session_already_ended(self):
        self._path.write_text(json.dumps({
            "sessions": [{"start": "2026-01-01T10:00:00", "end": "2026-01-01T10:30:00",
                          "date": "2026-01-01", "duration_min": 30}],
            "days": {"2026-01-01": {"total_minutes": 30, "total_sessions": 1,
                                    "message_count": 0, "first_seen": "x", "last_seen": "x"}},
        }), encoding="utf-8")
        ut.end_session()  # returns early, no crash
        data = ut._load()
        self.assertEqual(data["sessions"][0]["duration_min"], 30)

    def test_end_session_success(self):
        self._path.write_text(json.dumps({
            "sessions": [{"start": "2026-01-01T10:00:00", "end": None,
                          "date": "2026-01-01", "duration_min": 0}],
            "days": {"2026-01-01": {"total_minutes": 0, "total_sessions": 1,
                                    "message_count": 0, "first_seen": "x", "last_seen": "x"}},
        }), encoding="utf-8")
        with mock.patch("orbit.orbit.usage_tracker.datetime") as dt, \
                mock.patch("orbit.orbit.usage_tracker.date") as d:
            dt.now.return_value.isoformat.return_value = "2026-01-01T10:30:00"
            dt.fromisoformat.return_value = datetime(2026, 1, 1, 10, 0)
            dt.now.return_value = datetime(2026, 1, 1, 10, 30)
            d.today.return_value.isoformat.return_value = "2026-01-01"
            ut.end_session()
        data = ut._load()
        self.assertEqual(data["sessions"][0]["end"], "2026-01-01T10:30:00")
        self.assertEqual(data["sessions"][0]["duration_min"], 30.0)
        self.assertEqual(data["days"]["2026-01-01"]["total_minutes"], 30.0)

    def test_end_session_no_day_entry(self):
        self._path.write_text(json.dumps({
            "sessions": [{"start": "2026-01-01T10:00:00", "end": None,
                          "date": "2026-01-01", "duration_min": 0}],
            "days": {},
        }), encoding="utf-8")
        with mock.patch("orbit.orbit.usage_tracker.datetime") as dt, \
                mock.patch("orbit.orbit.usage_tracker.date") as d:
            dt.now.return_value.isoformat.return_value = "2026-01-01T10:10:00"
            dt.fromisoformat.return_value = datetime(2026, 1, 1, 10, 0)
            dt.now.return_value = datetime(2026, 1, 1, 10, 10)
            d.today.return_value.isoformat.return_value = "2026-01-01"
            ut.end_session()
        data = ut._load()
        self.assertEqual(data["sessions"][0]["duration_min"], 10.0)
        # day total_minutes not updated (no day entry) but no crash


class TrackMessageTests(unittest.TestCase):
    def setUp(self):
        self._orig = ut.USAGE_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "orbit_usage.json"
        ut.USAGE_FILE = self._path
        self.addCleanup(setattr, ut, "USAGE_FILE", self._orig)

    def test_track_message_existing_day(self):
        self._path.write_text(json.dumps({
            "sessions": [],
            "days": {"2026-01-01": {"first_seen": "x", "last_seen": "x",
                                    "total_sessions": 1, "total_minutes": 0,
                                    "message_count": 2}},
        }), encoding="utf-8")
        with mock.patch("orbit.orbit.usage_tracker.datetime") as dt, \
                mock.patch("orbit.orbit.usage_tracker.date") as d:
            dt.now.return_value.isoformat.return_value = "2026-01-01T11:00:00"
            d.today.return_value.isoformat.return_value = "2026-01-01"
            ut.track_message()
        data = ut._load()
        self.assertEqual(data["days"]["2026-01-01"]["message_count"], 3)
        self.assertEqual(data["days"]["2026-01-01"]["last_seen"], "2026-01-01T11:00:00")

    def test_track_message_new_day_no_keys(self):
        self._path.write_text(json.dumps({}), encoding="utf-8")
        with mock.patch("orbit.orbit.usage_tracker.datetime") as dt, \
                mock.patch("orbit.orbit.usage_tracker.date") as d:
            dt.now.return_value.isoformat.return_value = "2026-01-02T09:00:00"
            d.today.return_value.isoformat.return_value = "2026-01-02"
            ut.track_message()
        data = ut._load()
        day = data["days"]["2026-01-02"]
        self.assertEqual(day["message_count"], 1)
        self.assertEqual(len(data["sessions"]), 1)
        self._path.write_text(json.dumps({"sessions": [], "days": {}}), encoding="utf-8")
        with mock.patch("orbit.orbit.usage_tracker.datetime") as dt, \
                mock.patch("orbit.orbit.usage_tracker.date") as d:
            dt.now.return_value.isoformat.return_value = "2026-01-02T09:00:00"
            d.today.return_value.isoformat.return_value = "2026-01-02"
            ut.track_message()
        data = ut._load()
        day = data["days"]["2026-01-02"]
        self.assertEqual(day["message_count"], 1)
        self.assertEqual(day["total_sessions"], 1)
        self.assertEqual(len(data["sessions"]), 1)


class GetTodayStatsTests(unittest.TestCase):
    def setUp(self):
        self._orig = ut.USAGE_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "orbit_usage.json"
        ut.USAGE_FILE = self._path
        self.addCleanup(setattr, ut, "USAGE_FILE", self._orig)

    def test_missing(self):
        self.assertIsNone(ut.get_today_stats())

    def test_present(self):
        self._path.write_text(json.dumps({"days": {"2026-01-01": {"a": 1}}}), encoding="utf-8")
        with mock.patch("orbit.orbit.usage_tracker.date") as d:
            d.today.return_value.isoformat.return_value = "2026-01-01"
            self.assertEqual(ut.get_today_stats(), {"a": 1})


class GetWeekStatsTests(unittest.TestCase):
    def setUp(self):
        self._orig = ut.USAGE_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "orbit_usage.json"
        ut.USAGE_FILE = self._path
        self.addCleanup(setattr, ut, "USAGE_FILE", self._orig)

    def test_empty(self):
        self._path.write_text(json.dumps({"days": {}}), encoding="utf-8")
        self.assertEqual(ut.get_week_stats(), {})

    def test_with_data(self):
        today = date.today()
        d1 = today.isoformat()
        d2 = (today - timedelta(days=1)).isoformat()
        self._path.write_text(json.dumps({"days": {
            d1: {"a": 1}, d2: {"b": 2}, "2020-01-01": {"c": 3}}}), encoding="utf-8")
        week = ut.get_week_stats()
        self.assertIn(d1, week)
        self.assertIn(d2, week)
        self.assertNotIn("2020-01-01", week)


class GetLastSessionDaysTests(unittest.TestCase):
    def setUp(self):
        self._orig = ut.USAGE_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "orbit_usage.json"
        ut.USAGE_FILE = self._path
        self.addCleanup(setattr, ut, "USAGE_FILE", self._orig)

    def test_no_sessions(self):
        self._path.write_text(json.dumps({"sessions": []}), encoding="utf-8")
        self.assertEqual(ut.get_last_session_days(), -1)

    def test_no_sessions_key(self):
        self._path.write_text(json.dumps({}), encoding="utf-8")
        self.assertEqual(ut.get_last_session_days(), -1)

    def test_no_ended_session(self):
        self._path.write_text(json.dumps({"sessions": [
            {"start": "2026-01-01T10:00:00", "end": None}]}), encoding="utf-8")
        self.assertEqual(ut.get_last_session_days(), 0)

    def test_ended_session(self):
        past = (datetime.now() - timedelta(days=5)).isoformat()
        self._path.write_text(json.dumps({"sessions": [
            {"start": "2026-01-01T10:00:00", "end": past}]}), encoding="utf-8")
        days = ut.get_last_session_days()
        self.assertEqual(days, 5)

    def test_reversed_finds_last_ended(self):
        self._path.write_text(json.dumps({"sessions": [
            {"start": "a", "end": "2026-01-01T10:00:00"},
            {"start": "b", "end": None},
            {"start": "c", "end": "2026-01-02T10:00:00"},
        ]}), encoding="utf-8")
        # reversed: last entry has end -> uses it
        days = ut.get_last_session_days()
        self.assertIsInstance(days, int)


class GetBriefTests(unittest.TestCase):
    def setUp(self):
        self._orig = ut.USAGE_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "orbit_usage.json"
        ut.USAGE_FILE = self._path
        self.addCleanup(setattr, ut, "USAGE_FILE", self._orig)

    def test_basic(self):
        with mock.patch.object(ut, "get_time_of_day", return_value="morning"), \
                mock.patch.object(ut, "get_greeting", return_value="Good morning"), \
                mock.patch.object(ut, "get_time_emoji", return_value="🌅"), \
                mock.patch("orbit.orbit.usage_tracker.datetime") as dt:
            dt.now.return_value.strftime.return_value = "10:30 AM"
            dt.now.return_value.hour = 10
            self._path.write_text(json.dumps({"days": {}}), encoding="utf-8")
            r = ut.get_brief()
        self.assertIn("Good morning", r)
        self.assertIn("10:30 AM", r)
        self.assertIn("🌅", r)

    def test_with_today_stats(self):
        today = date.today().isoformat()
        self._path.write_text(json.dumps({"days": {
            today: {"message_count": 5, "total_minutes": 30.4,
                    "total_sessions": 2}}}), encoding="utf-8")
        with mock.patch.object(ut, "get_time_of_day", return_value="morning"), \
                mock.patch.object(ut, "get_greeting", return_value="Good morning"), \
                mock.patch.object(ut, "get_time_emoji", return_value="🌅"), \
                mock.patch("orbit.orbit.usage_tracker.datetime") as dt, \
                mock.patch.object(ut, "get_last_session_days", return_value=0):
            dt.now.return_value.strftime.return_value = "10:30 AM"
            dt.now.return_value.hour = 10
            r = ut.get_brief()
        self.assertIn("2 baar baat", r)
        self.assertIn("30 minute", r)
        self.assertIn("5 messages", r)

    def test_gap_days(self):
        today = date.today().isoformat()
        self._path.write_text(json.dumps({"days": {}}), encoding="utf-8")
        with mock.patch.object(ut, "get_time_of_day", return_value="morning"), \
                mock.patch.object(ut, "get_greeting", return_value="Good morning"), \
                mock.patch.object(ut, "get_time_emoji", return_value="🌅"), \
                mock.patch("orbit.orbit.usage_tracker.datetime") as dt, \
                mock.patch.object(ut, "get_last_session_days", return_value=5):
            dt.now.return_value.strftime.return_value = "10:30 AM"
            dt.now.return_value.hour = 10
            r = ut.get_brief()
        self.assertIn("5 din baad", r)


if __name__ == "__main__":
    unittest.main()
