"""Unit tests for orbit/orbit/core/clipboard_manager.py."""

import os
import sys
import time
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

import orbit.core.clipboard_manager as cm_mod
from orbit.core.clipboard_manager import ClipboardManager, get_clipboard_manager


class TestClipboardManagerNoPyperclip(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(cm_mod, "HAS_PYPERCLIP", False)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cm = ClipboardManager()

    def test_get_current_error(self):
        self.assertEqual(self.cm.get_current(), {"error": "pyperclip not installed"})

    def test_copy_error(self):
        self.assertEqual(self.cm.copy("hi"), {"error": "pyperclip not installed"})

    def test_start_monitoring_noop(self):
        self.cm.start_monitoring()
        self.assertFalse(self.cm._running)


class TestClipboardManagerWithPyperclip(unittest.TestCase):
    def setUp(self):
        self.pyperclip = MagicMock()
        patcher = patch.object(cm_mod, "HAS_PYPERCLIP", True)
        patcher.start()
        self.addCleanup(patcher.stop)
        # bind pyperclip in module namespace
        cm_mod.pyperclip = self.pyperclip
        self.addCleanup(lambda: delattr(cm_mod, "pyperclip") if hasattr(cm_mod, "pyperclip") else None)
        self.cm = ClipboardManager(max_history=3)

    def test_get_current(self):
        self.pyperclip.paste.return_value = "hello world"
        r = self.cm.get_current()
        self.assertEqual(r["content"], "hello world")
        self.assertEqual(r["length"], 11)

    def test_get_current_truncates(self):
        self.pyperclip.paste.return_value = "x" * 6000
        r = self.cm.get_current()
        self.assertEqual(len(r["content"]), 5000)

    def test_get_current_exception(self):
        self.pyperclip.paste.side_effect = RuntimeError("no clipboard")
        r = self.cm.get_current()
        self.assertEqual(r, {"error": "no clipboard"})

    def test_copy(self):
        r = self.cm.copy("text")
        self.assertEqual(r, {"status": "copied", "length": 4})
        self.pyperclip.copy.assert_called_once_with("text")
        self.assertEqual(len(self.cm.get_history()), 1)

    def test_copy_exception(self):
        self.pyperclip.copy.side_effect = RuntimeError("fail")
        r = self.cm.copy("text")
        self.assertEqual(r, {"error": "fail"})

    def test_copy_empty_not_added(self):
        r = self.cm.copy("")
        self.assertEqual(r, {"status": "copied", "length": 0})
        self.assertEqual(len(self.cm.get_history()), 0)

    def test_copy_large_not_added(self):
        self.cm.copy("x" * 10000)
        self.assertEqual(len(self.cm.get_history()), 0)

    def test_get_history_limit(self):
        for i in range(5):
            self.cm.copy(f"t{i}")
        hist = self.cm.get_history(limit=2)
        self.assertEqual(len(hist), 2)
        self.assertEqual(hist[-1]["content"], "t4")

    def test_get_history_default(self):
        self.cm.copy("a")
        self.cm.copy("b")
        self.assertEqual(len(self.cm.get_history()), 2)

    def test_clear_history(self):
        self.cm.copy("a")
        self.cm.clear_history()
        self.assertEqual(self.cm.get_history(), [])

    def test_max_history_deque(self):
        for i in range(5):
            self.cm.copy(f"t{i}")
        self.assertEqual(len(self.cm.get_history()), 3)  # max_history=3

    def test_start_stop_monitoring(self):
        self.cm.start_monitoring()
        self.assertTrue(self.cm._running)
        self.assertIsNotNone(self.cm._thread)
        self.cm.stop_monitoring()
        self.assertFalse(self.cm._running)

    def test_start_monitoring_idempotent(self):
        self.cm.start_monitoring()
        t1 = self.cm._thread
        self.cm.start_monitoring()
        self.assertIs(self.cm._thread, t1)
        self.cm.stop_monitoring()

    def test_get_stats(self):
        self.cm.copy("a")
        stats = self.cm.get_stats()
        self.assertEqual(stats["history_size"], 1)
        self.assertFalse(stats["monitoring"])
        self.assertTrue(stats["pyperclip_available"])

    def test_singleton(self):
        cm_mod._clipboard = None
        a = get_clipboard_manager()
        b = get_clipboard_manager()
        self.assertIs(a, b)
        cm_mod._clipboard = None


if __name__ == "__main__":
    unittest.main()
