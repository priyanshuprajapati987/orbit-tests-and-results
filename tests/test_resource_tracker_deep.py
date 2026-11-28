"""Deep tests for orbit/orbit/core/resource_tracker.py (Loop 21/5)."""

import json
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from orbit.orbit.core import resource_tracker as rt


class InitLoadSaveTests(unittest.TestCase):
    def _tmp(self):
        import tempfile
        d = tempfile.mkdtemp()
        return str(Path(d) / "resource_usage.json")

    def test_init_defaults(self):
        p = self._tmp()
        r = rt.ResourceTracker(storage_file=p)
        self.assertEqual(r.usage, {})
        self.assertEqual(r.budgets, {})
        self.assertEqual(r.alerts, [])
        # default quotas set
        self.assertIn("openrouter", r.quotas)
        self.assertIn("gemini", r.quotas)
        self.assertIn("ollama", r.quotas)
        r._save_data()  # ensure no crash (optional)

    def test_init_loads_existing(self):
        p = self._tmp()
        Path(p).parent.mkdir(parents=True, exist_ok=True)
        Path(p).write_text(json.dumps({
            "usage": {"groq": [{"date": "2026-01-01", "resource_type": "api_call",
                                "amount": 1, "cost": 0.1, "timestamp": "t",
                                "metadata": {}}]},
            "quotas": {"groq": {"daily_calls": 5}},
            "budgets": {"groq": 10.0},
            "alerts": [{"a": 1}],
        }), encoding="utf-8")
        r = rt.ResourceTracker(storage_file=p)
        self.assertIn("groq", r.usage)
        self.assertEqual(r.quotas["groq"], {"daily_calls": 5})
        self.assertEqual(r.budgets["groq"], 10.0)
        self.assertEqual(r.alerts, [{"a": 1}])

    def test_init_load_corrupt(self):
        p = self._tmp()
        Path(p).parent.mkdir(parents=True, exist_ok=True)
        Path(p).write_text("{bad", encoding="utf-8")
        with mock.patch.object(rt, "logger") as lg:
            r = rt.ResourceTracker(storage_file=p)
        lg.error.assert_called()
        # defaults still set
        self.assertIn("openrouter", r.quotas)

    def test_init_load_missing(self):
        p = self._tmp()
        r = rt.ResourceTracker(storage_file=p)
        self.assertIn("openrouter", r.quotas)

    def test_set_default_quotas_does_not_overwrite(self):
        p = self._tmp()
        Path(p).parent.mkdir(parents=True, exist_ok=True)
        Path(p).write_text(json.dumps({
            "usage": {},
            "quotas": {"openrouter": {"daily_calls": 999}},
            "budgets": {},
            "alerts": [],
        }), encoding="utf-8")
        r = rt.ResourceTracker(storage_file=p)
        self.assertEqual(r.quotas["openrouter"]["daily_calls"], 999)

    def test_save_success(self):
        p = self._tmp()
        r = rt.ResourceTracker(storage_file=p)
        r.usage["groq"] = [{"date": "2026-01-01", "resource_type": "api_call",
                            "amount": 1, "cost": 0.1, "timestamp": "t",
                            "metadata": {}}]
        r._save_data()
        self.assertTrue(Path(p).exists())
        data = json.loads(Path(p).read_text("utf-8"))
        self.assertEqual(len(data["usage"]["groq"]), 1)

    def test_save_caps_usage_10000(self):
        p = self._tmp()
        r = rt.ResourceTracker(storage_file=p)
        r.usage["groq"] = [{"i": i} for i in range(10005)]
        r._save_data()
        data = json.loads(Path(p).read_text("utf-8"))
        self.assertEqual(len(data["usage"]["groq"]), 10000)

    def test_save_caps_alerts_100(self):
        p = self._tmp()
        r = rt.ResourceTracker(storage_file=p)
        r.alerts = [{"i": i} for i in range(150)]
        r._save_data()
        data = json.loads(Path(p).read_text("utf-8"))
        self.assertEqual(len(data["alerts"]), 100)

    def test_save_failure_logged(self):
        p = self._tmp()
        r = rt.ResourceTracker(storage_file=p)
        with mock.patch("builtins.open", side_effect=OSError("boom")), \
                mock.patch.object(rt, "logger") as lg:
            r._save_data()
        lg.error.assert_called_once()

    def test_path_method_none(self):
        # _ensure_storage_dir
        p = self._tmp()
        r = rt.ResourceTracker(storage_file=p)
        self.assertTrue(Path(p).parent.exists())


class RecordUsageTests(unittest.TestCase):
    def _make(self):
        p = self._tmp_path()
        r = rt.ResourceTracker(storage_file=p)
        return r

    def _tmp_path(self):
        import tempfile
        return str(Path(tempfile.mkdtemp()) / "ru.json")

    def test_record_basic(self):
        r = self._make()
        r.record_usage("groq", "api_call", 1.0, cost=0.5, metadata={"k": "v"})
        self.assertIn("groq", r.usage)
        self.assertEqual(len(r.usage["groq"]), 1)
        e = r.usage["groq"][0]
        self.assertEqual(e["resource_type"], "api_call")
        self.assertEqual(e["amount"], 1.0)
        self.assertEqual(e["cost"], 0.5)
        self.assertEqual(e["metadata"], {"k": "v"})
        self.assertIn("date", e)
        self.assertIn("timestamp", e)

    def test_record_default_metadata(self):
        r = self._make()
        r.record_usage("groq", "api_call", 1.0)
        e = r.usage["groq"][0]
        self.assertEqual(e["metadata"], {})

    def test_record_cap_providers(self):
        r = self._make()
        # fill to MAX_PROVIDERS
        for i in range(rt.ResourceTracker.MAX_PROVIDERS):
            r.usage[f"p{i}"] = []
        with mock.patch.object(rt, "logger") as lg:
            r.record_usage("newprovider", "api_call", 1.0)
        lg.warning.assert_called_once()
        self.assertNotIn("newprovider", r.usage)

    def test_record_cap_entries_10000(self):
        r = self._make()
        r.usage["groq"] = [{"i": i} for i in range(10001)]
        r.record_usage("groq", "api_call", 1.0)
        self.assertEqual(len(r.usage["groq"]), 10000)

    def test_record_triggers_quota_alert_calls(self):
        r = self._make()
        r.quotas["groq"] = {"daily_calls": 1}
        r.record_usage("groq", "api_call", 1.0)
        # second call exceeds
        r.record_usage("groq", "api_call", 1.0)
        self.assertGreaterEqual(len(r.alerts), 1)
        self.assertIn("daily_calls", r.alerts[-1]["quota_type"])

    def test_record_triggers_quota_alert_tokens(self):
        r = self._make()
        r.quotas["groq"] = {"daily_tokens": 5}
        r.record_usage("groq", "token", 10.0)
        self.assertGreaterEqual(len(r.alerts), 1)
        self.assertIn("daily_tokens", r.alerts[-1]["quota_type"])

    def test_record_triggers_quota_alert_cost(self):
        r = self._make()
        r.quotas["groq"] = {"daily_cost": 0.5}
        r.record_usage("groq", "api_call", 1.0, cost=1.0)
        self.assertGreaterEqual(len(r.alerts), 1)
        self.assertIn("daily_cost", r.alerts[-1]["quota_type"])

    def test_record_quota_no_alert_below(self):
        r = self._make()
        r.quotas["groq"] = {"daily_calls": 100}
        r.record_usage("groq", "api_call", 1.0)
        self.assertEqual(len(r.alerts), 0)

    def test_record_no_quota_no_alert(self):
        r = self._make()
        # remove quota
        r.quotas.pop("groq", None)
        r.record_usage("groq", "api_call", 1.0)
        self.assertEqual(len(r.alerts), 0)

    def test_add_alert_dedup_within_5min(self):
        r = self._make()
        from datetime import datetime
        now = datetime.now().isoformat()
        r.alerts.append({"provider": "groq", "quota_type": "daily_calls",
                         "timestamp": now})
        r._add_alert("groq", "daily_calls", 5, 3)
        # deduped -> no new alert
        self.assertEqual(len(r.alerts), 1)

    def test_add_alert_after_5min(self):
        r = self._make()
        from datetime import datetime, timedelta
        old = (datetime.now() - timedelta(minutes=10)).isoformat()
        r.alerts.append({"provider": "groq", "quota_type": "daily_calls",
                         "timestamp": old})
        r._add_alert("groq", "daily_calls", 5, 3)
        self.assertEqual(len(r.alerts), 2)

    def test_add_alert_invalid_timestamp(self):
        r = self._make()
        r.alerts.append({"provider": "groq", "quota_type": "daily_calls",
                         "timestamp": "bad"})
        r._add_alert("groq", "daily_calls", 5, 3)
        self.assertEqual(len(r.alerts), 2)

    def test_add_alert_logs_warning(self):
        r = self._make()
        with mock.patch.object(rt, "logger") as lg:
            r._add_alert("groq", "daily_calls", 5, 3)
        lg.warning.assert_called_once()

    def test_add_alert_checks_last_10(self):
        r = self._make()
        # 15 alerts, dedup only checks last 10
        for i in range(15):
            r.alerts.append({"provider": "other", "quota_type": "x",
                             "timestamp": "2020-01-01T00:00:00"})
        r._add_alert("groq", "daily_calls", 5, 3)
        self.assertEqual(len(r.alerts), 16)


class GetUsageSummaryTests(unittest.TestCase):
    def _make(self):
        p = self._tmp_path()
        r = rt.ResourceTracker(storage_file=p)
        return r

    def _tmp_path(self):
        import tempfile
        return str(Path(tempfile.mkdtemp()) / "ru.json")

    def test_summary_specific_provider(self):
        r = self._make()
        r.record_usage("groq", "api_call", 1.0, cost=0.5)
        r.record_usage("groq", "token", 10.0, cost=0.1)
        s = r.get_usage_summary("groq", days=7)
        self.assertIn("groq", s)
        self.assertEqual(s["groq"]["total_calls"], 2)
        self.assertEqual(s["groq"]["total_tokens"], 10.0)
        self.assertAlmostEqual(s["groq"]["total_cost"], 0.6, places=5)
        self.assertAlmostEqual(s["groq"]["avg_daily_calls"], 2 / 7, places=5)
        self.assertAlmostEqual(s["groq"]["avg_daily_cost"], 0.6 / 7, places=5)

    def test_summary_all_providers(self):
        r = self._make()
        r.record_usage("groq", "api_call", 1.0, cost=0.5)
        r.record_usage("gemini", "api_call", 1.0, cost=0.2)
        s = r.get_usage_summary(days=7)
        self.assertIn("groq", s)
        self.assertIn("gemini", s)

    def test_summary_empty(self):
        r = self._make()
        s = r.get_usage_summary("groq", days=7)
        self.assertEqual(s["groq"]["total_calls"], 0)
        self.assertEqual(s["groq"]["total_tokens"], 0)
        self.assertEqual(s["groq"]["total_cost"], 0)

    def test_summary_days_zero_no_division(self):
        r = self._make()
        r.record_usage("groq", "api_call", 1.0, cost=0.5)
        s = r.get_usage_summary("groq", days=0)
        self.assertEqual(s["groq"]["avg_daily_calls"], 0)
        self.assertEqual(s["groq"]["avg_daily_cost"], 0)

    def test_summary_cutoff_filters_old(self):
        r = self._make()
        # seed an old entry
        from datetime import datetime, timedelta
        old_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        r.usage["groq"] = [{"date": old_date, "resource_type": "api_call",
                            "amount": 1, "cost": 0.5, "timestamp": "t",
                            "metadata": {}}]
        s = r.get_usage_summary("groq", days=7)
        self.assertEqual(s["groq"]["total_calls"], 0)


class GetDailyUsageTests(unittest.TestCase):
    def _make(self):
        p = self._tmp_path()
        r = rt.ResourceTracker(storage_file=p)
        return r

    def _tmp_path(self):
        import tempfile
        return str(Path(tempfile.mkdtemp()) / "ru.json")

    def test_default_date_today(self):
        r = self._make()
        r.record_usage("groq", "api_call", 1.0, cost=0.5)
        d = r.get_daily_usage("groq")
        self.assertEqual(d["date"], __import__("datetime").datetime.now().strftime("%Y-%m-%d"))
        self.assertEqual(d["calls"], 1)
        self.assertEqual(d["tokens"], 0)
        self.assertEqual(d["cost"], 0.5)

    def test_specific_date(self):
        r = self._make()
        r.record_usage("groq", "api_call", 1.0, cost=0.5)
        d = r.get_daily_usage("groq", "2020-01-01")
        self.assertEqual(d["calls"], 0)
        self.assertEqual(d["provider"], "groq")

    def test_tokens_summed(self):
        r = self._make()
        r.record_usage("groq", "token", 10.0, cost=0.1)
        r.record_usage("groq", "token", 5.0, cost=0.05)
        d = r.get_daily_usage("groq")
        self.assertEqual(d["tokens"], 15.0)
        self.assertEqual(d["calls"], 2)


class CheckBudgetTests(unittest.TestCase):
    def _make(self):
        p = self._tmp_path()
        r = rt.ResourceTracker(storage_file=p)
        return r

    def _tmp_path(self):
        import tempfile
        return str(Path(tempfile.mkdtemp()) / "ru.json")

    def test_no_budget(self):
        r = self._make()
        self.assertEqual(r.check_budget("groq"), {"status": "no_budget",
                                                  "message": "No budget set"})

    def test_ok(self):
        r = self._make()
        r.set_budget("groq", 10.0)
        r.record_usage("groq", "api_call", 1.0, cost=1.0)
        b = r.check_budget("groq")
        self.assertEqual(b["status"], "ok")
        self.assertEqual(b["budget"], 10.0)
        self.assertEqual(b["spent"], 1.0)
        self.assertEqual(b["remaining"], 9.0)
        self.assertAlmostEqual(b["percentage"], 10.0, places=5)

    def test_warning(self):
        r = self._make()
        r.set_budget("groq", 10.0)
        r.record_usage("groq", "api_call", 1.0, cost=8.0)
        b = r.check_budget("groq")
        self.assertEqual(b["status"], "warning")

    def test_critical(self):
        r = self._make()
        r.set_budget("groq", 10.0)
        r.record_usage("groq", "api_call", 1.0, cost=9.5)
        b = r.check_budget("groq")
        self.assertEqual(b["status"], "critical")

    def test_zero_budget_percentage(self):
        r = self._make()
        r.set_budget("groq", 0.0)
        r.record_usage("groq", "api_call", 1.0, cost=1.0)
        b = r.check_budget("groq")
        self.assertEqual(b["percentage"], 0)


class SetBudgetQuotaTests(unittest.TestCase):
    def _make(self):
        p = self._tmp_path()
        r = rt.ResourceTracker(storage_file=p)
        return r

    def _tmp_path(self):
        import tempfile
        return str(Path(tempfile.mkdtemp()) / "ru.json")

    def test_set_budget(self):
        r = self._make()
        r.set_budget("groq", 5.0)
        self.assertEqual(r.budgets["groq"], 5.0)
        self.assertTrue(Path(r.storage_file).exists())

    def test_set_budget_logs(self):
        r = self._make()
        with mock.patch.object(rt, "logger") as lg:
            r.set_budget("groq", 5.0)
        lg.info.assert_called_once()

    def test_set_quota_new_provider(self):
        r = self._make()
        r.set_quota("newp", daily_calls=10, daily_tokens=100, daily_cost=1.0)
        self.assertEqual(r.quotas["newp"], {"daily_calls": 10, "daily_tokens": 100,
                                            "daily_cost": 1.0})

    def test_set_quota_partial(self):
        r = self._make()
        r.quotas["groq"] = {"daily_calls": 5}
        r.set_quota("groq", daily_cost=2.0)
        self.assertEqual(r.quotas["groq"], {"daily_calls": 5, "daily_cost": 2.0})

    def test_set_quota_logs(self):
        r = self._make()
        with mock.patch.object(rt, "logger") as lg:
            r.set_quota("groq", daily_calls=5)
        lg.info.assert_called_once()


class GetAlertsTests(unittest.TestCase):
    def _make(self):
        p = self._tmp_path()
        r = rt.ResourceTracker(storage_file=p)
        return r

    def _tmp_path(self):
        import tempfile
        return str(Path(tempfile.mkdtemp()) / "ru.json")

    def test_get_alerts_empty(self):
        r = self._make()
        self.assertEqual(r.get_alerts(), [])

    def test_get_alerts_limit(self):
        r = self._make()
        r.alerts = [{"i": i} for i in range(30)]
        self.assertEqual(len(r.get_alerts(5)), 5)
        self.assertEqual(r.get_alerts(5)[-1]["i"], 29)


class GetCostForecastTests(unittest.TestCase):
    def _make(self):
        p = self._tmp_path()
        r = rt.ResourceTracker(storage_file=p)
        return r

    def _tmp_path(self):
        import tempfile
        return str(Path(tempfile.mkdtemp()) / "ru.json")

    def test_no_data(self):
        r = self._make()
        fc = r.get_cost_forecast("groq", days=30)
        self.assertEqual(fc["provider"], "groq")
        self.assertEqual(fc["forecasted_cost"], 0.0)

    def test_with_data(self):
        r = self._make()
        r.record_usage("groq", "api_call", 1.0, cost=0.5)
        fc = r.get_cost_forecast("groq", days=30)
        self.assertEqual(fc["provider"], "groq")
        self.assertEqual(fc["forecast_days"], 30)
        self.assertAlmostEqual(fc["avg_daily_cost"], 0.5 / 7, places=5)
        self.assertAlmostEqual(fc["forecasted_cost"], (0.5 / 7) * 30, places=5)


class GetOptimizationSuggestionsTests(unittest.TestCase):
    def _make(self):
        p = self._tmp_path()
        r = rt.ResourceTracker(storage_file=p)
        return r

    def _tmp_path(self):
        import tempfile
        return str(Path(tempfile.mkdtemp()) / "ru.json")

    def test_no_suggestions(self):
        r = self._make()
        r.record_usage("groq", "api_call", 1.0, cost=0.1)
        s = r.get_optimization_suggestions()
        self.assertEqual(s, ["All resources within normal limits"])

    def test_critical_suggestion(self):
        r = self._make()
        r.set_budget("groq", 1.0)
        r.record_usage("groq", "api_call", 1.0, cost=0.95)
        s = r.get_optimization_suggestions()
        self.assertTrue(any("Budget critical" in x for x in s))

    def test_high_usage_suggestion(self):
        r = self._make()
        r.set_budget("groq", 10.0)
        r.record_usage("groq", "api_call", 1.0, cost=6.0)
        s = r.get_optimization_suggestions()
        self.assertTrue(any("High usage" in x for x in s))

    def test_both_suggestions(self):
        r = self._make()
        r.set_budget("groq", 1.0)
        r.record_usage("groq", "api_call", 1.0, cost=0.95)
        s = r.get_optimization_suggestions()
        self.assertTrue(any("Budget critical" in x for x in s))
        self.assertTrue(any("High usage" in x for x in s))


class ModuleLevelTests(unittest.TestCase):
    def test_record_usage(self):
        with mock.patch("orbit.orbit.core.resource_tracker.get_resource_tracker") as g:
            m = mock.MagicMock()
            g.return_value = m
            rt.record_usage("p", "api_call", 1.0, 0.5, {"k": "v"})
        m.record_usage.assert_called_once_with("p", "api_call", 1.0, 0.5, {"k": "v"})

    def test_get_usage_summary(self):
        with mock.patch("orbit.orbit.core.resource_tracker.get_resource_tracker") as g:
            m = mock.MagicMock()
            m.get_usage_summary.return_value = {"p": {}}
            g.return_value = m
            r = rt.get_usage_summary("p", 7)
        self.assertEqual(r, {"p": {}})
        m.get_usage_summary.assert_called_once_with("p", 7)

    def test_check_budget(self):
        with mock.patch("orbit.orbit.core.resource_tracker.get_resource_tracker") as g:
            m = mock.MagicMock()
            m.check_budget.return_value = {"status": "ok"}
            g.return_value = m
            r = rt.check_budget("p")
        self.assertEqual(r, {"status": "ok"})

    def test_set_budget(self):
        with mock.patch("orbit.orbit.core.resource_tracker.get_resource_tracker") as g:
            m = mock.MagicMock()
            g.return_value = m
            rt.set_budget("p", 5.0)
        m.set_budget.assert_called_once_with("p", 5.0)

    def test_get_cost_forecast(self):
        with mock.patch("orbit.orbit.core.resource_tracker.get_resource_tracker") as g:
            m = mock.MagicMock()
            m.get_cost_forecast.return_value = {"forecast": 10}
            g.return_value = m
            r = rt.get_cost_forecast("p", 30)
        self.assertEqual(r, {"forecast": 10})
        m.get_cost_forecast.assert_called_once_with("p", 30)

    def test_get_resource_tracker_singleton(self):
        rt._resource_tracker = None
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d) / "ru.json"
        with mock.patch("orbit.orbit.core.resource_tracker.ResourceTracker",
                        wraps=rt.ResourceTracker) as C:
            # can't inject storage_file easily; just call (creates orbit_data)
            pass
        a = rt.get_resource_tracker()
        b = rt.get_resource_tracker()
        self.assertIs(a, b)
        rt._resource_tracker = None


if __name__ == "__main__":
    unittest.main()
