"""Deep tests for orbit/orbit/core/wifi_manager.py (Loop 12/2).

Covers every statement:
  * ``WiFiManager.list_networks`` — parsing of netsh output (SSID/Signal/
    Authentication/Encryption), multi-network accumulation, empty output,
    subprocess failure/timeout → ``[{"error": ...}]``.
  * ``get_status`` — connected/disconnected states, missing SSID, exception.
  * ``connect`` — ssid/password validation (type, empty, length), XML
    escaping, profile write + chmod (OSError swallowed), add-profile +
    connect subprocess calls, success/failure detection, temp-file cleanup
    (always), exception path.
  * ``disconnect`` — success + exception.
  * ``get_wifi_manager`` — singleton creation + reuse; ``_wifi`` reset.
"""

import subprocess
import tempfile
import unittest
from unittest import mock

from orbit.orbit.core import wifi_manager as wm


def _run(stdout="", returncode=0, side_effect=None):
    m = mock.MagicMock()
    if side_effect is not None:
        m.side_effect = side_effect
    else:
        m.return_value = mock.MagicMock(stdout=stdout, returncode=returncode,
                                       stderr="")
    return m


class ListNetworksTests(unittest.TestCase):
    def test_parses_single_network(self):
        out = (
            "SSID 1 : HomeNet\n"
            "    Signal             : 80%\n"
            "    Authentication     : WPA2-Personal\n"
            "    Encryption         : CCMP\n"
        )
        with mock.patch("subprocess.run", return_value=mock.MagicMock(
                stdout=out, returncode=0)):
            nets = wm.WiFiManager().list_networks()
        self.assertEqual(len(nets), 1)
        self.assertEqual(nets[0]["ssid"], "HomeNet")
        self.assertEqual(nets[0]["signal"], "80%")
        self.assertEqual(nets[0]["auth"], "WPA2-Personal")
        self.assertEqual(nets[0]["encryption"], "CCMP")

    def test_parses_multiple_networks(self):
        out = (
            "SSID 1 : NetA\n"
            "    Signal             : 90%\n"
            "SSID 2 : NetB\n"
            "    Signal             : 40%\n"
            "    Authentication     : Open\n"
        )
        with mock.patch("subprocess.run", return_value=mock.MagicMock(
                stdout=out, returncode=0)):
            nets = wm.WiFiManager().list_networks()
        self.assertEqual([n["ssid"] for n in nets], ["NetA", "NetB"])
        self.assertEqual(nets[1]["auth"], "Open")

    def test_empty_output_returns_empty(self):
        with mock.patch("subprocess.run", return_value=mock.MagicMock(
                stdout="", returncode=0)):
            self.assertEqual(wm.WiFiManager().list_networks(), [])

    def test_subprocess_exception_returns_error(self):
        with mock.patch("subprocess.run", side_effect=OSError("netsh missing")):
            self.assertEqual(wm.WiFiManager().list_networks(),
                             [{"error": "netsh missing"}])

    def test_timeout_returns_error(self):
        with mock.patch("subprocess.run",
                        side_effect=subprocess.TimeoutExpired(cmd="x", timeout=10)):
            res = wm.WiFiManager().list_networks()
        self.assertEqual(len(res), 1)
        self.assertIn("error", res[0])

    def test_bssid_line_not_treated_as_ssid(self):
        out = (
            "SSID 1 : RealNet\n"
            "    BSSID 1            : aa:bb:cc:dd:ee:ff\n"
            "    Signal             : 70%\n"
        )
        with mock.patch("subprocess.run", return_value=mock.MagicMock(
                stdout=out, returncode=0)):
            nets = wm.WiFiManager().list_networks()
        self.assertEqual(len(nets), 1)
        self.assertEqual(nets[0]["ssid"], "RealNet")

    def test_trailing_current_appended(self):
        # a network with no trailing fields still gets appended
        out = "SSID 1 : LoneNet\n"
        with mock.patch("subprocess.run", return_value=mock.MagicMock(
                stdout=out, returncode=0)):
            nets = wm.WiFiManager().list_networks()
        self.assertEqual(nets, [{"ssid": "LoneNet"}])


class GetStatusTests(unittest.TestCase):
    def test_connected(self):
        out = "SSID                   : HomeNet\nState                  : connected\n"
        with mock.patch("subprocess.run", return_value=mock.MagicMock(
                stdout=out, returncode=0)):
            s = wm.WiFiManager().get_status()
        self.assertEqual(s, {"ssid": "HomeNet", "state": "connected"})

    def test_disconnected_no_ssid(self):
        out = "State                  : disconnected\n"
        with mock.patch("subprocess.run", return_value=mock.MagicMock(
                stdout=out, returncode=0)):
            s = wm.WiFiManager().get_status()
        self.assertEqual(s, {"ssid": "", "state": "disconnected"})

    def test_bssid_not_captured_as_ssid(self):
        out = "BSSID                  : aa:bb\nState                  : connected\n"
        with mock.patch("subprocess.run", return_value=mock.MagicMock(
                stdout=out, returncode=0)):
            s = wm.WiFiManager().get_status()
        self.assertEqual(s["ssid"], "")

    def test_exception_returns_error(self):
        with mock.patch("subprocess.run", side_effect=OSError("boom")):
            self.assertEqual(wm.WiFiManager().get_status(), {"error": "boom"})


class ConnectValidationTests(unittest.TestCase):
    def _run(self, stdout="", side_effect=None):
        if side_effect is not None:
            return mock.patch("subprocess.run", side_effect=side_effect)
        return mock.patch("subprocess.run",
                          return_value=mock.MagicMock(stdout=stdout,
                                                     returncode=0))

    def test_invalid_ssid_type(self):
        self.assertEqual(wm.WiFiManager().connect(123)["error"], "invalid ssid")

    def test_empty_ssid(self):
        self.assertEqual(wm.WiFiManager().connect("   ")["error"], "invalid ssid")

    def test_ssid_too_long(self):
        self.assertEqual(wm.WiFiManager().connect("a" * 33)["error"],
                         "invalid ssid")

    def test_password_wrong_type(self):
        self.assertEqual(wm.WiFiManager().connect("Net", password=123)["error"],
                         "invalid password")

    def test_password_too_long(self):
        self.assertEqual(wm.WiFiManager().connect("Net", password="p" * 129)["error"],
                         "invalid password")

    def test_none_password_is_allowed(self):
        # no profile written; connect subprocess called
        with self._run(stdout="successfully connected"):
            res = wm.WiFiManager().connect("Net", password=None)
        self.assertEqual(res, {"status": "connected", "ssid": "Net"})

    def test_success_with_password(self):
        with self._run(stdout="successfully connected") as run:
            # capture calls: add profile + connect
            res = wm.WiFiManager().connect("Net", password="secret")
        self.assertEqual(res, {"status": "connected", "ssid": "Net"})
        # two subprocess.run calls (add profile, connect)
        self.assertEqual(run.call_count, 2)
        # profile add call uses filename=
        add_call = run.call_args_list[0]
        self.assertIn("add", add_call.args[0])
        self.assertTrue(any("filename=" in str(a) for a in add_call.args[0]))
        conn_call = run.call_args_list[1]
        self.assertIn("connect", conn_call.args[0])

    def test_connect_failure_returns_failed(self):
        with self._run(stdout="The network is not available"):
            res = wm.WiFiManager().connect("Net")
        self.assertEqual(res, {"status": "failed",
                               "error": "The network is not available"})

    def test_connect_empty_stdout_failed(self):
        with self._run(stdout=""):
            res = wm.WiFiManager().connect("Net")
        self.assertEqual(res, {"status": "failed", "error": ""})

    def test_xml_escaping_in_profile(self):
        captured = {}

        def fake_run(cmd, *a, **k):
            if "add" in " ".join(cmd):
                # read the profile file path from cmd
                for c in cmd:
                    if c.startswith("filename="):
                        path = c.split("=", 1)[1]
                        with open(path, encoding="utf-8") as f:
                            captured["xml"] = f.read()
            return mock.MagicMock(stdout="successfully connected",
                                 returncode=0)

        with mock.patch("subprocess.run", side_effect=fake_run):
            wm.WiFiManager().connect("N<et>", password="p&w")
        self.assertIn("&lt;et&gt;", captured["xml"])  # ssid escaped
        self.assertIn("&amp;w", captured["xml"])      # password escaped

    def test_chmod_oserror_swallowed(self):
        real_mkstemp = tempfile.mkstemp

        def fake_mkstemp(*a, **k):
            fd, path = real_mkstemp(*a, **k)
            return fd, path

        with mock.patch("tempfile.mkstemp", side_effect=fake_mkstemp), \
                mock.patch("os.chmod", side_effect=OSError("no chmod")), \
                mock.patch("subprocess.run",
                           return_value=mock.MagicMock(stdout="successfully connected",
                                                      returncode=0)):
            res = wm.WiFiManager().connect("Net", password="secret")
        self.assertEqual(res["status"], "connected")

    def test_temp_profile_cleaned_up(self):
        seen_paths = []

        def fake_run(cmd, *a, **k):
            for c in cmd:
                if c.startswith("filename="):
                    seen_paths.append(c.split("=", 1)[1])
            return mock.MagicMock(stdout="successfully connected",
                                 returncode=0)

        with mock.patch("subprocess.run", side_effect=fake_run):
            wm.WiFiManager().connect("Net", password="secret")
        for p in seen_paths:
            import os
            self.assertFalse(os.path.exists(p))

    def test_profile_add_exception_returns_error(self):
        # connect raises during profile add -> caught by outer except
        with mock.patch("subprocess.run",
                        side_effect=OSError("add failed")):
            res = wm.WiFiManager().connect("Net", password="secret")
        self.assertEqual(res, {"error": "add failed"})

    def test_profile_unlink_oserror_swallowed(self):
        with mock.patch("subprocess.run",
                        return_value=mock.MagicMock(stdout="successfully connected",
                                                   returncode=0)), \
                mock.patch("os.unlink", side_effect=OSError("locked")):
            res = wm.WiFiManager().connect("Net", password="secret")
        self.assertEqual(res["status"], "connected")
        # no password: only connect subprocess, which raises
        with mock.patch("subprocess.run",
                        side_effect=OSError("connect failed")):
            res = wm.WiFiManager().connect("Net")
        self.assertEqual(res, {"error": "connect failed"})


class DisconnectTests(unittest.TestCase):
    def test_disconnect_success(self):
        with mock.patch("subprocess.run", return_value=mock.MagicMock()):
            self.assertEqual(wm.WiFiManager().disconnect(),
                             {"status": "disconnected"})

    def test_disconnect_exception(self):
        with mock.patch("subprocess.run", side_effect=OSError("boom")):
            self.assertEqual(wm.WiFiManager().disconnect(),
                             {"error": "boom"})


class SingletonTests(unittest.TestCase):
    def setUp(self):
        self._saved = wm._wifi
        wm._wifi = None
        self.addCleanup(setattr, wm, "_wifi", self._saved)

    def test_creates_instance(self):
        a = wm.get_wifi_manager()
        self.assertIsInstance(a, wm.WiFiManager)
        self.assertIs(wm._wifi, a)

    def test_reuses_instance(self):
        a = wm.get_wifi_manager()
        b = wm.get_wifi_manager()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
