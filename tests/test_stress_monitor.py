"""Unit tests for orbit/orbit/core/stress_monitor.py."""

import os
import sys
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.stress_monitor import (
    StressThresholds,
    StressSnapshot,
    StressLevel,
    StressMonitor,
    get_stress_monitor,
)
import orbit.core.stress_monitor as sm_mod


class FakeProc:
    """psutil.Process stand-in with optional num_fds attribute."""

    def __init__(self, rss_mb=512, mem_pct=10.0, cpu=5.0,
                 threads=4, with_fds=True, fds=77):
        self._rss = rss_mb
        self._mem_pct = mem_pct
        self._cpu = cpu
        self._threads = threads
        if with_fds:
            self.num_fds = lambda: fds

    def memory_info(self):
        return SimpleNamespace(rss=int(self._rss * 1024 * 1024))

    def memory_percent(self):
        return self._mem_pct

    def cpu_percent(self, interval=None):
        return self._cpu

    def num_threads(self):
        return self._threads


def fake_psutil(proc=None, disk_percent=55.0, disk_error=False):
    mod = MagicMock()
    mod.Process.return_value = proc or FakeProc()
    if disk_error:
        mod.disk_usage.side_effect = OSError("no disk")
    else:
        mod.disk_usage.return_value = SimpleNamespace(percent=disk_percent)
    return mod


class TestDataclasses(unittest.TestCase):
    def test_threshold_defaults(self):
        t = StressThresholds()
        self.assertEqual(t.memory_warning_mb, 1024)
        self.assertEqual(t.memory_critical_mb, 2048)
        self.assertEqual(t.cpu_warning, 80.0)
        self.assertEqual(t.cpu_critical, 95.0)
        self.assertEqual(t.disk_warning_percent, 85.0)
        self.assertEqual(t.disk_critical_percent, 95.0)

    def test_snapshot_defaults(self):
        s = StressSnapshot()
        self.assertEqual(s.memory_mb, 0.0)
        self.assertEqual(s.memory_percent, 0.0)
        self.assertEqual(s.cpu_percent, 0.0)
        self.assertEqual(s.disk_percent, 0.0)
        self.assertEqual(s.open_fds, 0)
        self.assertEqual(s.threads, 0)
        self.assertEqual(s.gc_objects, 0)
        self.assertEqual(s.timestamp, 0.0)

    def test_stress_levels(self):
        self.assertEqual(StressLevel.NORMAL, "normal")
        self.assertEqual(StressLevel.WARNING, "warning")
        self.assertEqual(StressLevel.CRITICAL, "critical")

    def test_monitor_defaults(self):
        m = StressMonitor()
        self.assertIsInstance(m.thresholds, StressThresholds)
        self.assertEqual(m._max_history, 120)
        self.assertTrue(m._auto_cleanup_enabled)
        self.assertEqual(m._cleanup_cooldown, 60.0)
        self.assertEqual(m._history, [])
        self.assertEqual(m._alerts, [])

    def test_custom_thresholds(self):
        t = StressThresholds(memory_critical_mb=99)
        m = StressMonitor(thresholds=t)
        self.assertIs(m.thresholds, t)


class TestSnapshot(unittest.TestCase):
    def setUp(self):
        self.mon = StressMonitor()

    def test_full_success(self):
        proc = FakeProc(rss_mb=768, mem_pct=22.2, cpu=33.3,
                        threads=9, fds=55)
        with patch.dict(sys.modules, {"psutil": fake_psutil(proc, 66.0)}):
            snap = self.mon.snapshot()
        self.assertEqual(snap.memory_mb, 768.0)
        self.assertEqual(snap.memory_percent, 22.2)
        self.assertEqual(snap.cpu_percent, 33.3)
        self.assertEqual(snap.open_fds, 55)
        self.assertEqual(snap.threads, 9)
        self.assertEqual(snap.disk_percent, 66.0)
        self.assertGreater(snap.timestamp, 0)
        self.assertGreater(snap.gc_objects, 0)

    def test_history_recorded(self):
        with patch.dict(sys.modules, {"psutil": fake_psutil()}):
            self.mon.snapshot()
        self.assertEqual(len(self.mon._history), 1)

    def test_history_capped_120(self):
        with patch.dict(sys.modules, {"psutil": fake_psutil()}):
            for _ in range(125):
                self.mon.snapshot()
        self.assertEqual(len(self.mon._history), 120)

    def test_missing_num_fds_attribute(self):
        proc = FakeProc(with_fds=False)
        with patch.dict(sys.modules, {"psutil": fake_psutil(proc)}):
            snap = self.mon.snapshot()
        self.assertEqual(snap.open_fds, 0)  # hasattr branch

    def test_psutil_failure_returns_partial_snap(self):
        mod = MagicMock()
        mod.Process.side_effect = RuntimeError("psutil broken")
        with patch.dict(sys.modules, {"psutil": mod}):
            with self.assertLogs("orbit.core.stress_monitor",
                                 level="ERROR") as cm:
                snap = self.mon.snapshot()
        self.assertIn("snapshot failed", cm.output[0])
        self.assertEqual(snap.memory_mb, 0.0)
        self.assertEqual(snap.gc_objects, 0)  # early return skips gc line
        self.assertEqual(self.mon._history, [])  # no history append

    def test_disk_usage_error_keeps_zero(self):
        with patch.dict(sys.modules,
                        {"psutil": fake_psutil(disk_error=True)}):
            snap = self.mon.snapshot()
        self.assertEqual(snap.disk_percent, 0.0)  # inner except: pass

    def test_app_root_failure_anchor_slash(self):
        with patch.dict(sys.modules, {"psutil": fake_psutil()}), \
             patch("orbit.core.runtime_paths.app_root",
                   side_effect=RuntimeError("no root")):
            snap = self.mon.snapshot()
            # disk_usage still called (anchor "/")
        self.assertEqual(snap.disk_percent, 55.0)

    def test_memory_rounded_one_decimal(self):
        proc = FakeProc(rss_mb=123.456)
        with patch.dict(sys.modules, {"psutil": fake_psutil(proc)}):
            snap = self.mon.snapshot()
        self.assertEqual(snap.memory_mb, 123.5)


class TestThresholds(unittest.TestCase):
    def setUp(self):
        self.mon = StressMonitor()

    def _snap(self, **kw):
        return StressSnapshot(**kw)

    def test_no_alerts_normal(self):
        with self.assertNoLogs("orbit.core.stress_monitor", level="WARNING"):
            self.mon._check_thresholds(self._snap(
                memory_mb=100, cpu_percent=10, disk_percent=20))
        self.assertEqual(self.mon._alerts, [])

    def test_memory_critical(self):
        self.mon._check_thresholds(self._snap(memory_mb=3000))
        self.assertEqual(len(self.mon._alerts), 1)
        a = self.mon._alerts[0]
        self.assertEqual(a["type"], "memory")
        self.assertEqual(a["level"], "critical")
        self.assertEqual(a["value"], 3000)
        self.assertEqual(a["threshold"], 2048)
        self.assertIn("timestamp", a)

    def test_memory_warning(self):
        self.mon._check_thresholds(self._snap(memory_mb=1500))
        self.assertEqual(self.mon._alerts[0]["level"], "warning")

    def test_memory_zero_never_alerts(self):
        # memory_mb == 0 guard: unknown memory must not alert
        self.mon._check_thresholds(self._snap(memory_mb=0))
        self.assertEqual(self.mon._alerts, [])

    def test_cpu_critical(self):
        self.mon._check_thresholds(self._snap(cpu_percent=96.0))
        self.assertEqual(self.mon._alerts[0]["type"], "cpu")
        self.assertEqual(self.mon._alerts[0]["level"], "critical")

    def test_cpu_warning(self):
        self.mon._check_thresholds(self._snap(cpu_percent=85.0))
        self.assertEqual(self.mon._alerts[0]["level"], "warning")

    def test_cpu_below_no_alert(self):
        self.mon._check_thresholds(self._snap(cpu_percent=79.9))
        self.assertEqual(self.mon._alerts, [])

    def test_disk_critical(self):
        self.mon._check_thresholds(self._snap(disk_percent=96.0))
        self.assertEqual(self.mon._alerts[0]["type"], "disk")
        self.assertEqual(self.mon._alerts[0]["level"], "critical")

    def test_disk_warning(self):
        self.mon._check_thresholds(self._snap(disk_percent=90.0))
        self.assertEqual(self.mon._alerts[0]["level"], "warning")

    def test_combined_alerts_all_recorded(self):
        self.mon._check_thresholds(self._snap(
            memory_mb=3000, cpu_percent=85.0, disk_percent=96.0))
        self.assertEqual(len(self.mon._alerts), 3)
        types = [a["type"] for a in self.mon._alerts]
        self.assertEqual(types, ["memory", "cpu", "disk"])

    def test_warning_logged(self):
        with self.assertLogs("orbit.core.stress_monitor",
                             level="WARNING") as cm:
            self.mon._check_thresholds(self._snap(cpu_percent=90.0))
        self.assertIn("Stress alert", cm.output[0])

    def test_alerts_capped_200(self):
        for i in range(210):
            self.mon._check_thresholds(self._snap(cpu_percent=96.0))
        self.assertEqual(len(self.mon._alerts), 200)
        # oldest evicted: first kept alert came from iteration 10
        self.assertGreaterEqual(self.mon._alerts[0]["timestamp"], 0)

    def test_auto_cleanup_on_critical(self):
        with patch.object(sm_mod.gc, "collect", return_value=5) as gc_c:
            self.mon._check_thresholds(self._snap(memory_mb=5000))
        gc_c.assert_called_once()
        self.assertGreater(self.mon._last_cleanup_time, 0)

    def test_mixed_critical_and_warning_still_cleans(self):
        # regression: max("critical","warning") == "warning" used to
        # skip cleanup whenever a warning co-occurred with a critical
        with patch.object(sm_mod.gc, "collect", return_value=1) as gc_c:
            self.mon._check_thresholds(self._snap(
                memory_mb=5000, cpu_percent=85.0))
        gc_c.assert_called_once()

    def test_no_cleanup_on_warning_only(self):
        with patch.object(sm_mod.gc, "collect") as gc_c:
            self.mon._check_thresholds(self._snap(cpu_percent=90.0))
        gc_c.assert_not_called()

    def test_cleanup_cooldown(self):
        with patch.object(sm_mod.gc, "collect") as gc_c:
            self.mon._check_thresholds(self._snap(memory_mb=5000))
            gc_c.assert_called_once()
            # second critical inside cooldown window
            self.mon._check_thresholds(self._snap(memory_mb=5000))
            gc_c.assert_called_once()  # still just one

    def test_cleanup_disabled(self):
        self.mon._auto_cleanup_enabled = False
        with patch.object(sm_mod.gc, "collect") as gc_c:
            self.mon._check_thresholds(self._snap(memory_mb=5000))
        gc_c.assert_not_called()

    def test_auto_cleanup_sets_last_time(self):
        before = self.mon._last_cleanup_time
        self.mon.auto_cleanup()
        self.assertGreaterEqual(self.mon._last_cleanup_time, before)


class TestStressLevel(unittest.TestCase):
    def _mon_with(self, snap):
        mon = StressMonitor()
        patcher = patch.object(mon, "snapshot", return_value=snap)
        patcher.start()
        self.addCleanup(patcher.stop)
        return mon

    def test_critical_memory(self):
        mon = self._mon_with(StressSnapshot(memory_mb=3000))
        self.assertEqual(mon.get_stress_level(), StressLevel.CRITICAL)

    def test_critical_cpu(self):
        mon = self._mon_with(StressSnapshot(cpu_percent=97.0))
        self.assertEqual(mon.get_stress_level(), StressLevel.CRITICAL)

    def test_warning_memory(self):
        mon = self._mon_with(StressSnapshot(memory_mb=1500))
        self.assertEqual(mon.get_stress_level(), StressLevel.WARNING)

    def test_warning_cpu(self):
        mon = self._mon_with(StressSnapshot(cpu_percent=85.0))
        self.assertEqual(mon.get_stress_level(), StressLevel.WARNING)

    def test_critical_disk(self):
        mon = self._mon_with(StressSnapshot(disk_percent=96.0))
        self.assertEqual(mon.get_stress_level(), StressLevel.CRITICAL)

    def test_warning_disk(self):
        mon = self._mon_with(StressSnapshot(disk_percent=90.0))
        self.assertEqual(mon.get_stress_level(), StressLevel.WARNING)

    def test_normal(self):
        mon = self._mon_with(StressSnapshot(
            memory_mb=100, cpu_percent=10, disk_percent=20))
        self.assertEqual(mon.get_stress_level(), StressLevel.NORMAL)


class TestStatus(unittest.TestCase):
    def test_status_shape(self):
        mon = StressMonitor()
        snap = StressSnapshot(memory_mb=500, cpu_percent=10, threads=7)
        with patch.object(mon, "snapshot", return_value=snap):
            status = mon.get_status()
        self.assertEqual(set(status.keys()), {
            "stress_level", "snapshot", "thresholds",
            "alerts_count", "auto_cleanup_enabled"})
        self.assertEqual(status["stress_level"], "normal")
        self.assertEqual(status["snapshot"], {
            "memory_mb": 500, "memory_percent": 0.0, "cpu_percent": 10,
            "disk_percent": 0.0, "open_fds": 0, "threads": 7,
            "gc_objects": 0})
        self.assertEqual(status["thresholds"]["memory_warning_mb"], 1024)
        self.assertEqual(status["thresholds"]["disk_critical_percent"], 95.0)
        self.assertEqual(status["alerts_count"], 0)
        self.assertTrue(status["auto_cleanup_enabled"])

    def test_status_reflects_alerts(self):
        mon = StressMonitor()
        mon._alerts = [{"type": "cpu"}] * 3
        snap = StressSnapshot()
        with patch.object(mon, "snapshot", return_value=snap):
            status = mon.get_status()
        self.assertEqual(status["alerts_count"], 3)


class TestAlerts(unittest.TestCase):
    def test_get_alerts_default_20(self):
        mon = StressMonitor()
        mon._alerts = [{"i": i} for i in range(30)]
        got = mon.get_alerts()
        self.assertEqual(len(got), 20)
        self.assertEqual(got[-1]["i"], 29)  # newest last

    def test_get_alerts_limit(self):
        mon = StressMonitor()
        mon._alerts = [{"i": i} for i in range(10)]
        got = mon.get_alerts(limit=3)
        self.assertEqual(got, [{"i": 7}, {"i": 8}, {"i": 9}])

    def test_get_alerts_empty(self):
        mon = StressMonitor()
        self.assertEqual(mon.get_alerts(), [])

    def test_get_alerts_returns_copy(self):
        mon = StressMonitor()
        mon._alerts = [{"i": 1}]
        got = mon.get_alerts()
        got.append({"i": 999})
        self.assertEqual(len(mon._alerts), 1)


class TestSingleton(unittest.TestCase):
    def test_singleton(self):
        self.assertIs(get_stress_monitor(), get_stress_monitor())

    def test_type(self):
        self.assertIsInstance(get_stress_monitor(), StressMonitor)

    def test_creates_when_none(self):
        with patch.object(sm_mod, "_monitor", None):
            m1 = get_stress_monitor()
            self.assertIsInstance(m1, StressMonitor)
            self.assertIs(get_stress_monitor(), m1)


if __name__ == "__main__":
    unittest.main()
