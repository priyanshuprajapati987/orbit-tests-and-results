"""Unit tests for orbit/orbit/core/obsidian_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.obsidian_bp import obsidian_bp


class TestObsidianBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(obsidian_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(obsidian_bp.name, "obsidian")

    def test_url_prefix(self):
        self.assertEqual(obsidian_bp.url_prefix, "/api/obsidian")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/obsidian/status", "/api/obsidian/notes", "/api/obsidian/note",
                  "/api/obsidian/search"]:
            self.assertIn(p, rules)

    def test_status(self):
        with patch("orbit.core.obsidian_bp.get_obsidian_vault") as gv:
            gv.return_value.get_status.return_value = {"ok": True}
            r = self.client.get("/api/obsidian/status")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])

    def test_list_notes(self):
        with patch("orbit.core.obsidian_bp.get_obsidian_vault") as gv:
            gv.return_value.list_notes.return_value = {"notes": ["a.md"]}
            r = self.client.get("/api/obsidian/notes?subdir=sub")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["notes"], ["a.md"])
        gv.return_value.list_notes.assert_called_once_with(subdir="sub")

    def test_list_notes_default(self):
        with patch("orbit.core.obsidian_bp.get_obsidian_vault") as gv:
            gv.return_value.list_notes.return_value = {"notes": []}
            r = self.client.get("/api/obsidian/notes")
        gv.return_value.list_notes.assert_called_once_with(subdir="")

    def test_read_note_missing_400(self):
        r = self.client.get("/api/obsidian/note")
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_read_note_by_path(self):
        with patch("orbit.core.obsidian_bp.get_obsidian_vault") as gv:
            gv.return_value.read_note.return_value = {"content": "hi"}
            r = self.client.get("/api/obsidian/note?path=note.md")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["content"], "hi")
        gv.return_value.read_note.assert_called_once_with("note.md")

    def test_read_note_by_rel(self):
        with patch("orbit.core.obsidian_bp.get_obsidian_vault") as gv:
            gv.return_value.read_note.return_value = {"content": "hi"}
            r = self.client.get("/api/obsidian/note?rel=note.md")
        gv.return_value.read_note.assert_called_once_with("note.md")

    def test_write_note_missing_400(self):
        r = self.client.post("/api/obsidian/note", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_write_note_missing_content_400(self):
        r = self.client.post("/api/obsidian/note", json={"path": "note.md"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_write_note_success(self):
        with patch("orbit.core.obsidian_bp.get_obsidian_vault") as gv:
            gv.return_value.write_note.return_value = {"ok": True}
            r = self.client.post("/api/obsidian/note", json={"path": "note.md", "content": "hi", "tags": ["a"]})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        gv.return_value.write_note.assert_called_once_with("note.md", "hi", tags=["a"])

    def test_write_note_error_403(self):
        with patch("orbit.core.obsidian_bp.get_obsidian_vault") as gv:
            gv.return_value.write_note.return_value = {"error": "bad"}
            r = self.client.post("/api/obsidian/note", json={"path": "note.md", "content": "hi"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("error", r.get_json())

    def test_write_note_no_body(self):
        r = self.client.post("/api/obsidian/note")
        self.assertEqual(r.status_code, 400)

    def test_delete_note_missing_400(self):
        r = self.client.delete("/api/obsidian/note")
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_delete_note_success(self):
        with patch("orbit.core.obsidian_bp.get_obsidian_vault") as gv:
            gv.return_value.delete_note.return_value = {"deleted": True}
            r = self.client.delete("/api/obsidian/note", json={"path": "note.md"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["deleted"])
        gv.return_value.delete_note.assert_called_once_with("note.md")

    def test_delete_note_by_query(self):
        with patch("orbit.core.obsidian_bp.get_obsidian_vault") as gv:
            gv.return_value.delete_note.return_value = {"deleted": True}
            r = self.client.delete("/api/obsidian/note?path=note.md")
        gv.return_value.delete_note.assert_called_once_with("note.md")

    def test_delete_note_error_403(self):
        with patch("orbit.core.obsidian_bp.get_obsidian_vault") as gv:
            gv.return_value.delete_note.return_value = {"error": "bad"}
            r = self.client.delete("/api/obsidian/note", json={"path": "note.md"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("error", r.get_json())

    def test_search_missing_query_400(self):
        r = self.client.get("/api/obsidian/search")
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_search_success(self):
        with patch("orbit.core.obsidian_bp.get_obsidian_vault") as gv:
            gv.return_value.search_notes.return_value = {"results": ["n.md"]}
            r = self.client.get("/api/obsidian/search?q=hi&limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["results"], ["n.md"])
        gv.return_value.search_notes.assert_called_once_with("hi", limit=5)

    def test_search_bad_limit(self):
        with patch("orbit.core.obsidian_bp.get_obsidian_vault") as gv:
            gv.return_value.search_notes.return_value = {"results": []}
            r = self.client.get("/api/obsidian/search?q=hi&limit=abc")
        gv.return_value.search_notes.assert_called_once_with("hi", limit=20)


if __name__ == "__main__":
    unittest.main()
