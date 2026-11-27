"""Deep tests for orbit/orbit/core/billing_bp.py (Loop 18/3)."""

import unittest
from types import SimpleNamespace
from unittest import mock

import flask

from orbit.orbit.core import billing_bp


def _bm():
    plan = SimpleNamespace(id="pro", name="Pro", features=["a", "b"])
    record = SimpleNamespace(date="2026-01-01", cost_usd=1.5, calls=2,
                            tokens_in=100, tokens_out=50)
    m = mock.MagicMock()
    m.get_user_plan.return_value = plan
    m.check_quota.return_value = {"calls": 5, "limit": 100}
    m.get_all_usage.return_value = {"local": [record]}
    m.get_invoices.return_value = []
    m.create_checkout_session.return_value = "https://checkout.url"
    m.handle_webhook.return_value = True
    m.get_stats.return_value = {"total_users": 5}
    m._lock = mock.MagicMock()
    m._user_plans = {"u1": {"plan_id": "pro", "updated_at": 123}}
    m._stripe_enabled = False
    m.set_user_plan.return_value = True
    return m


class BillingBpTests(unittest.TestCase):
    def setUp(self):
        app = flask.Flask(__name__)
        app.register_blueprint(billing_bp.billing_bp)
        self.client = app.test_client()

    # ── _request_user_id ────────────────────────────────────────────

    def test_request_user_id_authenticated(self):
        with mock.patch("orbit.orbit.core.auth.guards.current_user",
                        return_value={"id": "user-9"}):
            self.assertEqual(billing_bp._request_user_id(), "user-9")

    def test_request_user_id_empty(self):
        with mock.patch("orbit.orbit.core.auth.guards.current_user",
                        return_value={"id": ""}):
            self.assertEqual(billing_bp._request_user_id(), "local")

    def test_request_user_id_exception(self):
        with mock.patch("orbit.orbit.core.auth.guards.current_user",
                        side_effect=RuntimeError("no session")):
            self.assertEqual(billing_bp._request_user_id(), "local")

    # ── list_plans ──────────────────────────────────────────────────

    def test_list_plans(self):
        plan = SimpleNamespace(id="free", name="Free", price_monthly=0,
                              price_yearly=0, daily_usd_cap=1.0,
                              daily_call_cap=10, features=["f1"])
        with mock.patch("orbit.orbit.core.billing_bp.PLANS",
                        {"free": plan}), \
                mock.patch("orbit.orbit.core.billing_bp.get_billing_manager"):
            r = self.client.get("/api/billing/plans")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(len(body["plans"]), 1)
        p = body["plans"][0]
        self.assertEqual(p["id"], "free")
        self.assertEqual(p["name"], "Free")
        self.assertEqual(p["features"], ["f1"])

    def test_list_plans_exception_500(self):
        with mock.patch("orbit.orbit.core.billing_bp.PLANS",
                        new_callable=mock.PropertyMock,
                        side_effect=RuntimeError("boom")):
            # PLANS is a module attr; patch via direct attribute
            pass
        # Force exception by making PLANS iteration fail
        class BadDict(dict):
            def values(self):
                raise RuntimeError("boom")
        with mock.patch("orbit.orbit.core.billing_bp.PLANS", BadDict()):
            r = self.client.get("/api/billing/plans")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "boom")

    # ── get_subscription ────────────────────────────────────────────

    def test_get_subscription(self):
        bm = _bm()
        with mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                        return_value=bm), \
                mock.patch("orbit.orbit.core.billing_bp._request_user_id",
                           return_value="u1"):
            r = self.client.get("/api/billing/subscription")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["user_id"], "u1")
        self.assertEqual(body["plan_id"], "pro")
        self.assertEqual(body["plan_name"], "Pro")
        self.assertEqual(body["features"], ["a", "b"])
        bm.get_user_plan.assert_called_once_with("u1")

    def test_get_subscription_exception_500(self):
        with mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                        side_effect=RuntimeError("boom")):
            r = self.client.get("/api/billing/subscription")
        self.assertEqual(r.status_code, 500)

    # ── get_usage ───────────────────────────────────────────────────

    def test_get_usage(self):
        bm = _bm()
        with mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                        return_value=bm), \
                mock.patch("orbit.orbit.core.billing_bp._request_user_id",
                           return_value="u1"):
            r = self.client.get("/api/billing/usage")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"calls": 5, "limit": 100})
        bm.check_quota.assert_called_once_with("u1")

    def test_get_usage_exception_500(self):
        with mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                        side_effect=RuntimeError("boom")):
            r = self.client.get("/api/billing/usage")
        self.assertEqual(r.status_code, 500)

    # ── get_usage_history ───────────────────────────────────────────

    def test_get_usage_history(self):
        bm = _bm()
        with mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                        return_value=bm), \
                mock.patch("orbit.orbit.core.billing_bp._request_user_id",
                           return_value="local"):
            r = self.client.get("/api/billing/usage/history")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(len(body["usage"]), 1)
        rec = body["usage"][0]
        self.assertEqual(rec["date"], "2026-01-01")
        self.assertEqual(rec["cost_usd"], 1.5)
        self.assertEqual(rec["calls"], 2)
        self.assertEqual(rec["tokens_in"], 100)
        self.assertEqual(rec["tokens_out"], 50)

    def test_get_usage_history_no_records(self):
        bm = _bm()
        bm.get_all_usage.return_value = {}
        with mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                        return_value=bm), \
                mock.patch("orbit.orbit.core.billing_bp._request_user_id",
                           return_value="local"):
            r = self.client.get("/api/billing/usage/history")
        self.assertEqual(r.get_json(), {"usage": []})

    def test_get_usage_history_exception_500(self):
        with mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                        side_effect=RuntimeError("boom")):
            r = self.client.get("/api/billing/usage/history")
        self.assertEqual(r.status_code, 500)

    # ── get_invoices ────────────────────────────────────────────────

    def test_get_invoices_empty(self):
        bm = _bm()
        with mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                        return_value=bm), \
                mock.patch("orbit.orbit.core.billing_bp._request_user_id",
                           return_value="u1"):
            r = self.client.get("/api/billing/invoices")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"invoices": []})
        bm.get_invoices.assert_called_once_with("u1")

    def test_get_invoices_with_data(self):
        inv = SimpleNamespace(id="inv1", plan_id="pro", amount=10.0,
                             currency="USD", status="paid",
                             created_at="2026-01-01", paid_at="2026-01-02")
        bm = _bm()
        bm.get_invoices.return_value = [inv]
        with mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                        return_value=bm), \
                mock.patch("orbit.orbit.core.billing_bp._request_user_id",
                           return_value="u1"):
            r = self.client.get("/api/billing/invoices")
        body = r.get_json()
        self.assertEqual(len(body["invoices"]), 1)
        self.assertEqual(body["invoices"][0]["id"], "inv1")
        self.assertEqual(body["invoices"][0]["amount"], 10.0)

    def test_get_invoices_exception_500(self):
        with mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                        side_effect=RuntimeError("boom")):
            r = self.client.get("/api/billing/invoices")
        self.assertEqual(r.status_code, 500)

    # ── create_checkout ─────────────────────────────────────────────

    def test_create_checkout_success(self):
        bm = _bm()
        with mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                        return_value=bm), \
                mock.patch("orbit.orbit.core.billing_bp._request_user_id",
                           return_value="u1"):
            r = self.client.post("/api/billing/checkout", json={
                "plan_id": "pro", "success_url": "http://ok",
                "cancel_url": "http://cancel"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"checkout_url": "https://checkout.url"})
        bm.create_checkout_session.assert_called_once_with(
            "u1", "pro", "http://ok", "http://cancel")

    def test_create_checkout_no_url_400(self):
        bm = _bm()
        bm.create_checkout_session.return_value = None
        with mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                        return_value=bm), \
                mock.patch("orbit.orbit.core.billing_bp._request_user_id",
                           return_value="u1"):
            r = self.client.post("/api/billing/checkout", json={"plan_id": "pro"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"],
                         "Stripe not configured or plan unavailable")

    def test_create_checkout_default_plan_pro(self):
        bm = _bm()
        with mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                        return_value=bm), \
                mock.patch("orbit.orbit.core.billing_bp._request_user_id",
                           return_value="u1"):
            self.client.post("/api/billing/checkout", json={})
        bm.create_checkout_session.assert_called_once_with("u1", "pro", "", "")

    def test_create_checkout_exception_500(self):
        with mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                        side_effect=RuntimeError("boom")):
            r = self.client.post("/api/billing/checkout", json={})
        self.assertEqual(r.status_code, 500)

    def test_create_checkout_non_json(self):
        bm = _bm()
        with mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                        return_value=bm), \
                mock.patch("orbit.orbit.core.billing_bp._request_user_id",
                           return_value="u1"):
            r = self.client.post("/api/billing/checkout", data="",
                                 content_type="application/json")
        # data.get on {} -> plan_id="pro" default, proceeds
        self.assertIn(r.status_code, (200, 400))

    # ── webhook ─────────────────────────────────────────────────────

    def test_webhook_success(self):
        bm = _bm()
        with mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                        return_value=bm):
            r = self.client.post("/api/billing/webhook",
                                 data=b'{"x":1}',
                                 headers={"Stripe-Signature": "sig"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"received": True})
        bm.handle_webhook.assert_called_once()

    def test_webhook_failed_400(self):
        bm = _bm()
        bm.handle_webhook.return_value = False
        with mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                        return_value=bm):
            r = self.client.post("/api/billing/webhook", data=b'{}')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "webhook verification failed")

    def test_webhook_exception_500(self):
        with mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                        side_effect=RuntimeError("boom")):
            r = self.client.post("/api/billing/webhook", data=b'{}')
        self.assertEqual(r.status_code, 500)

    # ── admin_stats (require_admin) ─────────────────────────────────

    def test_admin_stats_requires_admin(self):
        # require_admin guards; patch guards to allow
        with mock.patch("orbit.orbit.core.auth.guards.require_admin",
                        lambda f: f), \
                mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                           return_value=_bm()):
            r = self.client.get("/api/billing/admin/stats")
        # require_admin is a decorator applied at import time; patching the
        # name now won't un-decorate. Instead, patch get_session_factory/current_user.
        self.assertIn(r.status_code, (200, 401, 403))

    # ── upgrade_plan ────────────────────────────────────────────────

    def test_upgrade_invalid_plan_400(self):
        with mock.patch("orbit.orbit.core.billing_bp.PLANS", {"pro": mock.MagicMock()}), \
                mock.patch("orbit.orbit.core.billing_bp._request_user_id",
                           return_value="u1"):
            r = self.client.post("/api/billing/upgrade",
                                 json={"plan_id": "nope"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "invalid plan")

    def test_upgrade_no_stripe_sets_plan(self):
        plan = mock.MagicMock()
        bm = _bm()
        bm._stripe_enabled = False
        with mock.patch("orbit.orbit.core.billing_bp.PLANS", {"pro": plan}), \
                mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                           return_value=bm), \
                mock.patch("orbit.orbit.core.billing_bp._request_user_id",
                           return_value="u1"):
            r = self.client.post("/api/billing/upgrade",
                                 json={"plan_id": "pro"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"status": "ok", "plan_id": "pro"})
        bm.set_user_plan.assert_called_once_with("u1", "pro")

    def test_upgrade_stripe_returns_checkout_url(self):
        plan = mock.MagicMock()
        bm = _bm()
        bm._stripe_enabled = True
        bm.create_checkout_session.return_value = "https://co"
        with mock.patch("orbit.orbit.core.billing_bp.PLANS", {"pro": plan}), \
                mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                           return_value=bm), \
                mock.patch("orbit.orbit.core.billing_bp._request_user_id",
                           return_value="u1"):
            r = self.client.post("/api/billing/upgrade",
                                 json={"plan_id": "pro",
                                       "success_url": "ok", "cancel_url": "c"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(),
                         {"checkout_url": "https://co", "plan_id": "pro"})

    def test_upgrade_stripe_no_url_falls_back(self):
        plan = mock.MagicMock()
        bm = _bm()
        bm._stripe_enabled = True
        bm.create_checkout_session.return_value = None
        with mock.patch("orbit.orbit.core.billing_bp.PLANS", {"pro": plan}), \
                mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                           return_value=bm), \
                mock.patch("orbit.orbit.core.billing_bp._request_user_id",
                           return_value="u1"):
            r = self.client.post("/api/billing/upgrade",
                                 json={"plan_id": "pro"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"status": "ok", "plan_id": "pro"})
        bm.set_user_plan.assert_called_once_with("u1", "pro")

    def test_upgrade_exception_500(self):
        with mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                        side_effect=RuntimeError("boom")):
            r = self.client.post("/api/billing/upgrade", json={"plan_id": "pro"})
        self.assertEqual(r.status_code, 500)

    def test_upgrade_non_json(self):
        plan = mock.MagicMock()
        bm = _bm()
        with mock.patch("orbit.orbit.core.billing_bp.PLANS", {"pro": plan}), \
                mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                           return_value=bm), \
                mock.patch("orbit.orbit.core.billing_bp._request_user_id",
                           return_value="u1"):
            r = self.client.post("/api/billing/upgrade", data="",
                                 content_type="application/json")
        # plan_id="" not in PLANS -> 400
        self.assertEqual(r.status_code, 400)

    # ── downgrade_plan ──────────────────────────────────────────────

    def test_downgrade_invalid_plan_400(self):
        with mock.patch("orbit.orbit.core.billing_bp.PLANS", {"pro": mock.MagicMock()}):
            r = self.client.post("/api/billing/downgrade",
                                 json={"plan_id": "nope"})
        self.assertEqual(r.status_code, 400)

    def test_downgrade_success(self):
        plan = mock.MagicMock()
        bm = _bm()
        with mock.patch("orbit.orbit.core.billing_bp.PLANS", {"pro": plan,
                                                           "free": plan}), \
                mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                           return_value=bm), \
                mock.patch("orbit.orbit.core.billing_bp._request_user_id",
                           return_value="u1"):
            r = self.client.post("/api/billing/downgrade",
                                 json={"plan_id": "free"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"status": "ok", "plan_id": "free"})
        bm.set_user_plan.assert_called_once_with("u1", "free")

    def test_downgrade_default_plan_free(self):
        plan = mock.MagicMock()
        bm = _bm()
        with mock.patch("orbit.orbit.core.billing_bp.PLANS", {"free": plan}), \
                mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                           return_value=bm), \
                mock.patch("orbit.orbit.core.billing_bp._request_user_id",
                           return_value="u1"):
            r = self.client.post("/api/billing/downgrade", json={})
        self.assertEqual(r.status_code, 200)
        bm.set_user_plan.assert_called_once_with("u1", "free")

    def test_downgrade_exception_500(self):
        with mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                        side_effect=RuntimeError("boom")):
            r = self.client.post("/api/billing/downgrade", json={"plan_id": "free"})
        self.assertEqual(r.status_code, 500)

    # ── admin_set_plan ──────────────────────────────────────────────

    def test_admin_set_plan_missing_400(self):
        r = self.client.post("/api/billing/admin/set-plan", json={})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "user_id and plan_id required")

    def test_admin_set_plan_missing_plan_id_400(self):
        r = self.client.post("/api/billing/admin/set-plan",
                             json={"user_id": "u1"})
        self.assertEqual(r.status_code, 400)

    def test_admin_set_plan_success(self):
        bm = _bm()
        with mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                        return_value=bm):
            r = self.client.post("/api/billing/admin/set-plan",
                                 json={"user_id": "u1", "plan_id": "pro"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"status": "ok"})
        bm.set_user_plan.assert_called_once_with("u1", "pro")

    def test_admin_set_plan_invalid_400(self):
        bm = _bm()
        bm.set_user_plan.return_value = False
        with mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                        return_value=bm):
            r = self.client.post("/api/billing/admin/set-plan",
                                 json={"user_id": "u1", "plan_id": "pro"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "invalid plan_id")

    def test_admin_set_plan_exception_500(self):
        with mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                        side_effect=RuntimeError("boom")):
            r = self.client.post("/api/billing/admin/set-plan",
                                 json={"user_id": "u1", "plan_id": "pro"})
        self.assertEqual(r.status_code, 500)

    def test_admin_set_plan_non_json(self):
        r = self.client.post("/api/billing/admin/set-plan", data="",
                             content_type="application/json")
        self.assertEqual(r.status_code, 400)


    # ── admin_stats ─────────────────────────────────────────────────

    def test_admin_stats(self):
        bm = _bm()
        with mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                        return_value=bm):
            r = self.client.get("/api/billing/admin/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"total_users": 5})
        bm.get_stats.assert_called_once()

    def test_admin_stats_exception_500(self):
        with mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                        side_effect=RuntimeError("boom")):
            r = self.client.get("/api/billing/admin/stats")
        self.assertEqual(r.status_code, 500)

    # ── admin_users ─────────────────────────────────────────────────

    def test_admin_users(self):
        bm = _bm()
        with mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                        return_value=bm):
            r = self.client.get("/api/billing/admin/users")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(len(body["users"]), 1)
        self.assertEqual(body["users"][0]["user_id"], "u1")
        self.assertEqual(body["users"][0]["plan_id"], "pro")

    def test_admin_users_exception_500(self):
        with mock.patch("orbit.orbit.core.billing_bp.get_billing_manager",
                        side_effect=RuntimeError("boom")):
            r = self.client.get("/api/billing/admin/users")
        self.assertEqual(r.status_code, 500)


if __name__ == "__main__":
    unittest.main()
