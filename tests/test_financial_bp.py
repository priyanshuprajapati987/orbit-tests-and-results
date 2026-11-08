"""Unit tests for orbit/orbit/core/financial_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.financial_bp import financial_bp


class TestFinancialBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(financial_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(financial_bp.name, "financial_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/finance/add", "/api/finance/transactions", "/api/finance/summary",
                  "/api/finance/report", "/api/finance/orbit-cost", "/api/finance/budget",
                  "/api/finance/budgets", "/api/finance/delete/<trans_id>"]:
            self.assertIn(p, rules)

    def test_add_missing_fields_400(self):
        r = self.client.post("/api/finance/add", json={"type": "income"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_add_success(self):
        with patch("orbit.core.financial_bp.get_financial_tracker") as gf:
            gf.return_value.add_transaction.return_value = {"id": "t1"}
            r = self.client.post("/api/finance/add", json={
                "type": "income", "amount": 100, "category": "salary", "description": "pay", "tags": ["x"]
            })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], "t1")
        gf.return_value.add_transaction.assert_called_once_with(
            type="income", amount=100, category="salary", description="pay", tags=["x"]
        )

    def test_add_no_body(self):
        r = self.client.post("/api/finance/add")
        self.assertEqual(r.status_code, 400)

    def test_transactions(self):
        with patch("orbit.core.financial_bp.get_financial_tracker") as gf:
            gf.return_value.get_transactions.return_value = [{"id": "t1"}, {"id": "t2"}]
            r = self.client.get("/api/finance/transactions?limit=5&category=food&type=expense")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["count"], 2)
        self.assertEqual(len(body["transactions"]), 2)
        gf.return_value.get_transactions.assert_called_once_with(limit=5, category="food", type="expense")

    def test_transactions_defaults(self):
        with patch("orbit.core.financial_bp.get_financial_tracker") as gf:
            gf.return_value.get_transactions.return_value = []
            r = self.client.get("/api/finance/transactions")
        gf.return_value.get_transactions.assert_called_once_with(limit=50, category=None, type=None)

    def test_summary(self):
        with patch("orbit.core.financial_bp.get_financial_tracker") as gf:
            gf.return_value.get_summary.return_value = {"total": 100}
            r = self.client.get("/api/finance/summary")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 100)

    def test_report(self):
        with patch("orbit.core.financial_bp.get_financial_tracker") as gf:
            gf.return_value.get_monthly_report.return_value = {"month": "2026-01"}
            r = self.client.get("/api/finance/report?month=2026-01")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["month"], "2026-01")
        gf.return_value.get_monthly_report.assert_called_once_with(month="2026-01")

    def test_report_default(self):
        with patch("orbit.core.financial_bp.get_financial_tracker") as gf:
            gf.return_value.get_monthly_report.return_value = {}
            r = self.client.get("/api/finance/report")
        gf.return_value.get_monthly_report.assert_called_once_with(month=None)

    def test_orbit_cost(self):
        with patch("orbit.core.financial_bp.get_financial_tracker") as gf:
            gf.return_value.get_orbit_cost.return_value = {"cost": 1.5}
            r = self.client.get("/api/finance/orbit-cost")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["cost"], 1.5)

    def test_budget_set_missing_amount_400(self):
        r = self.client.post("/api/finance/budget", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_budget_set_success(self):
        with patch("orbit.core.financial_bp.get_financial_tracker") as gf:
            r = self.client.post("/api/finance/budget", json={"amount": 100.5})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertEqual(r.get_json()["amount"], 100.5)
        gf.return_value.set_budget.assert_called_once_with(100.5)

    def test_budget_set_no_body(self):
        r = self.client.post("/api/finance/budget")
        self.assertEqual(r.status_code, 400)

    def test_budgets(self):
        with patch("orbit.core.financial_bp.get_financial_tracker") as gf:
            gf.return_value.get_budget_status.return_value = {"ok": True}
            r = self.client.get("/api/finance/budgets")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])

    def test_delete_success(self):
        with patch("orbit.core.financial_bp.get_financial_tracker") as gf:
            gf.return_value.delete_transaction.return_value = True
            r = self.client.post("/api/finance/delete/t1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "deleted")
        gf.return_value.delete_transaction.assert_called_once_with("t1")

    def test_delete_not_found_404(self):
        with patch("orbit.core.financial_bp.get_financial_tracker") as gf:
            gf.return_value.delete_transaction.return_value = False
            r = self.client.post("/api/finance/delete/t1")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())


if __name__ == "__main__":
    unittest.main()
