"""Unit tests for orbit/orbit/core/conversation_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.conversation_bp import conversation_bp


class TestConversationBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(conversation_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(conversation_bp.name, "conversation")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/conversations", "/api/conversations/new", "/api/conversations/<conv_id>",
                  "/api/conversations/<conv_id>/rename", "/api/conversations/<conv_id>/send",
                  "/api/conversations/search", "/api/conversations/<conv_id>/export"]:
            self.assertIn(p, rules)

    def test_list_conversations(self):
        with patch("orbit.core.conversation_bp._request_user_id", return_value="u1"), \
             patch("orbit.core.conversation_bp.get_conversation_manager") as gm:
            gm.return_value.list_all.return_value = [{"id": "c1"}]
            r = self.client.get("/api/conversations")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["conversations"], [{"id": "c1"}])
        gm.return_value.list_all.assert_called_once_with(user_id="u1")

    def test_new_conversation(self):
        with patch("orbit.core.conversation_bp._request_user_id", return_value="u1"), \
             patch("orbit.core.conversation_bp.get_conversation_manager") as gm:
            gm.return_value.create.return_value = {"id": "c2"}
            r = self.client.post("/api/conversations/new", json={"title": "T", "message": "hi"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertEqual(r.get_json()["conversation"]["id"], "c2")
        gm.return_value.create.assert_called_once_with(title="T", first_message="hi", user_id="u1")

    def test_new_conversation_defaults(self):
        with patch("orbit.core.conversation_bp._request_user_id", return_value="u1"), \
             patch("orbit.core.conversation_bp.get_conversation_manager") as gm:
            gm.return_value.create.return_value = {"id": "c3"}
            r = self.client.post("/api/conversations/new", json={})
        gm.return_value.create.assert_called_once_with(title="", first_message="", user_id="u1")

    def test_new_conversation_no_body(self):
        with patch("orbit.core.conversation_bp._request_user_id", return_value="u1"), \
             patch("orbit.core.conversation_bp.get_conversation_manager") as gm:
            gm.return_value.create.return_value = {"id": "c4"}
            r = self.client.post("/api/conversations/new")
        gm.return_value.create.assert_called_once_with(title="", first_message="", user_id="u1")

    def test_get_conversation_found(self):
        with patch("orbit.core.conversation_bp._request_user_id", return_value="u1"), \
             patch("orbit.core.conversation_bp.get_conversation_manager") as gm:
            gm.return_value.get.return_value = {"id": "c1"}
            r = self.client.get("/api/conversations/c1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], "c1")
        gm.return_value.get.assert_called_once_with("c1", user_id="u1")

    def test_get_conversation_not_found_404(self):
        with patch("orbit.core.conversation_bp._request_user_id", return_value="u1"), \
             patch("orbit.core.conversation_bp.get_conversation_manager") as gm:
            gm.return_value.get.return_value = None
            r = self.client.get("/api/conversations/c1")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_delete_conversation_success(self):
        with patch("orbit.core.conversation_bp._request_user_id", return_value="u1"), \
             patch("orbit.core.conversation_bp.get_conversation_manager") as gm:
            gm.return_value.delete.return_value = True
            r = self.client.delete("/api/conversations/c1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        gm.return_value.delete.assert_called_once_with("c1", user_id="u1")

    def test_delete_conversation_not_found_404(self):
        with patch("orbit.core.conversation_bp._request_user_id", return_value="u1"), \
             patch("orbit.core.conversation_bp.get_conversation_manager") as gm:
            gm.return_value.delete.return_value = False
            r = self.client.delete("/api/conversations/c1")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_rename_missing_title_400(self):
        r = self.client.post("/api/conversations/c1/rename", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_rename_success(self):
        with patch("orbit.core.conversation_bp._request_user_id", return_value="u1"), \
             patch("orbit.core.conversation_bp.get_conversation_manager") as gm:
            gm.return_value.rename.return_value = True
            r = self.client.post("/api/conversations/c1/rename", json={"title": "new"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        gm.return_value.rename.assert_called_once_with("c1", "new", user_id="u1")

    def test_rename_not_found_404(self):
        with patch("orbit.core.conversation_bp._request_user_id", return_value="u1"), \
             patch("orbit.core.conversation_bp.get_conversation_manager") as gm:
            gm.return_value.rename.return_value = False
            r = self.client.post("/api/conversations/c1/rename", json={"title": "new"})
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_rename_no_body(self):
        r = self.client.post("/api/conversations/c1/rename")
        self.assertEqual(r.status_code, 400)

    def test_send_missing_content_400(self):
        r = self.client.post("/api/conversations/c1/send", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_send_success(self):
        with patch("orbit.core.conversation_bp._request_user_id", return_value="u1"), \
             patch("orbit.core.conversation_bp.get_conversation_manager") as gm:
            gm.return_value.send.return_value = {"id": "m1"}
            r = self.client.post("/api/conversations/c1/send", json={"role": "assistant", "content": "hi", "agent": "TAS"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertEqual(r.get_json()["message"]["id"], "m1")
        gm.return_value.send.assert_called_once_with("c1", "assistant", "hi", "TAS", user_id="u1")

    def test_send_defaults(self):
        with patch("orbit.core.conversation_bp._request_user_id", return_value="u1"), \
             patch("orbit.core.conversation_bp.get_conversation_manager") as gm:
            gm.return_value.send.return_value = {"id": "m2"}
            r = self.client.post("/api/conversations/c1/send", json={"content": "hi"})
        gm.return_value.send.assert_called_once_with("c1", "user", "hi", "", user_id="u1")

    def test_send_not_found_404(self):
        with patch("orbit.core.conversation_bp._request_user_id", return_value="u1"), \
             patch("orbit.core.conversation_bp.get_conversation_manager") as gm:
            gm.return_value.send.return_value = None
            r = self.client.post("/api/conversations/c1/send", json={"content": "hi"})
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_send_no_body(self):
        r = self.client.post("/api/conversations/c1/send")
        self.assertEqual(r.status_code, 400)

    def test_search_missing_q_400(self):
        r = self.client.get("/api/conversations/search")
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_search_success(self):
        with patch("orbit.core.conversation_bp._request_user_id", return_value="u1"), \
             patch("orbit.core.conversation_bp.get_conversation_manager") as gm:
            gm.return_value.search.return_value = [{"id": "c1"}]
            r = self.client.get("/api/conversations/search?q=hi")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["results"], [{"id": "c1"}])
        self.assertEqual(body["count"], 1)
        gm.return_value.search.assert_called_once_with("hi", user_id="u1")

    def test_export_found(self):
        with patch("orbit.core.conversation_bp._request_user_id", return_value="u1"), \
             patch("orbit.core.conversation_bp.get_conversation_manager") as gm:
            gm.return_value.export_markdown.return_value = "# md"
            r = self.client.get("/api/conversations/c1/export")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["markdown"], "# md")
        gm.return_value.export_markdown.assert_called_once_with("c1", user_id="u1")

    def test_export_not_found_404(self):
        with patch("orbit.core.conversation_bp._request_user_id", return_value="u1"), \
             patch("orbit.core.conversation_bp.get_conversation_manager") as gm:
            gm.return_value.export_markdown.return_value = None
            r = self.client.get("/api/conversations/c1/export")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())


if __name__ == "__main__":
    unittest.main()
