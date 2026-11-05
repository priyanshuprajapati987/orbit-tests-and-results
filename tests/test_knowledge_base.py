# ORBIT — Knowledge Base tests (Phase 3)
# Run: python -m pytest tests/test_knowledge_base.py -v

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.unit

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")


def test_singleton():
    from orbit.orbit.core.knowledge_base import get_knowledge_base
    a = get_knowledge_base()
    b = get_knowledge_base()
    assert a is b


def test_get_all_and_stats():
    from orbit.orbit.core.knowledge_base import get_knowledge_base
    kb = get_knowledge_base()
    all_items = kb.get_all()
    assert isinstance(all_items, list)
    stats = kb.get_stats()
    assert isinstance(stats, dict)
