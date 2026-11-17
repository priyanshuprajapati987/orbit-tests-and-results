"""Unit tests for orbit/orbit/core/overnight.py."""

import os
import sys
import time
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

import orbit.core.overnight as ov
from orbit.core.overnight import start_overnight, status, _cycle, _state


def _reset_state():
    with ov._lock:
        _state["running"] = False
        _state["goal"] = None
        _state["done"] = 0
        _state["log"] = []


def _wait_idle(timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with ov._lock:
            if not _state["running"]:
                return True
        time.sleep(0.02)
    return False


def _mock_lh(advance_side_effect=None, advance_return=None):
    lh = MagicMock()
    lh.start_goal.return_value = {"id": "gid1", "goal": "g"}
    if advance_side_effect is not None:
        lh.advance.side_effect = advance_side_effect
    else:
        lh.advance.return_value = advance_return if advance_return is not None else {"goal": "g"}
    return lh


class TestStartOvernightValidation(unittest.TestCase):
    def setUp(self):
        _reset_state()

    def tearDown(self):
        _wait_idle()
        _reset_state()

    def test_empty_goal(self):
        r = start_overnight("", 3)
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"], "empty goal")

    def test_whitespace_goal(self):
        r = start_overnight("   ", 3)
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"], "empty goal")

    def test_none_goal(self):
        r = start_overnight(None, 3)
        self.assertFalse(r["ok"])

    def test_bad_iterations(self):
        r = start_overnight("goal", "abc")
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"], "iterations must be an integer")

    def test_none_iterations(self):
        r = start_overnight("goal", None)
        self.assertFalse(r["ok"])

    def test_already_running(self):
        with ov._lock:
            _state["running"] = True
        r = start_overnight("goal", 3)
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"], "already running")


class TestStartOvernightSuccess(unittest.TestCase):
    def setUp(self):
        _reset_state()

    def tearDown(self):
        _wait_idle()
        _reset_state()

    def test_success(self):
        lh = _mock_lh(advance_side_effect=[{"goal": "my goal"}, {"goal": "my goal"}])
        with patch("orbit.core.long_horizon.get_long_horizon", return_value=lh):
            r = start_overnight("my goal", 2)
            self.assertTrue(r["ok"])
            self.assertEqual(r["goal"], "my goal")
            self.assertEqual(r["iterations"], 2)
            _wait_idle()
            lh.start_goal.assert_called_once_with("my goal")
            self.assertEqual(lh.advance.call_count, 2)

    def test_iterations_clamped_to_max_100(self):
        lh = _mock_lh(advance_return={"goal": "g"})
        with patch("orbit.core.long_horizon.get_long_horizon", return_value=lh):
            r = start_overnight("g", 9999)
            self.assertTrue(r["ok"])
            self.assertEqual(r["iterations"], 100)
            _wait_idle()

    def test_iterations_clamped_to_min_1(self):
        lh = _mock_lh(advance_return={"goal": "g"})
        with patch("orbit.core.long_horizon.get_long_horizon", return_value=lh):
            r = start_overnight("g", -5)
            self.assertTrue(r["ok"])
            self.assertEqual(r["iterations"], 1)
            _wait_idle()

    def test_string_iterations_coerced(self):
        lh = _mock_lh(advance_return={"goal": "g"})
        with patch("orbit.core.long_horizon.get_long_horizon", return_value=lh):
            r = start_overnight("g", "7")
            self.assertTrue(r["ok"])
            self.assertEqual(r["iterations"], 7)
            _wait_idle()

    def test_goal_stripped(self):
        lh = _mock_lh(advance_return={"goal": "padded goal"})
        with patch("orbit.core.long_horizon.get_long_horizon", return_value=lh):
            r = start_overnight("  padded goal  ", 1)
            self.assertTrue(r["ok"])
            self.assertEqual(r["goal"], "padded goal")
            _wait_idle()
            lh.start_goal.assert_called_once_with("padded goal")

    def test_concurrent_start_only_one_wins(self):
        import threading as th
        gate = th.Event()
        lh = _mock_lh()
        lh.advance.side_effect = lambda gid: (gate.wait(2.0), {"goal": "g"})[1]
        with patch("orbit.core.long_horizon.get_long_horizon", return_value=lh):
            r1 = start_overnight("g1", 1)
            r2 = start_overnight("g2", 1)
            self.assertTrue(r1["ok"])
            self.assertFalse(r2["ok"])
            self.assertEqual(r2["error"], "already running")
            gate.set()
            _wait_idle()


class TestCycle(unittest.TestCase):
    def setUp(self):
        _reset_state()

    def tearDown(self):
        _wait_idle()
        _reset_state()

    def test_cycle_sets_state_and_completes(self):
        lh = _mock_lh(advance_side_effect=[{"goal": "a"}, {"goal": "b"}])
        with patch("orbit.core.long_horizon.get_long_horizon", return_value=lh):
            _cycle("goal", 2)
        self.assertFalse(_state["running"])
        self.assertEqual(_state["done"], 2)
        self.assertEqual(_state["log"], ["a", "b"])
        lh.start_goal.assert_called_once_with("goal")

    def test_cycle_advance_none_logs_str_none(self):
        lh = _mock_lh(advance_side_effect=[None, None])
        with patch("orbit.core.long_horizon.get_long_horizon", return_value=lh):
            _cycle("g", 2)
        self.assertEqual(_state["log"], ["None", "None"])

    def test_cycle_advance_non_dict_coerced_to_str(self):
        lh = _mock_lh(advance_side_effect=["raw-note", {"goal": "d"}])
        with patch("orbit.core.long_horizon.get_long_horizon", return_value=lh):
            _cycle("g", 2)
        self.assertEqual(_state["log"], ["raw-note", "d"])

    def test_cycle_advance_missing_goal_key(self):
        lh = _mock_lh(advance_side_effect=[{}, {"other": 1}])
        with patch("orbit.core.long_horizon.get_long_horizon", return_value=lh):
            _cycle("g", 2)
        self.assertEqual(_state["log"], ["", ""])

    def test_cycle_exception_stops_but_marks_not_running(self):
        lh = _mock_lh()
        lh.advance.side_effect = RuntimeError("boom")
        with patch("orbit.core.long_horizon.get_long_horizon", return_value=lh):
            _cycle("g", 5)
        self.assertFalse(_state["running"])
        self.assertEqual(_state["done"], 0)

    def test_cycle_start_goal_raises(self):
        lh = _mock_lh()
        lh.start_goal.side_effect = ValueError("bad goal")
        with patch("orbit.core.long_horizon.get_long_horizon", return_value=lh):
            _cycle("g", 5)
        self.assertFalse(_state["running"])

    def test_cycle_log_capped_at_200(self):
        lh = _mock_lh(advance_side_effect=[{"goal": str(i)} for i in range(210)])
        with patch("orbit.core.long_horizon.get_long_horizon", return_value=lh):
            _cycle("g", 210)
        self.assertEqual(len(_state["log"]), 200)
        self.assertEqual(_state["log"][-1], "209")
        self.assertEqual(_state["log"][0], "10")

    def test_cycle_resets_previous_state(self):
        with ov._lock:
            _state["done"] = 99
            _state["log"] = ["old"]
        lh = _mock_lh(advance_return={"goal": "n"})
        with patch("orbit.core.long_horizon.get_long_horizon", return_value=lh):
            _cycle("g", 1)
        self.assertEqual(_state["done"], 1)
        self.assertEqual(_state["log"], ["n"])

    def test_cycle_passes_goal_id_to_advance(self):
        lh = _mock_lh(advance_return={"goal": "g"})
        with patch("orbit.core.long_horizon.get_long_horizon", return_value=lh):
            _cycle("g", 1)
        lh.advance.assert_called_once_with("gid1")


class TestStatus(unittest.TestCase):
    def setUp(self):
        _reset_state()

    def tearDown(self):
        _reset_state()

    def test_status_returns_copy(self):
        s = status()
        self.assertIn("running", s)
        self.assertIn("goal", s)
        self.assertIn("done", s)
        self.assertIn("log", s)
        self.assertFalse(s["running"])

    def test_status_is_not_alias(self):
        s = status()
        s["running"] = True
        with ov._lock:
            self.assertFalse(_state["running"])

    def test_status_reflects_state(self):
        with ov._lock:
            _state["running"] = True
            _state["goal"] = "g"
            _state["done"] = 3
        s = status()
        self.assertTrue(s["running"])
        self.assertEqual(s["goal"], "g")
        self.assertEqual(s["done"], 3)


if __name__ == "__main__":
    unittest.main()
