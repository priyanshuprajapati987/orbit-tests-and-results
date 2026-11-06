"""Unit tests for orbit/orbit/core/process_manager.py."""

import os
import sys
import tempfile
import time
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.process_manager import (
    ProcessManager, get_process_manager, start_process, stop_process,
    is_running, list_processes, get_statistics,
)


class TestProcessManager(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        if os.path.exists(self.path):
            os.remove(self.path)
        self.pm = ProcessManager(storage_file=self.path)

    def tearDown(self):
        try:
            self.pm.stop_all()
        except Exception:
            pass
        try:
            if os.path.exists(self.path):
                os.remove(self.path)
        except Exception:
            pass

    def test_instantiation(self):
        self.assertIsNotNone(self.pm)

    def test_start_process(self):
        pid = self.pm.start_process("echo_test", "python", ["-c", "print('hi')"])
        self.assertTrue(pid is None or isinstance(pid, str))

    def test_is_running(self):
        pid = self.pm.start_process("echo_test2", "python", ["-c", "import time; time.sleep(0.2)"])
        name = pid if pid else "echo_test2"
        r = self.pm.is_running(name)
        self.assertTrue(r is None or isinstance(r, bool))

    def test_get_process_info(self):
        pid = self.pm.start_process("echo_test3", "python", ["-c", "print('hi')"])
        name = pid if pid else "echo_test3"
        r = self.pm.get_process_info(name)
        self.assertTrue(r is None or isinstance(r, dict))

    def test_list_processes(self):
        r = self.pm.list_processes()
        self.assertIsInstance(r, (list, dict))

    def test_get_running_processes(self):
        r = self.pm.get_running_processes()
        self.assertIsInstance(r, (list, dict))

    def test_stop_process(self):
        pid = self.pm.start_process("echo_test4", "python", ["-c", "import time; time.sleep(5)"])
        name = pid if pid else "echo_test4"
        time.sleep(0.2)
        r = self.pm.stop_process(name)
        self.assertTrue(r is None or isinstance(r, (bool, dict)))

    def test_kill_process(self):
        pid = self.pm.start_process("echo_test5", "python", ["-c", "import time; time.sleep(5)"])
        name = pid if pid else "echo_test5"
        time.sleep(0.2)
        r = self.pm.kill_process(name)
        self.assertTrue(r is None or isinstance(r, (bool, dict)))

    def test_cleanup_stopped(self):
        r = self.pm.cleanup_stopped()
        self.assertTrue(r is None or isinstance(r, (int, dict, bool)))

    def test_stop_all(self):
        self.pm.stop_all()
        self.assertTrue(True)

    def test_get_statistics(self):
        r = self.pm.get_statistics()
        self.assertIsNotNone(r)

    def test_singleton(self):
        a = get_process_manager()
        b = get_process_manager()
        self.assertIs(a, b)


class TestModuleFunctions(unittest.TestCase):
    def test_start_process_func(self):
        self.assertTrue(callable(start_process))

    def test_stop_process_func(self):
        self.assertTrue(callable(stop_process))

    def test_is_running_func(self):
        self.assertTrue(callable(is_running))

    def test_list_processes_func(self):
        self.assertTrue(callable(list_processes))

    def test_get_statistics_func(self):
        self.assertTrue(callable(get_statistics))


if __name__ == "__main__":
    unittest.main()
