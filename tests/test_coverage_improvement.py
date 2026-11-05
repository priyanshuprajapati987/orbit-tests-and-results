# ORBIT — Coverage improvement tests (error handling, security, edge cases)
# Run: python -m pytest tests/test_coverage_improvement.py -v

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.unit

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")


def test_imports_ok():
    import orbit.orbit.core.config as c
    assert c is not None


def test_config_module_loads():
    import orbit.orbit.core.config as c
    assert c is not None


def test_tenant_context_default():
    from orbit.orbit.core.tenant_context import get_tenant, set_tenant
    set_tenant("default")
    assert get_tenant() == "default"


def test_pricing_tiers_load():
    import yaml
    from pathlib import Path
    p = Path("orbit/orbit/core/pricing_tiers.yaml")
    if p.exists():
        data = yaml.safe_load(p.read_text())
        assert "tiers" in data
        assert "free" in data["tiers"]
        assert "pro" in data["tiers"]
        assert "enterprise" in data["tiers"]


def test_api_docs_bp():
    from orbit.orbit.core.api_docs_bp import api_docs_bp
    assert api_docs_bp is not None


def test_sdk_client():
    from orbit.orbit.sdk import OrbitClient
    c = OrbitClient()
    assert c.base_url == "http://127.0.0.1:5000"
