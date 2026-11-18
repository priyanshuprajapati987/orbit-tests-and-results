"""Unit tests for orbit/orbit/core/relationship_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.relationship_bp import relationship_bp


class RelBpBase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(relationship_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(relationship_bp.name, "relationship_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/relationships", "/api/relationships/<contact_id>",
                  "/api/relationships/add",
                  "/api/relationships/update/<contact_id>",
                  "/api/relationships/delete/<contact_id>",
                  "/api/relationships/interact/<contact_id>",
                  "/api/relationships/reminders",
                  "/api/relationships/birthdays",
                  "/api/relationships/search"]:
            self.assertIn(p, rules)


class TestListContacts(RelBpBase):
    def test_list_default(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker") as gt:
            gt.return_value.list_contacts.return_value = [{"id": "c1"}]
            r = self.client.get("/api/relationships")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["contacts"], [{"id": "c1"}])
        self.assertEqual(body["total"], 1)
        gt.return_value.list_contacts.assert_called_once_with(category=None)

    def test_list_with_category(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker") as gt:
            gt.return_value.list_contacts.return_value = []
            r = self.client.get("/api/relationships?category=family")
        gt.return_value.list_contacts.assert_called_once_with(category="family")

    def test_list_exception_500(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker",
                   side_effect=RuntimeError("x")):
            r = self.client.get("/api/relationships")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "internal error")


class TestGetContact(RelBpBase):
    def test_found(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker") as gt:
            gt.return_value.get_contact.return_value = {"id": "c1", "name": "A"}
            r = self.client.get("/api/relationships/c1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["name"], "A")

    def test_not_found_404(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker") as gt:
            gt.return_value.get_contact.return_value = None
            r = self.client.get("/api/relationships/nope")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"], "contact not found")

    def test_exception_500(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker",
                   side_effect=RuntimeError("x")):
            r = self.client.get("/api/relationships/c1")
        self.assertEqual(r.status_code, 500)


class TestAddContact(RelBpBase):
    def test_add_defaults(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker") as gt:
            gt.return_value.add_contact.return_value = {"id": "c1", "name": "A"}
            r = self.client.post("/api/relationships/add", json={"name": "A"})
        self.assertEqual(r.status_code, 201)
        gt.return_value.add_contact.assert_called_once_with(
            name="A", relationship="friend", importance=5,
            notes="", birthday="", phone="", email="")

    def test_add_all_fields(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker") as gt:
            gt.return_value.add_contact.return_value = {"id": "c1"}
            r = self.client.post("/api/relationships/add", json={
                "name": "A", "relationship": "family", "importance": 8,
                "notes": "N", "birthday": "1990-01-01",
                "phone": "123", "email": "a@b.c"})
        self.assertEqual(r.status_code, 201)
        gt.return_value.add_contact.assert_called_once_with(
            name="A", relationship="family", importance=8,
            notes="N", birthday="1990-01-01", phone="123", email="a@b.c")

    def test_importance_clamped_high(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker") as gt:
            gt.return_value.add_contact.return_value = {"id": "c1"}
            r = self.client.post("/api/relationships/add",
                                 json={"name": "A", "importance": 99})
        gt.return_value.add_contact.assert_called_once_with(
            name="A", relationship="friend", importance=10,
            notes="", birthday="", phone="", email="")

    def test_importance_clamped_low(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker") as gt:
            gt.return_value.add_contact.return_value = {"id": "c1"}
            r = self.client.post("/api/relationships/add",
                                 json={"name": "A", "importance": -5})
        kwargs = gt.return_value.add_contact.call_args.kwargs
        self.assertEqual(kwargs["importance"], 1)

    def test_importance_string_coerced(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker") as gt:
            gt.return_value.add_contact.return_value = {"id": "c1"}
            r = self.client.post("/api/relationships/add",
                                 json={"name": "A", "importance": "7"})
        kwargs = gt.return_value.add_contact.call_args.kwargs
        self.assertEqual(kwargs["importance"], 7)

    def test_importance_bad_400(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker") as gt:
            r = self.client.post("/api/relationships/add",
                                 json={"name": "A", "importance": "abc"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("importance must be an integer", r.get_json()["error"])
        gt.return_value.add_contact.assert_not_called()

    def test_missing_name_400(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker") as gt:
            r = self.client.post("/api/relationships/add", json={"notes": "x"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("name required", r.get_json()["error"])

    def test_no_body_400(self):
        r = self.client.post("/api/relationships/add")
        self.assertEqual(r.status_code, 400)

    def test_exception_500(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker",
                   side_effect=RuntimeError("x")):
            r = self.client.post("/api/relationships/add", json={"name": "A"})
        self.assertEqual(r.status_code, 500)


class TestUpdateContact(RelBpBase):
    def test_update_fields(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker") as gt:
            gt.return_value.update_contact.return_value = {"id": "c1", "name": "New"}
            r = self.client.post("/api/relationships/update/c1",
                                 json={"name": "New"})
        self.assertEqual(r.status_code, 200)
        gt.return_value.update_contact.assert_called_once_with("c1", name="New")

    def test_update_importance_clamped(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker") as gt:
            gt.return_value.update_contact.return_value = {"id": "c1"}
            r = self.client.post("/api/relationships/update/c1",
                                 json={"importance": 99})
        gt.return_value.update_contact.assert_called_once_with("c1", importance=10)

    def test_update_importance_bad_400(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker") as gt:
            r = self.client.post("/api/relationships/update/c1",
                                 json={"importance": "abc"})
        self.assertEqual(r.status_code, 400)
        gt.return_value.update_contact.assert_not_called()

    def test_update_not_found_404(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker") as gt:
            gt.return_value.update_contact.return_value = None
            r = self.client.post("/api/relationships/update/nope",
                                 json={"name": "x"})
        self.assertEqual(r.status_code, 404)

    def test_update_no_body(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker") as gt:
            gt.return_value.update_contact.return_value = {"id": "c1"}
            r = self.client.post("/api/relationships/update/c1")
        self.assertEqual(r.status_code, 200)
        gt.return_value.update_contact.assert_called_once_with("c1")

    def test_exception_500(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker",
                   side_effect=RuntimeError("x")):
            r = self.client.post("/api/relationships/update/c1", json={"a": 1})
        self.assertEqual(r.status_code, 500)


class TestDeleteContact(RelBpBase):
    def test_delete_ok(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker") as gt:
            gt.return_value.delete_contact.return_value = True
            r = self.client.post("/api/relationships/delete/c1")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "deleted")
        self.assertEqual(body["id"], "c1")

    def test_delete_not_found_404(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker") as gt:
            gt.return_value.delete_contact.return_value = False
            r = self.client.post("/api/relationships/delete/nope")
        self.assertEqual(r.status_code, 404)

    def test_exception_500(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker",
                   side_effect=RuntimeError("x")):
            r = self.client.post("/api/relationships/delete/c1")
        self.assertEqual(r.status_code, 500)


class TestLogInteraction(RelBpBase):
    def test_log_success(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker") as gt:
            gt.return_value.log_interaction.return_value = {"id": "i1"}
            r = self.client.post("/api/relationships/interact/c1",
                                 json={"type": "call", "notes": "n"})
        self.assertEqual(r.status_code, 201)
        gt.return_value.log_interaction.assert_called_once_with(
            contact_id="c1", interaction_type="call", notes="n")

    def test_log_default_notes(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker") as gt:
            gt.return_value.log_interaction.return_value = {"id": "i1"}
            r = self.client.post("/api/relationships/interact/c1",
                                 json={"type": "meet"})
        gt.return_value.log_interaction.assert_called_once_with(
            contact_id="c1", interaction_type="meet", notes="")

    def test_missing_type_400(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker") as gt:
            r = self.client.post("/api/relationships/interact/c1", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("interaction type required", r.get_json()["error"])
        gt.return_value.log_interaction.assert_not_called()

    def test_no_body_400(self):
        r = self.client.post("/api/relationships/interact/c1")
        self.assertEqual(r.status_code, 400)

    def test_contact_not_found_404(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker") as gt:
            gt.return_value.log_interaction.return_value = None
            r = self.client.post("/api/relationships/interact/nope",
                                 json={"type": "call"})
        self.assertEqual(r.status_code, 404)

    def test_exception_500(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker",
                   side_effect=RuntimeError("x")):
            r = self.client.post("/api/relationships/interact/c1",
                                 json={"type": "call"})
        self.assertEqual(r.status_code, 500)


class TestRemindersBirthdaysSearch(RelBpBase):
    def test_reminders(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker") as gt:
            gt.return_value.get_reminders.return_value = ["call mom"]
            r = self.client.get("/api/relationships/reminders")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["reminders"], ["call mom"])

    def test_reminders_exception_500(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker",
                   side_effect=RuntimeError("x")):
            r = self.client.get("/api/relationships/reminders")
        self.assertEqual(r.status_code, 500)

    def test_birthdays(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker") as gt:
            gt.return_value.get_birthday_reminders.return_value = ["bob"]
            r = self.client.get("/api/relationships/birthdays")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["birthdays"], ["bob"])

    def test_birthdays_exception_500(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker",
                   side_effect=RuntimeError("x")):
            r = self.client.get("/api/relationships/birthdays")
        self.assertEqual(r.status_code, 500)

    def test_search_success(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker") as gt:
            gt.return_value.search_contacts.return_value = [{"id": "c1"}]
            r = self.client.get("/api/relationships/search?q=al")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["results"], [{"id": "c1"}])
        self.assertEqual(body["total"], 1)
        gt.return_value.search_contacts.assert_called_once_with("al")

    def test_search_missing_q_400(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker") as gt:
            r = self.client.get("/api/relationships/search")
        self.assertEqual(r.status_code, 400)
        self.assertIn("q", r.get_json()["error"])
        gt.return_value.search_contacts.assert_not_called()

    def test_search_blank_q_400(self):
        r = self.client.get("/api/relationships/search?q=")
        self.assertEqual(r.status_code, 400)

    def test_search_exception_500(self):
        with patch("orbit.core.relationship_bp.get_relationship_tracker",
                   side_effect=RuntimeError("x")):
            r = self.client.get("/api/relationships/search?q=x")
        self.assertEqual(r.status_code, 500)


if __name__ == "__main__":
    unittest.main()
