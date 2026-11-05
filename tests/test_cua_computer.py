# ORBIT — CUA Computer tests (Phase 2)
# Run: python -m pytest tests/test_cua_computer.py -v

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.unit

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")


def test_is_available_returns_bool():
    from orbit.orbit.tools.cua_computer import is_available
    assert isinstance(is_available(), bool)


def test_tool_instantiates():
    from orbit.orbit.tools.cua_computer import CuaComputerTool
    t = CuaComputerTool()
    assert t is not None
