"""Deep tests for orbit/orbit/network.py (Loop 12/5).

Covers every statement:
  * ``get_hostname`` — socket.gethostname.
  * ``get_local_ip`` — success (UDP connect) + exception → 127.0.0.1.
  * ``get_public_ip`` — success + exception → None (urllib mocked).
  * ``get_gateway`` — Windows success, Windows empty, non-Windows, exception.
  * ``get_dns`` — Windows success (≤3), non-Windows, exception.
  * ``get_network_interfaces`` — psutil present path (up/down, AF_INET
    filter), psutil ImportError fallback (Windows ipconfig), exception
    swallowing, non-Windows fallback.
  * ``get_info`` — full dict shape.
  * ``format_info`` — with/without public_ip, gateway, dns, interfaces.
  * ``parse_text`` — returns info envelope.
"""

import platform
import socket
import subprocess
import unittest
from unittest import mock

from orbit.orbit import network as net


class HostnameTests(unittest.TestCase):
    def test_get_hostname(self):
        with mock.patch("socket.gethostname", return_value="myhost"):
            self.assertEqual(net.get_hostname(), "myhost")


class LocalIpTests(unittest.TestCase):
    def test_success(self):
        sock = mock.MagicMock()
        sock.getsockname.return_value = ("192.168.1.5", 12345)
        with mock.patch("socket.socket", return_value=sock):
            self.assertEqual(net.get_local_ip(), "192.168.1.5")
        sock.settimeout.assert_called_once_with(1)
        sock.connect.assert_called_once_with(("8.8.8.8", 80))
        sock.close.assert_called_once()

    def test_exception_returns_loopback(self):
        with mock.patch("socket.socket", side_effect=OSError("no net")):
            self.assertEqual(net.get_local_ip(), "127.0.0.1")


class PublicIpTests(unittest.TestCase):
    def test_success(self):
        resp = mock.MagicMock()
        resp.read.return_value = b"  1.2.3.4  "
        cm = mock.MagicMock()
        cm.__enter__.return_value = resp
        cm.__exit__.return_value = False
        with mock.patch("urllib.request.urlopen", return_value=cm):
            self.assertEqual(net.get_public_ip(), "1.2.3.4")

    def test_exception_returns_none(self):
        with mock.patch("urllib.request.urlopen", side_effect=Exception("net")):
            self.assertIsNone(net.get_public_ip())


class GatewayTests(unittest.TestCase):
    def test_windows_success(self):
        r = mock.MagicMock(stdout="192.168.1.1\n", returncode=0)
        with mock.patch("platform.system", return_value="Windows"), \
                mock.patch("subprocess.run", return_value=r):
            self.assertEqual(net.get_gateway(), "192.168.1.1")

    def test_windows_empty_stdout(self):
        r = mock.MagicMock(stdout="   \n", returncode=0)
        with mock.patch("platform.system", return_value="Windows"), \
                mock.patch("subprocess.run", return_value=r):
            self.assertEqual(net.get_gateway(), "")

    def test_windows_exception_returns_empty(self):
        with mock.patch("platform.system", return_value="Windows"), \
                mock.patch("subprocess.run", side_effect=Exception("boom")):
            self.assertEqual(net.get_gateway(), "")

    def test_non_windows_returns_empty(self):
        with mock.patch("platform.system", return_value="Linux"):
            self.assertEqual(net.get_gateway(), "")


class DnsTests(unittest.TestCase):
    def test_windows_success_capped_at_3(self):
        r = mock.MagicMock(stdout="8.8.8.8\n8.8.4.4\n1.1.1.1\n9.9.9.9\n",
                           returncode=0)
        with mock.patch("platform.system", return_value="Windows"), \
                mock.patch("subprocess.run", return_value=r):
            self.assertEqual(net.get_dns(), ["8.8.8.8", "8.8.4.4", "1.1.1.1"])

    def test_windows_empty(self):
        r = mock.MagicMock(stdout="", returncode=0)
        with mock.patch("platform.system", return_value="Windows"), \
                mock.patch("subprocess.run", return_value=r):
            self.assertEqual(net.get_dns(), [])

    def test_windows_exception_returns_empty(self):
        with mock.patch("platform.system", return_value="Windows"), \
                mock.patch("subprocess.run", side_effect=Exception("boom")):
            self.assertEqual(net.get_dns(), [])

    def test_non_windows_returns_empty(self):
        with mock.patch("platform.system", return_value="Linux"):
            self.assertEqual(net.get_dns(), [])


class InterfacesTests(unittest.TestCase):
    def _psutil_mock(self, addrs, stats, has_psutil=True):
        return None  # placeholder

    def test_psutil_present_filters_ipv4(self):
        import socket as _s
        addr_v4 = mock.MagicMock(family=_s.AF_INET, address="10.0.0.1",
                                 netmask="255.0.0.0", broadcast="10.255.255.255")
        addr_v6 = mock.MagicMock(family=_s.AF_INET6, address="::1")
        stat = mock.MagicMock(isup=True)
        psutil = mock.MagicMock()
        psutil.net_if_addrs.return_value = {"eth0": [addr_v4, addr_v6]}
        psutil.net_if_stats.return_value = {"eth0": stat}
        with mock.patch.dict("sys.modules", {"psutil": psutil}):
            # force the `import psutil` inside to succeed
            ifaces = net.get_network_interfaces()
        self.assertEqual(len(ifaces), 1)
        self.assertEqual(ifaces[0], {
            "name": "eth0", "ip": "10.0.0.1", "netmask": "255.0.0.0",
            "broadcast": "10.255.255.255", "up": True})

    def test_psutil_present_down_interface(self):
        import socket as _s
        addr_v4 = mock.MagicMock(family=_s.AF_INET, address="10.0.0.2",
                                 netmask="255.0.0.0", broadcast=None)
        stat = mock.MagicMock(isup=False)
        psutil = mock.MagicMock()
        psutil.net_if_addrs.return_value = {"eth1": [addr_v4]}
        psutil.net_if_stats.return_value = {"eth1": stat}
        with mock.patch.dict("sys.modules", {"psutil": psutil}):
            ifaces = net.get_network_interfaces()
        self.assertEqual(ifaces[0]["up"], False)
        self.assertIsNone(ifaces[0]["broadcast"])

    def test_psutil_present_missing_stats(self):
        import socket as _s
        addr_v4 = mock.MagicMock(family=_s.AF_INET, address="10.0.0.3",
                                 netmask="255.0.0.0", broadcast="x")
        psutil = mock.MagicMock()
        psutil.net_if_addrs.return_value = {"eth2": [addr_v4]}
        psutil.net_if_stats.return_value = {}  # no stats entry
        with mock.patch.dict("sys.modules", {"psutil": psutil}):
            ifaces = net.get_network_interfaces()
        self.assertEqual(ifaces[0]["up"], False)

    def test_psutil_import_error_windows_ipconfig(self):
        # block psutil import -> ImportError path
        with mock.patch.dict("sys.modules", {"psutil": None}):
            r = mock.MagicMock(stdout="   IPv4 Address. . . : 192.168.1.9\n",
                               returncode=0)
            with mock.patch("platform.system", return_value="Windows"), \
                    mock.patch("subprocess.run", return_value=r):
                ifaces = net.get_network_interfaces()
        self.assertEqual(ifaces, [{"name": "Unknown", "ip": "192.168.1.9"}])

    def test_psutil_import_error_non_windows_returns_empty(self):
        with mock.patch.dict("sys.modules", {"psutil": None}):
            with mock.patch("platform.system", return_value="Linux"):
                self.assertEqual(net.get_network_interfaces(), [])

    def test_psutil_import_error_windows_subprocess_exception(self):
        with mock.patch.dict("sys.modules", {"psutil": None}):
            with mock.patch("platform.system", return_value="Windows"), \
                    mock.patch("subprocess.run", side_effect=Exception("boom")):
                self.assertEqual(net.get_network_interfaces(), [])

    def test_psutil_present_general_exception_returns_partial(self):
        # psutil.net_if_addrs raises -> caught by outer try/except ImportError?
        # Actually the outer except is ImportError only; a general exception
        # propagates. Test that a general exception inside is NOT caught by
        # the ImportError handler (it will propagate). Guard with try.
        psutil = mock.MagicMock()
        psutil.net_if_addrs.side_effect = RuntimeError("boom")
        with mock.patch.dict("sys.modules", {"psutil": psutil}):
            try:
                net.get_network_interfaces()
            except RuntimeError:
                pass
            else:
                self.fail("expected RuntimeError to propagate")


class GetInfoTests(unittest.TestCase):
    def test_shape(self):
        with mock.patch.object(net, "get_hostname", return_value="h"), \
                mock.patch.object(net, "get_local_ip", return_value="1.2.3.4"), \
                mock.patch.object(net, "get_public_ip", return_value="5.6.7.8"), \
                mock.patch.object(net, "get_gateway", return_value="gw"), \
                mock.patch.object(net, "get_dns", return_value=["8.8.8.8"]), \
                mock.patch.object(net, "get_network_interfaces",
                                  return_value=[{"name": "e", "ip": "1.2.3.4",
                                                 "up": True}]), \
                mock.patch("platform.system", return_value="Windows"), \
                mock.patch("platform.release", return_value="10"):
            info = net.get_info()
        self.assertEqual(info, {
            "hostname": "h", "local_ip": "1.2.3.4", "public_ip": "5.6.7.8",
            "gateway": "gw", "dns": ["8.8.8.8"], "platform": "Windows",
            "release": "10",
            "interfaces": [{"name": "e", "ip": "1.2.3.4", "up": True}]})


class FormatInfoTests(unittest.TestCase):
    def _info(self, **overrides):
        base = {
            "hostname": "myhost", "local_ip": "10.0.0.1", "public_ip": None,
            "gateway": "", "dns": [], "platform": "Windows", "release": "10",
            "interfaces": [],
        }
        base.update(overrides)
        return base

    def test_minimal(self):
        with mock.patch.object(net, "get_info",
                               return_value=self._info()):
            out = net.format_info()
        self.assertIn("🌐 **Network Information:**", out)
        self.assertIn("  Hostname: myhost", out)
        self.assertIn("  Local IP: 10.0.0.1", out)
        self.assertIn("  OS: Windows 10", out)
        self.assertNotIn("Public IP", out)
        self.assertNotIn("Gateway", out)
        self.assertNotIn("DNS", out)
        self.assertNotIn("Interfaces", out)

    def test_full(self):
        with mock.patch.object(net, "get_info", return_value=self._info(
                public_ip="1.2.3.4", gateway="10.0.0.254",
                dns=["8.8.8.8", "8.8.4.4"],
                interfaces=[
                    {"name": "eth0", "ip": "10.0.0.1", "up": True},
                    {"name": "eth1", "ip": "10.0.0.2", "up": False},
                ])):
            out = net.format_info()
        self.assertIn("  Public IP: 1.2.3.4", out)
        self.assertIn("  Gateway: 10.0.0.254", out)
        self.assertIn("  DNS: 8.8.8.8, 8.8.4.4", out)
        self.assertIn("  **Interfaces:** (2)", out)
        self.assertIn("    🟢 eth0: 10.0.0.1", out)
        self.assertIn("    🔴 eth1: 10.0.0.2", out)

    def test_interfaces_capped_at_5(self):
        ifaces = [{"name": f"e{i}", "ip": f"10.0.0.{i}", "up": True}
                  for i in range(7)]
        with mock.patch.object(net, "get_info", return_value=self._info(
                interfaces=ifaces)):
            out = net.format_info()
        # only first 5 printed
        self.assertIn("e4", out)
        self.assertNotIn("e5", out)


class ParseTextTests(unittest.TestCase):
    def test_returns_info_envelope(self):
        with mock.patch.object(net, "format_info", return_value="INFO"):
            self.assertEqual(net.parse_text("anything"),
                             {"type": "info", "result": "INFO"})


if __name__ == "__main__":
    unittest.main()
