"""Milestone 6 — Stripe end-to-end tests (hermetic: fake Stripe SDK, no network).

Covers: checkout session creation, webhook signature verification,
checkout.session.completed → plan upgrade + invoice + persistence,
full free→pro→free lifecycle with quota change, API-level checkout/webhook
endpoints, malformed-event safety, invoice ID uniqueness, and the
invoice-append lock regression.
"""

import json
import os
import threading
import time
from types import SimpleNamespace

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")

import pytest

VALID_SIG = "t=1700000000,v1=valid"


class FakeStripe:
    """In-memory stand-in for the stripe SDK — validates sig, parses payload."""

    api_key = None

    def __init__(self):
        self.create_calls = []
        self.fail_create = False
        self.checkout = SimpleNamespace(Session=SimpleNamespace(create=self._create_session))
        self.Webhook = SimpleNamespace(construct_event=self._construct_event)

    def _create_session(self, **kwargs):
        if self.fail_create:
            raise RuntimeError("stripe API unavailable")
        self.create_calls.append(kwargs)
        return SimpleNamespace(url="https://checkout.stripe.com/c/pay/cs_test_e2e", id="cs_test_e2e")

    def _construct_event(self, payload, sig_header, secret):
        if sig_header != VALID_SIG:
            raise ValueError("Invalid Stripe signature")
        return json.loads(payload)


@pytest.fixture()
def stripe_env(tmp_path, monkeypatch):
    import orbit.orbit.core.billing as billing

    fake = FakeStripe()
    monkeypatch.setattr(billing, "stripe", fake)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake_123")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_123")
    monkeypatch.setattr(billing.PLANS["pro"], "stripe_price_id_monthly", "price_pro_monthly")
    monkeypatch.setattr(billing.PLANS["free"], "stripe_price_id_monthly", "")
    monkeypatch.setattr(billing, "_billing_manager", None)
    mgr = billing.BillingManager(data_dir=str(tmp_path / "billing"))
    monkeypatch.setattr(billing, "_billing_manager", mgr)
    yield mgr, fake, billing


def _event(user_id="u1", plan_id="pro", event_type="checkout.session.completed", session_id="cs_1"):
    return json.dumps(
        {
            "type": event_type,
            "data": {
                "object": {
                    "id": session_id,
                    "metadata": {"user_id": user_id, "plan_id": plan_id},
                }
            },
        }
    ).encode("utf-8")


# ── Checkout session ────────────────────────────────────────────────


def test_checkout_session_created(stripe_env):
    mgr, fake, _ = stripe_env
    url = mgr.create_checkout_session("u1", "pro", "https://x/success", "https://x/cancel")
    assert url == "https://checkout.stripe.com/c/pay/cs_test_e2e"
    assert len(fake.create_calls) == 1
    call = fake.create_calls[0]
    assert call["mode"] == "subscription"
    assert call["metadata"] == {"user_id": "u1", "plan_id": "pro"}
    assert call["line_items"] == [{"price": "price_pro_monthly", "quantity": 1}]
    assert call["success_url"] == "https://x/success"
    assert "customer_email" not in call


def test_checkout_without_price_id_returns_none(stripe_env):
    mgr, fake, _ = stripe_env
    assert mgr.create_checkout_session("u1", "free", "https://x/s", "https://x/c") is None
    assert fake.create_calls == []


def test_checkout_api_error_returns_none(stripe_env):
    mgr, fake, _ = stripe_env
    fake.fail_create = True
    assert mgr.create_checkout_session("u1", "pro", "https://x/s", "https://x/c") is None


def test_checkout_disabled_without_secret_key(stripe_env):
    mgr, fake, _ = stripe_env
    mgr._stripe_enabled = False
    assert mgr.create_checkout_session("u1", "pro", "https://x/s", "https://x/c") is None
    assert fake.create_calls == []


# ── Webhook ─────────────────────────────────────────────────────────


def test_webhook_upgrades_plan_and_creates_invoice(stripe_env, monkeypatch):
    mgr, _, billing = stripe_env
    assert mgr.get_user_plan("u1").id == "free"
    assert mgr.handle_webhook(_event(user_id="u1", plan_id="pro"), VALID_SIG) is True
    assert mgr.get_user_plan("u1").id == "pro"
    invoices = mgr.get_invoices("u1")
    assert len(invoices) == 1
    assert invoices[0].status == "paid"
    assert invoices[0].amount == 20
    assert invoices[0].stripe_invoice_id == "cs_1"
    persisted = billing.BillingManager(data_dir=str(mgr._data_dir))
    assert persisted.get_user_plan("u1").id == "pro"
    assert len(persisted.get_invoices("u1")) == 1


def test_webhook_invalid_signature_rejected(stripe_env):
    mgr, _, _ = stripe_env
    assert mgr.handle_webhook(_event(), "t=1,v1=wrong") is False
    assert mgr.get_user_plan("u1").id == "free"
    assert mgr.get_invoices("u1") == []


def test_webhook_missing_secret_rejected(stripe_env, monkeypatch):
    mgr, _, _ = stripe_env
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET")
    assert mgr.handle_webhook(_event(), VALID_SIG) is False
    assert mgr.get_user_plan("u1").id == "free"


def test_webhook_disabled_returns_false(stripe_env):
    mgr, _, _ = stripe_env
    mgr._stripe_enabled = False
    assert mgr.handle_webhook(_event(), VALID_SIG) is False
    assert mgr.get_user_plan("u1").id == "free"


def test_webhook_unknown_event_type_ignored(stripe_env):
    mgr, _, _ = stripe_env
    assert mgr.handle_webhook(_event(event_type="customer.created"), VALID_SIG) is True
    assert mgr.get_user_plan("u1").id == "free"
    assert mgr.get_invoices("u1") == []


def test_webhook_unknown_plan_ignored(stripe_env):
    mgr, _, _ = stripe_env
    assert mgr.handle_webhook(_event(plan_id="platinum"), VALID_SIG) is True
    assert mgr.get_user_plan("u1").id == "free"
    assert mgr.get_invoices("u1") == []


def test_webhook_malformed_event_no_crash(stripe_env):
    mgr, _, _ = stripe_env
    assert mgr.handle_webhook(b'{"unexpected": true}', VALID_SIG) is True
    assert mgr.handle_webhook(b"not json at all", VALID_SIG) is False
    assert mgr.get_user_plan("u1").id == "free"


def test_webhook_missing_metadata_ignored(stripe_env):
    mgr, _, _ = stripe_env
    payload = json.dumps({"type": "checkout.session.completed", "data": {"object": {"id": "cs_2"}}}).encode()
    assert mgr.handle_webhook(payload, VALID_SIG) is True
    assert mgr.get_invoices("u1") == []


def test_invoice_ids_unique_same_second(stripe_env):
    mgr, _, _ = stripe_env
    mgr.handle_webhook(_event(user_id="u1", session_id="cs_a"), VALID_SIG)
    mgr.handle_webhook(_event(user_id="u2", session_id="cs_b"), VALID_SIG)
    ids = [inv.id for inv in mgr.get_invoices("u1") + mgr.get_invoices("u2")]
    assert len(ids) == len(set(ids)), f"duplicate invoice ids: {ids}"


# ── Full lifecycle ──────────────────────────────────────────────────


def test_full_lifecycle_free_to_pro_to_free(stripe_env):
    mgr, fake, _ = stripe_env
    assert mgr.check_quota("u1")["plan_id"] == "free"
    free_cap = mgr.check_quota("u1")["daily_usd_cap"]
    url = mgr.create_checkout_session("u1", "pro", "https://x/s", "https://x/c")
    assert url
    assert mgr.handle_webhook(_event(user_id="u1"), VALID_SIG) is True
    assert mgr.check_quota("u1")["plan_id"] == "pro"
    assert mgr.check_quota("u1")["daily_usd_cap"] > free_cap
    stats = mgr.get_stats()
    assert stats["total_revenue"] == 20
    assert stats["plan_counts"].get("pro") == 1
    assert mgr.set_user_plan("u1", "free") is True
    assert mgr.check_quota("u1")["plan_id"] == "free"
    assert mgr.get_stats()["total_revenue"] == 20


# ── API-level e2e (Flask) ──────────────────────────────────────────


@pytest.fixture()
def billing_client(stripe_env):
    from flask import Flask

    from orbit.orbit.core.billing_bp import billing_bp

    app = Flask(__name__)
    app.register_blueprint(billing_bp)
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_api_plans_endpoint(billing_client):
    r = billing_client.get("/api/billing/plans")
    assert r.status_code == 200
    plans = r.get_json()["plans"]
    assert {p["id"] for p in plans} >= {"free", "pro", "enterprise"}


def test_api_checkout_success(billing_client, stripe_env):
    mgr, fake, _ = stripe_env
    r = billing_client.post("/api/billing/checkout", json={"plan_id": "pro"})
    assert r.status_code == 200
    assert r.get_json()["checkout_url"].startswith("https://checkout.stripe.com/")
    assert fake.create_calls[0]["metadata"]["user_id"] == "local"


def test_api_checkout_stripe_disabled_400(billing_client, stripe_env):
    mgr, _, _ = stripe_env
    mgr._stripe_enabled = False
    r = billing_client.post("/api/billing/checkout", json={"plan_id": "pro"})
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_api_webhook_success(billing_client):
    r = billing_client.post(
        "/api/billing/webhook",
        data=_event(user_id="api_user", plan_id="pro"),
        headers={"Stripe-Signature": VALID_SIG, "Content-Type": "application/json"},
    )
    assert r.status_code == 200
    assert r.get_json()["received"] is True


def test_api_webhook_bad_signature_400(billing_client):
    r = billing_client.post(
        "/api/billing/webhook",
        data=_event(),
        headers={"Stripe-Signature": "t=1,v1=bogus", "Content-Type": "application/json"},
    )
    assert r.status_code == 400
    assert "error" in r.get_json()


# ── Concurrency regression (invoice append must be under lock) ─────


def test_invoice_append_thread_safety(stripe_env):
    mgr, _, _ = stripe_env
    errors = []
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            try:
                mgr.get_invoices("u1")
                mgr.get_stats()
            except Exception as e:  # noqa: BLE001
                errors.append(e)

    threads = [threading.Thread(target=reader, daemon=True) for _ in range(4)]
    for t in threads:
        t.start()
    try:
        for i in range(50):
            mgr.handle_webhook(_event(user_id=f"u{i}", session_id=f"cs_{i}"), VALID_SIG)
            time.sleep(0.002)
    finally:
        stop.set()
        for t in threads:
            t.join(timeout=5)
    assert errors == [], f"concurrent access raised: {errors[:3]}"
    total = sum(len(mgr.get_invoices(u)) for u in [f"u{i}" for i in range(50)])
    assert total == 50
