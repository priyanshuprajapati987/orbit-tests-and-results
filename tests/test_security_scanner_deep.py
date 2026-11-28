"""Deep tests for orbit/orbit/core/security_scanner.py (Loop 23/3)."""

import hashlib
import json
import os
import socket
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from orbit.orbit.core import security_scanner as ss


class ThreatLevelTests(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(ss.ThreatLevel.LOW, "low")
        self.assertEqual(ss.ThreatLevel.MEDIUM, "medium")
        self.assertEqual(ss.ThreatLevel.HIGH, "high")
        self.assertEqual(ss.ThreatLevel.CRITICAL, "critical")


class InitLoadTests(unittest.TestCase):
    def _tmp(self):
        import tempfile
        d = tempfile.mkdtemp()
        return str(Path(d) / "sec.json")

    def test_init_defaults(self):
        p = self._tmp()
        s = ss.SecurityScanner(storage_file=p)
        self.assertEqual(s.file_hashes, {})
        self.assertEqual(s.threats, [])
        self.assertEqual(s.login_attempts, {})
        self.assertEqual(s.suspicious_ips, {})
        self.assertEqual(s.blocked_ips, set())
        self.assertEqual(s.max_login_attempts, 5)
        self.assertEqual(s.lockout_duration, 900)
        self.assertEqual(s.monitored_paths, [str(__import__("orbit.orbit.core.security_scanner", fromlist=["app_root"]).app_root() / "config"),
                                            str(__import__("orbit.orbit.core.security_scanner", fromlist=["env_path"]).env_path()),
                                            str(__import__("orbit.orbit.core.security_scanner", fromlist=["app_root"]).app_root() / ".fernet_key")])

    def test_init_loads_existing(self):
        p = self._tmp()
        Path(p).parent.mkdir(parents=True, exist_ok=True)
        Path(p).write_text(json.dumps({
            "file_hashes": {"a": "h1"},
            "threats": [{"id": "t1"}],
            "blocked_ips": ["1.2.3.4"],
        }), encoding="utf-8")
        s = ss.SecurityScanner(storage_file=p)
        self.assertEqual(s.file_hashes, {"a": "h1"})
        self.assertEqual(s.threats, [{"id": "t1"}])
        self.assertEqual(s.blocked_ips, {"1.2.3.4"})

    def test_init_load_corrupt(self):
        p = self._tmp()
        Path(p).parent.mkdir(parents=True, exist_ok=True)
        Path(p).write_text("{bad", encoding="utf-8")
        with mock.patch.object(ss, "logger") as lg:
            s = ss.SecurityScanner(storage_file=p)
        lg.error.assert_called()

    def test_init_load_missing(self):
        p = self._tmp()
        s = ss.SecurityScanner(storage_file=p)
        self.assertEqual(s.file_hashes, {})

    def test_setup_monitored_paths(self):
        p = self._tmp()
        s = ss.SecurityScanner(storage_file=p)
        self.assertEqual(len(s.monitored_paths), 3)

    def test_save_success(self):
        p = self._tmp()
        s = ss.SecurityScanner(storage_file=p)
        s.file_hashes = {"a": "h"}
        s.threats = [{"id": "t"}]
        s.blocked_ips = {"1.1.1.1"}
        s._save_data()
        self.assertTrue(Path(p).exists())
        data = json.loads(Path(p).read_text("utf-8"))
        self.assertEqual(data["file_hashes"], {"a": "h"})
        self.assertEqual(data["threats"], [{"id": "t"}])
        self.assertEqual(data["blocked_ips"], ["1.1.1.1"])

    def test_save_caps_threats_1000(self):
        p = self._tmp()
        s = ss.SecurityScanner(storage_file=p)
        s.threats = [{"i": i} for i in range(1005)]
        s._save_data()
        data = json.loads(Path(p).read_text("utf-8"))
        self.assertEqual(len(data["threats"]), 1000)

        p = self._tmp()
        s = ss.SecurityScanner(storage_file=p)
        with mock.patch("tempfile.mkstemp", side_effect=OSError("boom")), \
                mock.patch.object(ss, "logger") as lg:
            s._save_data()
        lg.error.assert_called()

    def test_save_tmp_fd_cleanup(self):
        p = self._tmp()
        s = ss.SecurityScanner(storage_file=p)
        # make write fail -> tmp file removed, re-raised, caught by outer except
        with mock.patch("os.fdopen", side_effect=OSError("write fail")), \
                mock.patch("os.remove") as rm, \
                mock.patch.object(ss, "logger") as lg:
            s._save_data()
        rm.assert_called()
        lg.error.assert_called()


class HashFileTests(unittest.TestCase):
    def test_hash_file(self):
        import tempfile
        d = tempfile.mkdtemp()
        f = Path(d) / "f.txt"
        f.write_text("hello", encoding="utf-8")
        s = ss.SecurityScanner.__new__(ss.SecurityScanner)
        h = s._hash_file(f)
        import hashlib
        self.assertEqual(h, hashlib.sha256(b"hello").hexdigest())


class ScanFileIntegrityTests(unittest.TestCase):
    def _make(self):
        p = self._tmp_path()
        s = ss.SecurityScanner(storage_file=p)
        return s, p

    def _tmp_path(self):
        import tempfile
        return str(Path(tempfile.mkdtemp()) / "sec.json")

    def test_new_file(self):
        import tempfile
        d = tempfile.mkdtemp()
        f = Path(d) / "f.txt"
        f.write_text("hello", encoding="utf-8")
        s, p = self._make()
        s.monitored_paths = [str(f)]
        s.file_hashes = {}
        changes = s.scan_file_integrity()
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["type"], "new")
        self.assertEqual(changes[0]["path"], str(f))
        self.assertIn("hash", changes[0])
        self.assertIn(str(f), s.file_hashes)

    def test_modified_file(self):
        import tempfile
        import hashlib
        d = tempfile.mkdtemp()
        f = Path(d) / "f.txt"
        f.write_text("hello", encoding="utf-8")
        h1 = hashlib.sha256(b"hello").hexdigest()
        s, p = self._make()
        s.monitored_paths = [str(f)]
        s.file_hashes = {str(f): "oldhash"}
        changes = s.scan_file_integrity()
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["type"], "modified")
        self.assertEqual(changes[0]["old_hash"], "oldhash")
        self.assertEqual(changes[0]["new_hash"], h1)

    def test_deleted_file(self):
        s, p = self._make()
        path = "/tmp/nonexistent_xyz"
        s.monitored_paths = [path]
        s.file_hashes = {path: "h1"}
        changes = s.scan_file_integrity()
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["type"], "deleted")
        self.assertEqual(changes[0]["path"], path)
        self.assertNotIn(path, s.file_hashes)

    def test_deleted_not_tracked_no_change(self):
        s, p = self._make()
        path = "/tmp/nonexistent_xyz"
        s.monitored_paths = [path]
        s.file_hashes = {}
        changes = s.scan_file_integrity()
        self.assertEqual(changes, [])

    def test_unchanged_file_no_change(self):
        import tempfile, hashlib
        d = tempfile.mkdtemp()
        f = Path(d) / "f.txt"
        f.write_text("hello", encoding="utf-8")
        h = hashlib.sha256(b"hello").hexdigest()
        s, p = self._make()
        s.monitored_paths = [str(f)]
        s.file_hashes = {str(f): h}
        changes = s.scan_file_integrity()
        self.assertEqual(changes, [])

    def test_scan_error_logged(self):
        s, p = self._make()
        path = "/tmp/f.txt"
        s.monitored_paths = [path]
        # file exists check: make Path.exists return True but _hash_file raise
        with mock.patch("pathlib.Path.exists", return_value=True), \
                mock.patch.object(s, "_hash_file", side_effect=RuntimeError("boom")), \
                mock.patch.object(ss, "logger") as lg:
            changes = s.scan_file_integrity()
        self.assertEqual(changes, [])
        lg.error.assert_called()

    def test_changes_record_threat(self):
        import tempfile
        d = tempfile.mkdtemp()
        f = Path(d) / "f.txt"
        f.write_text("hello", encoding="utf-8")
        s, p = self._make()
        s.monitored_paths = [str(f)]
        s.file_hashes = {}
        with mock.patch.object(s, "_record_threat") as rt:
            s.scan_file_integrity()
        rt.assert_called_once_with("file_integrity", ss.ThreatLevel.MEDIUM,
                                   mock.ANY)

    def test_no_changes_no_threat(self):
        s, p = self._make()
        s.monitored_paths = []
        with mock.patch.object(s, "_record_threat") as rt:
            s.scan_file_integrity()
        rt.assert_not_called()


class CheckLoginAttemptTests(unittest.TestCase):
    def _make(self):
        p = self._tmp_path()
        s = ss.SecurityScanner(storage_file=p)
        return s

    def _tmp_path(self):
        import tempfile
        return str(Path(tempfile.mkdtemp()) / "sec.json")

    def test_blocked_ip(self):
        s = self._make()
        s.blocked_ips = {"1.2.3.4"}
        r = s.check_login_attempt("1.2.3.4", "u", True)
        self.assertEqual(r, {"blocked": True, "reason": "IP is blocked"})

    def test_first_failed(self):
        s = self._make()
        r = s.check_login_attempt("1.2.3.4", "u", False)
        self.assertEqual(r, {"blocked": False, "failed_attempts": 1})

    def test_success_no_failed_count(self):
        s = self._make()
        r = s.check_login_attempt("1.2.3.4", "u", True)
        self.assertEqual(r, {"blocked": False, "failed_attempts": 0})

    def test_three_failed_records_suspicious(self):
        s = self._make()
        for i in range(3):
            s.check_login_attempt("1.2.3.4", "u", False)
        # 3rd call records suspicious threat
        threats = [t for t in s.threats if t["type"] == "suspicious_login"]
        self.assertEqual(len(threats), 1)

    def test_five_failed_blocks(self):
        s = self._make()
        for i in range(4):
            s.check_login_attempt("1.2.3.4", "u", False)
        r = s.check_login_attempt("1.2.3.4", "u", False)
        self.assertEqual(r, {"blocked": True, "reason": "Too many failed attempts"})
        threats = [t for t in s.threats if t["type"] == "brute_force"]
        self.assertEqual(len(threats), 1)

    def test_cutoff_filters_old_attempts(self):
        s = self._make()
        from datetime import datetime, timedelta
        old = datetime.now() - timedelta(seconds=1000)
        s.login_attempts["1.2.3.4"] = [{"time": old, "username": "u",
                                       "success": False}]
        # old attempt filtered out by cutoff (lockout 900s)
        r = s.check_login_attempt("1.2.3.4", "u", True)
        self.assertEqual(r, {"blocked": False, "failed_attempts": 0})

    def test_success_after_failures(self):
        s = self._make()
        s.check_login_attempt("1.2.3.4", "u", False)
        r = s.check_login_attempt("1.2.3.4", "u", True)
        self.assertEqual(r, {"blocked": False, "failed_attempts": 1})
        # the failed attempt still in list (not cleared on success)
        self.assertEqual(len(s.login_attempts["1.2.3.4"]), 2)


class CheckSuspiciousActivityTests(unittest.TestCase):
    def _make(self):
        p = self._tmp_path()
        return ss.SecurityScanner(storage_file=p)

    def _tmp_path(self):
        import tempfile
        return str(Path(tempfile.mkdtemp()) / "sec.json")

    def test_sql_injection(self):
        s = self._make()
        self.assertTrue(s.check_suspicious_activity("input", {"q": "union select * from users"}))
        self.assertEqual(s.threats[-1]["details"]["pattern"], "sql_injection")

    def test_xss(self):
        s = self._make()
        self.assertTrue(s.check_suspicious_activity("input", {"q": "<script>alert(1)</script>"}))
        self.assertEqual(s.threats[-1]["details"]["pattern"], "xss_attack")

    def test_path_traversal(self):
        s = self._make()
        self.assertTrue(s.check_suspicious_activity("input", {"q": "../../etc/passwd"}))
        self.assertEqual(s.threats[-1]["details"]["pattern"], "path_traversal")

    def test_command_injection(self):
        s = self._make()
        self.assertTrue(s.check_suspicious_activity("input", {"q": "ls; rm -rf /"}))
        self.assertEqual(s.threats[-1]["details"]["pattern"], "command_injection")

    def test_no_match(self):
        s = self._make()
        self.assertFalse(s.check_suspicious_activity("input", {"q": "hello world"}))

    def test_threat_recorded(self):
        s = self._make()
        s.check_suspicious_activity("input", {"q": "union select"})
        self.assertEqual(len(s.threats), 1)
        self.assertEqual(s.threats[0]["type"], "suspicious_activity")
        self.assertEqual(s.threats[0]["level"], ss.ThreatLevel.HIGH)


class ScanOpenPortsTests(unittest.TestCase):
    def _make(self):
        p = self._tmp_path()
        return ss.SecurityScanner(storage_file=p)

    def _tmp_path(self):
        import tempfile
        return str(Path(tempfile.mkdtemp()) / "sec.json")

    def test_default_ports(self):
        s = self._make()
        with mock.patch("socket.socket") as sock_cls:
            sock = mock.MagicMock()
            sock.connect_ex.return_value = 1  # all closed
            sock_cls.return_value = sock
            r = s.scan_open_ports()
        self.assertEqual(r, [])
        self.assertEqual(sock.settimeout.call_count, 8)
        self.assertEqual(sock.close.call_count, 8)

    def test_open_port(self):
        s = self._make()
        sock = mock.MagicMock()
        sock.connect_ex.return_value = 0
        with mock.patch("socket.socket", return_value=sock):
            r = s.scan_open_ports([80, 443])
        self.assertEqual(len(r), 2)
        self.assertEqual(r[0], {"port": 80, "status": "open",
                                "timestamp": r[0]["timestamp"]})
        self.assertIn("timestamp", r[0])

    def test_custom_ports(self):
        s = self._make()
        sock = mock.MagicMock()
        sock.connect_ex.return_value = 1
        with mock.patch("socket.socket", return_value=sock):
            r = s.scan_open_ports([1234])
        self.assertEqual(r, [])

    def test_mixed(self):
        s = self._make()
        sock = mock.MagicMock()
        sock.connect_ex.side_effect = [0, 1, 0]
        with mock.patch("socket.socket", return_value=sock):
            r = s.scan_open_ports([80, 443, 8080])
        self.assertEqual(len(r), 2)
        self.assertEqual(r[0]["port"], 80)
        self.assertEqual(r[1]["port"], 8080)


class RecordThreatTests(unittest.TestCase):
    def _make(self):
        p = self._tmp_path()
        return ss.SecurityScanner(storage_file=p)

    def _tmp_path(self):
        import tempfile
        return str(Path(tempfile.mkdtemp()) / "sec.json")

    def test_record_threat(self):
        s = self._make()
        with mock.patch.object(ss, "logger") as lg:
            t = s._record_threat("test_type", ss.ThreatLevel.LOW, {"k": "v"})
        self.assertTrue(t["id"])
        self.assertEqual(t["type"], "test_type")
        self.assertEqual(t["level"], ss.ThreatLevel.LOW)
        self.assertEqual(t["details"], {"k": "v"})
        self.assertIn("timestamp", t)
        self.assertFalse(t["resolved"])
        self.assertEqual(len(s.threats), 1)
        lg.warning.assert_called_once()

    def test_cap_1000(self):
        s = self._make()
        s.threats = [{"id": str(i)} for i in range(1001)]
        s._record_threat("t", ss.ThreatLevel.LOW, {})
        self.assertEqual(len(s.threats), 1000)

    def test_id_deterministic_length(self):
        s = self._make()
        t = s._record_threat("t", ss.ThreatLevel.LOW, {})
        self.assertEqual(len(t["id"]), 12)


class GetThreatsTests(unittest.TestCase):
    def _make(self):
        p = self._tmp_path()
        s = ss.SecurityScanner(storage_file=p)
        s.threats = [
            {"id": "1", "type": "t", "level": "high", "resolved": False, "timestamp": "x"},
            {"id": "2", "type": "t", "level": "low", "resolved": True, "timestamp": "y"},
            {"id": "3", "type": "t", "level": "high", "resolved": False, "timestamp": "z"},
        ]
        return s

    def _tmp_path(self):
        import tempfile
        return str(Path(tempfile.mkdtemp()) / "sec.json")

    def test_no_filter(self):
        s = self._make()
        r = s.get_threats()
        self.assertEqual(len(r), 3)

    def test_filter_level(self):
        s = self._make()
        r = s.get_threats(level="high")
        self.assertEqual(len(r), 2)
        self.assertTrue(all(t["level"] == "high" for t in r))

    def test_filter_resolved(self):
        s = self._make()
        r = s.get_threats(resolved=True)
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["id"], "2")

    def test_filter_resolved_false(self):
        s = self._make()
        r = s.get_threats(resolved=False)
        self.assertEqual(len(r), 2)

    def test_limit(self):
        s = self._make()
        r = s.get_threats(limit=2)
        self.assertEqual(len(r), 2)
        self.assertEqual(r[0]["id"], "2")
        self.assertEqual(r[1]["id"], "3")

    def test_level_and_resolved(self):
        s = self._make()
        r = s.get_threats(level="high", resolved=False)
        self.assertEqual(len(r), 2)


class ResolveThreatTests(unittest.TestCase):
    def _make(self):
        p = self._tmp_path()
        s = ss.SecurityScanner(storage_file=p)
        s.threats = [{"id": "t1", "resolved": False}]
        return s

    def _tmp_path(self):
        import tempfile
        return str(Path(tempfile.mkdtemp()) / "sec.json")

    def test_resolve_success(self):
        s = self._make()
        self.assertTrue(s.resolve_threat("t1"))
        self.assertTrue(s.threats[0]["resolved"])
        self.assertIn("resolved_at", s.threats[0])

    def test_resolve_missing(self):
        s = self._make()
        self.assertFalse(s.resolve_threat("nope"))

    def test_resolve_saves(self):
        s = self._make()
        with mock.patch.object(s, "_save_data") as sv:
            s.resolve_threat("t1")
        sv.assert_called_once()


class BlockUnblockIpTests(unittest.TestCase):
    def _make(self):
        p = self._tmp_path()
        return ss.SecurityScanner(storage_file=p)

    def _tmp_path(self):
        import tempfile
        return str(Path(tempfile.mkdtemp()) / "sec.json")

    def test_block_ip(self):
        s = self._make()
        with mock.patch.object(ss, "logger") as lg:
            s.block_ip("1.2.3.4")
        self.assertIn("1.2.3.4", s.blocked_ips)
        lg.warning.assert_called_once()

    def test_unblock_success(self):
        s = self._make()
        s.blocked_ips = {"1.2.3.4"}
        self.assertTrue(s.unblock_ip("1.2.3.4"))
        self.assertNotIn("1.2.3.4", s.blocked_ips)

    def test_unblock_missing(self):
        s = self._make()
        self.assertFalse(s.unblock_ip("1.2.3.4"))

    def test_unblock_saves(self):
        s = self._make()
        s.blocked_ips = {"1.2.3.4"}
        with mock.patch.object(s, "_save_data") as sv:
            s.unblock_ip("1.2.3.4")
        sv.assert_called_once()


class GetSecurityStatusTests(unittest.TestCase):
    def _make(self):
        p = self._tmp_path()
        s = ss.SecurityScanner(storage_file=p)
        return s

    def _tmp_path(self):
        import tempfile
        return str(Path(tempfile.mkdtemp()) / "sec.json")

    def test_empty(self):
        s = self._make()
        st = s.get_security_status()
        self.assertEqual(st["total_threats"], 0)
        self.assertEqual(st["unresolved_threats"], 0)
        self.assertEqual(st["blocked_ips"], 0)
        self.assertEqual(st["monitored_files"], 0)
        self.assertEqual(st["threats_by_level"], {})
        self.assertIn("last_scan", st)

    def test_with_data(self):
        s = self._make()
        s.file_hashes = {"a": "h", "b": "h2"}
        s.blocked_ips = {"1.1.1.1", "2.2.2.2"}
        s.threats = [
            {"id": "1", "level": "high", "resolved": False},
            {"id": "2", "level": "low", "resolved": True},
            {"id": "3", "level": "high", "resolved": False},
        ]
        st = s.get_security_status()
        self.assertEqual(st["total_threats"], 3)
        self.assertEqual(st["unresolved_threats"], 2)
        self.assertEqual(st["blocked_ips"], 2)
        self.assertEqual(st["monitored_files"], 2)
        self.assertEqual(st["threats_by_level"], {"high": 2})


class RunFullScanTests(unittest.TestCase):
    def _make(self):
        p = self._tmp_path()
        s = ss.SecurityScanner(storage_file=p)
        return s

    def _tmp_path(self):
        import tempfile
        return str(Path(tempfile.mkdtemp()) / "sec.json")

    def test_run_full_scan(self):
        s = self._make()
        with mock.patch.object(s, "scan_file_integrity", return_value=[{"type": "new"}]), \
                mock.patch.object(s, "scan_open_ports", return_value=[{"port": 80}]), \
                mock.patch.object(s, "get_security_status", return_value={"status": "ok"}), \
                mock.patch.object(ss, "logger") as lg:
            r = s.run_full_scan()
        self.assertEqual(r["file_integrity"], [{"type": "new"}])
        self.assertEqual(r["open_ports"], [{"port": 80}])
        self.assertEqual(r["security_status"], {"status": "ok"})
        lg.info.assert_called_once()

    def test_run_full_scan_empty(self):
        s = self._make()
        with mock.patch.object(s, "scan_file_integrity", return_value=[]), \
                mock.patch.object(s, "scan_open_ports", return_value=[]), \
                mock.patch.object(s, "get_security_status", return_value={}):
            r = s.run_full_scan()
        self.assertEqual(r["file_integrity"], [])
        self.assertEqual(r["open_ports"], [])


class ModuleLevelTests(unittest.TestCase):
    def test_get_security_scanner_singleton(self):
        ss._security_scanner = None
        a = ss.get_security_scanner()
        b = ss.get_security_scanner()
        self.assertIs(a, b)
        ss._security_scanner = None

    def test_scan_file_integrity_module(self):
        with mock.patch.object(ss, "get_security_scanner") as g:
            s = mock.MagicMock()
            s.scan_file_integrity.return_value = [{"t": 1}]
            g.return_value = s
            self.assertEqual(ss.scan_file_integrity(), [{"t": 1}])

    def test_check_login_attempt_module(self):
        with mock.patch.object(ss, "get_security_scanner") as g:
            s = mock.MagicMock()
            s.check_login_attempt.return_value = {"blocked": False}
            g.return_value = s
            self.assertEqual(ss.check_login_attempt("ip", "u", True), {"blocked": False})
            s.check_login_attempt.assert_called_once_with("ip", "u", True)

    def test_get_threats_module(self):
        with mock.patch.object(ss, "get_security_scanner") as g:
            s = mock.MagicMock()
            s.get_threats.return_value = [{"id": 1}]
            g.return_value = s
            self.assertEqual(ss.get_threats(level="high", limit=10), [{"id": 1}])
            s.get_threats.assert_called_once_with(level="high", limit=10)

    def test_get_security_status_module(self):
        with mock.patch.object(ss, "get_security_scanner") as g:
            s = mock.MagicMock()
            s.get_security_status.return_value = {"status": "ok"}
            g.return_value = s
            self.assertEqual(ss.get_security_status(), {"status": "ok"})

    def test_run_full_scan_module(self):
        with mock.patch.object(ss, "get_security_scanner") as g:
            s = mock.MagicMock()
            s.run_full_scan.return_value = {"r": 1}
            g.return_value = s
            self.assertEqual(ss.run_full_scan(), {"r": 1})


if __name__ == "__main__":
    unittest.main()
