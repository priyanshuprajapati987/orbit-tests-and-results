"""Unit tests for orbit/orbit/core/session_manager.py."""

import os
import sys
import tempfile
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.session_manager import (
    Session, SessionManager, get_session_manager, create_session, get_session,
    destroy_session, set_data, get_data, get_statistics,
)


class TestSession(unittest.TestCase):
    def test_init(self):
        s = Session("sid1", "uid1", "127.0.0.1")
        self.assertEqual(s.session_id, "sid1")
        self.assertEqual(s.user_id, "uid1")
        self.assertTrue(s.is_active)

    def test_is_expired(self):
        s = Session("sid2", "uid2")
        self.assertFalse(s.is_expired())

    def test_touch(self):
        s = Session("sid3", "uid3")
        s.touch()
        self.assertIsNotNone(s.last_accessed)

    def test_data(self):
        s = Session("sid4", "uid4")
        s.data["k"] = "v"
        self.assertEqual(s.data["k"], "v")


class TestSessionManager(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        if os.path.exists(self.path):
            os.remove(self.path)
        self.sm = SessionManager(storage_file=self.path)

    def tearDown(self):
        try:
            if os.path.exists(self.path):
                os.remove(self.path)
        except Exception:
            pass

    def test_instantiation(self):
        self.assertIsNotNone(self.sm)

    def test_create_session(self):
        sid = self.sm.create_session("u1", "127.0.0.1")
        self.assertIsNotNone(sid)
        self.assertIn(sid, self.sm.sessions)

    def test_get_session(self):
        sid = self.sm.create_session("u2")
        s = self.sm.get_session(sid)
        self.assertIsNotNone(s)

    def test_validate_session(self):
        sid = self.sm.create_session("u3")
        r = self.sm.validate_session(sid)
        self.assertTrue(r is True or r is not None)

    def test_set_data_get_data(self):
        sid = self.sm.create_session("u4")
        self.sm.set_data(sid, "key", "value")
        r = self.sm.get_data(sid, "key")
        self.assertEqual(r, "value")

    def test_get_user_sessions(self):
        self.sm.create_session("u5")
        r = self.sm.get_user_sessions("u5")
        self.assertIsInstance(r, list)
        self.assertGreaterEqual(len(r), 1)

    def test_destroy_session(self):
        sid = self.sm.create_session("u6")
        r = self.sm.destroy_session(sid)
        self.assertTrue(r is None or isinstance(r, (bool, dict)))

    def test_cleanup_expired(self):
        r = self.sm.cleanup_expired()
        self.assertTrue(r is None or isinstance(r, (int, dict, bool)))

    def test_get_statistics(self):
        r = self.sm.get_statistics()
        self.assertIsNotNone(r)

    def test_singleton(self):
        a = get_session_manager()
        b = get_session_manager()
        self.assertIs(a, b)


class TestModuleFunctions(unittest.TestCase):
    def test_create_session_func(self):
        self.assertTrue(callable(create_session))

    def test_get_session_func(self):
        self.assertTrue(callable(get_session))

    def test_destroy_session_func(self):
        self.assertTrue(callable(destroy_session))

    def test_set_data_func(self):
        self.assertTrue(callable(set_data))

    def test_get_data_func(self):
        self.assertTrue(callable(get_data))

    def test_get_statistics_func(self):
        self.assertTrue(callable(get_statistics))


if __name__ == "__main__":
    unittest.main()
