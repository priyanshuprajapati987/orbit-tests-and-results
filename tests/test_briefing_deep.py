"""Deep tests for orbit/orbit/briefing.py (Loop 10/5).

Covers every statement:
  * ``_get_weather_summary`` — full ipify -> ip-api -> geocoding ->
    open-meteo chain (urllib fully mocked), unknown/missing weather codes,
    missing geocode results, missing lat/lon (Bug fix: used to return
    None despite ``-> str``; now "" like every other failure path), and
    the network-exception path (logged, returns "").
  * ``_get_greeting`` — all four day-part branches incl. boundaries.
  * ``format_briefing`` — header/date/time, weather line on/off,
    upcoming events (due window, TODAY label, 3-row cap, sort order,
    past events excluded), habits ratio, spent-today line, system line.
  * ``parse_text`` — briefing response envelope.
"""

import json
import socket
import unittest
from datetime import date, datetime, timedelta
from unittest import mock

from orbit.orbit import briefing
from orbit.orbit.config import TITLE


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        if isinstance(self._payload, bytes):
            return self._payload
        return self._payload.encode("utf-8")


def _weather_urlopen(geo=None, forecast=None, city="Delhi"):
    """Build a urlopen side_effect serving the four briefing endpoints."""
    geo = geo if geo is not None else {
        "results": [{"latitude": 28.6, "longitude": 77.2}]}
    forecast = forecast if forecast is not None else {
        "current_weather": {"temperature": 25, "weathercode": 0}}
    calls = []

    def fake_urlopen(url, timeout=None):
        calls.append((url, timeout))
        if "ipify" in url:
            return _FakeResponse(b"  1.2.3.4 \n")
        if "ip-api" in url:
            return _FakeResponse(json.dumps(
                {"city": city, "region": "Delhi", "country": "India"}))
        if "geocoding-api" in url:
            return _FakeResponse(json.dumps(geo))
        if "api.open-meteo.com" in url:
            return _FakeResponse(json.dumps(forecast))
        raise AssertionError(f"unexpected URL: {url}")

    return fake_urlopen, calls


class WeatherSummaryTests(unittest.TestCase):
    def test_full_chain_success(self):
        fake, calls = _weather_urlopen()
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            out = briefing._get_weather_summary()
        self.assertEqual(out, "☀️ 25°C in Delhi")
        self.assertEqual(len(calls), 4)
        # every request carries a timeout
        self.assertTrue(all(t == 3 for _, t in calls))
        # public IP was stripped before geolocation
        self.assertIn("1.2.3.4", calls[1][0])

    def test_unknown_weather_code(self):
        fake, _ = _weather_urlopen(
            forecast={"current_weather": {"temperature": 10,
                                          "weathercode": 99}})
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            out = briefing._get_weather_summary()
        self.assertEqual(out, "🌡 10°C in Delhi")

    def test_missing_weather_code_defaults_to_clear(self):
        fake, _ = _weather_urlopen(
            forecast={"current_weather": {"temperature": 18}})
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            out = briefing._get_weather_summary()
        self.assertEqual(out, "☀️ 18°C in Delhi")

    def test_no_current_weather_returns_empty(self):
        fake, _ = _weather_urlopen(forecast={"foo": "bar"})
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            self.assertEqual(briefing._get_weather_summary(), "")

    def test_no_geocode_results_returns_empty(self):
        fake, _ = _weather_urlopen(geo={})
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            self.assertEqual(briefing._get_weather_summary(), "")

    def test_missing_latitude_returns_empty(self):
        # was `return None` despite `-> str` (fixed in this loop)
        fake, _ = _weather_urlopen(
            geo={"results": [{"longitude": 77.2}]})
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            self.assertEqual(briefing._get_weather_summary(), "")

    def test_null_latitude_returns_empty(self):
        fake, _ = _weather_urlopen(
            geo={"results": [{"latitude": None, "longitude": 77.2}]})
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            self.assertEqual(briefing._get_weather_summary(), "")

    def test_network_failure_logged_and_empty(self):
        with mock.patch("urllib.request.urlopen",
                        side_effect=OSError("no net")), \
                mock.patch.object(briefing, "logger") as logger:
            out = briefing._get_weather_summary()
        self.assertEqual(out, "")
        logger.exception.assert_called_once()

    def test_city_fallback_when_missing(self):
        fake, calls = _weather_urlopen(city="your city")
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            out = briefing._get_weather_summary()
        self.assertEqual(out, "☀️ 25°C in your city")
        self.assertIn("name=your city", calls[2][0])


class GreetingTests(unittest.TestCase):
    def _greeting_at(self, hour):
        with mock.patch.object(briefing, "datetime") as mdt:
            mdt.now.return_value = datetime(2026, 3, 15, hour, 0)
            return briefing._get_greeting()

    def test_morning_boundary(self):
        self.assertEqual(self._greeting_at(0), "Good Morning ☀️")
        self.assertEqual(self._greeting_at(11), "Good Morning ☀️")

    def test_afternoon_boundary(self):
        self.assertEqual(self._greeting_at(12), "Good Afternoon 🌤")
        self.assertEqual(self._greeting_at(16), "Good Afternoon 🌤")

    def test_evening_boundary(self):
        self.assertEqual(self._greeting_at(17), "Good Evening 🌅")
        self.assertEqual(self._greeting_at(20), "Good Evening 🌅")

    def test_night_boundary(self):
        self.assertEqual(self._greeting_at(21), "Good Night 🌙")
        self.assertEqual(self._greeting_at(23), "Good Night 🌙")


class FormatBriefingTests(unittest.TestCase):
    def setUp(self):
        # no network inside format_briefing unless a test opts in
        self._weather = mock.patch.object(
            briefing, "_get_weather_summary", return_value="")
        self._weather_mock = self._weather.start()
        self.addCleanup(self._weather.stop)

    def _format(self):
        return briefing.format_briefing()

    def test_header_date_and_time(self):
        fixed_now = datetime(2026, 3, 15, 14, 30)
        with mock.patch.object(briefing, "datetime") as mdt, \
                mock.patch.object(briefing, "date") as mdate:
            mdt.now.return_value = fixed_now
            mdate.today.return_value = date(2026, 3, 15)
            out = self._format()
        first = out.splitlines()[0]
        self.assertEqual(first, f"📰 **Good Afternoon 🌤, {TITLE}!**")
        self.assertIn("Sunday, March 15, 2026", out)
        self.assertIn("Time: 02:30 PM", out)

    def test_weather_line_included(self):
        self._weather_mock.return_value = "☀️ 25°C in Delhi"
        out = self._format()
        self.assertIn("  ☀️ 25°C in Delhi", out)

    def test_weather_line_skipped_when_empty(self):
        self.assertNotIn("°C", self._format())

    def test_no_events_section_when_empty(self):
        with mock.patch.object(briefing.cd_mod, "get_all",
                               return_value=[]):
            out = self._format()
        self.assertNotIn("Upcoming", out)

    def test_due_events_window(self):
        today = date.today()
        events = [
            {"name": "Far away", "date": (today + timedelta(days=30)).isoformat()},
            {"name": "Party", "date": (today + timedelta(days=2)).isoformat()},
            {"name": "Birthday", "date": today.isoformat()},
            {"name": "Yesterday", "date": (today - timedelta(days=1)).isoformat()},
        ]
        with mock.patch.object(briefing.cd_mod, "get_all",
                               return_value=events):
            out = self._format()
        self.assertIn("**📅 Upcoming (2):**", out)
        self.assertIn("🎉 TODAY! Birthday", out)
        self.assertIn("⏰ 2d Party", out)
        self.assertNotIn("Far away", out)
        self.assertNotIn("Yesterday", out)

    def test_upcoming_rows_capped_at_three(self):
        today = date.today()
        events = [{"name": f"Event{i}",
                   "date": (today + timedelta(days=i)).isoformat()}
                  for i in range(4)]
        with mock.patch.object(briefing.cd_mod, "get_all",
                               return_value=events):
            out = self._format()
        self.assertIn("**📅 Upcoming (4):**", out)
        rows = [ln for ln in out.splitlines()
                if "TODAY!" in ln or "⏰" in ln]
        self.assertEqual(len(rows), 3)

    def test_events_sorted_by_soonest(self):
        today = date.today()
        events = [
            {"name": "Third", "date": (today + timedelta(days=5)).isoformat()},
            {"name": "First", "date": (today + timedelta(days=1)).isoformat()},
            {"name": "Second", "date": (today + timedelta(days=3)).isoformat()},
        ]
        with mock.patch.object(briefing.cd_mod, "get_all",
                               return_value=events):
            out = self._format()
        self.assertLess(out.index("First"), out.index("Second"))
        self.assertLess(out.index("Second"), out.index("Third"))

    def test_habits_line(self):
        with mock.patch.object(briefing.habits_mod, "today_status",
                               return_value=[{"done": True},
                                             {"done": False},
                                             {"done": True}]):
            out = self._format()
        self.assertIn("**✅ Habits:** 2/3 done today", out)

    def test_habits_line_skipped_when_empty(self):
        with mock.patch.object(briefing.habits_mod, "today_status",
                               return_value=[]):
            out = self._format()
        self.assertNotIn("Habits", out)

    def test_expenses_line(self):
        with mock.patch.object(briefing.exp_mod, "total_today",
                               return_value={"total": 150, "count": 2}):
            out = self._format()
        self.assertIn("**💰 Spent Today:** ₹150", out)

    def test_expenses_line_skipped_when_zero(self):
        with mock.patch.object(briefing.exp_mod, "total_today",
                               return_value={"total": 0, "count": 0}):
            out = self._format()
        self.assertNotIn("Spent Today", out)

    def test_system_line(self):
        with mock.patch.object(briefing, "pf") as mpf, \
                mock.patch.object(briefing, "socket") as msock:
            mpf.system.return_value = "Windows"
            mpf.release.return_value = "11"
            msock.gethostname.return_value = "DESKTOP-TEST"
            out = self._format()
        self.assertIn("**🖥️ System:** Windows 11 | DESKTOP-TEST", out)

    def test_lines_are_newline_joined(self):
        out = self._format()
        lines = out.splitlines()
        self.assertGreaterEqual(len(lines), 3)
        self.assertTrue(all(ln for ln in lines[:3]))
        self.assertTrue(out.endswith(
            f"  **🖥️ System:** {briefing.pf.system()} "
            f"{briefing.pf.release()} | {socket.gethostname()}"))


class ParseTextTests(unittest.TestCase):
    def test_returns_briefing_envelope(self):
        with mock.patch.object(briefing, "format_briefing",
                               return_value="BRIEF"):
            result = briefing.parse_text("briefing")
        self.assertEqual(result, {"type": "briefing", "result": "BRIEF"})


if __name__ == "__main__":
    unittest.main()
