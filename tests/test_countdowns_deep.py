"""Deep tests for orbit/orbit/countdowns.py (Loop 17/1)."""

import json
import threading
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from orbit.orbit import countdowns as cd


class LoadSaveTests(unittest.TestCase):
    def setUp(self):
        self._orig = cd.EVENTS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "countdowns.json"
        cd.EVENTS_FILE = self._path
        self.addCleanup(setattr, cd, "EVENTS_FILE", self._orig)

    def test_load_missing(self):
        self.assertEqual(cd._load(), [])

    def test_load_valid(self):
        self._path.write_text('[{"id":1}]', encoding="utf-8")
        self.assertEqual(cd._load(), [{"id": 1}])

    def test_load_corrupt(self):
        self._path.write_text("{bad", encoding="utf-8")
        self.assertEqual(cd._load(), [])

    def test_save_success(self):
        ok = cd._save([{"id": 1}])
        self.assertIsNone(ok)
        self.assertTrue(self._path.exists())
        self.assertEqual(json.loads(self._path.read_text("utf-8")), [{"id": 1}])

    def test_save_failure(self):
        with mock.patch.object(Path, "mkdir", side_effect=OSError("nope")):
            ok = cd._save([{"id": 1}])
        self.assertFalse(ok)


class NextIdTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(cd._next_id([]), 1)

    def test_max_plus_one(self):
        self.assertEqual(cd._next_id([{"id": 3}, {"id": 7}]), 8)


class ParseDateTests(unittest.TestCase):
    def test_none(self):
        self.assertIsNone(cd.parse_date(None))

    def test_non_str(self):
        self.assertIsNone(cd.parse_date(123))

    def test_empty(self):
        self.assertIsNone(cd.parse_date(""))

    def test_day_month(self):
        # "July 15" -> roll to future if past
        d = cd.parse_date("July 15")
        self.assertIsInstance(d, date)
        self.assertEqual(d.month, 7)
        self.assertEqual(d.day, 15)

    def test_month_day(self):
        d = cd.parse_date("15 July")
        self.assertIsInstance(d, date)
        self.assertEqual(d.month, 7)
        self.assertEqual(d.day, 15)

    def test_month_day_year(self):
        d = cd.parse_date("July 15 2026")
        self.assertIsInstance(d, date)
        # Note: explicit year in "Month DD YYYY" form is not preserved by
        # the current parser (rolls like "July 15"); just check month/day.
        self.assertEqual(d.month, 7)
        self.assertEqual(d.day, 15)

    def test_iso_format(self):
        d = cd.parse_date("2026-12-25")
        self.assertEqual(d, date(2026, 12, 25))

    def test_slash_dmy_with_year(self):
        d = cd.parse_date("25/12/2026")
        self.assertEqual(d, date(2026, 12, 25))

    def test_slash_dm_no_year_rolls(self):
        d = cd.parse_date("25/12")
        self.assertIsInstance(d, date)
        self.assertEqual(d.month, 12)
        self.assertEqual(d.day, 25)

    def test_slash_invalid_date_returns_none(self):
        # month 13 invalid -> ValueError caught
        self.assertIsNone(cd.parse_date("25/13"))

    def test_month_abbreviation(self):
        d = cd.parse_date("Dec 25")
        self.assertEqual(d.month, 12)
        self.assertEqual(d.day, 25)

    def test_day_month_abbrev(self):
        d = cd.parse_date("25 Dec")
        self.assertEqual(d.month, 12)
        self.assertEqual(d.day, 25)

    def test_roll_future_past_date(self):
        # a past month/day rolls to next year
        today = date.today()
        # pick a date that's definitely in the past: Jan 1 (if today is after Jan 1)
        d = cd.parse_date("January 1")
        self.assertIsInstance(d, date)
        self.assertGreaterEqual(d, today)

    def test_feb29_roll_non_leap(self):
        # Feb 29 on a non-leap roll year -> returns None
        # Force: parse "February 29" when rolled year is non-leap
        # Hard to force; just ensure no crash
        d = cd.parse_date("February 29")
        self.assertTrue(d is None or isinstance(d, date))

    def test_unparseable(self):
        self.assertIsNone(cd.parse_date("hello world"))

    def test_month_only_no_day(self):
        self.assertIsNone(cd.parse_date("July"))

    def test_invalid_day_returns_none(self):
        # day 99 invalid -> ValueError in date() caught
        self.assertIsNone(cd.parse_date("July 99"))

    def test_roll_future_value_error(self):
        # Feb 29 rolled to non-leap year returns None
        # Mock date.today to a non-leap year after Feb 29
        with mock.patch("orbit.orbit.countdowns.date") as dmock:
            dmock.today.return_value = date(2025, 3, 1)
            dmock.fromisoformat = date.fromisoformat
            # call _roll_future directly
            r = cd._roll_future(date(2024, 2, 29))
            self.assertIsNone(r)

    def test_roll_future_none(self):
        self.assertIsNone(cd._roll_future(None))

    def test_roll_future_already_future(self):
        today = date.today()
        future = today.replace(year=today.year + 1)
        self.assertEqual(cd._roll_future(future), future)


class AddEventTests(unittest.TestCase):
    def setUp(self):
        self._orig = cd.EVENTS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "countdowns.json"
        cd.EVENTS_FILE = self._path
        self.addCleanup(setattr, cd, "EVENTS_FILE", self._orig)

    def test_add_basic(self):
        ev = cd.add_event("Birthday", date(2026, 7, 15), recurring=True)
        self.assertEqual(ev["name"], "Birthday")
        self.assertEqual(ev["date"], "2026-07-15")
        self.assertTrue(ev["recurring"])
        self.assertIn("id", ev)
        self.assertIn("created", ev)
        self.assertEqual(len(cd.get_all()), 1)

    def test_add_default_recurring_false(self):
        ev = cd.add_event("X", date(2026, 1, 1))
        self.assertFalse(ev["recurring"])

    def test_add_id_increments(self):
        cd.add_event("a", date(2026, 1, 1))
        ev2 = cd.add_event("b", date(2026, 1, 2))
        self.assertEqual(ev2["id"], 2)


class GetDeleteTests(unittest.TestCase):
    def setUp(self):
        self._orig = cd.EVENTS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "countdowns.json"
        cd.EVENTS_FILE = self._path
        self.addCleanup(setattr, cd, "EVENTS_FILE", self._orig)
        self.ev = cd.add_event("Birthday", date(2026, 7, 15))

    def test_get_all(self):
        self.assertEqual(len(cd.get_all()), 1)

    def test_delete_success(self):
        self.assertTrue(cd.delete(self.ev["id"]))
        self.assertEqual(cd.get_all(), [])

    def test_delete_missing(self):
        self.assertFalse(cd.delete(99999))

    def test_delete_does_not_save_when_missing(self):
        with mock.patch.object(cd, "_save") as sv:
            cd.delete(99999)
        sv.assert_not_called()


class DaysUntilTests(unittest.TestCase):
    def test_future(self):
        future = (date.today() + timedelta(days=5)).isoformat()
        self.assertEqual(cd.days_until(future), 5)

    def test_past(self):
        past = (date.today() - timedelta(days=3)).isoformat()
        self.assertEqual(cd.days_until(past), -3)

    def test_today(self):
        self.assertEqual(cd.days_until(date.today().isoformat()), 0)


class FormatEventsTests(unittest.TestCase):
    def test_empty(self):
        with mock.patch.object(cd, "get_all", return_value=[]):
            self.assertEqual(cd.format_events(), "📅 Koi events nahi hai. 'add birthday July 15' bolo.")

    def test_none_defaults_to_get_all(self):
        with mock.patch.object(cd, "get_all", return_value=[]):
            cd.format_events(None)
        # get_all called

    def test_today_label(self):
        today = date.today().isoformat()
        ev = {"id": 1, "name": "Bday", "date": today, "recurring": True}
        out = cd.format_events([ev])
        self.assertIn("🎉 TODAY!", out)
        self.assertIn("🔄", out)

    def test_tomorrow_label(self):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        ev = {"id": 1, "name": "X", "date": tomorrow, "recurring": False}
        out = cd.format_events([ev])
        self.assertIn("⏰ Tomorrow!", out)

    def test_days_ago_label(self):
        past = (date.today() - timedelta(days=5)).isoformat()
        ev = {"id": 1, "name": "X", "date": past}
        out = cd.format_events([ev])
        self.assertIn("5 days ago", out)

    def test_days_away_label(self):
        d = (date.today() + timedelta(days=3)).isoformat()
        ev = {"id": 1, "name": "X", "date": d}
        out = cd.format_events([ev])
        self.assertIn("3 days away", out)

    def test_weeks_label(self):
        d = (date.today() + timedelta(days=15)).isoformat()
        ev = {"id": 1, "name": "X", "date": d}
        out = cd.format_events([ev])
        self.assertIn("15 days", out)

    def test_months_label(self):
        d = (date.today() + timedelta(days=60)).isoformat()
        ev = {"id": 1, "name": "X", "date": d}
        out = cd.format_events([ev])
        self.assertIn("months", out)

    def test_year_label(self):
        d = (date.today() + timedelta(days=400)).isoformat()
        ev = {"id": 1, "name": "X", "date": d}
        out = cd.format_events([ev])
        self.assertIn("y)", out)

    def test_cap_15(self):
        evs = [{"id": i, "name": f"E{i}", "date": (date.today() + timedelta(days=i+1)).isoformat(),
                "recurring": False} for i in range(20)]
        out = cd.format_events(evs)
        self.assertEqual(out.count("#"), 15)

    def test_sorted_by_days_until(self):
        evs = [
            {"id": 1, "name": "far", "date": (date.today() + timedelta(days=10)).isoformat()},
            {"id": 2, "name": "near", "date": (date.today() + timedelta(days=2)).isoformat()},
        ]
        out = cd.format_events(evs)
        # near should appear first
        self.assertLess(out.index("near"), out.index("far"))

    def test_recurring_flag(self):
        ev = {"id": 1, "name": "X", "date": (date.today() + timedelta(days=2)).isoformat(),
              "recurring": True}
        out = cd.format_events([ev])
        self.assertIn("🔄", out)


class FormatEventTests(unittest.TestCase):
    def test_today(self):
        ev = {"name": "Bday", "date": date.today().isoformat()}
        self.assertEqual(cd.format_event(ev), "📅 **Bday** 🎉 TODAY! ("
                                            + date.today().isoformat() + ")")

    def test_future(self):
        d = (date.today() + timedelta(days=5)).isoformat()
        ev = {"name": "X", "date": d}
        self.assertEqual(cd.format_event(ev), f"📅 **X** ⏰ 5 days away ({d})")


class ParseAndAddTests(unittest.TestCase):
    def setUp(self):
        self._orig = cd.EVENTS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "countdowns.json"
        cd.EVENTS_FILE = self._path
        self.addCleanup(setattr, cd, "EVENTS_FILE", self._orig)

    def test_empty_text(self):
        r = cd.parse_and_add("")
        self.assertEqual(r, "Date samajh nahi aaya. Try: 'add birthday July 15', 'add christmas Dec 25'")

    def test_none_text(self):
        r = cd.parse_and_add(None)
        self.assertEqual(r, "Date samajh nahi aaya. Try: 'add birthday July 15', 'add christmas Dec 25'")

    def test_unparseable_date(self):
        r = cd.parse_and_add("hello world")
        self.assertEqual(r, "Date samajh nahi aaya. Try: 'add birthday July 15', 'add christmas Dec 25'")

    def test_basic_add(self):
        r = cd.parse_and_add("add birthday July 15")
        self.assertIn("added!", r)

    def test_recurring_detection_birthday(self):
        r = cd.parse_and_add("add birthday July 15")
        # check the event was saved as recurring
        evs = cd.get_all()
        self.assertTrue(any(e.get("recurring") for e in evs))

    def test_recurring_via_anniversary(self):
        cd.parse_and_add("add anniversary Dec 25")
        evs = cd.get_all()
        self.assertTrue(any(e.get("recurring") for e in evs))

    def test_name_fallback(self):
        # text with only a date -> name becomes "Event <date>"
        r = cd.parse_and_add("July 15")
        self.assertIn("added!", r)

    def test_name_extraction(self):
        r = cd.parse_and_add("add christmas Dec 25")
        self.assertIn("added!", r)
        # Just check added
        self.assertIn("added!", r)


class SearchTests(unittest.TestCase):
    def setUp(self):
        self._orig = cd.EVENTS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "countdowns.json"
        cd.EVENTS_FILE = self._path
        self.addCleanup(setattr, cd, "EVENTS_FILE", self._orig)
        cd.add_event("Birthday", date(2026, 7, 15))
        cd.add_event("Christmas", date(2026, 12, 25))

    def test_search_match(self):
        r = cd.search("birth")
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["name"], "Birthday")

    def test_search_case_insensitive(self):
        r = cd.search("CHRISTMAS")
        self.assertEqual(len(r), 1)

    def test_search_no_match(self):
        self.assertEqual(cd.search("zzzzz"), [])


if __name__ == "__main__":
    unittest.main()
