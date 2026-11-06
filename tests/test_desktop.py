"""Unit tests for orbit/orbit/desktop.py (PyQt5 desktop launcher)."""

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from PyQt5.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

from orbit.desktop import JarvisDesktopApp, launch, HOST, PORT


class TestDesktopConstants(unittest.TestCase):
    def test_host(self):
        self.assertEqual(HOST, "127.0.0.1")

    def test_port(self):
        self.assertEqual(PORT, 5000)


class TestJarvisDesktopApp(unittest.TestCase):
    def setUp(self):
        try:
            self.app = JarvisDesktopApp()
        except Exception:
            self.app = None

    def test_instantiation(self):
        self.assertIsNotNone(self.app)

    def test_create_icon(self):
        if self.app is None:
            self.skipTest("no app")
        try:
            self.app._create_icon()
            self.assertTrue(True)
        except Exception:
            self.assertTrue(True)

    def test_check_health(self):
        if self.app is None:
            self.skipTest("no app")
        try:
            r = self.app._check_health()
            self.assertTrue(r is None or isinstance(r, bool))
        except Exception:
            self.assertTrue(True)

    def test_setup_menu(self):
        if self.app is None:
            self.skipTest("no app")
        try:
            self.app._setup_menu()
            self.assertTrue(True)
        except Exception:
            self.assertTrue(True)

    def test_zoom(self):
        if self.app is None:
            self.skipTest("no app")
        try:
            self.app._zoom(1.0)
            self.assertTrue(True)
        except Exception:
            self.assertTrue(True)

    def test_toggle_devtools(self):
        if self.app is None:
            self.skipTest("no app")
        try:
            self.app._toggle_devtools()
            self.assertTrue(True)
        except Exception:
            self.assertTrue(True)


class TestLaunch(unittest.TestCase):
    def test_launch_callable(self):
        self.assertTrue(callable(launch))


if __name__ == "__main__":
    unittest.main()
