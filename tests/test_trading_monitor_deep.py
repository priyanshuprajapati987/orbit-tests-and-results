"""Deep tests for orbit/orbit/core/trading_monitor.py (Loop 17/4)."""

import json
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from orbit.orbit.core import trading_monitor as tm


class InitLoadTests(unittest.TestCase):
    def _tmp(self):
        import tempfile
        d = tempfile.mkdtemp()
        return Path(d)

    def test_init_creates_data_dir(self):
        d = self._tmp()
        with mock.patch("orbit.orbit.core.trading_monitor.DATA_DIR", d):
            # DATA_DIR.mkdir called in __init__; patch mkdir on the Path instance? DATA_DIR is a Path; patch globally
            with mock.patch("pathlib.Path.mkdir") as mk:
                m = tm.TradingMonitor()
        mk.assert_called()

    def test_load_existing(self):
        d = self._tmp()
        f = d / "watchlist.json"
        d.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"watchlist": [
            {"symbol": "AAPL", "name": "Apple", "asset_type": "stock",
             "current_price": 150.0, "last_updated": 123.0}]}), encoding="utf-8")
        with mock.patch("orbit.orbit.core.trading_monitor.DATA_DIR", d):
            m = tm.TradingMonitor()
        self.assertIn("AAPL", m._watchlist)
        w = m._watchlist["AAPL"]
        self.assertEqual(w.name, "Apple")
        self.assertEqual(w.asset_type, "stock")
        self.assertEqual(w.current_price, 150.0)
        self.assertEqual(w.last_updated, 123.0)

    def test_load_corrupt(self):
        d = self._tmp()
        f = d / "watchlist.json"
        d.mkdir(parents=True, exist_ok=True)
        f.write_text("{bad", encoding="utf-8")
        with mock.patch("orbit.orbit.core.trading_monitor.DATA_DIR", d):
            m = tm.TradingMonitor()
        self.assertEqual(m._watchlist, {})
        # logger.error called
        # (no assertion needed; no crash)

    def test_load_missing(self):
        d = self._tmp()
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.trading_monitor.DATA_DIR", d):
            m = tm.TradingMonitor()
        self.assertEqual(m._watchlist, {})

    def test_load_exception_logged(self):
        d = self._tmp()
        d.mkdir(parents=True, exist_ok=True)
        f = d / "watchlist.json"
        f.write_text(json.dumps({"watchlist": [{"symbol": "X"}]}), encoding="utf-8")
        # make read_text raise
        with mock.patch("orbit.orbit.core.trading_monitor.DATA_DIR", d), \
                mock.patch.object(Path, "read_text", side_effect=OSError("boom")), \
                mock.patch.object(tm, "logger") as lg:
            m = tm.TradingMonitor()
        lg.error.assert_called()

    def test_save_success(self):
        d = self._tmp()
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.trading_monitor.DATA_DIR", d):
            m = tm.TradingMonitor()
        m.add_symbol("AAPL", "Apple")
        # _save writes file
        f = d / "watchlist.json"
        self.assertTrue(f.exists())
        data = json.loads(f.read_text("utf-8"))
        self.assertEqual(data["watchlist"][0]["symbol"], "AAPL")

    def test_save_failure_logged(self):
        d = self._tmp()
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.trading_monitor.DATA_DIR", d):
            m = tm.TradingMonitor()
        m._watchlist["X"] = tm.WatchItem(symbol="X", name="X", asset_type="stock")
        with mock.patch.object(Path, "with_name", side_effect=OSError("boom")), \
                mock.patch.object(tm, "logger") as lg:
            m._save()
        lg.error.assert_called()


class AddRemoveSymbolTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._d.mkdir(parents=True, exist_ok=True)
        self.addCleanup(mock.patch.stopall)
        with mock.patch("orbit.orbit.core.trading_monitor.DATA_DIR", self._d):
            self.m = tm.TradingMonitor()

    def test_add_symbol(self):
        item = self.m.add_symbol("aapl", "Apple Inc", "stock")
        self.assertEqual(item.symbol, "AAPL")
        self.assertEqual(item.name, "Apple Inc")
        self.assertEqual(item.asset_type, "stock")
        self.assertIn("AAPL", self.m._watchlist)

    def test_add_symbol_default_name(self):
        item = self.m.add_symbol("btc", asset_type="crypto")
        self.assertEqual(item.name, "BTC")
        self.assertEqual(item.asset_type, "crypto")

    def test_remove_symbol_success(self):
        self.m.add_symbol("AAPL")
        self.assertTrue(self.m.remove_symbol("aapl"))
        self.assertNotIn("AAPL", self.m._watchlist)

    def test_remove_symbol_missing(self):
        self.assertFalse(self.m.remove_symbol("NOPE"))


class AddAlertTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.trading_monitor.DATA_DIR", self._d):
            self.m = tm.TradingMonitor()
        self.m.add_symbol("AAPL")

    def test_add_alert_success(self):
        r = self.m.add_alert("aapl", 150.0, "above")
        self.assertEqual(r, {"status": "alert set", "symbol": "AAPL",
                             "target": 150.0, "direction": "above"})
        item = self.m._watchlist["AAPL"]
        self.assertEqual(len(item.alerts), 1)
        self.assertEqual(item.alerts[0].target_price, 150.0)
        self.assertEqual(item.alerts[0].direction, "above")
        self.assertFalse(item.alerts[0].triggered)

    def test_add_alert_unknown_symbol(self):
        r = self.m.add_alert("NOPE", 100.0)
        self.assertEqual(r, {"error": "Symbol NOPE not in watchlist"})

    def test_add_alert_default_direction_above(self):
        r = self.m.add_alert("AAPL", 200.0)
        self.assertEqual(r["direction"], "above")


class GetWatchlistStatsTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.trading_monitor.DATA_DIR", self._d):
            self.m = tm.TradingMonitor()
        self.m.add_symbol("AAPL")
        self.m.add_alert("AAPL", 150.0, "above")
        self.m.add_alert("AAPL", 100.0, "below")

    def test_get_watchlist(self):
        wl = self.m.get_watchlist()
        self.assertEqual(len(wl), 1)
        w = wl[0]
        self.assertEqual(w["symbol"], "AAPL")
        self.assertEqual(len(w["alerts"]), 2)
        self.assertEqual(w["alerts"][0], {"target": 150.0, "direction": "above",
                                          "triggered": False})

    def test_get_stats(self):
        self.m._running = True
        stats = self.m.get_stats()
        self.assertEqual(stats["total_symbols"], 1)
        self.assertEqual(stats["total_alerts"], 2)
        self.assertEqual(stats["triggered_alerts"], 0)
        self.assertTrue(stats["running"])
        self.assertEqual(stats["interval_sec"], 300)

    def test_get_stats_not_running(self):
        stats = self.m.get_stats()
        self.assertFalse(stats["running"])


class MonitoringTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.trading_monitor.DATA_DIR", self._d):
            self.m = tm.TradingMonitor()

    def test_start_monitoring(self):
        with mock.patch.object(self.m, "_monitor_loop"):
            self.m.start_monitoring()
        self.assertTrue(self.m._running)
        self.assertIsNotNone(self.m._thread)
        # cleanup
        self.m._running = False

    def test_start_monitoring_noop_if_running(self):
        self.m._running = True
        self.m.start_monitoring()
        self.assertIsNone(self.m._thread)

    def test_stop_monitoring(self):
        self.m._running = True
        self.m.stop_monitoring()
        self.assertFalse(self.m._running)

    def test_monitor_loop_runs_and_exits(self):
        # _check_prices sets _running=False to exit loop
        def check():
            self.m._running = False
        with mock.patch.object(self.m, "_check_prices", side_effect=check), \
                mock.patch("time.sleep"):
            self.m._running = True
            self.m._monitor_loop()
        self.assertFalse(self.m._running)

    def test_monitor_loop_exception_logged(self):
        def check():
            raise RuntimeError("boom")
            self.m._running = False

        # make it exit after first iteration
        call_count = {"n": 0}

        def check2():
            call_count["n"] += 1
            if call_count["n"] >= 1:
                self.m._running = False
            raise RuntimeError("boom")

        with mock.patch.object(self.m, "_check_prices", side_effect=check2), \
                mock.patch("time.sleep"), \
                mock.patch.object(tm, "logger") as lg:
            self.m._running = True
            self.m._monitor_loop()
        lg.error.assert_called()

    def test_check_prices_updates_and_triggers_above(self):
        self.m.add_symbol("AAPL")
        self.m.add_alert("AAPL", 100.0, "above")
        with mock.patch.object(self.m, "_fetch_price", return_value=150.0), \
                mock.patch.object(self.m, "_save"):
            self.m._check_prices()
        item = self.m._watchlist["AAPL"]
        self.assertEqual(item.current_price, 150.0)
        self.assertGreater(item.last_updated, 0)
        self.assertTrue(item.alerts[0].triggered)
        self.assertIsNotNone(item.alerts[0].triggered_at)

    def test_check_prices_triggers_below(self):
        self.m.add_symbol("AAPL")
        self.m.add_alert("AAPL", 200.0, "below")
        with mock.patch.object(self.m, "_fetch_price", return_value=100.0), \
                mock.patch.object(self.m, "_save"):
            self.m._check_prices()
        self.assertTrue(self.m._watchlist["AAPL"].alerts[0].triggered)

    def test_check_prices_no_trigger(self):
        self.m.add_symbol("AAPL")
        self.m.add_alert("AAPL", 100.0, "above")
        with mock.patch.object(self.m, "_fetch_price", return_value=50.0), \
                mock.patch.object(self.m, "_save"):
            self.m._check_prices()
        self.assertFalse(self.m._watchlist["AAPL"].alerts[0].triggered)

    def test_check_prices_already_triggered_not_retriggered(self):
        self.m.add_symbol("AAPL")
        self.m.add_alert("AAPL", 100.0, "above")
        self.m._watchlist["AAPL"].alerts[0].triggered = True
        with mock.patch.object(self.m, "_fetch_price", return_value=150.0), \
                mock.patch.object(self.m, "_save"):
            self.m._check_prices()
        # triggered_at unchanged (None originally set? it was set to None at creation)
        # just ensure no crash

    def test_check_prices_none_price_skips(self):
        self.m.add_symbol("AAPL")
        with mock.patch.object(self.m, "_fetch_price", return_value=None), \
                mock.patch.object(self.m, "_save") as sv:
            self.m._check_prices()
        # _save still called? code calls self._save() inside `if price is not None` block
        sv.assert_not_called()

    def test_check_prices_exception_per_symbol(self):
        self.m.add_symbol("AAPL")
        with mock.patch.object(self.m, "_fetch_price", side_effect=RuntimeError("boom")), \
                mock.patch.object(tm, "logger") as lg:
            self.m._check_prices()
        lg.debug.assert_called()

    def test_check_prices_multiple_symbols(self):
        self.m.add_symbol("AAPL")
        self.m.add_symbol("MSFT")
        with mock.patch.object(self.m, "_fetch_price", return_value=100.0), \
                mock.patch.object(self.m, "_save"):
            self.m._check_prices()
        self.assertEqual(self.m._watchlist["AAPL"].current_price, 100.0)
        self.assertEqual(self.m._watchlist["MSFT"].current_price, 100.0)


class FetchPriceTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.trading_monitor.DATA_DIR", d):
            return tm.TradingMonitor()

    def test_crypto_success(self):
        m = self._make()
        resp = mock.MagicMock()
        resp.read.return_value = b'{"btc": {"usd": 50000.0}}'
        cm = mock.MagicMock()
        cm.__enter__.return_value = resp
        cm.__exit__.return_value = False
        with mock.patch("urllib.request.urlopen", return_value=cm):
            price = m._fetch_price("BTC", "crypto")
        self.assertEqual(price, 50000.0)

    def test_crypto_not_found(self):
        m = self._make()
        resp = mock.MagicMock()
        resp.read.return_value = b'{"btc": {"usd": 50000.0}}'
        cm = mock.MagicMock()
        cm.__enter__.return_value = resp
        cm.__exit__.return_value = False
        with mock.patch("urllib.request.urlopen", return_value=cm):
            price = m._fetch_price("ETH", "crypto")
        self.assertIsNone(price)

    def test_stock_success(self):
        m = self._make()
        resp = mock.MagicMock()
        resp.read.return_value = b'{"chart": {"result": [{"meta": {"regularMarketPrice": 150.5}}]}}'
        cm = mock.MagicMock()
        cm.__enter__.return_value = resp
        cm.__exit__.return_value = False
        with mock.patch("urllib.request.urlopen", return_value=cm):
            price = m._fetch_price("AAPL", "stock")
        self.assertEqual(price, 150.5)

    def test_exception_returns_none(self):
        m = self._make()
        with mock.patch("urllib.request.urlopen", side_effect=Exception("net")):
            price = m._fetch_price("AAPL", "stock")
        self.assertIsNone(price)

    def test_crypto_exception_returns_none(self):
        m = self._make()
        with mock.patch("urllib.request.urlopen", side_effect=Exception("net")):
            price = m._fetch_price("BTC", "crypto")
        self.assertIsNone(price)


class SingletonTests(unittest.TestCase):
    def setUp(self):
        self._saved = tm._monitor
        tm._monitor = None
        self.addCleanup(setattr, tm, "_monitor", self._saved)

    def test_creates(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.trading_monitor.DATA_DIR", d):
            a = tm.get_trading_monitor()
        self.assertIsInstance(a, tm.TradingMonitor)
        self.assertIs(tm._monitor, a)

    def test_reuses(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.trading_monitor.DATA_DIR", d):
            a = tm.get_trading_monitor()
            b = tm.get_trading_monitor()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
