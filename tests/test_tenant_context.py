# ORBIT — Tenant Context tests (SaaS/PaaS)
# Run: python -m pytest tests/test_tenant_context.py -v

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.unit

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")


def test_default_tenant():
    from orbit.orbit.core.tenant_context import get_tenant
    assert get_tenant() == "default"


def test_set_tenant():
    from orbit.orbit.core.tenant_context import set_tenant, get_tenant
    set_tenant("acme")
    assert get_tenant() == "acme"
    set_tenant("default")


def test_tenant_scoped_path():
    from orbit.orbit.core.tenant_context import tenant_scoped_path, set_tenant
    set_tenant("t1")
    assert tenant_scoped_path("/data") == "/data/t1"
    set_tenant("default")
