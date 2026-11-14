"""Unit tests for orbit/orbit/core/disk_cleanup.py."""

import os
import sys
import tempfile
import time
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.disk_cleanup import DiskCleanup, get_cleanup


class TestDiskCleanup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dc = DiskCleanup()
        self.dc.TEMP_DIRS = [__import__("pathlib").Path(self.tmp)]

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_file(self, name, content=b"x", age_days=0):
        p = os.path.join(self.tmp, name)
        with open(p, "wb") as f:
            f.write(content)
        if age_days:
            import time as t
            old = t.time() - age_days * 86400
            os.utime(p, (old, old))
        return p

    def test_scan_empty(self):
        r = self.dc.scan()
        self.assertEqual(r["temp_files"], 0)
        self.assertEqual(r["temp_size"], 0)
        self.assertEqual(r["temp_size_mb"], 0.0)

    def test_scan_counts_files(self):
        self._make_file("a.txt", b"hello")
        self._make_file("b.log", b"world!")
        r = self.dc.scan()
        self.assertEqual(r["temp_files"], 2)
        self.assertEqual(r["temp_size"], 11)
        self.assertIn(".txt", r["categories"])
        self.assertIn(".log", r["categories"])

    def test_scan_no_ext(self):
        self._make_file("noext", b"x")
        r = self.dc.scan()
        self.assertIn("no_ext", r["categories"])

    def test_clean_dry_run(self):
        p = self._make_file("old.txt", b"hello", age_days=10)
        r = self.dc.clean(older_than_days=7, dry_run=True)
        self.assertEqual(r["removed"], 1)
        self.assertGreaterEqual(r["freed_mb"], 0)
        self.assertTrue(r["dry_run"])
        # file still exists (dry run)
        self.assertTrue(os.path.exists(p))

    def test_clean_real_delete(self):
        p = self._make_file("old.txt", b"hello", age_days=10)
        r = self.dc.clean(older_than_days=7, dry_run=False)
        self.assertEqual(r["removed"], 1)
        self.assertFalse(r["dry_run"])
        self.assertFalse(os.path.exists(p))

    def test_clean_young_file_not_removed(self):
        p = self._make_file("young.txt", b"hello", age_days=1)
        r = self.dc.clean(older_than_days=7, dry_run=False)
        self.assertEqual(r["removed"], 0)
        self.assertTrue(os.path.exists(p))

    def test_clean_clamp_zero(self):
        self._make_file("old.txt", b"hello", age_days=10)
        r = self.dc.clean(older_than_days=0, dry_run=True)
        # clamped to 1.0; 10 days old > 1 → removed
        self.assertEqual(r["older_than_days"], 1.0)
        self.assertEqual(r["removed"], 1)

    def test_clean_clamp_negative(self):
        r = self.dc.clean(older_than_days=-5, dry_run=True)
        self.assertEqual(r["older_than_days"], 1.0)

    def test_clean_bad_value(self):
        r = self.dc.clean(older_than_days="abc", dry_run=True)
        self.assertEqual(r["older_than_days"], 7.0)

    def test_clean_subdir(self):
        sub = os.path.join(self.tmp, "sub")
        os.makedirs(sub)
        with open(os.path.join(sub, "old.txt"), "wb") as f:
            f.write(b"x" * 100)
        old = time.time() - 10 * 86400
        os.utime(os.path.join(sub, "old.txt"), (old, old))
        r = self.dc.clean(older_than_days=7, dry_run=True)
        self.assertEqual(r["removed"], 1)

    def test_singleton(self):
        import orbit.core.disk_cleanup as dc_mod
        dc_mod._cleanup = None
        a = get_cleanup()
        b = get_cleanup()
        self.assertIs(a, b)
        dc_mod._cleanup = None


if __name__ == "__main__":
    unittest.main()
