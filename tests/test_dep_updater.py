"""Unit tests for orbit/orbit/core/dep_updater.py."""

import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.dep_updater import DependencyUpdater, get_dependency_updater


class TestDependencyUpdater(unittest.TestCase):
    def setUp(self):
        self.u = DependencyUpdater()

    def test_check_outdated_success(self):
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = json.dumps([{"name": "requests", "latest_version": "2.32"}])
        with patch("orbit.core.dep_updater.subprocess.run", return_value=proc):
            r = self.u.check_outdated()
        self.assertEqual(r, [{"name": "requests", "latest_version": "2.32"}])

    def test_check_outdated_nonzero(self):
        proc = MagicMock()
        proc.returncode = 1
        proc.stdout = ""
        with patch("orbit.core.dep_updater.subprocess.run", return_value=proc):
            r = self.u.check_outdated()
        self.assertEqual(r, [])

    def test_check_outdated_empty_stdout(self):
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = ""
        with patch("orbit.core.dep_updater.subprocess.run", return_value=proc):
            r = self.u.check_outdated()
        self.assertEqual(r, [])

    def test_check_outdated_exception(self):
        with patch("orbit.core.dep_updater.subprocess.run", side_effect=RuntimeError("pip missing")):
            r = self.u.check_outdated()
        self.assertEqual(r, [])

    def test_summary(self):
        with patch.object(self.u, "check_outdated", return_value=[{"name": "requests"}, {"name": "flask"}]):
            r = self.u.summary()
        self.assertEqual(r["total_outdated"], 2)
        self.assertEqual(r["packages"], ["requests", "flask"])

    def test_summary_empty(self):
        with patch.object(self.u, "check_outdated", return_value=[]):
            r = self.u.summary()
        self.assertEqual(r["total_outdated"], 0)
        self.assertEqual(r["packages"], [])

    def test_singleton(self):
        import orbit.core.dep_updater as du
        du._updater = None
        a = get_dependency_updater()
        b = get_dependency_updater()
        self.assertIs(a, b)
        du._updater = None


if __name__ == "__main__":
    unittest.main()
