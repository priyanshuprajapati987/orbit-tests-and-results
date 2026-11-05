# Auto-generated tests for perf_utils (coverage improvement)
# Run: python -m pytest tests/test_perf_utils.py -v

from __future__ import annotations

import os
import time

import pytest

pytestmark = pytest.mark.unit

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")


def test_lru_cache_basic():
    from orbit.orbit.core.perf_utils import LRUCache
    c = LRUCache(maxsize=2)
    c.set("a", 1)
    assert c.get("a") == 1
    assert c.get("missing") is None


def test_lru_cache_eviction():
    from orbit.orbit.core.perf_utils import LRUCache
    c = LRUCache(maxsize=2)
    c.set("a", 1)
    c.set("b", 2)
    c.set("c", 3)
    assert c.get("a") is None
    assert c.get("c") == 3


def test_memoize():
    from orbit.orbit.core.perf_utils import memoize

    calls = {"n": 0}

    @memoize(maxsize=8)
    def f(x):
        calls["n"] += 1
        return x * 2

    assert f(5) == 10
    assert f(5) == 10
    assert calls["n"] == 1


def test_timed():
    from orbit.orbit.core.perf_utils import timed

    @timed
    def f():
        return 42

    result, elapsed = f()
    assert result == 42
    assert elapsed >= 0
