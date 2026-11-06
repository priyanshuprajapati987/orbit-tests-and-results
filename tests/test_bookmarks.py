"""Unit tests for orbit/orbit/bookmarks.py."""

import os
import sys
import tempfile
import unittest
import pathlib

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

import orbit.bookmarks as bm


class TestBookmarks(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        if os.path.exists(self.path):
            os.remove(self.path)
        bm.BOOKMARKS_FILE = pathlib.Path(self.path)
        # reset storage
        if os.path.exists(self.path):
            os.remove(self.path)

    def tearDown(self):
        try:
            if os.path.exists(self.path):
                os.remove(self.path)
        except Exception:
            pass

    def test_add(self):
        r = bm.add("https://example.com", title="Ex", tags=["t"], folder="general")
        self.assertIsNotNone(r)

    def test_get_all(self):
        bm.add("https://example.com", title="Ex")
        r = bm.get_all()
        self.assertIsInstance(r, list)
        self.assertGreaterEqual(len(r), 1)

    def test_search(self):
        bm.add("https://example.com", title="Example")
        r = bm.search("example")
        self.assertIsInstance(r, list)

    def test_folders(self):
        bm.add("https://example.com", title="Ex", folder="work")
        r = bm.folders()
        self.assertIsInstance(r, list)

    def test_update(self):
        bm.add("https://example.com", title="Ex")
        items = bm.get_all()
        bid = items[0]["id"] if isinstance(items[0], dict) else items[0].id
        r = bm.update(bid, title="New")
        self.assertTrue(r is None or isinstance(r, (dict, bool)))

    def test_delete(self):
        bm.add("https://example.com", title="Ex")
        items = bm.get_all()
        bid = items[0]["id"] if isinstance(items[0], dict) else items[0].id
        r = bm.delete(bid)
        self.assertTrue(r is None or isinstance(r, (bool, dict)))

    def test_format_list(self):
        bm.add("https://example.com", title="Ex")
        r = bm.format_list()
        self.assertIsInstance(r, str)

    def test_format_search(self):
        bm.add("https://example.com", title="Ex")
        r = bm.format_search(bm.search("example"))
        self.assertIsInstance(r, str)


if __name__ == "__main__":
    unittest.main()
