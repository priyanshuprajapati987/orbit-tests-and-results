"""Deep tests for orbit/system_monitor.py (pure functions + safe widget construction) (Loop 23/1)."""

import os
import subprocess
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")

from PyQt5.QtWidgets import QApplication

_app = QApplication.instance() or QApplication(sys.argv)

from unittest import mock

from orbit import system_monitor as sm


class GpuTempTests(unittest.TestCase):
    def test_windows_success(self):
        r = mock.MagicMock(stdout="  65  \n", returncode=0)
        with mock.patch("platform.system", return_value="Windows"), \
                mock.patch("subprocess.run", return_value=r):
            self.assertEqual(sm.get_gpu_temp(), 65)

    def test_windows_fail_returncode(self):
        r = mock.MagicMock(stdout="", returncode=1)
        with mock.patch("platform.system", return_value="Windows"), \
                mock.patch("subprocess.run", return_value=r):
            self.assertIsNone(sm.get_gpu_temp())

    def test_windows_empty_stdout(self):
        r = mock.MagicMock(stdout="   ", returncode=0)
        with mock.patch("platform.system", return_value="Windows"), \
                mock.patch("subprocess.run", return_value=r):
            self.assertIsNone(sm.get_gpu_temp())

    def test_linux_success(self):
        r = mock.MagicMock(stdout="  70  \n", returncode=0)
        with mock.patch("platform.system", return_value="Linux"), \
                mock.patch("subprocess.run", return_value=r):
            self.assertEqual(sm.get_gpu_temp(), 70)

    def test_linux_fail(self):
        r = mock.MagicMock(stdout="", returncode=1)
        with mock.patch("platform.system", return_value="Linux"), \
                mock.patch("subprocess.run", return_value=r):
            self.assertIsNone(sm.get_gpu_temp())

    def test_exception_returns_none(self):
        with mock.patch("platform.system", return_value="Windows"), \
                mock.patch("subprocess.run", side_effect=Exception("boom")):
            self.assertIsNone(sm.get_gpu_temp())


class GpuNameTests(unittest.TestCase):
    def test_success(self):
        r = mock.MagicMock(stdout="  NVIDIA GeForce RTX 3080  \n", returncode=0)
        with mock.patch("subprocess.run", return_value=r):
            self.assertEqual(sm.get_gpu_name(), "NVIDIA GeForce RTX 3080")

    def test_fail_returncode(self):
        r = mock.MagicMock(stdout="", returncode=1)
        with mock.patch("subprocess.run", return_value=r):
            self.assertIsNone(sm.get_gpu_name())

    def test_empty_stdout(self):
        r = mock.MagicMock(stdout="   ", returncode=0)
        with mock.patch("subprocess.run", return_value=r):
            self.assertIsNone(sm.get_gpu_name())

    def test_exception_returns_none(self):
        with mock.patch("subprocess.run", side_effect=Exception("boom")):
            self.assertIsNone(sm.get_gpu_name())

    def test_truncates_30(self):
        r = mock.MagicMock(stdout="A" * 50, returncode=0)
        with mock.patch("subprocess.run", return_value=r):
            name = sm.get_gpu_name()
        self.assertEqual(len(name), 30)


class ColorForTests(unittest.TestCase):
    def test_danger(self):
        self.assertEqual(sm._color_for(90), "#f85149")

    def test_warn(self):
        self.assertEqual(sm._color_for(70), "#ffb800")

    def test_ok(self):
        self.assertEqual(sm._color_for(30), "#64d4ff")

    def test_boundary_warn(self):
        self.assertEqual(sm._color_for(60), "#ffb800")

    def test_boundary_danger(self):
        self.assertEqual(sm._color_for(85), "#f85149")

    def test_custom_thresholds(self):
        self.assertEqual(sm._color_for(50, warn=40, danger=80), "#ffb800")
        self.assertEqual(sm._color_for(90, warn=40, danger=80), "#f85149")
        self.assertEqual(sm._color_for(30, warn=40, danger=80), "#64d4ff")


class GaugeWidgetTests(unittest.TestCase):
    def test_construction(self):
        g = sm.GaugeWidget("CPU", 50, "%", thresholds={"warn": 70, "danger": 90})
        self.assertEqual(g._label, "CPU")
        self.assertEqual(g._value, 50)
        self.assertEqual(g._unit, "%")
        self.assertEqual(g._thresholds, {"warn": 70, "danger": 90})
        self.assertEqual(g._animated, 0.0)
        self.assertIsNone(g._display)

    def test_construction_defaults(self):
        g = sm.GaugeWidget("RAM")
        self.assertEqual(g._unit, "%")
        self.assertIsNone(g._display)
        self.assertEqual(g._thresholds, {"warn": 60, "danger": 85})

    def test_set_value_clamps(self):
        g = sm.GaugeWidget("CPU")
        g.set_value(150)
        self.assertEqual(g._value, 100)
        g.set_value(-10)
        self.assertEqual(g._value, 0)
        g.set_value(50)
        self.assertEqual(g._value, 50)

    def test_set_value_sets_anim_fields(self):
        g = sm.GaugeWidget("CPU")
        g._animated = 10.0
        g.set_value(50)
        self.assertEqual(g._anim_from, 10.0)
        self.assertEqual(g._anim_target, 50)
        self.assertEqual(g._anim_step, 0)

    def test_set_display(self):
        g = sm.GaugeWidget("CPU")
        g.set_display("N/A")
        self.assertEqual(g._display, "N/A")


class GaugeBarTests(unittest.TestCase):
    def test_construction_creates_5_gauges(self):
        bar = sm.GaugeBar()
        self.assertEqual(len(bar.gauges), 5)
        for key in ("cpu", "ram", "gpu", "disk", "proc"):
            self.assertIn(key, bar.gauges)

    def test_timer_created(self):
        bar = sm.GaugeBar()
        self.assertIsNotNone(bar._timer)

    def test_update_success(self):
        bar = sm.GaugeBar()
        ram_mock = mock.MagicMock(percent=60.0, used=8 * 1024**3, total=16 * 1024**3)
        disk_mock = mock.MagicMock(percent=50.0, used=50 * 1024**3, total=100 * 1024**3)
        with mock.patch("psutil.cpu_percent", return_value=25.0), \
                mock.patch("psutil.virtual_memory", return_value=ram_mock), \
                mock.patch("psutil.disk_usage", return_value=disk_mock), \
                mock.patch("psutil.pids", return_value=[1, 2, 3]), \
                mock.patch.object(sm, "get_gpu_temp", return_value=65):
            bar._update()
        self.assertEqual(bar.gauges["cpu"]._value, 25)
        self.assertEqual(bar.gauges["ram"]._value, 60)
        self.assertEqual(bar.gauges["disk"]._value, 50)
        self.assertEqual(bar.gauges["proc"]._value, min(100, 3 / 4))
        self.assertEqual(bar.gauges["gpu"]._value, 65)

    def test_update_gpu_none(self):
        bar = sm.GaugeBar()
        ram_mock = mock.MagicMock(percent=60.0, used=8 * 1024**3, total=16 * 1024**3)
        disk_mock = mock.MagicMock(percent=50.0, used=50 * 1024**3, total=100 * 1024**3)
        with mock.patch("psutil.cpu_percent", return_value=25.0), \
                mock.patch("psutil.virtual_memory", return_value=ram_mock), \
                mock.patch("psutil.disk_usage", return_value=disk_mock), \
                mock.patch("psutil.pids", return_value=[]), \
                mock.patch.object(sm, "get_gpu_temp", return_value=None):
            bar._update()
        self.assertEqual(bar.gauges["gpu"]._value, 0)
        self.assertEqual(bar.gauges["gpu"]._display, "N/A")

    def test_update_exception(self):
        bar = sm.GaugeBar()
        with mock.patch("psutil.cpu_percent", side_effect=Exception("boom")), \
                mock.patch.object(sm, "logger") as lg:
            bar._update()
        lg.exception.assert_called_once()

    def test_update_proc_pct_cap(self):
        bar = sm.GaugeBar()
        ram_mock = mock.MagicMock(percent=60.0, used=8 * 1024**3, total=16 * 1024**3)
        disk_mock = mock.MagicMock(percent=50.0, used=50 * 1024**3, total=100 * 1024**3)
        with mock.patch("psutil.cpu_percent", return_value=25.0), \
                mock.patch("psutil.virtual_memory", return_value=ram_mock), \
                mock.patch("psutil.disk_usage", return_value=disk_mock), \
                mock.patch("psutil.pids", return_value=list(range(500))), \
                mock.patch.object(sm, "get_gpu_temp", return_value=None):
            bar._update()
        self.assertEqual(bar.gauges["proc"]._value, 100)


class DetailedMonitorPanelTests(unittest.TestCase):
    def test_construction(self):
        panel = sm.DetailedMonitorPanel()
        self.assertFalse(panel.isVisible())
        self.assertEqual(len(panel.info_labels), 6)

    def test_timer_created(self):
        panel = sm.DetailedMonitorPanel()
        self.assertIsNotNone(panel._timer)

    def test_update_not_visible_early_return(self):
        panel = sm.DetailedMonitorPanel()
        panel.setVisible(False)
        panel._update()

    def test_update_success(self):
        panel = sm.DetailedMonitorPanel()
        panel.setVisible(True)
        ram = mock.MagicMock(percent=60.0, used=8 * 1024**3, total=16 * 1024**3)
        disk = mock.MagicMock(percent=50.0, used=50 * 1024**3, total=100 * 1024**3)
        with mock.patch("psutil.cpu_percent", return_value=25.0), \
                mock.patch("psutil.virtual_memory", return_value=ram), \
                mock.patch("psutil.disk_usage", return_value=disk), \
                mock.patch("psutil.pids", return_value=[1, 2, 3]), \
                mock.patch.object(sm, "get_gpu_temp", return_value=65), \
                mock.patch.object(sm, "get_gpu_name", return_value="RTX 3080"):
            panel._update()
        self.assertEqual(panel.info_labels["cpu"].text(), "25.0%")
        self.assertIn("60.0%", panel.info_labels["ram"].text())
        self.assertIn("50.0%", panel.info_labels["disk"].text())
        self.assertEqual(panel.info_labels["proc"].text(), "3")
        self.assertEqual(panel.info_labels["gpu"].text(), "65°C")
        self.assertEqual(panel.info_labels["gpu_name"].text(), "RTX 3080")

    def test_update_gpu_none(self):
        panel = sm.DetailedMonitorPanel()
        panel.setVisible(True)
        ram = mock.MagicMock(percent=60.0, used=8 * 1024**3, total=16 * 1024**3)
        disk = mock.MagicMock(percent=50.0, used=50 * 1024**3, total=100 * 1024**3)
        with mock.patch("psutil.cpu_percent", return_value=25.0), \
                mock.patch("psutil.virtual_memory", return_value=ram), \
                mock.patch("psutil.disk_usage", return_value=disk), \
                mock.patch("psutil.pids", return_value=[]), \
                mock.patch.object(sm, "get_gpu_temp", return_value=None), \
                mock.patch.object(sm, "get_gpu_name", return_value=None):
            panel._update()
        self.assertEqual(panel.info_labels["gpu"].text(), "N/A (no NVIDIA GPU)")
        self.assertEqual(panel.info_labels["gpu_name"].text(), "N/A")

    def test_update_exception(self):
        panel = sm.DetailedMonitorPanel()
        panel.setVisible(True)
        with mock.patch("psutil.cpu_percent", side_effect=Exception("boom")), \
                mock.patch.object(sm, "logger") as lg:
            panel._update()
        lg.exception.assert_called_once()

    def test_update_gpu_temp_color(self):
        panel = sm.DetailedMonitorPanel()
        panel.setVisible(True)
        ram = mock.MagicMock(percent=60.0, used=8 * 1024**3, total=16 * 1024**3)
        disk = mock.MagicMock(percent=50.0, used=50 * 1024**3, total=100 * 1024**3)
        with mock.patch("psutil.cpu_percent", return_value=25.0), \
                mock.patch("psutil.virtual_memory", return_value=ram), \
                mock.patch("psutil.disk_usage", return_value=disk), \
                mock.patch("psutil.pids", return_value=[]), \
                mock.patch.object(sm, "get_gpu_temp", return_value=75), \
                mock.patch.object(sm, "get_gpu_name", return_value="GPU"):
            panel._update()
        self.assertIn("#ff4444", panel.info_labels["gpu"].styleSheet())


if __name__ == "__main__":
    unittest.main()
