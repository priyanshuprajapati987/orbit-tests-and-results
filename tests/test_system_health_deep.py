"""Deep tests for orbit/orbit/core/system_health.py (Loop 11/1).

Covers every statement:
  * psutil-present and psutil-missing import paths (module reload with
    psutil blocked covers the ``except ImportError`` line).
  * ``get_snapshot`` — full metric shape, cpu/ram/disk status tiers
    (ok / warning / critical), history cap at 100, error dict on
    psutil failure.
  * ``_check_alerts`` / ``get_alerts`` / ``get_history`` — thresholds,
    50-alert cap, limit slicing.
  * ``get_top_processes`` — sorting, None-safe rounding, n-slicing,
    no-psutil and exception paths.
  * ``get_stats`` + ``get_system_health`` singleton.
"""

import importlib
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

from orbit.orbit.core import system_health as sh


def _fake_psutil(cpu=50.0, ram_pct=60.0, disk_pct=70.0, cpu_exc=None):
    m = mock.MagicMock()
    if cpu_exc is not None:
        m.cpu_percent.side_effect = cpu_exc
    else:
        m.cpu_percent.return_value = cpu
    m.virtual_memory.return_value = SimpleNamespace(
        total=8 * 1024**3, used=4 * 1024**3, percent=ram_pct)
    m.disk_usage.return_value = SimpleNamespace(
        total=100 * 1024**3, used=70 * 1024**3, percent=disk_pct)
    m.net_io_counters.return_value = SimpleNamespace(
        bytes_sent=1000, bytes_recv=2000, packets_sent=10, packets_recv=20)
    m.cpu_count.return_value = 8
    return m


def _proc(pid, name, cpu, mem):
    return SimpleNamespace(
        info={"pid": pid, "name": name, "cpu_percent": cpu,
              "memory_percent": mem})


class _Base(unittest.TestCase):
    def setUp(self):
        self._saved_health = sh._health
        self._saved_psutil_flag = sh.HAS_PSUTIL

        def _restore():
            sh._health = self._saved_health
            sh.HAS_PSUTIL = self._saved_psutil_flag

        self.addCleanup(_restore)

    def _snapshot(self, fake):
        with mock.patch.object(sh, "psutil", fake), \
                mock.patch.object(sh, "HAS_PSUTIL", True):
            return sh.SystemHealth().get_snapshot()


class SnapshotTests(_Base):
    def test_full_shape(self):
        snap = self._snapshot(_fake_psutil(cpu=50.0, ram_pct=60.0,
                                           disk_pct=70.0))
        self.assertIsInstance(snap["timestamp"], float)
        self.assertEqual(snap["cpu"]["percent"], 50.0)
        self.assertEqual(snap["cpu"]["cores"], 8)
        self.assertEqual(snap["cpu"]["status"], "ok")
        self.assertEqual(snap["ram"]["total_gb"], 8.0)
        self.assertEqual(snap["ram"]["used_gb"], 4.0)
        self.assertEqual(snap["ram"]["percent"], 60.0)
        self.assertEqual(snap["ram"]["status"], "ok")
        self.assertEqual(snap["disk"]["total_gb"], 100.0)
        self.assertEqual(snap["disk"]["used_gb"], 70.0)
        self.assertEqual(snap["disk"]["percent"], 70.0)
        self.assertEqual(snap["disk"]["status"], "ok")
        self.assertEqual(snap["network"]["bytes_sent"], 1000)
        self.assertEqual(snap["network"]["bytes_recv"], 2000)
        self.assertEqual(snap["network"]["packets_sent"], 10)
        self.assertEqual(snap["network"]["packets_recv"], 20)

    def test_cpu_status_tiers(self):
        self.assertEqual(self._snapshot(_fake_psutil(cpu=95.0))
                         ["cpu"]["status"], "critical")
        self.assertEqual(self._snapshot(_fake_psutil(cpu=85.0))
                         ["cpu"]["status"], "warning")
        self.assertEqual(self._snapshot(_fake_psutil(cpu=80.0))
                         ["cpu"]["status"], "ok")

    def test_ram_status_tiers(self):
        self.assertEqual(self._snapshot(_fake_psutil(ram_pct=95.0))
                         ["ram"]["status"], "critical")
        self.assertEqual(self._snapshot(_fake_psutil(ram_pct=85.0))
                         ["ram"]["status"], "warning")
        self.assertEqual(self._snapshot(_fake_psutil(ram_pct=80.0))
                         ["ram"]["status"], "ok")

    def test_disk_status_tiers(self):
        self.assertEqual(self._snapshot(_fake_psutil(disk_pct=96.0))
                         ["disk"]["status"], "critical")
        self.assertEqual(self._snapshot(_fake_psutil(disk_pct=92.0))
                         ["disk"]["status"], "warning")
        self.assertEqual(self._snapshot(_fake_psutil(disk_pct=90.0))
                         ["disk"]["status"], "ok")

    def test_history_appended_and_capped_at_100(self):
        inst = sh.SystemHealth()
        fake = _fake_psutil()
        with mock.patch.object(sh, "psutil", fake), \
                mock.patch.object(sh, "HAS_PSUTIL", True):
            for _ in range(105):
                inst.get_snapshot()
        self.assertEqual(len(inst._history), 100)
        self.assertEqual(len(inst.get_history(limit=1000)), 100)

    def test_psutil_failure_returns_error_dict(self):
        snap = self._snapshot(_fake_psutil(cpu_exc=RuntimeError("boom")))
        self.assertEqual(snap, {"error": "boom"})

    def test_no_psutil_returns_error_dict(self):
        with mock.patch.object(sh, "HAS_PSUTIL", False):
            snap = sh.SystemHealth().get_snapshot()
        self.assertEqual(snap, {"error": "psutil not installed"})


class PsutilMissingImportTests(_Base):
    def test_import_without_psutil_sets_flag_false(self):
        # cover the `except ImportError` line by blocking psutil on reload
        with mock.patch.dict(sys.modules, {"psutil": None}):
            importlib.reload(sh)
            self.assertFalse(sh.HAS_PSUTIL)
            self.assertEqual(sh.SystemHealth().get_snapshot(),
                             {"error": "psutil not installed"})
        # restore the normal (psutil-present) module state
        importlib.reload(sh)
        self.assertTrue(sh.HAS_PSUTIL)


class AlertsTests(_Base):
    def _inst_with(self, cpu=50.0, ram_pct=60.0, disk_pct=70.0):
        inst = sh.SystemHealth()
        with mock.patch.object(sh, "psutil",
                               _fake_psutil(cpu, ram_pct, disk_pct)), \
                mock.patch.object(sh, "HAS_PSUTIL", True):
            inst.get_snapshot()
        return inst

    def test_all_three_alerts_fire(self):
        inst = self._inst_with(cpu=96.0, ram_pct=95.0, disk_pct=97.0)
        types = [a["type"] for a in inst.get_alerts()]
        self.assertEqual(types, ["cpu", "ram", "disk"])

    def test_threshold_boundaries(self):
        # alert fires strictly above the threshold
        inst = self._inst_with(cpu=86.0, ram_pct=91.0, disk_pct=96.0)
        self.assertEqual([a["type"] for a in inst.get_alerts()],
                         ["cpu", "ram", "disk"])
        inst2 = self._inst_with(cpu=85.0, ram_pct=90.0, disk_pct=95.0)
        self.assertEqual(inst2.get_alerts(), [])

    def test_alerts_capped_at_50(self):
        inst = sh.SystemHealth()
        for i in range(60):
            inst._check_alerts({"cpu": {"percent": 99},
                                "ram": {"percent": 99},
                                "disk": {"percent": 99}})
        self.assertEqual(len(inst._alerts), 50)

    def test_get_alerts_limit(self):
        inst = sh.SystemHealth()
        for i in range(5):
            inst._check_alerts({"cpu": {"percent": 99},
                                "ram": {"percent": 0},
                                "disk": {"percent": 0}})
        self.assertEqual(len(inst.get_alerts()), 5)
        self.assertEqual(len(inst.get_alerts(limit=2)), 2)

    def test_get_history_limit(self):
        inst = sh.SystemHealth()
        with mock.patch.object(sh, "psutil", _fake_psutil()), \
                mock.patch.object(sh, "HAS_PSUTIL", True):
            for _ in range(3):
                inst.get_snapshot()
        self.assertEqual(len(inst.get_history()), 3)
        self.assertEqual(len(inst.get_history(limit=2)), 2)


class TopProcessesTests(_Base):
    def test_sorted_desc_and_sliced(self):
        procs = [_proc(1, "low", 1.0, 5.0),
                 _proc(2, "high", 90.5, 50.0),
                 _proc(3, "mid", 20.0, 10.0),
                 _proc(4, "none", None, None)]
        fake = _fake_psutil()
        fake.process_iter.return_value = procs
        with mock.patch.object(sh, "psutil", fake), \
                mock.patch.object(sh, "HAS_PSUTIL", True):
            out = sh.SystemHealth().get_top_processes(2)
        self.assertEqual([p["name"] for p in out], ["high", "mid"])
        self.assertEqual(out[0]["cpu"], 90.5)

    def test_none_cpu_and_memory_rounded_to_zero(self):
        fake = _fake_psutil()
        fake.process_iter.return_value = [_proc(9, "ghost", None, None)]
        with mock.patch.object(sh, "psutil", fake), \
                mock.patch.object(sh, "HAS_PSUTIL", True):
            out = sh.SystemHealth().get_top_processes()
        self.assertEqual(out[0]["cpu"], 0.0)
        self.assertEqual(out[0]["memory"], 0.0)

    def test_no_psutil_returns_empty(self):
        with mock.patch.object(sh, "HAS_PSUTIL", False):
            self.assertEqual(sh.SystemHealth().get_top_processes(), [])

    def test_process_iter_failure_returns_empty(self):
        fake = _fake_psutil()
        fake.process_iter.side_effect = OSError("gone")
        with mock.patch.object(sh, "psutil", fake), \
                mock.patch.object(sh, "HAS_PSUTIL", True):
            self.assertEqual(sh.SystemHealth().get_top_processes(), [])


class StatsAndSingletonTests(_Base):
    def test_get_stats(self):
        inst = sh.SystemHealth()
        stats = inst.get_stats()
        self.assertEqual(stats["snapshots"], 0)
        self.assertEqual(stats["alerts"], 0)
        self.assertEqual(stats["thresholds"],
                         {"cpu_high": 85, "ram_high": 90, "disk_high": 95})
        self.assertIs(stats["psutil_available"], sh.HAS_PSUTIL)

    def test_singleton_reuses_instance(self):
        sh._health = None
        a = sh.get_system_health()
        b = sh.get_system_health()
        self.assertIsInstance(a, sh.SystemHealth)
        self.assertIs(a, b)

    def test_singleton_creates_when_none(self):
        self.assertIsNone(sh._health)
        inst = sh.get_system_health()
        self.assertIs(sh._health, inst)


if __name__ == "__main__":
    unittest.main()
