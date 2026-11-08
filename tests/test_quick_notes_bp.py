"""Unit tests for orbit/orbit/core/quick_notes_bp.py."""

import os
import sys
import types
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.quick_notes_bp import quick_notes_bp


def make_note(**kw):
    return types.SimpleNamespace(**kw)


class TestQuickNotesBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(quick_notes_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(quick_notes_bp.name, "quick_notes_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/notes", "/api/notes/<note_id>", "/api/notes/search", "/api/notes/stats"]:
            self.assertIn(p, rules)

    def test_list_notes(self):
        with patch("orbit.core.quick_notes_bp.get_notes") as gn:
            gn.return_value.list_all.return_value = [make_note(id="n1")]
            r = self.client.get("/api/notes?limit=5")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["notes"], [{"id": "n1"}])
        gn.return_value.list_all.assert_called_once_with(5)

    def test_list_notes_default(self):
        with patch("orbit.core.quick_notes_bp.get_notes") as gn:
            gn.return_value.list_all.return_value = []
            r = self.client.get("/api/notes")
        gn.return_value.list_all.assert_called_once_with(50)

    def test_add_note_missing_content_400(self):
        r = self.client.post("/api/notes", json={"content": ""})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_add_note_bad_tags_400(self):
        r = self.client.post("/api/notes", json={"content": "hi", "tags": "notalist"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_add_note_success(self):
        with patch("orbit.core.quick_notes_bp.get_notes") as gn:
            gn.return_value.add.return_value = make_note(id="n2", content="hi")
            r = self.client.post("/api/notes", json={"content": "hi", "tags": ["a"]})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()["note"]["id"], "n2")
        gn.return_value.add.assert_called_once_with("hi", ["a"])

    def test_add_note_no_body(self):
        r = self.client.post("/api/notes")
        self.assertEqual(r.status_code, 400)

    def test_get_note_found(self):
        with patch("orbit.core.quick_notes_bp.get_notes") as gn:
            gn.return_value.get.return_value = make_note(id="n1")
            r = self.client.get("/api/notes/n1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["note"]["id"], "n1")
        gn.return_value.get.assert_called_once_with("n1")

    def test_get_note_not_found_404(self):
        with patch("orbit.core.quick_notes_bp.get_notes") as gn:
            gn.return_value.get.return_value = None
            r = self.client.get("/api/notes/n1")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_update_note(self):
        with patch("orbit.core.quick_notes_bp.get_notes") as gn:
            gn.return_value.update.return_value = make_note(id="n1", content="new")
            r = self.client.put("/api/notes/n1", json={"content": "new", "tags": ["b"]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["note"]["content"], "new")
        gn.return_value.update.assert_called_once_with("n1", content="new", tags=["b"])

    def test_update_note_not_found_404(self):
        with patch("orbit.core.quick_notes_bp.get_notes") as gn:
            gn.return_value.update.return_value = None
            r = self.client.put("/api/notes/n1", json={"content": "new"})
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_update_bad_content_400(self):
        r = self.client.put("/api/notes/n1", json={"content": 123})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_update_bad_tags_400(self):
        r = self.client.put("/api/notes/n1", json={"tags": "notalist"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_update_no_body(self):
        with patch("orbit.core.quick_notes_bp.get_notes") as gn:
            gn.return_value.update.return_value = make_note(id="n1")
            r = self.client.put("/api/notes/n1")
        gn.return_value.update.assert_called_once_with("n1", content=None, tags=None)

    def test_delete_note(self):
        with patch("orbit.core.quick_notes_bp.get_notes") as gn:
            gn.return_value.delete.return_value = True
            r = self.client.delete("/api/notes/n1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "deleted")
        gn.return_value.delete.assert_called_once_with("n1")

    def test_delete_note_not_found_404(self):
        with patch("orbit.core.quick_notes_bp.get_notes") as gn:
            gn.return_value.delete.return_value = False
            r = self.client.delete("/api/notes/n1")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_search_missing_q_400(self):
        r = self.client.get("/api/notes/search")
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_search_success(self):
        with patch("orbit.core.quick_notes_bp.get_notes") as gn:
            gn.return_value.search.return_value = [make_note(id="n1")]
            r = self.client.get("/api/notes/search?q=hi")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["count"], 1)
        gn.return_value.search.assert_called_once_with("hi")

    def test_stats(self):
        with patch("orbit.core.quick_notes_bp.get_notes") as gn:
            gn.return_value.get_stats.return_value = {"total": 5}
            r = self.client.get("/api/notes/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)


if __name__ == "__main__":
    unittest.main()
