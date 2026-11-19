"""Unit tests for orbit/orbit/core/security_hardening.py."""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

import orbit.core.security_hardening as sh
from orbit.core.security_hardening import (
    RateLimitEntry,
    SecurityHardening,
    get_security_hardening,
)


class SHBase(unittest.TestCase):
    """Fresh SecurityHardening on a temp DATA_DIR (never the real one)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_dir = Path(self._tmp.name) / "security"
        p = patch.object(sh, "DATA_DIR", self.data_dir)
        p.start()
        self.addCleanup(p.stop)
        self.h = SecurityHardening()


class TestRateLimitEntry(unittest.TestCase):
    def test_defaults(self):
        e = RateLimitEntry()
        self.assertEqual(e.count, 0)
        self.assertEqual(e.window_start, 0.0)

    def test_custom(self):
        e = RateLimitEntry(count=5, window_start=1.5)
        self.assertEqual(e.count, 5)
        self.assertEqual(e.window_start, 1.5)


class TestInit(SHBase):
    def test_data_dir_created(self):
        self.assertTrue(self.data_dir.is_dir())

    def test_default_config(self):
        cfg = self.h.get_config()
        self.assertEqual(cfg["rate_limit_per_minute"], 60)
        self.assertEqual(cfg["rate_limit_per_hour"], 1000)
        self.assertEqual(cfg["max_request_size_mb"], 10)
        self.assertTrue(cfg["require_api_key"])
        self.assertEqual(cfg["cors_origins"],
                         ["http://localhost:5173", "http://localhost:3000"])
        self.assertFalse(cfg["enable_request_signing"])

    def test_default_key_generated(self):
        keys = self.h._api_keys
        self.assertIn("default", keys)
        self.assertTrue(keys["default"].startswith("orbit_"))
        self.assertEqual(len(keys["default"]), len("orbit_") + 32)

    def test_api_keys_persisted_to_disk(self):
        raw = json.loads(
            (self.data_dir / "api_keys.json").read_text(encoding="utf-8"))
        self.assertEqual(raw, self.h._api_keys)

    def test_lock_exists(self):
        self.assertTrue(hasattr(self.h, "_lock"))

    def test_load_config_missing_file_ok(self):
        # fresh dir has no security_config.json -> defaults untouched
        self.assertEqual(self.h.get_config()["rate_limit_per_minute"], 60)

    def test_load_config_merges_saved(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "security_config.json").write_text(
            json.dumps({"rate_limit_per_minute": 5}), encoding="utf-8")
        h2 = SecurityHardening()
        cfg = h2.get_config()
        self.assertEqual(cfg["rate_limit_per_minute"], 5)
        # untouched keys keep defaults
        self.assertEqual(cfg["rate_limit_per_hour"], 1000)

    def test_load_config_corrupt_keeps_defaults(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "security_config.json").write_text(
            "{broken", encoding="utf-8")
        with self.assertLogs("orbit.core.security_hardening",
                             level="WARNING") as cm:
            h2 = SecurityHardening()
        self.assertIn("Corrupted security config", cm.output[0])
        self.assertEqual(h2.get_config()["rate_limit_per_minute"], 60)

    def test_generate_key_skipped_when_keys_exist(self):
        (self.data_dir / "api_keys.json").write_text(
            json.dumps({"existing": "orbit_aabb"}), encoding="utf-8")
        h2 = SecurityHardening()
        self.assertEqual(h2._api_keys, {"existing": "orbit_aabb"})


class TestSaveConfig(SHBase):
    def test_save_writes_json(self):
        self.h.update_config({"rate_limit_per_minute": 7})
        raw = json.loads(
            (self.data_dir / "security_config.json").read_text(
                encoding="utf-8"))
        self.assertEqual(raw["rate_limit_per_minute"], 7)

    def test_save_failure_returns_false(self):
        # a DIRECTORY at the .tmp path makes write_text fail
        tmp = self.data_dir / "security_config.json.tmp"
        tmp.mkdir()
        self.assertFalse(self.h._save_config())

    def test_save_failure_logs_error(self):
        tmp = self.data_dir / "security_config.json.tmp"
        tmp.mkdir()
        with self.assertLogs("orbit.core.security_hardening",
                             level="ERROR") as cm:
            self.h._save_config()
        self.assertIn("persistence failed", cm.output[0])


class TestSaveKeys(SHBase):
    def test_save_keys_writes_file(self):
        self.h.generate_api_key("second")
        raw = json.loads(
            (self.data_dir / "api_keys.json").read_text(encoding="utf-8"))
        self.assertIn("second", raw)

    def test_save_keys_failure_returns_false(self):
        tmp = self.data_dir / "api_keys.json.tmp"
        tmp.mkdir()
        self.assertFalse(self.h._save_keys())

    def test_generate_key_persist_failure_logs(self):
        tmp = self.data_dir / "api_keys.json.tmp"
        tmp.mkdir()
        with self.assertLogs("orbit.core.security_hardening",
                             level="ERROR") as cm:
            self.h.generate_api_key("k")
        self.assertIn("_save_keys persistence failed", cm.output[0])
        # in-memory key still usable despite disk failure
        self.assertIn("k", self.h._api_keys)


class TestApiKeyLifecycle(SHBase):
    def test_verify_correct_key(self):
        key = self.h._api_keys["default"]
        self.assertTrue(self.h.verify_api_key(key))

    def test_verify_wrong_key(self):
        self.assertFalse(self.h.verify_api_key("orbit_deadbeef"))

    def test_verify_empty_key(self):
        self.assertFalse(self.h.verify_api_key(""))

    def test_verify_always_true_when_not_required(self):
        self.h.update_config({"require_api_key": False})
        self.assertTrue(self.h.verify_api_key("anything"))
        self.assertTrue(self.h.verify_api_key(""))

    def test_generate_api_key_format_and_store(self):
        key = self.h.generate_api_key("mobile")
        self.assertTrue(key.startswith("orbit_"))
        self.assertEqual(len(key), len("orbit_") + 32)
        self.assertTrue(self.h.verify_api_key(key))

    def test_generate_keys_unique(self):
        a = self.h.generate_api_key("a")
        b = self.h.generate_api_key("b")
        self.assertNotEqual(a, b)

    def test_revoke_existing(self):
        self.h.generate_api_key("temp")
        self.assertTrue(self.h.revoke_api_key("temp"))
        self.assertNotIn("temp", self.h._api_keys)

    def test_revoke_missing(self):
        self.assertFalse(self.h.revoke_api_key("ghost"))

    def test_revoke_default_key(self):
        self.assertTrue(self.h.revoke_api_key("default"))
        self.assertNotIn("default", self.h._api_keys)

    def test_list_keys_preview_shape(self):
        key = self.h.generate_api_key("shown")
        items = self.h.list_api_keys()
        shown = next(i for i in items if i["name"] == "shown")
        self.assertEqual(shown["key_preview"], key[:12] + "...")
        self.assertTrue(shown["key_preview"].endswith("..."))

    def test_list_keys_hides_full_key(self):
        key = self.h.generate_api_key("hidden")
        previews = [i["key_preview"] for i in self.h.list_api_keys()]
        for p in previews:
            self.assertNotIn(key, p)


class TestRateLimit(SHBase):
    def test_first_call_allowed(self):
        self.assertTrue(self.h.check_rate_limit("1.2.3.4"))

    def test_within_limit_allowed(self):
        self.h.update_config({"rate_limit_per_minute": 3})
        for _ in range(3):
            self.assertTrue(self.h.check_rate_limit("5.6.7.8"))

    def test_over_minute_limit_blocked(self):
        self.h.update_config({"rate_limit_per_minute": 3})
        for _ in range(3):
            self.h.check_rate_limit("9.9.9.9")
        self.assertFalse(self.h.check_rate_limit("9.9.9.9"))

    def test_hour_limit_blocks_even_if_minute_ok(self):
        self.h.update_config({"rate_limit_per_minute": 100,
                              "rate_limit_per_hour": 2})
        self.assertTrue(self.h.check_rate_limit("2.2.2.2"))
        self.assertTrue(self.h.check_rate_limit("2.2.2.2"))
        self.assertFalse(self.h.check_rate_limit("2.2.2.2"))

    def test_ips_tracked_independently(self):
        self.h.update_config({"rate_limit_per_minute": 1})
        self.assertTrue(self.h.check_rate_limit("ip-a"))
        self.assertFalse(self.h.check_rate_limit("ip-a"))
        self.assertTrue(self.h.check_rate_limit("ip-b"))

    def test_minute_window_expiry_resets(self):
        self.h.update_config({"rate_limit_per_minute": 1})
        self.assertTrue(self.h.check_rate_limit("3.3.3.3"))
        self.assertFalse(self.h.check_rate_limit("3.3.3.3"))
        t0 = sh.time.time()
        with patch.object(sh.time, "time", return_value=t0 + 61):
            self.assertTrue(self.h.check_rate_limit("3.3.3.3"))

    def test_ttl_prune_drops_expired_entries(self):
        self.h.check_rate_limit("stale-ip")
        t0 = sh.time.time()
        with patch.object(sh.time, "time", return_value=t0 + 7000):
            self.h.check_rate_limit("fresh-ip")
        # stale minute+hour windows pruned; fresh ones present
        keys = list(self.h._rate_limits)
        self.assertTrue(all(not k.startswith("stale-ip") for k in keys))
        self.assertIn("fresh-ip:min", keys)
        self.assertIn("fresh-ip:hour", keys)

    def test_hard_cap_evicts_oldest(self):
        now = sh.time.time()
        for i in range(20001):
            self.h._rate_limits[f"fill{i}:min"] = RateLimitEntry(
                count=1, window_start=now)
        self.h.check_rate_limit("cap-ip")
        keys = list(self.h._rate_limits)
        self.assertNotIn("fill0:min", keys)  # oldest evicted first
        self.assertIn("cap-ip:min", keys)
        self.assertLessEqual(
            len(self.h._rate_limits),
            20001 + 2)  # capped then new ip windows appended


class TestIpBlocking(SHBase):
    def test_not_blocked_by_default(self):
        self.assertFalse(self.h.is_ip_blocked("8.8.8.8"))

    def test_block_ip(self):
        self.h.block_ip("8.8.8.8")
        self.assertTrue(self.h.is_ip_blocked("8.8.8.8"))

    def test_block_writes_audit(self):
        self.h.block_ip("8.8.8.8")
        top = self.h.get_audit_log(limit=1)[0]
        self.assertEqual(top["event"], "ip_blocked")
        self.assertEqual(top["details"], {"ip": "8.8.8.8"})

    def test_unblock_ip(self):
        self.h.block_ip("8.8.8.8")
        self.h.unblock_ip("8.8.8.8")
        self.assertFalse(self.h.is_ip_blocked("8.8.8.8"))

    def test_unblock_missing_is_noop(self):
        self.h.unblock_ip("never-blocked")  # must not raise
        self.assertFalse(self.h.is_ip_blocked("never-blocked"))


class TestSanitizeInput(SHBase):
    def test_script_tag_removed(self):
        out = self.h.sanitize_input(
            'hi <script>alert(1)</script> there')
        self.assertEqual(out, "hi  there")

    def test_multiline_script_removed(self):
        out = self.h.sanitize_input(
            "<script>\nvar x = 1;\n</script>ok")
        self.assertEqual(out, "ok")

    def test_javascript_uri_removed(self):
        out = self.h.sanitize_input("click javascript:evil()")
        self.assertNotIn("javascript:", out.lower())
        self.assertIn("click", out)

    def test_event_handler_removed(self):
        out = self.h.sanitize_input('<img onclick="steal()" src=x>')
        self.assertNotIn("onclick=", out.lower())
        self.assertIn("<img", out)
        self.assertIn("src=x>", out)

    def test_null_bytes_removed(self):
        out = self.h.sanitize_input("a\x00b\x00c")
        self.assertEqual(out, "abc")

    def test_plain_text_untouched(self):
        text = "Hello world! 123 + 45 = 578."
        self.assertEqual(self.h.sanitize_input(text), text)

    def test_case_insensitive_script(self):
        out = self.h.sanitize_input("<SCRIPT>bad()</SCRIPT>")
        self.assertNotIn("script", out.lower())


class TestRequestSigning(SHBase):
    def test_sign_deterministic(self):
        a = self.h.sign_request("payload", "secret")
        b = self.h.sign_request("payload", "secret")
        self.assertEqual(a, b)

    def test_sign_is_sha256_hex(self):
        sig = self.h.sign_request("payload", "secret")
        self.assertEqual(len(sig), 64)
        int(sig, 16)  # valid hex, raises otherwise

    def test_verify_valid_signature(self):
        sig = self.h.sign_request("payload", "secret")
        self.assertTrue(
            self.h.verify_signature("payload", sig, "secret"))

    def test_verify_tampered_payload(self):
        sig = self.h.sign_request("payload", "secret")
        self.assertFalse(
            self.h.verify_signature("payload!", sig, "secret"))

    def test_verify_wrong_secret(self):
        sig = self.h.sign_request("payload", "secret")
        self.assertFalse(
            self.h.verify_signature("payload", sig, "other"))

    def test_verify_empty_strings(self):
        sig = self.h.sign_request("", "")
        self.assertTrue(self.h.verify_signature("", sig, ""))


class TestSecurityHeaders(SHBase):
    def test_all_six_headers_present(self):
        h = self.h.get_security_headers()
        for k in ("X-Content-Type-Options", "X-Frame-Options",
                  "X-XSS-Protection", "Strict-Transport-Security",
                  "Content-Security-Policy", "Referrer-Policy"):
            self.assertIn(k, h)

    def test_header_values(self):
        h = self.h.get_security_headers()
        self.assertEqual(h["X-Content-Type-Options"], "nosniff")
        self.assertEqual(h["X-Frame-Options"], "DENY")
        self.assertEqual(h["X-XSS-Protection"], "1; mode=block")
        self.assertTrue(
            h["Strict-Transport-Security"].startswith("max-age=31536000"))
        self.assertEqual(h["Referrer-Policy"],
                         "strict-origin-when-cross-origin")

    def test_csp_frame_ancestors_none(self):
        csp = self.h.get_security_headers()["Content-Security-Policy"]
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertIn("default-src 'self'", csp)


class TestAuditLog(SHBase):
    def test_entry_shape(self):
        self.h._log_audit("test_event", {"a": 1})
        entry = self.h.get_audit_log(limit=1)[0]
        self.assertEqual(entry["event"], "test_event")
        self.assertEqual(entry["details"], {"a": 1})
        datetime.fromisoformat(entry["timestamp"])  # parses

    def test_details_defaults_to_empty(self):
        self.h._log_audit("bare")
        entry = self.h.get_audit_log(limit=1)[0]
        self.assertEqual(entry["details"], {})

    def test_newest_first_ordering(self):
        for name in ("first", "second", "third"):
            self.h._log_audit(name)
        events = [e["event"] for e in self.h.get_audit_log()]
        self.assertEqual(events, ["third", "second", "first"])

    def test_limit_returns_only_newest(self):
        for i in range(5):
            self.h._log_audit(f"e{i}")
        events = [e["event"] for e in self.h.get_audit_log(limit=2)]
        self.assertEqual(events, ["e4", "e3"])

    def test_default_limit_50(self):
        for i in range(60):
            self.h._log_audit(f"e{i}")
        self.assertEqual(len(self.h.get_audit_log()), 50)

    def test_capped_at_1000_entries(self):
        for i in range(1005):
            self.h._log_audit(f"e{i}")
        self.assertEqual(len(self.h._audit_log), 1000)
        # oldest evicted: last kept entry is the newest
        self.assertEqual(self.h._audit_log[-1]["event"], "e1004")
        self.assertEqual(self.h._audit_log[0]["event"], "e5")


class TestConfigAndStatus(SHBase):
    def test_get_config_returns_copy(self):
        cfg = self.h.get_config()
        cfg["rate_limit_per_minute"] = -1
        self.assertEqual(self.h.get_config()["rate_limit_per_minute"], 60)

    def test_update_config_merges(self):
        out = self.h.update_config({"rate_limit_per_minute": 9})
        self.assertEqual(out["rate_limit_per_minute"], 9)
        self.assertEqual(out["rate_limit_per_hour"], 1000)

    def test_update_config_returns_current(self):
        out = self.h.update_config({"max_request_size_mb": 3})
        self.assertEqual(out["max_request_size_mb"], 3)

    def test_get_status_shape(self):
        s = self.h.get_status()
        self.assertEqual(set(s), {"api_keys", "blocked_ips",
                                  "audit_events", "require_api_key",
                                  "rate_limit_per_minute"})
        self.assertEqual(s["api_keys"], 1)  # default key
        self.assertEqual(s["blocked_ips"], 0)
        self.assertEqual(s["audit_events"], 0)
        self.assertTrue(s["require_api_key"])
        self.assertEqual(s["rate_limit_per_minute"], 60)

    def test_get_status_reflects_changes(self):
        self.h.block_ip("1.1.1.1")   # also writes an ip_blocked audit row
        self.h._log_audit("x")
        s = self.h.get_status()
        self.assertEqual(s["blocked_ips"], 1)
        self.assertEqual(s["audit_events"], 2)


class TestSingleton(SHBase):
    def test_same_instance(self):
        with patch.object(sh, "_instance", None):
            a = get_security_hardening()
            b = get_security_hardening()
        self.assertIs(a, b)

    def test_creates_security_hardening(self):
        with patch.object(sh, "_instance", None):
            inst = get_security_hardening()
        self.assertIsInstance(inst, SecurityHardening)

    def test_cached_instance_returned_as_is(self):
        sentinel = object()
        with patch.object(sh, "_instance", sentinel):
            self.assertIs(get_security_hardening(), sentinel)

    def test_singleton_uses_patched_data_dir(self):
        with patch.object(sh, "_instance", None):
            inst = get_security_hardening()
            # cached inside the patch context (exiting restores _instance)
            self.assertIs(inst, get_security_hardening())
        # instance wrote into the patched temp dir, not the real one
        self.assertTrue(
            (self.data_dir / "api_keys.json").exists())


if __name__ == "__main__":
    unittest.main()
