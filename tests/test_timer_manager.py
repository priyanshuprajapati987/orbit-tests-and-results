"""Unit tests for orbit/orbit/core/timer_manager.py."""

import os
import sys
import threading
import time
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.timer_manager import TimerManager, get_timer


class TestCountdownValidation(unittest.TestCase):
    def setUp(self):
        self.tm = TimerManager()

    def test_bad_seconds_type(self):
        r = self.tm.countdown("abc")
        self.assertEqual(r["error"], "seconds must be an integer")

    def test_none_seconds(self):
        r = self.tm.countdown(None)
        self.assertEqual(r["error"], "seconds must be an integer")

    def test_zero_seconds(self):
        r = self.tm.countdown(0)
        self.assertEqual(r["error"], "seconds must be positive")

    def test_negative_seconds(self):
        r = self.tm.countdown(-5)
        self.assertEqual(r["error"], "seconds must be positive")

    def test_success(self):
        r = self.tm.countdown(1, label="tea")
        self.assertEqual(r["label"], "tea")
        self.assertEqual(r["seconds"], 1)
        self.assertTrue(r["id"].startswith("timer_"))
        # cleanup: stop the spawned thread
        self.tm.cancel(r["id"])

    def test_string_number_coerced(self):
        r = self.tm.countdown("1")
        self.assertEqual(r["seconds"], 1)
        self.tm.cancel(r["id"])

    def test_label_defaults_to_id(self):
        r = self.tm.countdown(1)
        self.assertEqual(r["label"], r["id"])
        self.tm.cancel(r["id"])

    def test_seconds_clamped_to_86400(self):
        r = self.tm.countdown(999999)
        self.assertEqual(r["seconds"], 86400)
        self.tm.cancel(r["id"])

    def test_id_increments(self):
        r1 = self.tm.countdown(1)
        r2 = self.tm.countdown(1)
        self.assertNotEqual(r1["id"], r2["id"])
        self.tm.cancel(r1["id"])
        self.tm.cancel(r2["id"])


class TestTimerLimits(unittest.TestCase):
    def setUp(self):
        self.tm = TimerManager()

    def test_max_timers_limit(self):
        # fill up without spawning threads: directly inject timers
        for i in range(100):
            self.tm._timers[f"t{i}"] = {"done": False}
        r = self.tm.countdown(1)
        self.assertEqual(r["error"], "too many timers (max 100)")

    def test_evict_done_frees_slots(self):
        for i in range(100):
            self.tm._timers[f"t{i}"] = {"done": (i % 2 == 0)}
        # 50 done -> evicted -> room available
        r = self.tm.countdown(1)
        self.assertNotIn("error", r)
        self.tm.cancel(r["id"])


class TestCancel(unittest.TestCase):
    def setUp(self):
        self.tm = TimerManager()

    def test_cancel_not_found(self):
        r = self.tm.cancel("nope")
        self.assertEqual(r["error"], "timer not found")

    def test_cancel_existing(self):
        r = self.tm.countdown(60)
        c = self.tm.cancel(r["id"])
        self.assertEqual(c["status"], "cancelled")
        self.assertEqual(self.tm.get_timers(), [])


class TestGetTimers(unittest.TestCase):
    def setUp(self):
        self.tm = TimerManager()

    def test_empty(self):
        self.assertEqual(self.tm.get_timers(), [])

    def test_snapshot_shape(self):
        self.tm._timers["t1"] = {
            "id": "t1", "label": "L", "remaining": 5, "total": 10, "done": False,
            "stop": threading.Event(),
        }
        lst = self.tm.get_timers()
        self.assertEqual(len(lst), 1)
        item = lst[0]
        self.assertEqual(set(item.keys()), {"id", "label", "remaining", "total", "done"})
        self.assertNotIn("stop", item)

    def test_get_timers_is_copy(self):
        self.tm._timers["t1"] = {
            "id": "t1", "label": "L", "remaining": 1, "total": 1, "done": False,
            "stop": threading.Event(),
        }
        lst = self.tm.get_timers()
        lst[0]["label"] = "mutated"
        self.assertEqual(self.tm._timers["t1"]["label"], "L")


class TestCountdownRun(unittest.TestCase):
    def setUp(self):
        self.tm = TimerManager()

    def test_run_completes_immediately_when_total_zero(self):
        # range(0,0,-1) is empty -> for-else sets done
        timer = {"total": 0, "remaining": 99, "done": False, "stop": threading.Event()}
        self.tm._countdown_run(timer)
        self.assertTrue(timer["done"])
        self.assertEqual(timer["remaining"], 0)

    def test_run_cancelled_midway(self):
        ev = threading.Event()
        timer = {"total": 5, "remaining": 5, "done": False, "stop": ev}
        # set stop immediately -> wait(1) returns True on first iter -> break, not done
        ev.set()
        self.tm._countdown_run(timer)
        self.assertFalse(timer["done"])

    def test_run_counts_down_with_fast_wait(self):
        ev = threading.Event()
        timer = {"total": 3, "remaining": 99, "done": False, "stop": ev}
        waits = []
        def fake_wait(t):
            waits.append(t)
            return False
        ev.wait = fake_wait
        self.tm._countdown_run(timer)
        self.assertTrue(timer["done"])
        self.assertEqual(timer["remaining"], 0)
        self.assertEqual(len(waits), 3)  # called once per second


class TestStopwatch(unittest.TestCase):
    def setUp(self):
        self.tm = TimerManager()

    def test_start(self):
        r = self.tm.stopwatch_start()
        self.assertEqual(r["status"], "started")
        self.assertTrue(self.tm._stopwatch_running)

    def test_stop_not_running(self):
        r = self.tm.stopwatch_stop()
        self.assertEqual(r["elapsed_sec"], 0)
        self.assertFalse(self.tm._stopwatch_running)

    def test_stop_running(self):
        self.tm.stopwatch_start()
        time.sleep(0.05)
        r = self.tm.stopwatch_stop()
        self.assertIn("elapsed_sec", r)
        self.assertIn("formatted", r)
        self.assertFalse(self.tm._stopwatch_running)

    def test_lap_not_running(self):
        r = self.tm.stopwatch_lap()
        self.assertEqual(r["error"], "stopwatch not running")

    def test_lap_running(self):
        self.tm.stopwatch_start()
        time.sleep(0.05)
        r = self.tm.stopwatch_lap()
        self.assertIn("lap_sec", r)
        self.assertIn("formatted", r)

    def test_start_resets_timer(self):
        self.tm.stopwatch_start()
        time.sleep(0.05)
        self.tm.stopwatch_start()  # restart
        r = self.tm.stopwatch_stop()
        # elapsed should be small since restarted
        self.assertLessEqual(r["elapsed_sec"], 1)


class TestFormat(unittest.TestCase):
    def setUp(self):
        self.tm = TimerManager()

    def test_seconds_only(self):
        self.assertEqual(self.tm._format(45), "45s")

    def test_zero(self):
        self.assertEqual(self.tm._format(0), "0s")

    def test_minutes(self):
        self.assertEqual(self.tm._format(90), "1m 30s")

    def test_exact_minute(self):
        self.assertEqual(self.tm._format(60), "1m 0s")

    def test_hours(self):
        self.assertEqual(self.tm._format(3661), "1h 1m 1s")

    def test_hours_zero_min(self):
        self.assertEqual(self.tm._format(7200), "2h 0m 0s")


class TestGetTimer(unittest.TestCase):
    def test_singleton(self):
        self.assertIs(get_timer(), get_timer())

    def test_type(self):
        self.assertIsInstance(get_timer(), TimerManager)


if __name__ == "__main__":
    unittest.main()
