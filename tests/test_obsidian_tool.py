"""Unit tests for orbit/orbit/tools/obsidian_tool.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.tools.obsidian_tool import ObsidianTool


class TestObsidianTool(unittest.TestCase):
    def setUp(self):
        self.tool = ObsidianTool()
        self.vault = MagicMock()
        self.patcher = patch("orbit.tools.obsidian_tool.get_obsidian_vault", return_value=self.vault)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_metadata(self):
        self.assertEqual(self.tool.name, "obsidian")
        self.assertIn("write", self.tool.requires_approval)
        self.assertIn("delete", self.tool.requires_approval)

    def test_read(self):
        self.vault.read_note.return_value = {"content": "hi"}
        r = self.tool.read("note.md")
        self.assertEqual(r, {"content": "hi"})
        self.vault.read_note.assert_called_once_with("note.md")

    def test_write(self):
        self.vault.write_note.return_value = {"ok": True}
        r = self.tool.write("note.md", "content", tags=["a"])
        self.assertEqual(r, {"ok": True})
        self.vault.write_note.assert_called_once_with("note.md", "content", tags=["a"])

    def test_write_default_tags(self):
        self.vault.write_note.return_value = {"ok": True}
        self.tool.write("n.md", "c")
        self.vault.write_note.assert_called_once_with("n.md", "c", tags=None)

    def test_delete(self):
        self.vault.delete_note.return_value = {"deleted": True}
        r = self.tool.delete("n.md")
        self.assertEqual(r, {"deleted": True})
        self.vault.delete_note.assert_called_once_with("n.md")

    def test_list(self):
        self.vault.list_notes.return_value = {"notes": []}
        r = self.tool.list("sub")
        self.assertEqual(r, {"notes": []})
        self.vault.list_notes.assert_called_once_with(subdir="sub")

    def test_list_default(self):
        self.vault.list_notes.return_value = {"notes": []}
        self.tool.list()
        self.vault.list_notes.assert_called_once_with(subdir="")

    def test_search(self):
        self.vault.search_notes.return_value = {"results": ["n.md"]}
        r = self.tool.search("query", limit=5)
        self.assertEqual(r, {"results": ["n.md"]})
        self.vault.search_notes.assert_called_once_with("query", limit=5)

    def test_search_default_limit(self):
        self.vault.search_notes.return_value = {"results": []}
        self.tool.search("q")
        self.vault.search_notes.assert_called_once_with("q", limit=20)

    def test_status(self):
        self.vault.get_status.return_value = {"ok": True}
        r = self.tool.status()
        self.assertEqual(r, {"ok": True})
        self.vault.get_status.assert_called_once()


if __name__ == "__main__":
    unittest.main()
