"""Deep tests for orbit/orbit/core/time_tracker.py (Loop 16/3)."""

import json
import threading
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from orbit.orbit.core import time_tracker as tt


class InitLoadTests(unittest.TestCase):
    def test_init_creates_data_dir(self):
        with mock.patch("pathlib.Path.mkdir") as mk:
            t = tt.TimeTracker.__new__(tt.TimeTracker)
            # manually init without _load side effects by patching _load
            with mock.patch.object(tt.TimeTracker, "_load"):
                t2 = tt.TimeTracker()
        mk.assert_called()

    def test_load_existing(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d) / "time_data.json"
        p.write_text(json.dumps({
            "sessions": [{"id": "s1", "start": "2026-01-01T10:00:00"}],
            "pomodoro_count": 5,
            "streak_start": "2026-01-01",
        }), encoding="utf-8")
        with mock.patch.object(tt.TimeTracker, "_path", lambda self: p):
            with mock.patch("pathlib.Path.mkdir"):
                t = tt.TimeTracker()
        self.assertEqual(len(t._sessions), 1)
        self.assertEqual(t._pomodoro_count, 5)
        self.assertEqual(t._streak_start, "2026-01-01")

    def test_load_corrupt(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d) / "time_data.json"
        p.write_text("{bad", encoding="utf-8")
        with mock.patch.object(tt.TimeTracker, "_path", lambda self: p):
            with mock.patch("pathlib.Path.mkdir"):
                t = tt.TimeTracker()
        self.assertEqual(t._sessions, [])
        self.assertEqual(t._pomodoro_count, 0)

    def test_load_missing(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d) / "time_data.json"
        with mock.patch.object(tt.TimeTracker, "_path", lambda self: p):
            with mock.patch("pathlib.Path.mkdir"):
                t = tt.TimeTracker()
        self.assertEqual(t._sessions, [])

    def test_save_success(self):
        t = tt.TimeTracker.__new__(tt.TimeTracker)
        t._lock = threading.Lock()
        t._sessions = [{"id": "s"}]
        t._pomodoro_count = 2
        t._streak_start = "2026-01-01"
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d) / "time_data.json"
        with mock.patch.object(t, "_path", lambda: p):
            ok = t._save()
        self.assertIsNone(ok)
        self.assertTrue(p.exists())
        data = json.loads(p.read_text("utf-8"))
        self.assertEqual(data["pomodoro_count"], 2)
        self.assertEqual(data["streak_start"], "2026-01-01")

    def test_save_failure(self):
        t = tt.TimeTracker.__new__(tt.TimeTracker)
        t._lock = threading.Lock()
        t._sessions = []
        t._pomodoro_count = 0
        t._streak_start = "x"
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d) / "time_data.json"
        with mock.patch.object(t, "_path", lambda: p), \
                mock.patch.object(Path, "with_name", side_effect=OSError("boom")), \
                mock.patch.object(tt, "logger") as lg:
            ok = t._save()
        self.assertFalse(ok)
        lg.error.assert_called_once()

    def test_save_caps_sessions_5000(self):
        t = tt.TimeTracker.__new__(tt.TimeTracker)
        t._lock = threading.Lock()
        t._sessions = [{"id": f"s{i}"} for i in range(5010)]
        t._pomodoro_count = 0
        t._streak_start = "x"
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d) / "time_data.json"
        with mock.patch.object(t, "_path", lambda: p):
            t._save()
        data = json.loads(p.read_text("utf-8"))
        self.assertEqual(len(data["sessions"]), 5000)


class StartStopSessionTests(unittest.TestCase):
    def _make(self):
        t = tt.TimeTracker.__new__(tt.TimeTracker)
        t._lock = threading.Lock()
        t._sessions = []
        t._active_session = None
        t._pomodoro_count = 0
        t._streak_start = "2026-01-01"
        t._save = mock.MagicMock(return_value=None)
        return t

    def test_start_session(self):
        t = self._make()
        with mock.patch("orbit.orbit.core.time_tracker.datetime") as dt, \
                mock.patch("orbit.orbit.core.time_tracker.time") as tm:
            dt.now.return_value.isoformat.return_value = "2026-01-01T10:00:00"
            tm.time.return_value = 12345.678
            s = t.start_session("coding", "g1")
        self.assertEqual(s["label"], "coding")
        self.assertEqual(s["goal_id"], "g1")
        self.assertEqual(s["start"], "2026-01-01T10:00:00")
        self.assertIsNone(s["end"])
        self.assertEqual(s["duration_seconds"], 0)
        self.assertEqual(s["pomodoros"], 0)
        self.assertTrue(s["id"].startswith("sess_"))
        self.assertIs(t._active_session, s)

    def test_start_session_already_active(self):
        t = self._make()
        t._active_session = {"id": "x"}
        r = t.start_session("coding")
        self.assertEqual(r, {"error": "Session already active", "active": {"id": "x"}})

    def test_stop_session_none(self):
        t = self._make()
        self.assertIsNone(t.stop_session())

    def test_stop_session(self):
        t = self._make()
        t._active_session = {
            "id": "s1", "label": "coding", "goal_id": "",
            "start": "2026-01-01T10:00:00", "end": None,
            "duration_seconds": 0, "pomodoros": 0}
        with mock.patch("orbit.orbit.core.time_tracker.datetime") as dt:
            dt.now.return_value.isoformat.return_value = "2026-01-01T10:30:00"
            start_dt = datetime.fromisoformat("2026-01-01T10:00:00")
            dt.fromisoformat.return_value = start_dt
            dt.now.return_value = datetime(2026, 1, 1, 10, 30)
            s = t.stop_session()
        self.assertEqual(s["end"], "2026-01-01T10:30:00")
        self.assertEqual(s["duration_seconds"], 1800)
        self.assertIsNone(t._active_session)
        self.assertEqual(len(t._sessions), 1)
        t._save.assert_called_once()

    def test_get_active_none(self):
        t = self._make()
        self.assertIsNone(t.get_active())

    def test_get_active_with_session(self):
        t = self._make()
        t._active_session = {"id": "s1", "start": "2026-01-01T10:00:00"}
        with mock.patch("orbit.orbit.core.time_tracker.datetime") as dt:
            dt.fromisoformat.return_value = datetime(2026, 1, 1, 10, 0)
            dt.now.return_value = datetime(2026, 1, 1, 10, 5)
            r = t.get_active()
        self.assertEqual(r["elapsed_seconds"], 300)
        self.assertEqual(r["id"], "s1")
        # original _active_session updated
        self.assertEqual(t._active_session["elapsed_seconds"], 300)

    def test_start_pomodoro(self):
        t = self._make()
        with mock.patch("orbit.orbit.core.time_tracker.datetime") as dt:
            dt.now.return_value.isoformat.return_value = "2026-01-01T10:00:00"
            r = t.start_pomodoro()
        self.assertEqual(r["pomodoro_number"], 1)
        self.assertEqual(r["work_minutes"], tt.POMODORO_WORK_MINUTES)
        self.assertEqual(r["break_minutes"], tt.POMODORO_BREAK_MINUTES)
        self.assertEqual(t._pomodoro_count, 1)
        t._save.assert_called_once()


class GetReportTests(unittest.TestCase):
    def _make(self, sessions):
        t = tt.TimeTracker.__new__(tt.TimeTracker)
        t._lock = threading.Lock()
        t._sessions = sessions
        t._active_session = None
        t._pomodoro_count = 0
        t._streak_start = "x"
        return t

    def test_today_period(self):
        today = datetime.now().strftime("%Y-%m-%d")
        sessions = [
            {"label": "coding", "start": f"{today}T10:00:00", "duration_seconds": 1800},
            {"label": "reading", "start": f"{today}T11:00:00", "duration_seconds": 600},
            {"label": "coding", "start": "2020-01-01T10:00:00", "duration_seconds": 100},
        ]
        t = self._make(sessions)
        r = t.get_report("today")
        self.assertEqual(r["period"], "today")
        self.assertEqual(r["total_sessions"], 2)
        self.assertEqual(r["total_minutes"], 40.0)
        self.assertEqual(r["total_hours"], 0.67)
        self.assertEqual(r["breakdown"], {"coding": 30.0, "reading": 10.0})
        self.assertEqual(r["focus_score"], 13)  # min(100, round(40/30*10)) = 13

    def test_week_period(self):
        now = datetime.now()
        week_start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        sessions = [
            {"label": "coding", "start": f"{week_start}T10:00:00", "duration_seconds": 600},
            {"label": "reading", "start": "2020-01-01T10:00:00", "duration_seconds": 100},
        ]
        t = self._make(sessions)
        r = t.get_report("week")
        self.assertEqual(r["period"], "week")
        self.assertEqual(r["total_sessions"], 1)

    def test_all_period(self):
        sessions = [
            {"label": "coding", "start": "2020-01-01T10:00:00", "duration_seconds": 600},
        ]
        t = self._make(sessions)
        r = t.get_report("other")
        self.assertEqual(r["period"], "other")
        self.assertEqual(r["total_sessions"], 1)

    def test_empty_sessions(self):
        t = self._make([])
        r = t.get_report("today")
        self.assertEqual(r["total_sessions"], 0)
        self.assertEqual(r["total_minutes"], 0.0)
        self.assertEqual(r["total_hours"], 0.0)
        self.assertEqual(r["breakdown"], {})
        self.assertEqual(r["focus_score"], 0)

    def test_focus_score_cap_100(self):
        today = datetime.now().strftime("%Y-%m-%d")
        sessions = [{"label": "c", "start": f"{today}T10:00:00",
                     "duration_seconds": 300 * 60}]  # 300 min -> 100
        t = self._make(sessions)
        r = t.get_report("today")
        self.assertEqual(r["focus_score"], 100)

    def test_breakdown_unknown_label(self):
        today = datetime.now().strftime("%Y-%m-%d")
        sessions = [{"start": f"{today}T10:00:00", "duration_seconds": 60}]
        t = self._make(sessions)
        r = t.get_report("today")
        self.assertEqual(r["breakdown"], {"unknown": 1.0})


class GetStreakTests(unittest.TestCase):
    def _make(self, sessions, streak_start="2026-01-01"):
        t = tt.TimeTracker.__new__(tt.TimeTracker)
        t._lock = threading.Lock()
        t._sessions = sessions
        t._active_session = None
        t._pomodoro_count = 0
        t._streak_start = streak_start
        return t

    def test_empty(self):
        t = self._make([])
        r = t.get_streak()
        self.assertEqual(r["current_streak"], 0)
        self.assertEqual(r["longest_streak"], 0)
        self.assertEqual(r["total_active_days"], 0)
        self.assertEqual(r["started_tracking"], "2026-01-01")
        self.assertEqual(r["pomodoro_total"], 0)

    def test_single_day_today(self):
        today = datetime.now().strftime("%Y-%m-%d")
        t = self._make([{"start": f"{today}T10:00:00"}])
        r = t.get_streak()
        self.assertEqual(r["current_streak"], 1)
        self.assertEqual(r["longest_streak"], 1)
        self.assertEqual(r["total_active_days"], 1)

    def test_multi_day_streak(self):
        today = datetime.now()
        days = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(3)]
        sessions = [{"start": f"{d}T10:00:00"} for d in days]
        t = self._make(sessions)
        r = t.get_streak()
        self.assertEqual(r["current_streak"], 3)
        self.assertEqual(r["longest_streak"], 3)

    def test_broken_streak(self):
        today = datetime.now()
        # today + 3 days ago (gap)
        days = [today.strftime("%Y-%m-%d"),
                (today - timedelta(days=3)).strftime("%Y-%m-%d")]
        sessions = [{"start": f"{d}T10:00:00"} for d in days]
        t = self._make(sessions)
        r = t.get_streak()
        self.assertEqual(r["current_streak"], 1)
        self.assertEqual(r["longest_streak"], 1)
        self.assertEqual(r["total_active_days"], 2)

    def test_longest_streak_among_past(self):
        # past streak of 3, today not active
        days = ["2020-01-01", "2020-01-02", "2020-01-03"]
        sessions = [{"start": f"{d}T10:00:00"} for d in days]
        t = self._make(sessions)
        r = t.get_streak()
        self.assertEqual(r["current_streak"], 0)
        self.assertEqual(r["longest_streak"], 3)

    def test_pomodoro_count(self):
        t = self._make([])
        t._pomodoro_count = 7
        r = t.get_streak()
        self.assertEqual(r["pomodoro_total"], 7)


class GetStatsTests(unittest.TestCase):
    def test_empty(self):
        t = tt.TimeTracker.__new__(tt.TimeTracker)
        t._lock = threading.Lock()
        t._sessions = []
        t._active_session = None
        t._pomodoro_count = 0
        t._streak_start = "x"
        r = t.get_stats()
        self.assertEqual(r, {"total_sessions": 0, "total_hours": 0.0,
                             "active": False, "pomodoro_total": 0})

    def test_with_data(self):
        t = tt.TimeTracker.__new__(tt.TimeTracker)
        t._lock = threading.Lock()
        t._sessions = [{"duration_seconds": 3600}, {"duration_seconds": 1800}]
        t._active_session = {"id": "x"}
        t._pomodoro_count = 3
        t._streak_start = "x"
        r = t.get_stats()
        self.assertEqual(r["total_sessions"], 2)
        self.assertEqual(r["total_hours"], 1.5)
        self.assertTrue(r["active"])
        self.assertEqual(r["pomodoro_total"], 3)


class PathMethodTests(unittest.TestCase):
    def test_path(self):
        t = tt.TimeTracker.__new__(tt.TimeTracker)
        p = t._path()
        self.assertTrue(str(p).endswith("time_data.json"))
    def setUp(self):
        self._saved = tt._instance
        tt._instance = None
        self.addCleanup(setattr, tt, "_instance", self._saved)

    def test_creates(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d) / "time_data.json"
        with mock.patch("orbit.orbit.core.time_tracker.DATA_DIR", Path(d)), \
                mock.patch.object(tt.TimeTracker, "_path", lambda self: p):
            a = tt.get_time_tracker()
        self.assertIsInstance(a, tt.TimeTracker)
        self.assertIs(tt._instance, a)

    def test_reuses(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d) / "time_data.json"
        with mock.patch("orbit.orbit.core.time_tracker.DATA_DIR", Path(d)), \
                mock.patch.object(tt.TimeTracker, "_path", lambda self: p):
            a = tt.get_time_tracker()
            b = tt.get_time_tracker()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
