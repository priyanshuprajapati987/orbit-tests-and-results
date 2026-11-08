"""Unit tests for orbit/orbit/core/email_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
import orbit.core.email_bp as email_bp_mod
from orbit.core.email_bp import email_bp


class TestEmailBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(email_bp)
        self.client = self.app.test_client()
        self.tool = MagicMock()
        self.patcher = patch.object(email_bp_mod, "_tool", self.tool)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_blueprint_name(self):
        self.assertEqual(email_bp.name, "email_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/email/config", "/api/email/send", "/api/email/send-bulk"]:
            self.assertIn(p, rules)

    def test_config(self):
        self.tool.check_config.return_value = {"configured": True}
        r = self.client.get("/api/email/config")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["configured"])

    def test_send_missing_fields_400(self):
        r = self.client.post("/api/email/send", json={"to": "a@b.com"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_send_success(self):
        self.tool.send.return_value = {"success": True}
        r = self.client.post("/api/email/send", json={
            "to": "a@b.com", "subject": "hi", "body": "body",
            "html": True, "cc": "c@d.com", "bcc": "e@f.com", "attachments": ["x.pdf"]
        })
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["success"])
        self.tool.send.assert_called_once_with("a@b.com", "hi", "body", True, "c@d.com", "e@f.com", ["x.pdf"])

    def test_send_defaults(self):
        self.tool.send.return_value = {"success": True}
        r = self.client.post("/api/email/send", json={"to": "a@b.com", "subject": "hi", "body": "body"})
        self.tool.send.assert_called_once_with("a@b.com", "hi", "body", False, "", "", [])

    def test_send_no_body(self):
        r = self.client.post("/api/email/send")
        self.assertEqual(r.status_code, 400)

    def test_send_exception_500(self):
        self.tool.send.side_effect = RuntimeError("smtp down")
        r = self.client.post("/api/email/send", json={"to": "a@b.com", "subject": "hi", "body": "body"})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "Email send failed")

    def test_send_bulk_missing_400(self):
        r = self.client.post("/api/email/send-bulk", json={"recipients": ["a@b.com"]})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_send_bulk_success(self):
        self.tool.send_bulk.return_value = {"sent": 2}
        r = self.client.post("/api/email/send-bulk", json={"recipients": ["a@b.com", "c@d.com"], "subject": "hi", "body": "body", "html": True})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["sent"], 2)
        self.tool.send_bulk.assert_called_once_with(["a@b.com", "c@d.com"], "hi", "body", True)

    def test_send_bulk_no_body(self):
        r = self.client.post("/api/email/send-bulk")
        self.assertEqual(r.status_code, 400)

    def test_send_bulk_exception_500(self):
        self.tool.send_bulk.side_effect = RuntimeError("smtp down")
        r = self.client.post("/api/email/send-bulk", json={"recipients": ["a@b.com"], "subject": "hi", "body": "body"})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "Bulk email failed")


if __name__ == "__main__":
    unittest.main()
