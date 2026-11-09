"""Unit tests for orbit/orbit/core/system_info.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

import orbit.core.system_info as si_mod
from orbit.core.system_info import SystemInfo, get_system_info


class TestSystemInfo(unittest.TestCase):
    def test_info_no_psutil(self):
        with patch.object(si_mod, "HAS_PSUTIL", False):
            s = SystemInfo()
            r = s.get_info()
        self.assertIn("os", r)
        self.assertIn("paths", r)
        self.assertIn("system", r["os"])
        self.assertIn("python", r["os"])
        self.assertNotIn("cpu", r)
        self.assertNotIn("ram", r)

    def test_info_with_psutil(self):
        psutil = MagicMock()
        psutil.cpu_count.side_effect = lambda logical=False: 4 if logical else 2
        freq = MagicMock()
        freq._asdict.return_value = {"current": 2400.0}
        psutil.cpu_freq.return_value = freq
        mem = MagicMock()
        mem.total = 16 * 1024**3
        mem.available = 8 * 1024**3
        mem.percent = 50.0
        psutil.virtual_memory.return_value = mem
        disk = MagicMock()
        disk.total = 100 * 1024**3
        disk.used = 40 * 1024**3
        disk.free = 60 * 1024**3
        psutil.disk_usage.return_value = disk
        psutil.boot_time.return_value = 12345.0
        with patch.object(si_mod, "HAS_PSUTIL", True), \
             patch.object(si_mod, "psutil", psutil), \
             patch("orbit.core.runtime_paths.app_root", side_effect=RuntimeError("no root")):
            s = SystemInfo()
            r = s.get_info()
        self.assertIn("cpu", r)
        self.assertEqual(r["cpu"]["cores_physical"], 2)
        self.assertEqual(r["cpu"]["cores_logical"], 4)
        self.assertEqual(r["ram"]["total_gb"], 16.0)
        self.assertEqual(r["ram"]["available_gb"], 8.0)
        self.assertEqual(r["ram"]["percent"], 50.0)
        self.assertIn("disk", r)
        self.assertEqual(r["disk"]["total_gb"], 100.0)
        self.assertEqual(r["boot_time"], 12345.0)

    def test_disk_anchor_fallback(self):
        psutil = MagicMock()
        psutil.cpu_count.return_value = 1
        psutil.cpu_freq.return_value = None
        mem = MagicMock()
        mem.total = 1 * 1024**3
        mem.available = 0.5 * 1024**3
        mem.percent = 50.0
        psutil.virtual_memory.return_value = mem
        # first anchor raises, second succeeds
        disk = MagicMock()
        disk.total = 50 * 1024**3
        disk.used = 10 * 1024**3
        disk.free = 40 * 1024**3
        psutil.disk_usage.side_effect = [RuntimeError("no"), disk]
        psutil.boot_time.return_value = 0
        with patch.object(si_mod, "HAS_PSUTIL", True), \
             patch.object(si_mod, "psutil", psutil), \
             patch("orbit.core.runtime_paths.app_root", return_value=__import__("pathlib").Path("/app")):
            s = SystemInfo()
            r = s.get_info()
        self.assertEqual(r["disk"]["total_gb"], 50.0)

    def test_disk_all_fail(self):
        psutil = MagicMock()
        psutil.cpu_count.return_value = 1
        psutil.cpu_freq.return_value = None
        mem = MagicMock()
        mem.total = 1 * 1024**3
        mem.available = 0.5 * 1024**3
        mem.percent = 50.0
        psutil.virtual_memory.return_value = mem
        psutil.disk_usage.side_effect = RuntimeError("no disk")
        psutil.boot_time.return_value = 0
        with patch.object(si_mod, "HAS_PSUTIL", True), \
             patch.object(si_mod, "psutil", psutil), \
             patch("orbit.core.runtime_paths.app_root", side_effect=RuntimeError("no")):
            s = SystemInfo()
            r = s.get_info()
        self.assertEqual(r["disk"], {"total_gb": 0, "used_gb": 0, "free_gb": 0})

    def test_cpu_freq_none(self):
        psutil = MagicMock()
        psutil.cpu_count.return_value = 1
        psutil.cpu_freq.return_value = None
        mem = MagicMock()
        mem.total = 1 * 1024**3
        mem.available = 0.5 * 1024**3
        mem.percent = 50.0
        psutil.virtual_memory.return_value = mem
        disk = MagicMock()
        disk.total = 1 * 1024**3
        disk.used = 0
        disk.free = 1 * 1024**3
        psutil.disk_usage.return_value = disk
        psutil.boot_time.return_value = 0
        with patch.object(si_mod, "HAS_PSUTIL", True), \
             patch.object(si_mod, "psutil", psutil), \
             patch("orbit.core.runtime_paths.app_root", side_effect=RuntimeError("no")):
            s = SystemInfo()
            r = s.get_info()
        self.assertIsNone(r["cpu"]["frequency"])

    def test_singleton(self):
        si_mod._info = None
        a = get_system_info()
        b = get_system_info()
        self.assertIs(a, b)
        si_mod._info = None


if __name__ == "__main__":
    unittest.main()
