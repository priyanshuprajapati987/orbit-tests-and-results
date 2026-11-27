"""Deep tests for orbit/orbit/core/cost_tracker.py (Loop 17/2)."""

import json
import threading
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from orbit.orbit.core import cost_tracker as ct


class InitLoadTests(unittest.TestCase):
    def test_init_creates_data_dir(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d)
        with mock.patch("pathlib.Path.mkdir") as mk:
            c = ct.CostTracker(data_dir=p)
        mk.assert_called()
        self.assertTrue(hasattr(c, "_lock"))

    def test_init_loads_existing(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d)
        p.mkdir(parents=True, exist_ok=True)
        records_file = p / "records.json"
        records_file.write_text(json.dumps({
            "records": [{"timestamp": 1.0, "provider": "groq", "model": "m",
                         "agent": "a", "tokens_in": 10, "tokens_out": 5,
                         "cost_usd": 0.001, "latency_ms": 50}],
            "budget": {"daily_limit_usd": 5.0, "monthly_limit_usd": 100.0,
                       "alert_threshold_pct": 70.0},
            "daily": {"2026-01-01": 0.001},
            "monthly": {"2026-01": 0.001},
            "providers": {"groq": 0.001},
            "agents": {"a": 0.001},
        }), encoding="utf-8")
        c = ct.CostTracker(data_dir=p)
        self.assertEqual(len(c._records), 1)
        self.assertEqual(c._budget.daily_limit_usd, 5.0)
        self.assertEqual(c._budget.monthly_limit_usd, 100.0)
        self.assertEqual(c._budget.alert_threshold_pct, 70.0)
        self.assertEqual(c._daily_costs, {"2026-01-01": 0.001})
        self.assertEqual(c._monthly_costs, {"2026-01": 0.001})
        self.assertEqual(c._provider_costs["groq"], 0.001)
        self.assertEqual(c._agent_costs["a"], 0.001)

    def test_init_corrupt_load_ignored(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d)
        p.mkdir(parents=True, exist_ok=True)
        (p / "records.json").write_text("{bad", encoding="utf-8")
        c = ct.CostTracker(data_dir=p)
        self.assertEqual(len(c._records), 0)

    def test_init_missing_file(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d)
        p.mkdir(parents=True, exist_ok=True)
        c = ct.CostTracker(data_dir=p)
        self.assertEqual(len(c._records), 0)

    def test_load_budget_partial(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d)
        p.mkdir(parents=True, exist_ok=True)
        (p / "records.json").write_text(json.dumps({
            "records": [], "budget": {"daily_limit_usd": 7.0}}), encoding="utf-8")
        c = ct.CostTracker(data_dir=p)
        self.assertEqual(c._budget.daily_limit_usd, 7.0)
        # monthly/alert keep defaults
        self.assertEqual(c._budget.monthly_limit_usd, 200.0)
        self.assertEqual(c._budget.alert_threshold_pct, 80.0)

    def test_save_success(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d)
        p.mkdir(parents=True, exist_ok=True)
        c = ct.CostTracker(data_dir=p)
        c._records.append(ct.CostRecord(timestamp=1.0, provider="groq", model="m",
                                       agent="a", tokens_in=10, tokens_out=5,
                                       cost_usd=0.001))
        c._daily_costs["2026-01-01"] = 0.001
        c._save()
        data = json.loads((p / "records.json").read_text("utf-8"))
        self.assertEqual(len(data["records"]), 1)
        self.assertEqual(data["records"][0]["provider"], "groq")
        self.assertIn("budget", data)

    def test_save_failure_logged(self):
        c = ct.CostTracker.__new__(ct.CostTracker)
        c._data_dir = Path("/tmp/x")
        c._lock = threading.RLock()
        c._records = ct.deque(maxlen=10000)
        c._budget = ct.DailyBudget()
        c._daily_costs = {}
        c._monthly_costs = {}
        c._provider_costs = ct.defaultdict(float)
        c._agent_costs = ct.defaultdict(float)
        with mock.patch("pathlib.Path.mkdir", side_effect=OSError("boom")), \
                mock.patch.object(ct, "logger") as lg:
            c._save()
        lg.warning.assert_called_once()


class CalculateCostTests(unittest.TestCase):
    def test_known_provider(self):
        c = ct.CostTracker.__new__(ct.CostTracker)
        c._data_dir = None
        # groq: input 0.00005, output 0.00015 per 1K
        cost = c.calculate_cost("groq", 1000, 1000)
        self.assertAlmostEqual(cost, 0.00005 + 0.00015, places=6)

    def test_unknown_provider_falls_back_openrouter(self):
        c = ct.CostTracker.__new__(ct.CostTracker)
        cost = c.calculate_cost("unknown", 1000, 1000)
        # openrouter: 0.0001 + 0.0003
        self.assertAlmostEqual(cost, 0.0001 + 0.0003, places=6)

    def test_ollama_free(self):
        c = ct.CostTracker.__new__(ct.CostTracker)
        self.assertEqual(c.calculate_cost("ollama", 10000, 10000), 0.0)

    def test_zero_tokens(self):
        c = ct.CostTracker.__new__(ct.CostTracker)
        self.assertEqual(c.calculate_cost("groq", 0, 0), 0.0)


class RecordTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d)
        p.mkdir(parents=True, exist_ok=True)
        c = ct.CostTracker(data_dir=p)
        return c, p

    def test_record_basic(self):
        c, p = self._make()
        r = c.record("groq", "llama", "agent1", 1000, 500, latency_ms=50, source="manual")
        self.assertIsNone(r)  # record returns None on success
        self.assertEqual(len(c._records), 1)
        rec = c._records[0]
        self.assertEqual(rec.provider, "groq")
        self.assertEqual(rec.model, "llama")
        self.assertEqual(rec.agent, "agent1")
        self.assertEqual(rec.tokens_in, 1000)
        self.assertEqual(rec.tokens_out, 500)
        self.assertEqual(rec.latency_ms, 50)
        self.assertEqual(rec.source, "manual")
        # daily/monthly/provider/agent updated
        today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        month = __import__("datetime").datetime.now().strftime("%Y-%m")
        self.assertIn(today, c._daily_costs)
        self.assertIn(month, c._monthly_costs)
        self.assertGreater(c._provider_costs["groq"], 0)
        self.assertGreater(c._agent_costs["agent1"], 0)

    def test_record_idempotency_duplicate(self):
        c, p = self._make()
        c.record("groq", "m", "a", 100, 50, idempotency_key="k1")
        r2 = c.record("groq", "m", "a", 100, 50, idempotency_key="k1")
        self.assertEqual(r2, {"status": "duplicate_ignored", "key": "k1"})
        self.assertEqual(len(c._records), 1)

    def test_record_idempotency_different_keys(self):
        c, p = self._make()
        c.record("groq", "m", "a", 100, 50, idempotency_key="k1")
        c.record("groq", "m", "a", 100, 50, idempotency_key="k2")
        self.assertEqual(len(c._records), 2)

    def test_record_idempotency_cutoff(self):
        c, p = self._make()
        c._idem_keys["old"] = time.time() - 90000  # > 24h ago
        c.record("groq", "m", "a", 100, 50, idempotency_key="old")
        # old key expired -> treated as new
        self.assertEqual(len(c._records), 1)

    def test_record_no_idempotency_key(self):
        c, p = self._make()
        c.record("groq", "m", "a", 100, 50)
        self.assertEqual(len(c._records), 1)
        self.assertEqual(c._idem_keys, {})

    def test_record_defaults(self):
        c, p = self._make()
        c.record("groq", "m", "a", 10, 5)
        rec = c._records[0]
        self.assertEqual(rec.latency_ms, 0)
        self.assertEqual(rec.source, "system")
        self.assertGreater(rec.timestamp, 0)


class BudgetTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d)
        p.mkdir(parents=True, exist_ok=True)
        return ct.CostTracker(data_dir=p)

    def test_set_budget_daily(self):
        c = self._make()
        c.set_budget(daily=5.0)
        self.assertEqual(c._budget.daily_limit_usd, 5.0)

    def test_set_budget_monthly(self):
        c = self._make()
        c.set_budget(monthly=100.0)
        self.assertEqual(c._budget.monthly_limit_usd, 100.0)

    def test_set_budget_alert_pct(self):
        c = self._make()
        c.set_budget(alert_pct=90.0)
        self.assertEqual(c._budget.alert_threshold_pct, 90.0)

    def test_set_budget_all(self):
        c = self._make()
        c.set_budget(daily=1.0, monthly=2.0, alert_pct=50.0)
        self.assertEqual(c._budget.daily_limit_usd, 1.0)
        self.assertEqual(c._budget.monthly_limit_usd, 2.0)
        self.assertEqual(c._budget.alert_threshold_pct, 50.0)

    def test_check_budget_empty(self):
        c = self._make()
        b = c.check_budget()
        self.assertEqual(b["daily"]["spent"], 0.0)
        self.assertEqual(b["daily"]["limit"], 10.0)
        self.assertEqual(b["daily"]["percentage"], 0.0)
        self.assertFalse(b["daily"]["alert"])
        self.assertEqual(b["monthly"]["spent"], 0.0)
        self.assertFalse(b["monthly"]["alert"])

    def test_check_budget_with_spend(self):
        c = self._make()
        c.record("groq", "m", "a", 1000, 1000)  # some cost
        b = c.check_budget()
        self.assertGreaterEqual(b["daily"]["spent"], 0)
        self.assertIn("percentage", b["daily"])
        self.assertIn("alert", b["daily"])

    def test_check_budget_alert_triggered(self):
        c = self._make()
        c.set_budget(daily=0.000001, alert_pct=1.0)
        c.record("groq", "m", "a", 100000, 100000)
        b = c.check_budget()
        self.assertTrue(b["daily"]["alert"])

    def test_check_budget_monthly_alert(self):
        c = self._make()
        c.set_budget(monthly=0.000001, alert_pct=1.0)
        c.record("groq", "m", "a", 100000, 100000)
        b = c.check_budget()
        self.assertTrue(b["monthly"]["alert"])


class AnalyticsMethodsTests(unittest.TestCase):
    def _make_with_records(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d)
        p.mkdir(parents=True, exist_ok=True)
        c = ct.CostTracker(data_dir=p)
        c.record("groq", "m1", "agentA", 1000, 500, latency_ms=100)
        c.record("openrouter", "m2", "agentB", 2000, 1000, latency_ms=200)
        return c

    def test_get_daily_costs(self):
        c = self._make_with_records()
        r = c.get_daily_costs(3)
        self.assertEqual(len(r), 3)
        self.assertIn("date", r[0])
        self.assertIn("cost", r[0])

    def test_get_daily_costs_default_30(self):
        c = self._make_with_records()
        r = c.get_daily_costs()
        self.assertEqual(len(r), 30)

    def test_get_provider_breakdown(self):
        c = self._make_with_records()
        r = c.get_provider_breakdown()
        self.assertGreaterEqual(len(r), 2)
        for item in r:
            self.assertIn("provider", item)
            self.assertIn("cost", item)
            self.assertIn("percentage", item)
            self.assertIn("label", item)

    def test_get_provider_breakdown_empty(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d)
        p.mkdir(parents=True, exist_ok=True)
        c = ct.CostTracker(data_dir=p)
        r = c.get_provider_breakdown()
        # total = sum (0) or 1 -> percentage 0/1
        self.assertEqual(r, [])

    def test_get_agent_breakdown(self):
        c = self._make_with_records()
        r = c.get_agent_breakdown()
        self.assertGreaterEqual(len(r), 2)
        for item in r:
            self.assertIn("agent", item)
            self.assertIn("cost", item)
            self.assertIn("percentage", item)

    def test_get_agent_breakdown_empty(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d)
        p.mkdir(parents=True, exist_ok=True)
        c = ct.CostTracker(data_dir=p)
        self.assertEqual(c.get_agent_breakdown(), [])

    def test_get_recent_records(self):
        c = self._make_with_records()
        r = c.get_recent_records(1)
        self.assertEqual(len(r), 1)
        rec = r[0]
        self.assertIn("timestamp", rec)
        self.assertIn("provider", rec)
        self.assertIn("model", rec)
        self.assertIn("agent", rec)
        self.assertIn("tokens_in", rec)
        self.assertIn("tokens_out", rec)
        self.assertIn("cost_usd", rec)
        self.assertIn("latency_ms", rec)

    def test_get_recent_records_default_50(self):
        c = self._make_with_records()
        r = c.get_recent_records()
        self.assertEqual(len(r), 2)

    def test_get_dashboard(self):
        c = self._make_with_records()
        d = c.get_dashboard()
        self.assertIn("timestamp", d)
        self.assertIn("total_cost_usd", d)
        self.assertIn("total_tokens_in", d)
        self.assertIn("total_tokens_out", d)
        self.assertIn("total_records", d)
        self.assertEqual(d["total_records"], 2)
        self.assertIn("daily_cost", d)
        self.assertIn("monthly_cost", d)
        self.assertIn("budget", d)
        self.assertIn("providers", d)
        self.assertIn("agents", d)
        self.assertIn("recent", d)
        self.assertIn("daily_trend", d)
        self.assertEqual(len(d["daily_trend"]), 14)

    def test_get_dashboard_empty(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d)
        p.mkdir(parents=True, exist_ok=True)
        c = ct.CostTracker(data_dir=p)
        dd = c.get_dashboard()
        self.assertEqual(dd["total_records"], 0)
        self.assertEqual(dd["total_cost_usd"], 0.0)


class SingletonTests(unittest.TestCase):
    def setUp(self):
        self._saved = ct._cost_tracker
        ct._cost_tracker = None
        self.addCleanup(setattr, ct, "_cost_tracker", self._saved)

    def test_creates(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d)
        p.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.cost_tracker.CostTracker",
                        wraps=ct.CostTracker) as C:
            # patch data_dir default by monkeypatching Path? Instead pass via env impossible.
            # CostTracker() uses default data_dir. Just call and check type.
            pass
        # call directly with default (creates orbit_data/cost_tracker) - acceptable
        a = ct.get_cost_tracker()
        self.assertIsInstance(a, ct.CostTracker)
        self.assertIs(ct._cost_tracker, a)

    def test_reuses(self):
        a = ct.get_cost_tracker()
        b = ct.get_cost_tracker()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
