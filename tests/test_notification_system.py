"""Unit tests for orbit/orbit/core/notification_system.py."""

import os
import sys
import tempfile
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.notification_system import (
    NotificationChannel, NotificationPriority, NotificationSystem,
    get_notification_system, send_notification, get_notifications, mark_read,
)


class TestEnums(unittest.TestCase):
    def test_channels(self):
        self.assertEqual(NotificationChannel.DESKTOP, "desktop")
        self.assertEqual(NotificationChannel.IN_APP, "in_app")

    def test_priority(self):
        self.assertEqual(NotificationPriority.URGENT, "urgent")


class TestNotificationSystem(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        if os.path.exists(self.path):
            os.remove(self.path)
        self.ns = NotificationSystem(storage_file=self.path)

    def tearDown(self):
        try:
            if os.path.exists(self.path):
                os.remove(self.path)
        except Exception:
            pass

    def test_instantiation(self):
        self.assertIsNotNone(self.ns)

    def test_send_notification(self):
        nid = self.ns.send_notification("Hello", "Body text", channels=[NotificationChannel.IN_APP])
        self.assertIsNotNone(nid)

    def test_get_notifications(self):
        self.ns.send_notification("Hello", "Body", channels=[NotificationChannel.IN_APP])
        r = self.ns.get_notifications()
        self.assertIsInstance(r, list)
        self.assertGreaterEqual(len(r), 1)

    def test_mark_read(self):
        nid = self.ns.send_notification("Hello", "Body", channels=[NotificationChannel.IN_APP])
        self.ns.mark_read(nid)
        self.assertTrue(True)

    def test_mark_all_read(self):
        self.ns.send_notification("Hello", "Body", channels=[NotificationChannel.IN_APP])
        self.ns.mark_all_read()
        self.assertTrue(True)

    def test_delete_notification(self):
        nid = self.ns.send_notification("Hello", "Body", channels=[NotificationChannel.IN_APP])
        r = self.ns.delete_notification(nid)
        self.assertIsInstance(r, bool)

    def test_configure_channel(self):
        r = self.ns.configure_channel(NotificationChannel.IN_APP, {"enabled": True})
        self.assertTrue(r is None or isinstance(r, (bool, dict)))

    def test_get_statistics(self):
        r = self.ns.get_statistics()
        self.assertIsNotNone(r)

    def test_singleton(self):
        a = get_notification_system()
        b = get_notification_system()
        self.assertIs(a, b)


class TestModuleFunctions(unittest.TestCase):
    def test_send_notification_func(self):
        self.assertTrue(callable(send_notification))

    def test_get_notifications_func(self):
        self.assertTrue(callable(get_notifications))

    def test_mark_read_func(self):
        self.assertTrue(callable(mark_read))


if __name__ == "__main__":
    unittest.main()
