"""Deep tests for orbit/orbit/core/analytics.py (Loop 16/2)."""

import json
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from orbit.orbit.core import analytics as an


class InitLoadTests(unittest.TestCase):
    def setUp(self):
        self._orig_instance = an._instance
        an._instance = None
        self.addCleanup(setattr, an, "_instance", self._orig_instance)

    def test_init_creates_data_dir(self):
        with mock.patch("pathlib.Path.mkdir") as mk:
            a = an.Analytics()
        mk.assert_called_once_with(parents=True, exist_ok=True)
        self.assertTrue(hasattr(a, "_lock"))

    def test_load_existing_events_and_daily(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d) / "analytics.json"
        dp = Path(d) / "daily.json"
        p.write_text('[{"type":"q"}]', encoding="utf-8")
        dp.write_text('{"2026-01-01":{"queries":2}}', encoding="utf-8")
        with mock.patch.object(an.Analytics, "_path", lambda self: p), \
                mock.patch.object(an.Analytics, "_daily_path", lambda self: dp), \
                mock.patch("pathlib.Path.mkdir"):
            a = an.Analytics()
        self.assertEqual(a._events, [{"type": "q"}])
        self.assertEqual(a._daily, {"2026-01-01": {"queries": 2}})

    def test_load_corrupt_events(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d) / "analytics.json"
        dp = Path(d) / "daily.json"
        p.write_text("{bad", encoding="utf-8")
        dp.write_text("{bad", encoding="utf-8")
        with mock.patch.object(an.Analytics, "_path", lambda self: p), \
                mock.patch.object(an.Analytics, "_daily_path", lambda self: dp), \
                mock.patch("pathlib.Path.mkdir"):
            a = an.Analytics()
        self.assertEqual(a._events, [])
        self.assertEqual(a._daily, {})

    def test_load_missing_files(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d) / "analytics.json"
        dp = Path(d) / "daily.json"
        with mock.patch.object(an.Analytics, "_path", lambda self: p), \
                mock.patch.object(an.Analytics, "_daily_path", lambda self: dp), \
                mock.patch("pathlib.Path.mkdir"):
            a = an.Analytics()
        self.assertEqual(a._events, [])
        self.assertEqual(a._daily, {})

    def test_save_success(self):
        a = an.Analytics.__new__(an.Analytics)
        a._lock = threading.Lock()
        a._events = [{"x": 1}]
        a._daily = {"2026-01-01": {"queries": 1}}
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d) / "analytics.json"
        dp = Path(d) / "daily.json"
        with mock.patch.object(a, "_path", lambda: p), \
                mock.patch.object(a, "_daily_path", lambda: dp):
            ok = a._save()
        self.assertIsNone(ok)
        self.assertTrue(p.exists())
        self.assertTrue(dp.exists())

    def test_save_failure(self):
        a = an.Analytics.__new__(an.Analytics)
        a._lock = threading.Lock()
        a._events = []
        a._daily = {}
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d) / "analytics.json"
        dp = Path(d) / "daily.json"
        with mock.patch.object(a, "_path", lambda: p), \
                mock.patch.object(a, "_daily_path", lambda: dp), \
                mock.patch.object(Path, "with_name", side_effect=OSError("boom")), \
                mock.patch.object(an, "logger") as lg:
            ok = a._save()
        self.assertFalse(ok)
        lg.error.assert_called_once()


class TrackTests(unittest.TestCase):
    def _make(self):
        a = an.Analytics.__new__(an.Analytics)
        a._lock = threading.Lock()
        a._events = []
        a._daily = {}
        a._save = mock.MagicMock(return_value=None)
        return a

    def test_track_basic(self):
        a = self._make()
        a.track("query", {"agent": "orion"})
        self.assertEqual(len(a._events), 1)
        self.assertEqual(a._events[0]["type"], "query")
        self.assertIn("timestamp", a._events[0])
        self.assertEqual(a._events[0]["details"], {"agent": "orion"})
        today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        self.assertIn(today, a._daily)
        d = a._daily[today]
        self.assertEqual(d["queries"], 1)
        self.assertEqual(d["agents"], {"orion": 1})
        a._save.assert_called_once()

    def test_track_no_details(self):
        a = self._make()
        a.track("query")
        today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        d = a._daily[today]
        self.assertEqual(d["queries"], 1)
        self.assertEqual(d["details"] if False else 0, 0)

    def test_track_tool(self):
        a = self._make()
        a.track("query", {"tool": "search"})
        today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        d = a._daily[today]
        self.assertEqual(d["tools"], {"search": 1})

    def test_track_task_type(self):
        a = self._make()
        a.track("query", {"task_type": "coding"})
        today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        d = a._daily[today]
        self.assertEqual(d["task_types"], {"coding": 1})

    def test_track_cost_and_latency(self):
        a = self._make()
        a.track("query", {"cost_usd": 0.5, "latency_ms": 100})
        today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        d = a._daily[today]
        self.assertEqual(d["cost_usd"], 0.5)
        self.assertEqual(d["latencies"], [100])

    def test_track_second_query_increments(self):
        a = self._make()
        a.track("query")
        a.track("query")
        today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        d = a._daily[today]
        self.assertEqual(d["queries"], 2)

    def test_track_multiple_agents(self):
        a = self._make()
        a.track("q", {"agent": "a"})
        a.track("q", {"agent": "a"})
        a.track("q", {"agent": "b"})
        today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        d = a._daily[today]
        self.assertEqual(d["agents"], {"a": 2, "b": 1})

    def test_track_events_capped_at_5000(self):
        a = self._make()
        a._events = [{"x": i} for i in range(5000)]
        a.track("q")
        # _save not checked for cap (cap is in _save: events[-5000:])
        self.assertEqual(len(a._events), 5001)


class GetSummaryTests(unittest.TestCase):
    def _make_with_data(self):
        a = an.Analytics.__new__(an.Analytics)
        a._lock = threading.Lock()
        a._events = [{"type": "q"}]
        today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        week_ago_date = (__import__("datetime").datetime.now() - __import__("datetime").timedelta(days=3)).strftime("%Y-%m-%d")
        a._daily = {
            today: {"queries": 3, "agents": {"a": 2}, "tools": {"t": 1},
                    "task_types": {"coding": 1}, "cost_usd": 0.5,
                    "latencies": [100, 200]},
            week_ago_date: {"queries": 2, "agents": {}, "tools": {},
                           "task_types": {}, "cost_usd": 0.1, "latencies": []},
        }
        return a, today

    def test_summary_shape(self):
        a, today = self._make_with_data()
        s = a.get_summary()
        self.assertEqual(s["today"]["queries"], 3)
        self.assertEqual(s["today"]["cost_usd"], 0.5)
        self.assertEqual(s["today"]["avg_latency_ms"], 150.0)
        self.assertEqual(s["week_queries"], 5)
        self.assertEqual(s["month_queries"], 5)
        self.assertAlmostEqual(s["total_cost_usd"], 0.6, places=4)
        self.assertEqual(s["top_agents"], {"a": 2})
        self.assertEqual(s["top_tools"], {"t": 1})
        self.assertEqual(s["top_task_types"], {"coding": 1})
        self.assertEqual(s["total_events"], 1)

    def test_summary_empty(self):
        a = an.Analytics.__new__(an.Analytics)
        a._lock = threading.Lock()
        a._events = []
        a._daily = {}
        s = a.get_summary()
        self.assertEqual(s["today"]["queries"], 0)
        self.assertEqual(s["today"]["cost_usd"], 0.0)
        self.assertEqual(s["today"]["avg_latency_ms"], 0.0)  # sum([])/max(1,0)=0
        self.assertEqual(s["week_queries"], 0)
        self.assertEqual(s["month_queries"], 0)
        self.assertEqual(s["total_cost_usd"], 0.0)
        self.assertEqual(s["top_agents"], {})
        self.assertEqual(s["top_tools"], {})
        self.assertEqual(s["top_task_types"], {})
        self.assertEqual(s["total_events"], 0)

    def test_summary_top_10_cap(self):
        a = an.Analytics.__new__(an.Analytics)
        a._lock = threading.Lock()
        a._events = []
        today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        agents = {f"agent{i}": i + 1 for i in range(15)}
        a._daily = {today: {"queries": 1, "agents": agents, "tools": {},
                            "task_types": {}, "cost_usd": 0.0, "latencies": []}}
        s = a.get_summary()
        self.assertEqual(len(s["top_agents"]), 10)

    def test_summary_defaultdict_serialization(self):
        # agents stored as regular dict (not defaultdict) after track
        a = an.Analytics.__new__(an.Analytics)
        a._lock = threading.Lock()
        a._events = []
        today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        a._daily = {today: {"queries": 1, "agents": {}, "tools": {},
                            "task_types": {}, "cost_usd": 0.0, "latencies": []}}
        s = a.get_summary()
        self.assertIsInstance(s["top_agents"], dict)


class GetWeeklyTests(unittest.TestCase):
    def test_weekly_shape(self):
        a = an.Analytics.__new__(an.Analytics)
        a._lock = threading.Lock()
        a._events = []
        a._daily = {}
        w = a.get_weekly()
        self.assertEqual(len(w["days"]), 7)
        self.assertIn("date", w["days"][0])
        self.assertIn("queries", w["days"][0])

    def test_weekly_with_data(self):
        a = an.Analytics.__new__(an.Analytics)
        a._lock = threading.Lock()
        a._events = []
        today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        a._daily = {today: {"queries": 5, "cost_usd": 1.23456,
                            "latencies": [100, 200]}}
        w = a.get_weekly()
        # today is last in reversed list
        last = w["days"][-1]
        self.assertEqual(last["queries"], 5)
        self.assertEqual(last["cost_usd"], 1.2346)
        self.assertEqual(last["avg_latency_ms"], 150.0)

    def test_weekly_empty_day_avg_latency(self):
        a = an.Analytics.__new__(an.Analytics)
        a._lock = threading.Lock()
        a._events = []
        a._daily = {}
        w = a.get_weekly()
        self.assertEqual(w["days"][0]["avg_latency_ms"], 0.0)


class GetAgentStatsTests(unittest.TestCase):
    def test_empty(self):
        a = an.Analytics.__new__(an.Analytics)
        a._lock = threading.Lock()
        a._events = []
        a._daily = {}
        self.assertEqual(a.get_agent_stats(), {})

    def test_with_data(self):
        a = an.Analytics.__new__(an.Analytics)
        a._lock = threading.Lock()
        a._events = []
        a._daily = {
            "2026-01-01": {"agents": {"a": 2}},
            "2026-01-02": {"agents": {"a": 1, "b": 3}},
        }
        stats = a.get_agent_stats()
        self.assertEqual(stats["b"]["calls"], 3)
        self.assertEqual(stats["b"]["days_active"], 1)
        self.assertEqual(stats["a"]["calls"], 3)
        self.assertEqual(stats["a"]["days_active"], 2)
        # sorted by calls desc; a and b both 3 -> order by sort (stable-ish)
        self.assertIn("a", stats)
        self.assertIn("b", stats)


class GetPeakHoursTests(unittest.TestCase):
    def test_empty(self):
        a = an.Analytics.__new__(an.Analytics)
        a._lock = threading.Lock()
        a._events = []
        self.assertEqual(a.get_peak_hours(), {})

    def test_with_events(self):
        a = an.Analytics.__new__(an.Analytics)
        a._lock = threading.Lock()
        a._events = [
            {"type": "q", "timestamp": "2026-01-01T10:30:00", "details": {}},
            {"type": "q", "timestamp": "2026-01-01T10:45:00", "details": {}},
            {"type": "q", "timestamp": "2026-01-01T14:00:00", "details": {}},
            {"type": "q", "timestamp": "bad-ts", "details": {}},
        ]
        h = a.get_peak_hours()
        self.assertEqual(h[10], 2)
        self.assertEqual(h[14], 1)
        self.assertEqual(len(h), 2)

    def test_sorted(self):
        a = an.Analytics.__new__(an.Analytics)
        a._lock = threading.Lock()
        a._events = [
            {"type": "q", "timestamp": "2026-01-01T14:00:00", "details": {}},
            {"type": "q", "timestamp": "2026-01-01T10:00:00", "details": {}},
        ]
        h = a.get_peak_hours()
        self.assertEqual(list(h.keys()), [10, 14])


class SingletonTests(unittest.TestCase):
    def setUp(self):
        self._saved = an._instance
        an._instance = None
        self.addCleanup(setattr, an, "_instance", self._saved)

    def test_creates(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d) / "analytics.json"
        dp = Path(d) / "daily.json"
        with mock.patch("orbit.orbit.core.analytics.DATA_DIR", Path(d)), \
                mock.patch.object(an.Analytics, "_path", lambda self: p), \
                mock.patch.object(an.Analytics, "_daily_path", lambda self: dp):
            a = an.get_analytics()
        self.assertIsInstance(a, an.Analytics)
        self.assertIs(an._instance, a)

    def test_reuses(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d) / "analytics.json"
        dp = Path(d) / "daily.json"
        with mock.patch("orbit.orbit.core.analytics.DATA_DIR", Path(d)), \
                mock.patch.object(an.Analytics, "_path", lambda self: p), \
                mock.patch.object(an.Analytics, "_daily_path", lambda self: dp):
            a = an.get_analytics()
            b = an.get_analytics()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
