"""
Tests for the sandboxed ORBIT <-> Obsidian vault connector.

Security focus: path-traversal escapes and non-Markdown writes must be rejected;
markdown round-trip + frontmatter + list/search must work.
"""

import tempfile
import unittest

import orbit.orbit.core.obsidian_bp as ob
from orbit.orbit.core.obsidian_vault import ObsidianVault


class TestObsidianVault(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.vault = ObsidianVault(vault_root=self._tmp)

    def test_write_read_roundtrip(self):
        r = self.vault.write_note("notes/hello.md", "Hi there", tags=["orbit", "test"])
        self.assertIn("ok", r)
        got = self.vault.read_note("notes/hello.md")
        self.assertEqual(got["body"].strip(), "Hi there")
        self.assertEqual(got["frontmatter"].get("type"), "orbit-note")

    def test_non_markdown_write_rejected(self):
        r = self.vault.write_note("evil.py", "import os")
        self.assertIn("error", r)

    def test_path_traversal_rejected(self):
        r = self.vault.write_note("../../escape.md", "pwn")
        self.assertIn("error", r)
        # URL-encoded "..%2f" is NOT decoded by Path(), so it stays a literal
        # in-vault filename -- the realpath check confines it, no escape occurs.
        contained = self.vault.write_note("..%2f..%2fescape.md", "pwn")
        self.assertIn("ok", contained)

    def test_list_and_search(self):
        self.vault.write_note("a.md", "alpha beta")
        self.vault.write_note("sub/b.md", "gamma delta")
        lst = self.vault.list_notes()
        self.assertEqual(lst["count"], 2)
        hits = self.vault.search_notes("gamma")
        self.assertEqual(hits["count"], 1)
        self.assertIn("sub/b.md", hits["hits"][0]["rel"])

    def test_delete(self):
        self.vault.write_note("d.md", "bye")
        self.assertIn("ok", self.vault.delete_note("d.md"))
        self.assertIn("error", self.vault.read_note("d.md"))

    def test_read_missing_is_error(self):
        self.assertIn("error", self.vault.read_note("nope.md"))


class TestObsidianAPI(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._vault = ObsidianVault(vault_root=self._tmp)
        self._orig = ob.get_obsidian_vault
        ob.get_obsidian_vault = lambda: self._vault
        from orbit.orbit.server import create_app

        self.app = create_app()
        self.client = self.app.test_client()

    def tearDown(self):
        ob.get_obsidian_vault = self._orig

    def test_status(self):
        r = self.client.get("/api/obsidian/status")
        self.assertEqual(r.status_code, 200)
        self.assertIn("note_count", r.get_json())

    def test_write_read_via_api(self):
        r = self.client.post(
            "/api/obsidian/note",
            json={"path": "api.md", "content": "via api", "tags": ["x"]},
        )
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        r = self.client.get("/api/obsidian/note?path=api.md")
        self.assertEqual(r.status_code, 200)
        self.assertIn("via api", r.get_json()["content"])

    def test_write_requires_path_and_content(self):
        r = self.client.post("/api/obsidian/note", json={"path": "x.md"})
        self.assertEqual(r.status_code, 400)

    def test_search_via_api(self):
        self._vault.write_note("s.md", "findme keyword")
        r = self.client.get("/api/obsidian/search?q=findme")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["count"], 1)


if __name__ == "__main__":
    unittest.main()
