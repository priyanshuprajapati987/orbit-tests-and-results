"""Unit tests for orbit/orbit/stopwatch.py."""

import os
import sys
import time
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

import orbit.stopwatch as sw


class TestStopwatch(unittest.TestCase):
    def setUp(self):
        sw.reset()
        sw.set_on_tick(None)
        # ensure not running
        sw.stop()

    def tearDown(self):
        sw.stop()
        sw.reset()
        sw.set_on_tick(None)

    def test_start_first(self):
        self.assertTrue(sw.start())
        st = sw.status()
        self.assertTrue(st["running"])
        self.assertEqual(st["laps"], 0)

    def test_start_already_running(self):
        sw.start()
        self.assertFalse(sw.start())

    def test_stop_returns_elapsed(self):
        sw.start()
        time.sleep(0.05)
        e = sw.stop()
        self.assertGreaterEqual(e, 0.0)
        self.assertFalse(sw.status()["running"])

    def test_stop_when_not_running(self):
        self.assertEqual(sw.stop(), 0.0)

    def test_lap_while_running(self):
        sw.start()
        time.sleep(0.02)
        lt = sw.lap()
        self.assertGreater(lt, 0)
        self.assertEqual(sw.status()["laps"], 1)

    def test_lap_when_not_running(self):
        self.assertEqual(sw.lap(), 0.0)

    def test_reset(self):
        sw.start()
        time.sleep(0.02)
        sw.stop()
        sw.reset()
        st = sw.status()
        self.assertEqual(st["elapsed"], 0.0)
        self.assertEqual(st["laps"], 0)

    def test_format_time_seconds(self):
        self.assertEqual(sw.format_time(45), "0:45")
        self.assertEqual(sw.format_time(65), "1:05")

    def test_format_time_hours(self):
        self.assertEqual(sw.format_time(3661), "1:01:01")

    def test_format_time_zero(self):
        self.assertEqual(sw.format_time(0), "0:00")

    def test_format_status_running(self):
        sw.start()
        st = sw.status()
        s = sw.format_status(st)
        self.assertIn("Stopwatch", s)
        self.assertIn("⏱", s)
        sw.stop()

    def test_format_status_stopped(self):
        sw.start()
        time.sleep(0.02)
        sw.stop()
        st = sw.status()
        s = sw.format_status(st)
        self.assertIn("Stopped", s)

    def test_format_status_ready(self):
        sw.reset()
        st = sw.status()
        s = sw.format_status(st)
        self.assertIn("ready", s)

    def test_format_status_none(self):
        sw.reset()
        s = sw.format_status(None)
        self.assertIn("ready", s)

    def test_set_on_tick(self):
        calls = []
        sw.set_on_tick(calls.append)
        sw.start()
        # wait for at least one tick
        time.sleep(0.6)
        sw.stop()
        self.assertGreater(len(calls), 0)
        sw.set_on_tick(None)

    def test_status_laps_list(self):
        sw.start()
        time.sleep(0.02)
        sw.lap()
        st = sw.status()
        self.assertEqual(len(st["laps_list"]), 1)
        sw.stop()


if __name__ == "__main__":
    unittest.main()
