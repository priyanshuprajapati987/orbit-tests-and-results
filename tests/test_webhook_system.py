# ORBIT — Webhook System tests (SaaS/PaaS)
# Run: python -m pytest tests/test_webhook_system.py -v

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.unit

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")


def test_webhook_module_imports():
    from orbit.orbit.core import webhook_system
    assert webhook_system is not None


def test_webhook_bp_imports():
    from orbit.orbit.core import webhook_system_bp
    assert webhook_system_bp is not None
