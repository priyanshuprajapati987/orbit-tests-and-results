"""Unit tests for orbit/orbit/core/security_hardening_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.security_hardening_bp import security_hardening_bp


class TestSecurityHardeningBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(security_hardening_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(security_hardening_bp.name, "security_hardening")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/security/status", "/api/security/config", "/api/security/report",
                  "/api/security/keys", "/api/security/key/generate", "/api/security/key/<name>",
                  "/api/security/audit", "/api/security/block", "/api/security/unblock",
                  "/api/security-hardening/status", "/api/security-hardening/report"]:
            self.assertIn(p, rules)

    def test_status(self):
        with patch("orbit.core.security_hardening_bp.get_security_hardening") as gsh:
            gsh.return_value.get_status.return_value = {"ok": True}
            r = self.client.get("/api/security/status")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])

    def test_status_alt_route(self):
        with patch("orbit.core.security_hardening_bp.get_security_hardening") as gsh:
            gsh.return_value.get_status.return_value = {"ok": True}
            r = self.client.get("/api/security-hardening/status")
        self.assertEqual(r.status_code, 200)

    def test_config(self):
        with patch("orbit.core.security_hardening_bp.get_security_hardening") as gsh:
            gsh.return_value.get_config.return_value = {"rate": 60}
            r = self.client.get("/api/security/config")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["rate"], 60)

    def test_report(self):
        with patch("orbit.core.security_hardening_bp.get_security_hardening") as gsh:
            gsh.return_value.get_status.return_value = {"ok": True}
            gsh.return_value.get_config.return_value = {"rate": 60}
            gsh.return_value.get_audit_log.return_value = [{"e": 1}]
            r = self.client.get("/api/security/report")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["status"]["ok"])
        self.assertEqual(body["config"]["rate"], 60)
        self.assertEqual(body["audit_log"], [{"e": 1}])
        gsh.return_value.get_audit_log.assert_called_once_with(limit=20)

    def test_report_alt_route(self):
        with patch("orbit.core.security_hardening_bp.get_security_hardening") as gsh:
            gsh.return_value.get_status.return_value = {}
            gsh.return_value.get_config.return_value = {}
            gsh.return_value.get_audit_log.return_value = []
            r = self.client.get("/api/security-hardening/report")
        self.assertEqual(r.status_code, 200)

    def test_config_update(self):
        with patch("orbit.core.security_hardening_bp.get_security_hardening") as gsh:
            gsh.return_value.update_config.return_value = {"rate_limit_per_minute": 100}
            r = self.client.post("/api/security/config", json={
                "rate_limit_per_minute": 100, "unknown_key": "x"
            })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        gsh.return_value.update_config.assert_called_once_with({"rate_limit_per_minute": 100})

    def test_config_update_no_body(self):
        with patch("orbit.core.security_hardening_bp.get_security_hardening") as gsh:
            gsh.return_value.update_config.return_value = {}
            r = self.client.post("/api/security/config")
        gsh.return_value.update_config.assert_called_once_with({})

    def test_keys(self):
        with patch("orbit.core.security_hardening_bp.get_security_hardening") as gsh:
            gsh.return_value.list_api_keys.return_value = ["k1"]
            r = self.client.get("/api/security/keys")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["keys"], ["k1"])

    def test_key_generate_missing_name_400(self):
        r = self.client.post("/api/security/key/generate", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_key_generate_success(self):
        with patch("orbit.core.security_hardening_bp.get_security_hardening") as gsh:
            gsh.return_value.generate_api_key.return_value = "secret-key"
            r = self.client.post("/api/security/key/generate", json={"name": "mykey"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["name"], "mykey")
        self.assertEqual(body["key"], "secret-key")
        gsh.return_value.generate_api_key.assert_called_once_with("mykey")

    def test_key_generate_no_body(self):
        r = self.client.post("/api/security/key/generate")
        self.assertEqual(r.status_code, 400)

    def test_key_revoke_success(self):
        with patch("orbit.core.security_hardening_bp.get_security_hardening") as gsh:
            gsh.return_value.revoke_api_key.return_value = True
            r = self.client.delete("/api/security/key/mykey")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        gsh.return_value.revoke_api_key.assert_called_once_with("mykey")

    def test_key_revoke_not_found_404(self):
        with patch("orbit.core.security_hardening_bp.get_security_hardening") as gsh:
            gsh.return_value.revoke_api_key.return_value = False
            r = self.client.delete("/api/security/key/mykey")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_audit(self):
        with patch("orbit.core.security_hardening_bp.get_security_hardening") as gsh:
            gsh.return_value.get_audit_log.return_value = [{"e": 1}]
            r = self.client.get("/api/security/audit?limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["audit_log"], [{"e": 1}])
        gsh.return_value.get_audit_log.assert_called_once_with(5)

    def test_audit_default(self):
        with patch("orbit.core.security_hardening_bp.get_security_hardening") as gsh:
            gsh.return_value.get_audit_log.return_value = []
            r = self.client.get("/api/security/audit")
        gsh.return_value.get_audit_log.assert_called_once_with(50)

    def test_block_missing_ip_400(self):
        r = self.client.post("/api/security/block", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_block_success(self):
        with patch("orbit.core.security_hardening_bp.get_security_hardening") as gsh:
            r = self.client.post("/api/security/block", json={"ip": "1.2.3.4"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertEqual(r.get_json()["blocked"], "1.2.3.4")
        gsh.return_value.block_ip.assert_called_once_with("1.2.3.4")

    def test_block_no_body(self):
        r = self.client.post("/api/security/block")
        self.assertEqual(r.status_code, 400)

    def test_unblock_missing_ip_400(self):
        r = self.client.post("/api/security/unblock", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_unblock_success(self):
        with patch("orbit.core.security_hardening_bp.get_security_hardening") as gsh:
            r = self.client.post("/api/security/unblock", json={"ip": "1.2.3.4"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertEqual(r.get_json()["unblocked"], "1.2.3.4")
        gsh.return_value.unblock_ip.assert_called_once_with("1.2.3.4")

    def test_unblock_no_body(self):
        r = self.client.post("/api/security/unblock")
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
