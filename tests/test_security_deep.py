"""Deep tests for orbit/orbit/tools/security.py (Loop 19/2)."""

import json
import unittest
from unittest import mock

from orbit.orbit.tools import security as sec


class PsQuoteTests(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(sec.SecurityTool._ps_quote("hello"), "'hello'")

    def test_single_quote_escaped(self):
        self.assertEqual(sec.SecurityTool._ps_quote("it's"), "'it''s'")

    def test_non_str_coerced(self):
        self.assertEqual(sec.SecurityTool._ps_quote(123), "'123'")


class PsTests(unittest.TestCase):
    def test_success_returns_stdout(self):
        tool = sec.SecurityTool()
        r = mock.MagicMock(stdout="  out  ", stderr="", returncode=0)
        with mock.patch("subprocess.run", return_value=r):
            self.assertEqual(tool._ps("cmd"), "out")

    def test_empty_stdout_returns_stderr(self):
        tool = sec.SecurityTool()
        r = mock.MagicMock(stdout="   ", stderr="  err  ", returncode=1)
        with mock.patch("subprocess.run", return_value=r):
            self.assertEqual(tool._ps("cmd"), "err")

    def test_exception_returns_str(self):
        tool = sec.SecurityTool()
        with mock.patch("subprocess.run", side_effect=Exception("boom")):
            self.assertEqual(tool._ps("cmd"), "boom")

    def test_truncation(self):
        tool = sec.SecurityTool()
        long_out = "x" * 3000
        r = mock.MagicMock(stdout=long_out, stderr="", returncode=0)
        with mock.patch("subprocess.run", return_value=r):
            out = tool._ps("cmd")
        self.assertEqual(len(out), 2000)


class ScanProcessesTests(unittest.TestCase):
    def test_success(self):
        tool = sec.SecurityTool()
        p1 = mock.MagicMock()
        p1.info = {"pid": 1, "name": "a", "cpu_percent": 50, "memory_percent": 10, "status": "running"}
        p2 = mock.MagicMock()
        p2.info = {"pid": 2, "name": "b", "cpu_percent": 10, "memory_percent": 5, "status": "running"}
        with mock.patch("psutil.process_iter", return_value=[p1, p2]):
            r = tool.scan_processes()
        self.assertEqual(r["total"], 2)
        self.assertEqual(r["top_cpu"][0]["name"], "a")
        self.assertEqual(len(r["top_cpu"]), 2)

    def test_no_such_process_skipped(self):
        tool = sec.SecurityTool()
        p1 = mock.MagicMock()
        p1.info = {"pid": 1, "name": "a", "cpu_percent": 50, "memory_percent": 10, "status": "running"}
        p2 = mock.MagicMock()
        type(p2).info = property(lambda self: (_ for _ in ()).throw(psutil.NoSuchProcess(1)))
        # Use side_effect on info access via mock
        p2 = mock.MagicMock()
        p2.info.side_effect = psutil.NoSuchProcess(1) if False else None
        # simpler: make info raise
        def raise_nsp(self):
            raise psutil.NoSuchProcess(1)
        p2 = mock.MagicMock()
        type(p2).info = property(raise_nsp)
        with mock.patch("psutil.process_iter", return_value=[p1, p2]):
            r = tool.scan_processes()
        self.assertEqual(r["total"], 1)

    def test_access_denied_skipped(self):
        tool = sec.SecurityTool()
        p1 = mock.MagicMock()
        p1.info = {"pid": 1, "name": "a", "cpu_percent": 5, "memory_percent": 1, "status": "running"}

        def raise_ad(self):
            raise psutil.AccessDenied(1)
        p2 = mock.MagicMock()
        type(p2).info = property(raise_ad)
        with mock.patch("psutil.process_iter", return_value=[p1, p2]):
            r = tool.scan_processes()
        self.assertEqual(r["total"], 1)

    def test_sorts_by_cpu_desc(self):
        tool = sec.SecurityTool()
        p1 = mock.MagicMock()
        p1.info = {"pid": 1, "name": "a", "cpu_percent": 5, "memory_percent": 1, "status": "running"}
        p2 = mock.MagicMock()
        p2.info = {"pid": 2, "name": "b", "cpu_percent": 50, "memory_percent": 1, "status": "running"}
        with mock.patch("psutil.process_iter", return_value=[p1, p2]):
            r = tool.scan_processes()
        self.assertEqual(r["top_cpu"][0]["name"], "b")


import psutil


class KillProcessTests(unittest.TestCase):
    def test_toolgate_blocked(self):
        tool = sec.SecurityTool()
        pe = mock.MagicMock()
        pe.check.return_value = mock.MagicMock(allowed=False, reason="nope")
        with mock.patch("orbit.orbit.core.policy_engine.get_policy_engine", return_value=pe):
            r = tool.kill_process("chrome")
        self.assertEqual(r, "❌ Blocked by security policy: nope")

    def test_toolgate_exception_fail_closed(self):
        tool = sec.SecurityTool()
        with mock.patch("orbit.orbit.core.policy_engine.get_policy_engine",
                        side_effect=RuntimeError("boom")):
            r = tool.kill_process("chrome")
        self.assertEqual(r, "❌ Security check failed, operation blocked: boom")

    def test_kills_safe_process(self):
        tool = sec.SecurityTool()
        pe = mock.MagicMock()
        pe.check.return_value = mock.MagicMock(allowed=True)
        proc = mock.MagicMock()
        proc.info = {"pid": 123, "name": "chrome.exe"}
        with mock.patch("orbit.orbit.core.policy_engine.get_policy_engine", return_value=pe), \
                mock.patch("psutil.process_iter", return_value=[proc]):
            r = tool.kill_process("chrome")
        self.assertIn("Killed:", r)
        self.assertIn("chrome.exe (PID: 123)", r)
        proc.kill.assert_called_once()

    def test_no_safe_process(self):
        tool = sec.SecurityTool()
        pe = mock.MagicMock()
        pe.check.return_value = mock.MagicMock(allowed=True)
        proc = mock.MagicMock()
        proc.info = {"pid": 1, "name": "system.exe"}
        with mock.patch("orbit.orbit.core.policy_engine.get_policy_engine", return_value=pe), \
                mock.patch("psutil.process_iter", return_value=[proc]):
            r = tool.kill_process("system")
        self.assertIn("No safe process found", r)

    def test_unsafe_name_not_killed(self):
        # name not in SAFE_TO_KILL -> not killed even if matches
        tool = sec.SecurityTool()
        pe = mock.MagicMock()
        pe.check.return_value = mock.MagicMock(allowed=True)
        proc = mock.MagicMock()
        proc.info = {"pid": 1, "name": "svchost.exe"}
        with mock.patch("orbit.orbit.core.policy_engine.get_policy_engine", return_value=pe), \
                mock.patch("psutil.process_iter", return_value=[proc]):
            r = tool.kill_process("svchost")
        self.assertIn("No safe process found", r)

    def test_substring_not_matched(self):
        # "e" should not match "chrome.exe"
        tool = sec.SecurityTool()
        pe = mock.MagicMock()
        pe.check.return_value = mock.MagicMock(allowed=True)
        proc = mock.MagicMock()
        proc.info = {"pid": 1, "name": "chrome.exe"}
        with mock.patch("orbit.orbit.core.policy_engine.get_policy_engine", return_value=pe), \
                mock.patch("psutil.process_iter", return_value=[proc]):
            r = tool.kill_process("e")
        self.assertIn("No safe process found", r)

    def test_nosuchprocess_skipped(self):
        tool = sec.SecurityTool()
        pe = mock.MagicMock()
        pe.check.return_value = mock.MagicMock(allowed=True)
        proc = mock.MagicMock()
        type(proc).info = property(lambda self: (_ for _ in ()).throw(psutil.NoSuchProcess(1)))
        with mock.patch("orbit.orbit.core.policy_engine.get_policy_engine", return_value=pe), \
                mock.patch("psutil.process_iter", return_value=[proc]):
            r = tool.kill_process("chrome")
        self.assertIn("No safe process found", r)

    def test_accessdenied_skipped(self):
        tool = sec.SecurityTool()
        pe = mock.MagicMock()
        pe.check.return_value = mock.MagicMock(allowed=True)
        proc = mock.MagicMock()
        type(proc).info = property(lambda self: (_ for _ in ()).throw(psutil.AccessDenied(1)))
        with mock.patch("orbit.orbit.core.policy_engine.get_policy_engine", return_value=pe), \
                mock.patch("psutil.process_iter", return_value=[proc]):
            r = tool.kill_process("chrome")
        self.assertIn("No safe process found", r)


class ScanPortsTests(unittest.TestCase):
    def test_success_list(self):
        tool = sec.SecurityTool()
        out = '[{"LocalPort": 80, "OwningProcess": 1}, {"LocalPort": 443, "OwningProcess": 2}]'
        with mock.patch.object(tool, "_ps", return_value=out):
            r = tool.scan_ports()
        self.assertEqual(r, ["Port 80 (PID: 1)", "Port 443 (PID: 2)"])

    def test_success_single_dict(self):
        tool = sec.SecurityTool()
        out = '{"LocalPort": 80, "OwningProcess": 1}'
        with mock.patch.object(tool, "_ps", return_value=out):
            r = tool.scan_ports()
        self.assertEqual(r, ["Port 80 (PID: 1)"])

    def test_invalid_json(self):
        tool = sec.SecurityTool()
        with mock.patch.object(tool, "_ps", return_value="not json"):
            r = tool.scan_ports()
        self.assertEqual(r, ["Could not scan ports"])

    def test_cap_20(self):
        tool = sec.SecurityTool()
        data = [{"LocalPort": i, "OwningProcess": i} for i in range(30)]
        with mock.patch.object(tool, "_ps", return_value=__import__("json").dumps(data)):
            r = tool.scan_ports()
        self.assertEqual(len(r), 20)


class OtherPsMethodsTests(unittest.TestCase):
    def test_scan_network(self):
        tool = sec.SecurityTool()
        with mock.patch.object(tool, "_ps", return_value="netinfo"):
            self.assertEqual(tool.scan_network(), "netinfo")

    def test_firewall_status_success(self):
        tool = sec.SecurityTool()
        out = '[{"Name": "Domain", "Enabled": true}, {"Name": "Public", "Enabled": false}]'
        with mock.patch.object(tool, "_ps", return_value=out):
            r = tool.firewall_status()
        self.assertEqual(r, "[ON] Domain\n[OFF] Public")

    def test_firewall_status_single_dict(self):
        tool = sec.SecurityTool()
        out = '{"Name": "Domain", "Enabled": true}'
        with mock.patch.object(tool, "_ps", return_value=out):
            r = tool.firewall_status()
        self.assertEqual(r, "[ON] Domain")

    def test_firewall_status_invalid(self):
        tool = sec.SecurityTool()
        with mock.patch.object(tool, "_ps", return_value="not json"):
            r = tool.firewall_status()
        self.assertEqual(r, "Firewall info unavailable")

    def test_firewall_toggle_blocked(self):
        tool = sec.SecurityTool()
        pe = mock.MagicMock()
        pe.check.return_value = mock.MagicMock(allowed=False, reason="nope")
        with mock.patch("orbit.orbit.core.policy_engine.get_policy_engine", return_value=pe):
            r = tool.firewall_toggle(True)
        self.assertEqual(r, "❌ Blocked by security policy: nope")

    def test_firewall_toggle_exception_fail_closed(self):
        tool = sec.SecurityTool()
        with mock.patch("orbit.orbit.core.policy_engine.get_policy_engine",
                        side_effect=RuntimeError("boom")):
            r = tool.firewall_toggle(True)
        self.assertEqual(r, "❌ Security check failed, operation blocked: boom")

    def test_firewall_toggle_success(self):
        tool = sec.SecurityTool()
        pe = mock.MagicMock()
        pe.check.return_value = mock.MagicMock(allowed=True)
        with mock.patch("orbit.orbit.core.policy_engine.get_policy_engine", return_value=pe), \
                mock.patch.object(tool, "_ps", return_value="ok") as ps:
            r = tool.firewall_toggle(True)
        self.assertEqual(r, "ok")
        ps.assert_called_once_with("Set-NetFirewallProfile -All -Enabled True")

    def test_firewall_toggle_disable(self):
        tool = sec.SecurityTool()
        pe = mock.MagicMock()
        pe.check.return_value = mock.MagicMock(allowed=True)
        with mock.patch("orbit.orbit.core.policy_engine.get_policy_engine", return_value=pe), \
                mock.patch.object(tool, "_ps", return_value="ok") as ps:
            tool.firewall_toggle(False)
        ps.assert_called_once_with("Set-NetFirewallProfile -All -Enabled False")

    def test_disk_usage(self):
        tool = sec.SecurityTool()
        part = mock.MagicMock()
        part.device = "C:"
        part.mountpoint = "C:\\"
        usage = mock.MagicMock(total=100 * 1024**3, used=50 * 1024**3,
                              free=50 * 1024**3, percent=50.0)
        with mock.patch("psutil.disk_partitions", return_value=[part]), \
                mock.patch("psutil.disk_usage", return_value=usage):
            r = tool.disk_usage()
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["device"], "C:")
        self.assertEqual(r[0]["total_gb"], 100.0)
        self.assertEqual(r[0]["used_gb"], 50.0)
        self.assertEqual(r[0]["free_gb"], 50.0)
        self.assertEqual(r[0]["percent"], 50.0)

    def test_disk_usage_skips_permission_error(self):
        tool = sec.SecurityTool()
        part = mock.MagicMock()
        part.device = "X:"
        part.mountpoint = "X:\\"
        with mock.patch("psutil.disk_partitions", return_value=[part]), \
                mock.patch("psutil.disk_usage", side_effect=PermissionError("no")):
            r = tool.disk_usage()
        self.assertEqual(r, [])

    def test_disk_usage_skips_oserror(self):
        tool = sec.SecurityTool()
        part = mock.MagicMock()
        part.device = "X:"
        part.mountpoint = "X:\\"
        with mock.patch("psutil.disk_partitions", return_value=[part]), \
                mock.patch("psutil.disk_usage", side_effect=OSError("no")):
            r = tool.disk_usage()
        self.assertEqual(r, [])

    def test_service_control_invalid_action(self):
        tool = sec.SecurityTool()
        self.assertEqual(tool.service_control("svc", "nope"),
                         "Invalid action. Use: start, stop, restart, status")

    def test_service_control_status(self):
        tool = sec.SecurityTool()
        with mock.patch.object(tool, "_ps", return_value="status") as ps:
            r = tool.service_control("svc", "status")
        self.assertEqual(r, "status")
        ps.assert_called_once()

    def test_service_control_start(self):
        tool = sec.SecurityTool()
        with mock.patch.object(tool, "_ps", return_value="ok") as ps:
            tool.service_control("svc", "start")
        ps.assert_called_once()

    def test_service_control_ps_quote(self):
        tool = sec.SecurityTool()
        with mock.patch.object(tool, "_ps", return_value="ok") as ps:
            tool.service_control("my'svc", "status")
        cmd = ps.call_args.args[0]
        self.assertIn("my''svc", cmd)

    def test_defender_scan(self):
        tool = sec.SecurityTool()
        with mock.patch.object(tool, "_ps", return_value="scan result"):
            self.assertEqual(tool.defender_scan(), "scan result")

    def test_active_connections(self):
        tool = sec.SecurityTool()
        with mock.patch.object(tool, "_ps", return_value="conns"):
            self.assertEqual(tool.active_connections(), "conns")

    def test_full_report(self):
        tool = sec.SecurityTool()
        mem = mock.MagicMock(percent=50.0, used=8 * 1024**3, total=16 * 1024**3)
        with mock.patch("psutil.cpu_percent", return_value=25.0), \
                mock.patch("psutil.virtual_memory", return_value=mem), \
                mock.patch.object(tool, "disk_usage", return_value=[
                    {"device": "C:", "used_gb": 50, "total_gb": 100, "percent": 50}]), \
                mock.patch.object(tool, "scan_processes", return_value={
                    "total": 10, "top_cpu": [{"name": "chrome", "cpu_percent": 90}]}), \
                mock.patch.object(tool, "firewall_status", return_value="FW"):
            r = tool.full_report()
        self.assertIn("🔒 SYSTEM SECURITY REPORT", r)
        self.assertIn("CPU: 25.0%", r)
        self.assertIn("Top CPU: chrome (90%)", r)
        self.assertIn("Firewall:", r)

    def test_full_report_no_top_cpu(self):
        tool = sec.SecurityTool()
        mem = mock.MagicMock(percent=50.0, used=8 * 1024**3, total=16 * 1024**3)
        with mock.patch("psutil.cpu_percent", return_value=25.0), \
                mock.patch("psutil.virtual_memory", return_value=mem), \
                mock.patch.object(tool, "disk_usage", return_value=[]), \
                mock.patch.object(tool, "scan_processes", return_value={
                    "total": 0, "top_cpu": []}), \
                mock.patch.object(tool, "firewall_status", return_value="FW"):
            r = tool.full_report()
        self.assertIn("Processes: 0 running", r)
        self.assertNotIn("Top CPU", r)


class HandleNaturalTests(unittest.TestCase):
    def setUp(self):
        self.tool = sec.SecurityTool()

    def test_kill_with_name(self):
        with mock.patch.object(self.tool, "kill_process", return_value="killed") as kp:
            r = self.tool.handle_natural("kill chrome")
        self.assertEqual(r, {"success": True, "result": "killed"})
        kp.assert_called_once_with("chrome")

    def test_kill_no_name(self):
        r = self.tool.handle_natural("kill")
        self.assertEqual(r, {"success": False, "error": "Specify process name to kill"})

    def test_kill_stop_process(self):
        with mock.patch.object(self.tool, "kill_process", return_value="k") as kp:
            r = self.tool.handle_natural("stop process notepad")
        kp.assert_called_once_with("notepad")

    def test_firewall_on(self):
        with mock.patch.object(self.tool, "firewall_toggle", return_value="on") as ft:
            r = self.tool.handle_natural("firewall on")
        ft.assert_called_once_with(True)
        self.assertIn("enabled", r["result"])

    def test_firewall_enable(self):
        with mock.patch.object(self.tool, "firewall_toggle", return_value="on") as ft:
            r = self.tool.handle_natural("firewall enable")
        ft.assert_called_once_with(True)

    def test_firewall_off(self):
        with mock.patch.object(self.tool, "firewall_toggle", return_value="off") as ft:
            r = self.tool.handle_natural("firewall off")
        ft.assert_called_once_with(False)
        self.assertIn("disabled", r["result"])

    def test_firewall_disable(self):
        with mock.patch.object(self.tool, "firewall_toggle", return_value="off") as ft:
            r = self.tool.handle_natural("firewall disable")
        ft.assert_called_once_with(False)

    def test_firewall_status(self):
        with mock.patch.object(self.tool, "firewall_status", return_value="FW"):
            r = self.tool.handle_natural("firewall status")
        self.assertIn("Firewall Status", r["result"])

    def test_firewall_connection_not_toggle(self):
        # "connection" contains "on" but status query must not toggle
        with mock.patch.object(self.tool, "firewall_status", return_value="FW"):
            r = self.tool.handle_natural("firewall connection")
        self.assertIn("Firewall Status", r["result"])

    def test_service(self):
        with mock.patch.object(self.tool, "service_control", return_value="svc") as sc:
            r = self.tool.handle_natural("service nginx status")
        self.assertEqual(r, {"success": True, "result": "svc"})

    def test_service_keyword_svc(self):
        with mock.patch.object(self.tool, "service_control", return_value="svc") as sc:
            r = self.tool.handle_natural("service start")
        sc.assert_called_once()
        # svc resolved to last word
        self.assertEqual(sc.call_args.args[0], "start")

    def test_defender(self):
        with mock.patch.object(self.tool, "defender_scan", return_value="scan"):
            r = self.tool.handle_natural("defender scan")
        self.assertIn("Defender Quick Scan", r["result"])

    def test_virus(self):
        with mock.patch.object(self.tool, "defender_scan", return_value="scan"):
            r = self.tool.handle_natural("virus check")
        self.assertIn("Defender Quick Scan", r["result"])

    def test_scan(self):
        with mock.patch.object(self.tool, "defender_scan", return_value="scan"):
            r = self.tool.handle_natural("scan system")
        self.assertIn("Defender Quick Scan", r["result"])

    def test_connection(self):
        with mock.patch.object(self.tool, "active_connections", return_value="conns"):
            r = self.tool.handle_natural("active connections")
        self.assertIn("Active Connections", r["result"])

    def test_established(self):
        with mock.patch.object(self.tool, "active_connections", return_value="conns"):
            r = self.tool.handle_natural("established")
        self.assertIn("Active Connections", r["result"])

    def test_disk(self):
        with mock.patch.object(self.tool, "disk_usage", return_value=[
                {"device": "C:", "used_gb": 50, "total_gb": 100, "percent": 50}]):
            r = self.tool.handle_natural("disk usage")
        self.assertIn("50/100 GB (50%)", r["result"])

    def test_storage(self):
        with mock.patch.object(self.tool, "disk_usage", return_value=[]):
            r = self.tool.handle_natural("storage")
        self.assertEqual(r["result"], "")

    def test_port(self):
        with mock.patch.object(self.tool, "scan_ports", return_value=["Port 80 (PID: 1)"]):
            r = self.tool.handle_natural("open ports")
        self.assertIn("Open ports", r["result"])

    def test_process(self):
        with mock.patch.object(self.tool, "scan_processes", return_value={
                "total": 1, "top_cpu": [{"name": "chrome", "cpu_percent": 90}]}):
            r = self.tool.handle_natural("top process")
        self.assertIn("Top processes", r["result"])
        self.assertIn("chrome: 90% CPU", r["result"])

    def test_network(self):
        with mock.patch.object(self.tool, "scan_network", return_value="netinfo"):
            r = self.tool.handle_natural("network config")
        self.assertIn("Network Config", r["result"])

    def test_fallback_full_report(self):
        with mock.patch.object(self.tool, "full_report", return_value="REPORT"):
            r = self.tool.handle_natural("something else")
        self.assertEqual(r, {"success": True, "result": "REPORT"})


if __name__ == "__main__":
    unittest.main()
