"""Deep tests for orbit/orbit/tools/email_tool.py (Loop 13/4).

Covers every statement of ``EmailTool``:
  * ``__init__`` — env parsing (SMTP_SERVER/PORT, EMAIL_ADDRESS), invalid
    port fallback to 587, empty port fallback.
  * ``_get_connection`` — missing creds → None; SMTP connect/starttls/login
    success; failure → None + log.
  * ``send`` — not configured, missing recipient, header sanitization
    (CR/LF stripping), cc/bcc, html/plain, attachments (blocked paths
    skipped, policy-engine block, missing file skipped, successful attach),
    recipients list, server sendmail success, SMTP failure, finally quit,
    outer exception.
  * ``send_bulk``.
  * ``check_config`` — configured/unconfigured, email masking.
"""

import os
import smtplib
import unittest
from pathlib import Path
from unittest import mock

from orbit.orbit.tools import email_tool as et


class InitTests(unittest.TestCase):
    def test_defaults(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            t = et.EmailTool()
        self.assertEqual(t.smtp_server, "smtp.gmail.com")
        self.assertEqual(t.smtp_port, 587)
        self.assertEqual(t.email_address, "")
        self.assertEqual(t._password_env, "EMAIL_PASSWORD")
        self.assertEqual(t.name, "email")

    def test_custom_env(self):
        with mock.patch.dict(os.environ, {
                "SMTP_SERVER": "smtp.example.com",
                "SMTP_PORT": "465",
                "EMAIL_ADDRESS": "me@example.com"}):
            t = et.EmailTool()
        self.assertEqual(t.smtp_server, "smtp.example.com")
        self.assertEqual(t.smtp_port, 465)
        self.assertEqual(t.email_address, "me@example.com")

    def test_invalid_port_falls_back(self):
        with mock.patch.dict(os.environ, {"SMTP_PORT": "abc"}):
            t = et.EmailTool()
        self.assertEqual(t.smtp_port, 587)

    def test_empty_port_falls_back_to_587(self):
        with mock.patch.dict(os.environ, {"SMTP_PORT": ""}):
            t = et.EmailTool()
        self.assertEqual(t.smtp_port, 587)

    def test_none_port_typeerror_fallback(self):
        # os.getenv returns str normally; simulate TypeError via patch
        with mock.patch.dict(os.environ, {"SMTP_PORT": "x"}), \
                mock.patch("builtins.int", side_effect=TypeError("x")):
            t = et.EmailTool()
        self.assertEqual(t.smtp_port, 587)


class GetConnectionTests(unittest.TestCase):
    def test_missing_creds_returns_none(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            t = et.EmailTool()
        self.assertIsNone(t._get_connection())

    def test_missing_password_returns_none(self):
        with mock.patch.dict(os.environ, {"EMAIL_ADDRESS": "me@x.com"}, clear=True):
            t = et.EmailTool()
        self.assertIsNone(t._get_connection())

    def test_success(self):
        server = mock.MagicMock()
        with mock.patch.dict(os.environ, {"EMAIL_ADDRESS": "me@x.com",
                                         "EMAIL_PASSWORD": "pw"}), \
                mock.patch("smtplib.SMTP", return_value=server) as smtp:
            t = et.EmailTool()
            conn = t._get_connection()
        self.assertIs(conn, server)
        smtp.assert_called_once_with("smtp.gmail.com", 587, timeout=15)
        server.starttls.assert_called_once()
        server.login.assert_called_once_with("me@x.com", "pw")

    def test_connection_failure_returns_none(self):
        with mock.patch.dict(os.environ, {"EMAIL_ADDRESS": "me@x.com",
                                         "EMAIL_PASSWORD": "pw"}), \
                mock.patch("smtplib.SMTP", side_effect=Exception("conn fail")), \
                mock.patch.object(et, "logger") as lg:
            t = et.EmailTool()
            self.assertIsNone(t._get_connection())
        lg.error.assert_called_once()


class SendTests(unittest.TestCase):
    def _tool(self, email="me@x.com", password="pw"):
        with mock.patch.dict(os.environ, {"EMAIL_ADDRESS": email,
                                         "EMAIL_PASSWORD": password}):
            return et.EmailTool()

    def test_not_configured(self):
        t = self._tool(email="")
        self.assertEqual(t.send("to@x.com", "s", "b"),
                         {"error": "Email not configured. Set EMAIL_ADDRESS and EMAIL_PASSWORD env vars."})

    def test_missing_recipient(self):
        t = self._tool()
        self.assertEqual(t.send("", "s", "b"),
                         {"error": "Recipient 'to' address is required"})

    def test_connection_failure(self):
        t = self._tool()
        with mock.patch.object(t, "_get_connection", return_value=None):
            self.assertEqual(t.send("to@x.com", "s", "b"),
                             {"error": "Failed to connect to SMTP server"})

    def test_sendmail_success_plain(self):
        t = self._tool()
        server = mock.MagicMock()
        with mock.patch.object(t, "_get_connection", return_value=server):
            r = t.send("to@x.com", "subj", "body", html=False)
        self.assertEqual(r, {"success": True, "to": "to@x.com", "subject": "subj"})
        server.sendmail.assert_called_once()
        args = server.sendmail.call_args.args
        self.assertEqual(args[0], "me@x.com")
        self.assertEqual(args[1], ["to@x.com"])
        self.assertIn("subj", args[2])
        server.quit.assert_called_once()

    def test_sendmail_success_html_cc_bcc(self):
        t = self._tool()
        server = mock.MagicMock()
        with mock.patch.object(t, "_get_connection", return_value=server):
            r = t.send("to@x.com", "subj", "<b>hi</b>", html=True,
                       cc="cc@x.com", bcc="bcc@x.com")
        self.assertTrue(r["success"])
        recipients = server.sendmail.call_args.args[1]
        self.assertEqual(recipients, ["to@x.com", "cc@x.com", "bcc@x.com"])

    def test_header_sanitization(self):
        t = self._tool()
        server = mock.MagicMock()
        with mock.patch.object(t, "_get_connection", return_value=server):
            t.send("to@x.com\r\n", "sub\rject", "body", cc="cc@x.com\r",
                   bcc="bcc@x.com\n")
        msg_str = server.sendmail.call_args.args[2]
        # no raw CR/LF in headers
        self.assertNotIn("\r", msg_str.split("\n\n")[0])

    def test_sendmail_exception_returns_error_and_quits(self):
        t = self._tool()
        server = mock.MagicMock()
        server.sendmail.side_effect = Exception("smtp fail")
        with mock.patch.object(t, "_get_connection", return_value=server), \
                mock.patch.object(et, "logger") as lg:
            r = t.send("to@x.com", "s", "b")
        self.assertEqual(r, {"error": "smtp fail"})
        server.quit.assert_called_once()
        lg.error.assert_called_once()

    def test_quit_called_in_finally_even_on_sendmail_fail(self):
        t = self._tool()
        server = mock.MagicMock()
        server.sendmail.side_effect = RuntimeError("x")
        server.quit.side_effect = None
        with mock.patch.object(t, "_get_connection", return_value=server), \
                mock.patch.object(et, "logger"):
            t.send("to@x.com", "s", "b")
        server.quit.assert_called_once()

    def test_outer_exception_returns_error(self):
        t = self._tool()
        # force exception before connection by patching MIMEMultipart
        with mock.patch("orbit.orbit.tools.email_tool.MIMEMultipart",
                        side_effect=RuntimeError("construct fail")), \
                mock.patch.object(et, "logger") as lg:
            r = t.send("to@x.com", "s", "b")
        self.assertEqual(r, {"error": "construct fail"})
        lg.error.assert_called_once()

    # attachments
    def test_attachment_blocked_path_skipped(self):
        t = self._tool()
        server = mock.MagicMock()
        with mock.patch.object(t, "_get_connection", return_value=server), \
                mock.patch("pathlib.Path.exists", return_value=True), \
                mock.patch("pathlib.Path.is_file", return_value=True), \
                mock.patch("pathlib.Path.resolve",
                           return_value=Path("C:/Windows/System32/x.txt")):
            r = t.send("to@x.com", "s", "b", attachments=["x.txt"])
        self.assertTrue(r["success"])
        # attachment not added (blocked) -> msg has no Content-Disposition
        self.assertNotIn("Content-Disposition", server.sendmail.call_args.args[2])

    def test_attachment_policy_blocked_skipped(self):
        t = self._tool()
        server = mock.MagicMock()
        pe = mock.MagicMock()
        pe.check_path.return_value = mock.MagicMock(allowed=False)
        with mock.patch.object(t, "_get_connection", return_value=server), \
                mock.patch("pathlib.Path.exists", return_value=True), \
                mock.patch("pathlib.Path.is_file", return_value=True), \
                mock.patch("pathlib.Path.resolve",
                           return_value=Path("C:/tmp/safe.txt")), \
                mock.patch("orbit.orbit.core.policy_engine.get_policy_engine",
                           return_value=pe):
            r = t.send("to@x.com", "s", "b", attachments=["safe.txt"])
        self.assertTrue(r["success"])
        pe.check_path.assert_called_once()
        self.assertNotIn("Content-Disposition", server.sendmail.call_args.args[2])

    def test_attachment_policy_engine_exception_ignored(self):
        t = self._tool()
        server = mock.MagicMock()
        with mock.patch.object(t, "_get_connection", return_value=server), \
                mock.patch("pathlib.Path.exists", return_value=True), \
                mock.patch("pathlib.Path.is_file", return_value=True), \
                mock.patch("pathlib.Path.resolve",
                           return_value=Path("C:/tmp/safe.txt")), \
                mock.patch("pathlib.Path.exists", return_value=True), \
                mock.patch("pathlib.Path.is_file", return_value=True), \
                mock.patch("builtins.open", mock.mock_open(read_data=b"data")), \
                mock.patch("orbit.orbit.core.policy_engine.get_policy_engine",
                           side_effect=RuntimeError("no engine")):
            r = t.send("to@x.com", "s", "b", attachments=["safe.txt"])
        self.assertTrue(r["success"])
        self.assertIn("Content-Disposition", server.sendmail.call_args.args[2])

    def test_attachment_missing_file_skipped(self):
        t = self._tool()
        server = mock.MagicMock()
        with mock.patch.object(t, "_get_connection", return_value=server), \
                mock.patch("pathlib.Path.exists", return_value=False):
            r = t.send("to@x.com", "s", "b", attachments=["nope.txt"])
        self.assertTrue(r["success"])
        self.assertNotIn("Content-Disposition", server.sendmail.call_args.args[2])

    def test_attachment_added_successfully(self):
        t = self._tool()
        server = mock.MagicMock()
        p = Path("C:/tmp/ok.txt")
        with mock.patch.object(t, "_get_connection", return_value=server), \
                mock.patch("pathlib.Path.exists", return_value=True), \
                mock.patch("pathlib.Path.is_file", return_value=True), \
                mock.patch("pathlib.Path.resolve", return_value=p), \
                mock.patch("builtins.open", mock.mock_open(read_data=b"data")), \
                mock.patch("orbit.orbit.core.policy_engine.get_policy_engine",
                           side_effect=ImportError("no engine")):
            r = t.send("to@x.com", "s", "b", attachments=["ok.txt"])
        self.assertTrue(r["success"])
        self.assertIn("Content-Disposition", server.sendmail.call_args.args[2])
        self.assertIn('filename="ok.txt"', server.sendmail.call_args.args[2])

    def test_attachments_none_no_loop(self):
        t = self._tool()
        server = mock.MagicMock()
        with mock.patch.object(t, "_get_connection", return_value=server):
            r = t.send("to@x.com", "s", "b", attachments=None)
        self.assertTrue(r["success"])


class SendBulkTests(unittest.TestCase):
    def test_send_bulk(self):
        t = et.EmailTool()
        with mock.patch.object(t, "send", side_effect=[
                {"success": True}, {"error": "fail"}]):
            r = t.send_bulk(["a@x.com", "b@x.com"], "s", "b", html=True)
        self.assertEqual(r["total"], 2)
        self.assertEqual(r["successful"], 1)
        self.assertEqual(r["results"][0], {"to": "a@x.com",
                                          "result": {"success": True}})
        self.assertEqual(r["results"][1]["result"], {"error": "fail"})


class CheckConfigTests(unittest.TestCase):
    def test_configured(self):
        with mock.patch.dict(os.environ, {"EMAIL_ADDRESS": "me@x.com",
                                         "EMAIL_PASSWORD": "pw",
                                         "SMTP_SERVER": "smtp.x.com",
                                         "SMTP_PORT": "25"}):
            t = et.EmailTool()
            c = t.check_config()
        self.assertTrue(c["configured"])
        self.assertEqual(c["smtp_server"], "smtp.x.com")
        self.assertEqual(c["smtp_port"], 25)
        self.assertEqual(c["email"], "me@***")

    def test_unconfigured(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            t = et.EmailTool()
        c = t.check_config()
        self.assertFalse(c["configured"])
        self.assertEqual(c["email"], "Not set")


if __name__ == "__main__":
    unittest.main()
