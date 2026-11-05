"""Tests for billing module — plans, usage tracking, quota, invoices."""

import os
import json
import time
import tempfile
import threading

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")

import pytest


@pytest.fixture
def billing(tmp_path, monkeypatch):
    from orbit.orbit.core.billing import BillingManager, PLANS

    bm = BillingManager(data_dir=str(tmp_path))
    return bm


def test_plans_defined():
    from orbit.orbit.core.billing import PLANS

    assert "free" in PLANS
    assert "pro" in PLANS
    assert "enterprise" in PLANS
    assert PLANS["free"].price_monthly == 0
    assert PLANS["pro"].price_monthly == 20
    assert PLANS["enterprise"].price_monthly == 200


def test_get_user_plan_default(billing):
    plan = billing.get_user_plan("newuser")
    assert plan.id == "free"


def test_set_user_plan(billing):
    assert billing.set_user_plan("user1", "pro") is True
    plan = billing.get_user_plan("user1")
    assert plan.id == "pro"


def test_set_user_plan_invalid(billing):
    assert billing.set_user_plan("user1", "invalid") is False


def test_record_usage(billing):
    billing.record_usage("user1", 0.5, 100, 50)
    usage = billing.get_usage_today("user1")
    assert usage.cost_usd == 0.5
    assert usage.calls == 1
    assert usage.tokens_in == 100
    assert usage.tokens_out == 50


def test_record_usage_accumulates(billing):
    billing.record_usage("user1", 0.5)
    billing.record_usage("user1", 0.3)
    usage = billing.get_usage_today("user1")
    assert usage.cost_usd == 0.8
    assert usage.calls == 2


def test_check_quota_free(billing):
    billing.record_usage("user1", 1.0)
    quota = billing.check_quota("user1")
    assert quota["plan_id"] == "free"
    assert quota["spent_today"] == 1.0
    assert quota["quota_exceeded"] is False


def test_check_quota_exceeded(billing):
    billing.set_user_plan("user1", "free")
    billing.record_usage("user1", 2.5)
    quota = billing.check_quota("user1")
    assert quota["quota_exceeded"] is True


def test_check_quota_call_limit(billing):
    billing.set_user_plan("user1", "free")
    for _ in range(200):
        billing.record_usage("user1", 0)
    quota = billing.check_quota("user1")
    assert quota["quota_exceeded"] is True


def test_get_invoices_empty(billing):
    invoices = billing.get_invoices("user1")
    assert invoices == []


def test_get_stats(billing):
    billing.set_user_plan("user1", "pro")
    billing.set_user_plan("user2", "free")
    stats = billing.get_stats()
    assert stats["total_users"] == 2
    assert stats["plan_counts"]["pro"] == 1
    assert stats["plan_counts"]["free"] == 1


def test_thread_safety(billing):
    errors = []

    def worker(n):
        try:
            for i in range(50):
                billing.record_usage(f"user{n}", 0.01, 10, 5)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0


def test_persistence(billing):
    billing.set_user_plan("user1", "pro")
    billing.record_usage("user1", 1.5, 100, 50)

    from orbit.orbit.core.billing import BillingManager

    bm2 = BillingManager(data_dir=str(billing._data_dir))
    plan = bm2.get_user_plan("user1")
    assert plan.id == "pro"
    usage = bm2.get_usage_today("user1")
    assert usage.cost_usd == 1.5


def test_stripe_disabled_by_default(billing):
    assert billing._stripe_enabled is False


def test_create_checkout_no_stripe(billing):
    url = billing.create_checkout_session("user1", "pro", "http://x", "http://y")
    assert url is None


def test_handle_webhook_no_stripe(billing):
    ok = billing.handle_webhook(b"{}", "sig")
    assert ok is False
