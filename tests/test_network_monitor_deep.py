"""Deep tests for orbit/orbit/core/network_monitor.py (Loop 21/4)."""

import json
import socket
import threading
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from orbit.orbit.core import network_monitor as nm


class InitLoadTests(unittest.TestCase):
    def _tmp(self):
        import tempfile
        d = tempfile.mkdtemp()
        return str(Path(d) / "nm.json")

    def test_init_defaults(self):
        p = self._tmp()
        with mock.patch.object(nm.NetworkMonitor, "check_connectivity", return_value=False):
            m = nm.NetworkMonitor(storage_file=p)
        self.assertEqual(m.endpoints, [
            {"name": "google", "host": "8.8.8.8", "port": 53},
            {"name": "cloudflare", "host": "1.1.1.1", "port": 53},
            {"name": "dns", "host": "208.67.222.222", "port": 53},
        ])
        self.assertFalse(m.is_online)
        self.assertEqual(m.check_interval, 60)
        self.assertEqual(m.timeout, 5)
        self.assertEqual(m.history, [])
        self.assertEqual(m.callbacks, [])
        self.assertIsNone(m._monitor_thread)
        m.stop_monitoring()

    def test_init_loads_history(self):
        p = self._tmp()
        Path(p).parent.mkdir(parents=True, exist_ok=True)
        Path(p).write_text(json.dumps({"history": [{"a": 1}, {"b": 2}]}),
                           encoding="utf-8")
        with mock.patch.object(nm.NetworkMonitor, "check_connectivity",
                               return_value=True):
            m = nm.NetworkMonitor(storage_file=p)
        self.assertEqual(m.history, [{"a": 1}, {"b": 2}])
        self.assertTrue(m.is_online)
        m.stop_monitoring()

    def test_init_load_caps_100(self):
        p = self._tmp()
        Path(p).parent.mkdir(parents=True, exist_ok=True)
        Path(p).write_text(json.dumps({"history": [{"i": i} for i in range(150)]}),
                           encoding="utf-8")
        with mock.patch.object(nm.NetworkMonitor, "check_connectivity",
                               return_value=False):
            m = nm.NetworkMonitor(storage_file=p)
        self.assertEqual(len(m.history), 100)
        m.stop_monitoring()

    def test_init_load_failure_logged(self):
        p = self._tmp()
        Path(p).parent.mkdir(parents=True, exist_ok=True)
        Path(p).write_text("{bad", encoding="utf-8")
        with mock.patch.object(nm.NetworkMonitor, "check_connectivity",
                               return_value=False), \
                mock.patch.object(nm, "logger") as lg:
            m = nm.NetworkMonitor(storage_file=p)
        lg.error.assert_called()
        m.stop_monitoring()

    def test_save_success(self):
        p = self._tmp()
        m = nm.NetworkMonitor(storage_file=p)
        m.history = [{"x": 1}]
        m._save_data()
        self.assertTrue(Path(p).exists())
        data = json.loads(Path(p).read_text("utf-8"))
        self.assertEqual(data, {"history": [{"x": 1}]})
        m.stop_monitoring()

    def test_save_caps_100(self):
        p = self._tmp()
        m = nm.NetworkMonitor(storage_file=p)
        m.history = [{"i": i} for i in range(150)]
        m._save_data()
        data = json.loads(Path(p).read_text("utf-8"))
        self.assertEqual(len(data["history"]), 100)
        m.stop_monitoring()

    def test_save_failure_logged(self):
        p = self._tmp()
        m = nm.NetworkMonitor(storage_file=p)
        with mock.patch("builtins.open", side_effect=OSError("boom")), \
                mock.patch.object(nm, "logger") as lg:
            m._save_data()
        lg.error.assert_called()
        m.stop_monitoring()


class CheckConnectivityTests(unittest.TestCase):
    def _make(self, endpoints=None):
        p = self._tmp_path()
        m = nm.NetworkMonitor(storage_file=p)
        m._stop_monitoring = True
        if endpoints is not None:
            m.endpoints = endpoints
        return m

    def _tmp_path(self):
        import tempfile
        return str(Path(tempfile.mkdtemp()) / "nm.json")

    def test_endpoint_success(self):
        m = self._make()
        sock = mock.MagicMock()
        with mock.patch("socket.socket", return_value=sock):
            r = m.check_connectivity({"name": "x", "host": "1.2.3.4", "port": 80})
        self.assertTrue(r)
        sock.connect.assert_called_once_with(("1.2.3.4", 80))
        sock.close.assert_called_once()
        m.stop_monitoring()

    def test_endpoint_fail(self):
        m = self._make()
        sock = mock.MagicMock()
        sock.connect.side_effect = Exception("refused")
        with mock.patch("socket.socket", return_value=sock):
            r = m.check_connectivity({"name": "x", "host": "1.2.3.4", "port": 80})
        self.assertFalse(r)
        sock.close.assert_called_once()
        m.stop_monitoring()

    def test_endpoints_loop_success(self):
        m = self._make(endpoints=[{"name": "a", "host": "1.1.1.1", "port": 53},
                                  {"name": "b", "host": "2.2.2.2", "port": 53}])
        sock = mock.MagicMock()
        sock.connect.side_effect = [Exception("fail"), None]
        with mock.patch("socket.socket", return_value=sock):
            r = m.check_connectivity()
        self.assertTrue(r)

    def test_endpoints_all_fail_dns_fallback_success(self):
        m = self._make(endpoints=[{"name": "a", "host": "1.1.1.1", "port": 53}])
        sock = mock.MagicMock()
        sock.connect.side_effect = Exception("fail")
        with mock.patch("socket.socket", return_value=sock), \
                mock.patch("socket.gethostbyname", return_value="142.250.1.1"):
            r = m.check_connectivity()
        self.assertTrue(r)
        m.stop_monitoring()

    def test_endpoints_all_fail_dns_fallback_fail(self):
        m = self._make(endpoints=[{"name": "a", "host": "1.1.1.1", "port": 53}])
        sock = mock.MagicMock()
        sock.connect.side_effect = Exception("fail")
        with mock.patch("socket.socket", return_value=sock), \
                mock.patch("socket.gethostbyname", side_effect=Exception("dns fail")), \
                mock.patch.object(nm, "logger") as lg:
            r = m.check_connectivity()
        self.assertFalse(r)
        lg.exception.assert_called_once()
        m.stop_monitoring()

    def test_outer_exception(self):
        m = self._make()
        with mock.patch("socket.socket", side_effect=Exception("outer")):
            r = m.check_connectivity()
        self.assertFalse(r)

    def test_endpoint_socket_close_on_fail(self):
        m = self._make()
        sock = mock.MagicMock()
        sock.connect.side_effect = Exception("refused")
        with mock.patch("socket.socket", return_value=sock):
            m.check_connectivity({"name": "x", "host": "1.2.3.4", "port": 80})
        sock.close.assert_called_once()


class MeasureLatencyTests(unittest.TestCase):
    def _make(self):
        p = self._tmp_path()
        m = nm.NetworkMonitor(storage_file=p)
        m._stop_monitoring = False
        return m

    def _tmp_path(self):
        import tempfile
        return str(Path(tempfile.mkdtemp()) / "nm.json")

    def test_success(self):
        m = self._make()
        sock = mock.MagicMock()
        with mock.patch("socket.socket", return_value=sock), \
                mock.patch("time.time", side_effect=[100.0, 100.05]):
            r = m.measure_latency("8.8.8.8", 53)
        self.assertEqual(r, 50.0)
        sock.connect.assert_called_once_with(("8.8.8.8", 53))
        sock.close.assert_called_once()
        m.stop_monitoring()

    def test_exception(self):
        m = self._make()
        sock = mock.MagicMock()
        sock.connect.side_effect = Exception("boom")
        with mock.patch("socket.socket", return_value=sock), \
                mock.patch.object(nm, "logger") as lg:
            r = m.measure_latency("8.8.8.8", 53)
        self.assertIsNone(r)
        lg.error.assert_called_once()
        m.stop_monitoring()

    def test_sock_close_exception_in_measure_latency(self):
        m = self._make()
        sock = mock.MagicMock()
        sock.connect.side_effect = Exception("boom")
        sock.close.side_effect = Exception("close boom")
        with mock.patch("socket.socket", return_value=sock), \
                mock.patch.object(nm, "logger") as lg:
            r = m.measure_latency("8.8.8.8", 53)
        self.assertIsNone(r)
        m.stop_monitoring()
        # socket.socket raises -> sock stays None -> finally skips close
        m = self._make()
        with mock.patch("socket.socket", side_effect=Exception("boom")), \
                mock.patch.object(nm, "logger") as lg:
            r = m.measure_latency("8.8.8.8", 53)
        self.assertIsNone(r)
        m.stop_monitoring()


class CheckDnsTests(unittest.TestCase):
    def _make(self):
        p = self._tmp_path()
        m = nm.NetworkMonitor(storage_file=p)
        m._stop_monitoring = False
        return m

    def _tmp_path(self):
        import tempfile
        return str(Path(tempfile.mkdtemp()) / "nm.json")

    def test_success(self):
        m = self._make()
        with mock.patch("socket.gethostbyname", return_value="142.250.1.1"):
            self.assertEqual(m.check_dns("google.com"), "142.250.1.1")
        m.stop_monitoring()

    def test_failure(self):
        m = self._make()
        with mock.patch("socket.gethostbyname", side_effect=Exception("dns")), \
                mock.patch.object(nm, "logger") as lg:
            self.assertIsNone(m.check_dns("google.com"))
        lg.error.assert_called_once()
        m.stop_monitoring()

    def test_default_hostname(self):
        m = self._make()
        with mock.patch("socket.gethostbyname", return_value="1.2.3.4") as gh:
            m.check_dns()
        gh.assert_called_once_with("google.com")
        m.stop_monitoring()


class CallbacksTests(unittest.TestCase):
    def _make(self):
        p = self._tmp_path()
        m = nm.NetworkMonitor(storage_file=p)
        m._stop_monitoring = False
        return m

    def _tmp_path(self):
        import tempfile
        return str(Path(tempfile.mkdtemp()) / "nm.json")

    def test_add_remove_callback(self):
        m = self._make()
        cb = lambda s, d: None
        m.add_callback(cb)
        self.assertIn(cb, m.callbacks)
        m.remove_callback(cb)
        self.assertNotIn(cb, m.callbacks)
        m.stop_monitoring()

    def test_remove_missing_no_crash(self):
        m = self._make()
        cb = lambda s, d: None
        m.remove_callback(cb)  # not present
        m.stop_monitoring()

    def test_notify_callbacks(self):
        m = self._make()
        cb1 = mock.MagicMock()
        cb2 = mock.MagicMock(side_effect=RuntimeError("boom"))
        m.callbacks = [cb1, cb2]
        with mock.patch.object(nm, "logger") as lg:
            m._notify_callbacks("online", {"x": 1})
        cb1.assert_called_once_with("online", {"x": 1})
        lg.error.assert_called_once()
        m.stop_monitoring()

    def test_notify_empty(self):
        m = self._make()
        m.callbacks = []
        m._notify_callbacks("online", {})
        m.stop_monitoring()


class MonitorLoopTests(unittest.TestCase):
    def _make(self):
        p = self._tmp_path()
        m = nm.NetworkMonitor(storage_file=p)
        m._stop_monitoring = False
        return m

    def _tmp_path(self):
        import tempfile
        return str(Path(tempfile.mkdtemp()) / "nm.json")

    def test_monitor_loop_status_change(self):
        m = self._make()
        m.is_online = False
        call_count = {"n": 0}

        def check_conn():
            call_count["n"] += 1
            if call_count["n"] >= 1:
                m._stop_monitoring = True
            return True

        with mock.patch.object(m, "check_connectivity", side_effect=check_conn), \
                mock.patch.object(m, "measure_latency", return_value=10.0), \
                mock.patch("time.sleep"), \
                mock.patch.object(m, "_notify_callbacks") as nc, \
                mock.patch.object(m, "_save_data"):
            m._monitor_loop()
        # status changed False->True -> notify called
        nc.assert_called_once()
        self.assertTrue(m.is_online)
        m.stop_monitoring()

    def test_monitor_loop_no_change(self):
        m = self._make()
        m.is_online = True
        call_count = {"n": 0}

        def check_conn():
            call_count["n"] += 1
            if call_count["n"] >= 1:
                m._stop_monitoring = True
            return True

        with mock.patch.object(m, "check_connectivity", side_effect=check_conn), \
                mock.patch.object(m, "measure_latency", return_value=None), \
                mock.patch("time.sleep"), \
                mock.patch.object(m, "_notify_callbacks") as nc, \
                mock.patch.object(m, "_save_data"):
            m._monitor_loop()
        nc.assert_not_called()
        m.stop_monitoring()

    def test_monitor_loop_exception(self):
        m = self._make()
        call_count = {"n": 0}

        def check_conn():
            call_count["n"] += 1
            if call_count["n"] >= 1:
                m._stop_monitoring = True
            raise RuntimeError("boom")

        with mock.patch.object(m, "check_connectivity", side_effect=check_conn), \
                mock.patch("time.sleep"), \
                mock.patch.object(nm, "logger") as lg:
            m._monitor_loop()
        lg.error.assert_called()
        m.stop_monitoring()

    def test_monitor_loop_history_cap(self):
        m = self._make()
        m.history = [{"i": i} for i in range(100)]
        m.is_online = True
        call_count = {"n": 0}

        def check_conn():
            call_count["n"] += 1
            if call_count["n"] >= 1:
                m._stop_monitoring = True
            return True

        with mock.patch.object(m, "check_connectivity", side_effect=check_conn), \
                mock.patch.object(m, "measure_latency", return_value=5.0), \
                mock.patch("time.sleep"), \
                mock.patch.object(m, "_save_data"):
            m._monitor_loop()
        self.assertEqual(len(m.history), 100)
        m.stop_monitoring()


class StartStopMonitoringTests(unittest.TestCase):
    def _make(self):
        p = self._tmp_path()
        m = nm.NetworkMonitor(storage_file=p)
        m._stop_monitoring = False
        return m

    def _tmp_path(self):
        import tempfile
        return str(Path(tempfile.mkdtemp()) / "nm.json")

    def test_start_monitoring(self):
        m = self._make()
        with mock.patch("threading.Thread") as T:
            t = mock.MagicMock()
            T.return_value = t
            m.start_monitoring(30)
        self.assertEqual(m.check_interval, 30)
        self.assertFalse(m._stop_monitoring)
        self.assertIs(m._monitor_thread, t)
        t.start.assert_called_once()
        m.stop_monitoring()

    def test_start_noop_if_alive(self):
        m = self._make()
        t = mock.MagicMock()
        t.is_alive.return_value = True
        m._monitor_thread = t
        m.start_monitoring()
        # no new thread
        self.assertIs(m._monitor_thread, t)
        m.stop_monitoring()

    def test_stop_monitoring(self):
        m = self._make()
        t = mock.MagicMock()
        m._monitor_thread = t
        m._stop_monitoring = False
        m.stop_monitoring()
        self.assertTrue(m._stop_monitoring)
        t.join.assert_called_once_with(timeout=5)
        m.stop_monitoring()

    def test_stop_monitoring_no_thread(self):
        m = self._make()
        m._monitor_thread = None
        m.stop_monitoring()  # no crash
        m.stop_monitoring()


class GetStatusTests(unittest.TestCase):
    def _make(self):
        p = self._tmp_path()
        m = nm.NetworkMonitor(storage_file=p)
        m._stop_monitoring = False
        return m

    def _tmp_path(self):
        import tempfile
        return str(Path(tempfile.mkdtemp()) / "nm.json")

    def test_get_status(self):
        m = self._make()
        m.is_online = True
        with mock.patch.object(m, "measure_latency", return_value=10.0), \
                mock.patch.object(m, "check_dns", return_value="1.2.3.4"):
            s = m.get_status()
        self.assertTrue(s["online"])
        self.assertEqual(s["latency_ms"], 10.0)
        self.assertEqual(s["dns_resolved"], "1.2.3.4")
        self.assertEqual(s["endpoints"], 3)
        self.assertFalse(s["monitoring_active"])  # thread not alive
        m.stop_monitoring()

    def test_get_status_monitoring_active(self):
        m = self._make()
        t = mock.MagicMock()
        t.is_alive.return_value = True
        m._monitor_thread = t
        with mock.patch.object(m, "measure_latency", return_value=None), \
                mock.patch.object(m, "check_dns", return_value=None):
            s = m.get_status()
        self.assertTrue(s["monitoring_active"])
        m.stop_monitoring()

    def test_get_status_no_latency(self):
        m = self._make()
        with mock.patch.object(m, "measure_latency", return_value=None), \
                mock.patch.object(m, "check_dns", return_value=None):
            s = m.get_status()
        self.assertIsNone(s["latency_ms"])
        self.assertIsNone(s["dns_resolved"])
        m.stop_monitoring()


class GetHistoryEndpointStatsTests(unittest.TestCase):
    def _make(self):
        p = self._tmp_path()
        m = nm.NetworkMonitor(storage_file=p)
        m._stop_monitoring = False
        return m

    def _tmp_path(self):
        import tempfile
        return str(Path(tempfile.mkdtemp()) / "nm.json")

    def test_get_history(self):
        m = self._make()
        m.history = [{"i": i} for i in range(10)]
        self.assertEqual(len(m.get_history(3)), 3)
        self.assertEqual(m.get_history(3)[0]["i"], 7)
        m.stop_monitoring()

    def test_get_history_default_50(self):
        m = self._make()
        m.history = [{"i": i} for i in range(60)]
        self.assertEqual(len(m.get_history()), 50)
        m.stop_monitoring()

    def test_add_endpoint(self):
        m = self._make()
        with mock.patch.object(nm, "logger") as lg:
            m.add_endpoint("custom", "9.9.9.9", 80)
        self.assertEqual(m.endpoints[-1], {"name": "custom", "host": "9.9.9.9", "port": 80})
        lg.info.assert_called_once()
        m.stop_monitoring()

    def test_remove_endpoint(self):
        m = self._make()
        m.endpoints = [{"name": "a"}, {"name": "b"}]
        with mock.patch.object(nm, "logger") as lg:
            m.remove_endpoint("a")
        self.assertEqual(m.endpoints, [{"name": "b"}])
        lg.info.assert_called_once()
        m.stop_monitoring()

    def test_get_statistics_empty(self):
        m = self._make()
        m.is_online = False
        s = m.get_statistics()
        self.assertEqual(s["total_checks"], 0)
        self.assertEqual(s["online_checks"], 0)
        self.assertEqual(s["offline_checks"], 0)
        self.assertEqual(s["current_status"], "offline")
        self.assertIsNone(s["average_latency_ms"])
        self.assertIsNone(s["min_latency_ms"])
        self.assertIsNone(s["max_latency_ms"])
        m.stop_monitoring()

    def test_get_statistics_with_data(self):
        m = self._make()
        m.is_online = True
        m.history = [
            {"online": True, "latency_ms": 10.0},
            {"online": False, "latency_ms": 20.0},
            {"online": True, "latency_ms": None},
        ]
        s = m.get_statistics()
        self.assertEqual(s["total_checks"], 3)
        self.assertEqual(s["online_checks"], 2)
        self.assertEqual(s["offline_checks"], 1)
        self.assertEqual(s["current_status"], "online")
        self.assertEqual(s["average_latency_ms"], 15.0)
        self.assertEqual(s["min_latency_ms"], 10.0)
        self.assertEqual(s["max_latency_ms"], 20.0)
        m.stop_monitoring()

    def test_get_statistics_no_latency(self):
        m = self._make()
        m.is_online = False
        m.history = [{"online": False, "latency_ms": None}]
        s = m.get_statistics()
        self.assertIsNone(s["average_latency_ms"])
        self.assertIsNone(s["min_latency_ms"])
        self.assertIsNone(s["max_latency_ms"])
        m.stop_monitoring()


class ModuleLevelTests(unittest.TestCase):
    def test_get_network_monitor_singleton(self):
        nm._network_monitor = None
        a = nm.get_network_monitor()
        b = nm.get_network_monitor()
        self.assertIs(a, b)
        nm._network_monitor = None

    def test_check_connectivity_module(self):
        with mock.patch.object(nm, "get_network_monitor") as gnm:
            m = mock.MagicMock()
            m.check_connectivity.return_value = True
            gnm.return_value = m
            self.assertTrue(nm.check_connectivity())
        m.check_connectivity.assert_called_once()

    def test_measure_latency_module(self):
        with mock.patch.object(nm, "get_network_monitor") as gnm:
            m = mock.MagicMock()
            m.measure_latency.return_value = 5.0
            gnm.return_value = m
            self.assertEqual(nm.measure_latency(), 5.0)

    def test_is_online_module(self):
        with mock.patch.object(nm, "get_network_monitor") as gnm:
            m = mock.MagicMock()
            m.is_online = True
            gnm.return_value = m
            self.assertTrue(nm.is_online())

    def test_get_status_module(self):
        with mock.patch.object(nm, "get_network_monitor") as gnm:
            m = mock.MagicMock()
            m.get_status.return_value = {"online": True}
            gnm.return_value = m
            self.assertEqual(nm.get_status(), {"online": True})

    def test_get_statistics_module(self):
        with mock.patch.object(nm, "get_network_monitor") as gnm:
            m = mock.MagicMock()
            m.get_statistics.return_value = {"total": 1}
            gnm.return_value = m
            self.assertEqual(nm.get_statistics(), {"total": 1})


if __name__ == "__main__":
    unittest.main()
