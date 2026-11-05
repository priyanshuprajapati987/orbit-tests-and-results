# ORBIT — Trading Monitor tests (Phase 3)
# Run: python -m pytest tests/test_trading_monitor.py -v

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.unit

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")


def test_singleton():
    from orbit.orbit.core.trading_monitor import get_trading_monitor
    a = get_trading_monitor()
    b = get_trading_monitor()
    assert a is b


def test_watchlist_and_stats():
    from orbit.orbit.core.trading_monitor import get_trading_monitor
    tm = get_trading_monitor()
    wl = tm.get_watchlist()
    assert isinstance(wl, list)
    stats = tm.get_stats()
    assert isinstance(stats, dict)
