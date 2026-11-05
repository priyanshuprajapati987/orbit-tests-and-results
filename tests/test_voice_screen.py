# ORBIT — Voice Screen tests (Phase 2)
# Run: python -m pytest tests/test_voice_screen.py -v

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.unit

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")


def test_singleton():
    from orbit.orbit.core.voice_screen import get_voice_screen
    a = get_voice_screen()
    b = get_voice_screen()
    assert a is b


def test_default_config():
    from orbit.orbit.core.voice_screen import get_voice_screen
    vs = get_voice_screen()
    cfg = vs.get_config()
    assert cfg["mode"] in ("wake", "continuous")
    assert "enabled" in cfg


def test_status_shape():
    from orbit.orbit.core.voice_screen import get_voice_screen
    vs = get_voice_screen()
    st = vs.get_status()
    assert "state" in st
    assert "config" in st
    assert "enabled" in st["config"]


def test_start_stop():
    from orbit.orbit.core.voice_screen import get_voice_screen
    vs = get_voice_screen()
    r = vs.start(mode="wake")
    assert isinstance(r, dict)
    vs.stop()
    st = vs.get_status()
    assert st["state"] in ("idle", "error")
