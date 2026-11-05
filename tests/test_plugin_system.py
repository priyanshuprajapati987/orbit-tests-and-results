# ORBIT — Plugin System tests (SaaS/PaaS)
# Run: python -m pytest tests/test_plugin_system.py -v

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.unit

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")


def test_plugin_store_imports():
    from orbit.orbit.core import plugin_store
    assert plugin_store is not None


def test_plugin_bridge_imports():
    from orbit.orbit.core import plugin_bridge
    assert plugin_bridge is not None
