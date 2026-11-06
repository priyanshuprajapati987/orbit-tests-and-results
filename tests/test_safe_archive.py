"""Unit tests for orbit/orbit/core/safe_archive.py."""

import io
import os
import sys
import tempfile
import unittest
import zipfile

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.safe_archive import safe_extract_zip, ZipSlipError


def make_zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    buf.seek(0)
    return buf.getvalue()


class TestSafeArchive(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dest = os.path.join(self.tmp, "out")
        os.makedirs(self.dest, exist_ok=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_zip(self, entries):
        zpath = os.path.join(self.tmp, "test.zip")
        with open(zpath, "wb") as f:
            f.write(make_zip(entries))
        return zpath

    def test_normal_extract(self):
        zpath = self._write_zip({"a.txt": "hello", "sub/b.txt": "world"})
        dest = safe_extract_zip(zpath, self.dest)
        self.assertTrue(os.path.exists(os.path.join(self.dest, "a.txt")))
        self.assertTrue(os.path.exists(os.path.join(self.dest, "sub", "b.txt")))

    def test_path_traversal_blocked(self):
        zpath = self._write_zip({"../../evil.txt": "x"})
        with self.assertRaises(ZipSlipError):
            safe_extract_zip(zpath, self.dest)

    def test_absolute_blocked(self):
        zpath = self._write_zip({"/etc/passwd": "x"})
        with self.assertRaises(ZipSlipError):
            safe_extract_zip(zpath, self.dest)

    def test_too_many_members(self):
        entries = {f"f{i}.txt": "x" for i in range(5)}
        zpath = self._write_zip(entries)
        with self.assertRaises(ZipSlipError):
            safe_extract_zip(zpath, self.dest, max_members=2)

    def test_too_large_member(self):
        zpath = self._write_zip({"big.txt": "x" * 100})
        with self.assertRaises(ZipSlipError):
            safe_extract_zip(zpath, self.dest, max_file_bytes=10)

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            safe_extract_zip(os.path.join(self.tmp, "nope.zip"), self.dest)

    def test_returns_dest(self):
        zpath = self._write_zip({"a.txt": "hi"})
        dest = safe_extract_zip(zpath, self.dest)
        self.assertTrue(str(dest).endswith("out"))


if __name__ == "__main__":
    unittest.main()
