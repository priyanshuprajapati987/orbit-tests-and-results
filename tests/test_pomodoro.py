"""Unit tests for orbit/orbit/core/pomodoro.py."""

import os
import sys
import time
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.pomodoro import PomodoroTimer, get_pomodoro


def _wait_idle(t: PomodoroTimer, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with t._lock:
            if not t._active:
                return True
        time.sleep(0.02)
    return False


class TestClampMinutes(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(PomodoroTimer._clamp_minutes(30, 25), 30)

    def test_clamp_max(self):
        self.assertEqual(PomodoroTimer._clamp_minutes(999, 25), 180)

    def test_clamp_min(self):
        self.assertEqual(PomodoroTimer._clamp_minutes(-5, 25), 1)

    def test_zero_clamped_to_one(self):
        self.assertEqual(PomodoroTimer._clamp_minutes(0, 25), 1)

    def test_none_defaults(self):
        self.assertEqual(PomodoroTimer._clamp_minutes(None, 25), 25)

    def test_string_number(self):
        self.assertEqual(PomodoroTimer._clamp_minutes("45", 25), 45)

    def test_bad_string_defaults(self):
        self.assertEqual(PomodoroTimer._clamp_minutes("abc", 25), 25)

    def test_float_truncated(self):
        self.assertEqual(PomodoroTimer._clamp_minutes(30.9, 25), 30)

    def test_boundary_180(self):
        self.assertEqual(PomodoroTimer._clamp_minutes(180, 25), 180)

    def test_boundary_1(self):
        self.assertEqual(PomodoroTimer._clamp_minutes(1, 25), 1)


class TestStartStop(unittest.TestCase):
    def setUp(self):
        self.t = PomodoroTimer()

    def tearDown(self):
        self.t.stop()
        _wait_idle(self.t)

    def test_start_returns_status(self):
        r = self.t.start(focus_min=1, break_min=1)
        self.assertEqual(r["status"], "started")
        self.assertEqual(r["mode"], "focus")
        self.assertEqual(r["duration_min"], 1)

    def test_start_sets_active(self):
        self.t.start(focus_min=1, break_min=1)
        self.assertTrue(self.t._active)

    def test_start_twice_errors(self):
        self.t.start(focus_min=1, break_min=1)
        r = self.t.start(focus_min=1, break_min=1)
        self.assertEqual(r["error"], "timer already running")

    def test_stop_not_running_errors(self):
        r = self.t.stop()
        self.assertEqual(r["error"], "timer not running")

    def test_stop_running(self):
        self.t.start(focus_min=1, break_min=1)
        time.sleep(0.05)
        r = self.t.stop()
        self.assertEqual(r["status"], "stopped")
        self.assertIn("elapsed_sec", r)
        self.assertEqual(r["sessions"], 0)

    def test_start_clamps_focus(self):
        r = self.t.start(focus_min=-10, break_min=1)
        self.assertEqual(r["duration_min"], 1)

    def test_start_clamps_break(self):
        r = self.t.start(focus_min=1, break_min=0)
        self.assertEqual(r["duration_min"], 1)  # focus stays 1

    def test_start_bad_focus_defaults_25(self):
        r = self.t.start(focus_min="abc", break_min=1)
        self.assertEqual(r["duration_min"], 25)


class TestStatus(unittest.TestCase):
    def setUp(self):
        self.t = PomodoroTimer()

    def tearDown(self):
        self.t.stop()
        _wait_idle(self.t)

    def test_inactive_status(self):
        s = self.t.status()
        self.assertFalse(s["active"])
        self.assertEqual(s["sessions"], 0)

    def test_active_status(self):
        self.t.start(focus_min=1, break_min=1)
        s = self.t.status()
        self.assertTrue(s["active"])
        self.assertEqual(s["mode"], "focus")
        self.assertIn("elapsed_sec", s)
        self.assertEqual(s["sessions"], 0)

    def test_sessions_accumulate(self):
        self.t._sessions = 3
        s = self.t.status()
        self.assertEqual(s["sessions"], 3)


class TestRun(unittest.TestCase):
    def setUp(self):
        self.t = PomodoroTimer()

    def tearDown(self):
        self.t.stop()
        _wait_idle(self.t)

    def test_run_increments_sessions_and_cycles(self):
        # make waits return immediately to fast-forward
        waits = {"n": 0}
        def fake_wait(timeout):
            waits["n"] += 1
            if waits["n"] >= 6:
                self.t._stop_event.set()
                return True
            return False
        self.t._stop_event.wait = fake_wait
        self.t._active = True
        self.t._run(1, 1)
        # 3 full cycles (focus+break) before stop -> 3 sessions
        self.assertEqual(self.t._sessions, 3)
        self.assertFalse(self.t._active)

    def test_run_stops_on_focus_interrupt(self):
        def fake_wait(timeout):
            self.t._stop_event.set()
            return True
        self.t._stop_event.wait = fake_wait
        self.t._active = True
        self.t._run(1, 1)
        self.assertEqual(self.t._sessions, 0)
        self.assertFalse(self.t._active)

    def test_run_stops_on_break_interrupt(self):
        waits = {"n": 0}
        def fake_wait(timeout):
            waits["n"] += 1
            if waits["n"] == 1:
                return False  # focus completes
            self.t._stop_event.set()
            return True
        self.t._stop_event.wait = fake_wait
        self.t._active = True
        self.t._run(1, 1)
        self.assertEqual(self.t._sessions, 1)
        self.assertFalse(self.t._active)

    def test_run_sets_mode_focus_then_break(self):
        modes = []
        waits = {"n": 0}
        def fake_wait(timeout):
            modes.append(self.t._mode)
            waits["n"] += 1
            if waits["n"] >= 2:
                self.t._stop_event.set()
                return True
            return False
        self.t._stop_event.wait = fake_wait
        self.t._active = True
        self.t._run(1, 1)
        self.assertEqual(modes[0], "focus")
        self.assertEqual(modes[1], "break")


class TestGetPomodoro(unittest.TestCase):
    def test_singleton(self):
        self.assertIs(get_pomodoro(), get_pomodoro())

    def test_type(self):
        self.assertIsInstance(get_pomodoro(), PomodoroTimer)


if __name__ == "__main__":
    unittest.main()
