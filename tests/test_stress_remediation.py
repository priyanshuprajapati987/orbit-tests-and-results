"""
Regression tests for stress-test remediation fixes (Round 33).

Covers:
1. Decision/analyze input validation (500 fix)
2. FinancialTracker API contract (5 missing methods)
3. Multi-tier Memory get_recent() kwarg fix
4. Pipeline test timeout bounds
5. Bugfixer scan timeout bounds
6. n8n status timeout reduction
7. /api/whatif/stats route existence
"""

import os
import sys
import tempfile
import threading
import time

import pytest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from orbit.orbit.server import create_app


@pytest.fixture(scope="module")
def app():
    return create_app()


@pytest.fixture(scope="module")
def client(app):
    app.config["TESTING"] = True
    return app.test_client()


# ── 1. Decision/analyze input validation ─────────────────────────────────────


class TestDecisionAnalyze:
    """POST /api/decision/analyze must reject string options with 400, not 500."""

    def test_valid_options(self, client):
        r = client.post(
            "/api/decision/analyze",
            json={"question": "Which?", "options": [{"name": "A"}, {"name": "B"}]},
        )
        assert r.status_code == 200

    def test_string_options_rejected(self, client):
        """Previously returned 500 — must now return 400."""
        r = client.post(
            "/api/decision/analyze",
            json={"question": "Which?", "options": ["A", "B"]},
        )
        assert r.status_code == 400
        data = r.get_json()
        assert "error" in data
        assert "dict" in data["error"].lower() or "object" in data["error"].lower()

    def test_empty_options_rejected(self, client):
        r = client.post("/api/decision/analyze", json={"question": "X", "options": []})
        assert r.status_code == 400

    def test_missing_question_rejected(self, client):
        r = client.post("/api/decision/analyze", json={"options": [{"name": "A"}]})
        assert r.status_code == 400

    def test_non_list_options_rejected(self, client):
        r = client.post(
            "/api/decision/analyze", json={"question": "X", "options": "not a list"}
        )
        assert r.status_code == 400

    def test_mixed_list_rejected(self, client):
        """List with strings AND dicts must be rejected."""
        r = client.post(
            "/api/decision/analyze",
            json={"question": "X", "options": ["A", {"name": "B"}]},
        )
        assert r.status_code == 400


# ── 2. FinancialTracker API contract ──────────────────────────────────────────


class TestFinancialTracker:
    """Verify the 5 missing methods exist and work correctly."""

    def _tracker(self):
        from orbit.orbit.core.financial_tracker import get_financial_tracker

        return get_financial_tracker()

    def test_add_transaction_expense(self):
        t = self._tracker()
        result = t.add_transaction(
            type="expense", amount=10.50, category="api_call", description="test"
        )
        assert "id" in result
        assert result["amount_usd"] == 10.50

    def test_add_transaction_income(self):
        t = self._tracker()
        result = t.add_transaction(
            type="income", amount=100, category="fiverr", description="project"
        )
        assert "id" in result
        assert result["amount_usd"] == 100

    def test_get_transactions_returns_list(self):
        t = self._tracker()
        txns = t.get_transactions(limit=10)
        assert isinstance(txns, list)

    def test_get_transactions_filter_type(self):
        t = self._tracker()
        t.add_transaction(type="expense", amount=1, category="test", description="x")
        t.add_transaction(type="income", amount=2, category="test", description="y")
        expenses = t.get_transactions(type="expense")
        incomes = t.get_transactions(type="income")
        assert all(tx["type"] == "expense" for tx in expenses)
        assert all(tx["type"] == "income" for tx in incomes)

    def test_get_transactions_limit(self):
        t = self._tracker()
        txns = t.get_transactions(limit=5)
        assert len(txns) <= 5

    def test_get_monthly_report_current(self):
        t = self._tracker()
        report = t.get_monthly_report()
        assert "month" in report
        assert "total_expenses" in report
        assert "total_income" in report
        assert "net" in report
        assert isinstance(report["by_category"], dict)

    def test_get_monthly_report_specific_month(self):
        t = self._tracker()
        report = t.get_monthly_report(month="2026-01")
        assert report["month"] == "2026-01"

    def test_get_monthly_report_invalid_month(self):
        t = self._tracker()
        report = t.get_monthly_report(month="invalid")
        # Should fall back to last 30 days, not crash
        assert "total_expenses" in report

    def test_get_orbit_cost(self):
        t = self._tracker()
        cost = t.get_orbit_cost()
        assert "total_cost" in cost
        assert "total_requests" in cost
        assert "by_provider" in cost
        assert isinstance(cost["by_provider"], dict)

    def test_delete_transaction_nonexistent(self):
        t = self._tracker()
        assert t.delete_transaction("nonexistent_id") is False

    def test_delete_transaction_real(self):
        t = self._tracker()
        result = t.add_transaction(
            type="expense", amount=0.01, category="test", description="del"
        )
        tid = result["id"]
        assert t.delete_transaction(tid) is True
        assert t.delete_transaction(tid) is False  # Already deleted

    def test_api_endpoint_transactions(self, client):
        r = client.get("/api/finance/transactions")
        assert r.status_code == 200

    def test_api_endpoint_report(self, client):
        r = client.get("/api/finance/report")
        assert r.status_code == 200

    def test_api_endpoint_orbit_cost(self, client):
        r = client.get("/api/finance/orbit-cost")
        assert r.status_code == 200


# ── 3. Multi-tier Memory get_recent() kwarg fix ──────────────────────────────


class TestMultiTierMemory:
    """get_recent(n=...) must not raise TypeError on 'limit' kwarg."""

    def test_stats_no_crash(self, client):
        r = client.get("/api/multi-tier-memory/stats")
        assert r.status_code == 200

    def test_stats_shape(self, client):
        r = client.get("/api/multi-tier-memory/stats")
        data = r.get_json()
        assert (
            "tier0" in data
            or "tier1" in data
            or "total_entries" in data
            or "tiers" in data
        )


# ── 4. Pipeline test timeout bounds ──────────────────────────────────────────


class TestPipelineTestTimeout:
    """Pipeline test must complete within a bounded time."""

    def test_pipeline_test_completes(self, client):
        # Ceiling 60s -> 120s (2026-10-06). run_full_test now enforces a
        # 60s TOTAL budget (per-call 10s caps alone did not bound it —
        # ThreadPoolExecutor __exit__ waited for timed-out workers; observed
        # 166s under suite load). 120s = budget + provider probe + save +
        # flask overhead, with headroom for suite load.
        t0 = time.monotonic()
        r = client.get("/api/pipeline/test")
        elapsed_s = time.monotonic() - t0
        assert r.status_code == 200
        assert elapsed_s < 120, (
            f"Pipeline test took {elapsed_s:.1f}s — exceeds 120s ceiling"
        )

    def test_pipeline_test_provider_probe_fast(self):
        """_get_available_provider() must complete in < 2s (timeout=1s)."""
        from orbit.orbit.core.pipeline_test import _get_available_provider

        t0 = time.monotonic()
        provider = _get_available_provider()
        elapsed_s = time.monotonic() - t0
        assert elapsed_s < 2.0, f"Provider probe took {elapsed_s:.1f}s"
        assert provider in ("ollama", "openrouter", "mock")


# ── 5. Bugfixer scan timeout bounds ──────────────────────────────────────────


class TestBugfixerTimeout:
    """Bugfixer scan must complete within bounded time."""

    def test_scan_completes(self, client):
        t0 = time.monotonic()
        r = client.post("/api/bugfixer/scan", json={"code": "x = 1"})
        elapsed_s = time.monotonic() - t0
        assert r.status_code == 200
        assert elapsed_s < 15, (
            f"Bugfixer scan took {elapsed_s:.1f}s — exceeds 15s ceiling"
        )

    def test_scan_returns_report(self, client):
        r = client.post("/api/bugfixer/scan", json={"code": "x = 1"})
        data = r.get_json()
        assert "files_scanned" in data
        assert "findings_count" in data

    def test_scan_single_file(self):
        """Scan a single small file — must be fast."""
        from orbit.orbit.core.bugfixer import get_bugfixer

        tmpdir = tempfile.mkdtemp()
        fpath = os.path.join(tmpdir, "small_test.py")
        with open(fpath, "w") as f:
            f.write("x = 1\n")
        try:
            t0 = time.monotonic()
            report = get_bugfixer().scan(fpath)
            elapsed_s = time.monotonic() - t0
            assert elapsed_s < 2.0
            assert report.files_scanned == 1
        finally:
            try:
                os.unlink(fpath)
                os.rmdir(tmpdir)
            except OSError:
                pass


# ── 6. n8n status timeout ────────────────────────────────────────────────────


class TestN8nStatusTimeout:
    """n8n status must fail fast when n8n is not running."""

    def test_n8n_status_fast(self, client):
        t0 = time.monotonic()
        r = client.get("/api/n8n/status")
        elapsed_s = time.monotonic() - t0
        assert r.status_code == 200
        assert elapsed_s < 2.0, f"n8n status took {elapsed_s:.1f}s — should fail fast"

    def test_n8n_status_shape(self, client):
        r = client.get("/api/n8n/status")
        data = r.get_json()
        assert "n8n_online" in data
        assert isinstance(data["n8n_online"], bool)


# ── 7. Route existence ───────────────────────────────────────────────────────


class TestRouteExistence:
    """Verify routes that previously 404'd now exist or behave correctly."""

    def test_whatif_stats_exists(self, client):
        r = client.get("/api/whatif/stats")
        assert r.status_code == 200
        data = r.get_json()
        assert "status" in data

    def test_team_current_returns_404_when_empty(self, client):
        """team/current returns 404 when no structure — this is correct behavior."""
        r = client.get("/api/team/current")
        # 404 means no structure yet — not a bug
        assert r.status_code in (200, 404)


# ── Concurrent access ────────────────────────────────────────────────────────


class TestConcurrentAccess:
    """All fixed endpoints must handle concurrent access without errors."""

    def test_concurrent_financial(self, client):
        errors = []

        def hit():
            try:
                r = client.get("/api/finance/transactions")
                if r.status_code not in (200,):
                    errors.append(f"transactions:{r.status_code}")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=hit) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        assert errors == [], f"Concurrent errors: {errors}"

    def test_concurrent_decision(self, client):
        errors = []

        def hit():
            try:
                r = client.post(
                    "/api/decision/analyze",
                    json={"question": "X", "options": [{"name": "A"}]},
                )
                if r.status_code not in (200,):
                    errors.append(f"decision:{r.status_code}")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=hit) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        assert errors == [], f"Concurrent errors: {errors}"
