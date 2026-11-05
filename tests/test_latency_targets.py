"""Regression tests that the committed latency/reliability SLOs are present and sane.

These back the Phase SHOCK roadmap "Latency + reliability targets" checklist item:
wake->reply < 2s, query p95 < 3s, provider failover < 100ms, uptime >= 99%.
"""

import os
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from orbit.orbit.core import config


def test_latency_targets_present():
    t = config.get_latency_targets()
    assert "wake_to_reply_sec" in t
    assert "query_p95_sec" in t
    assert "provider_failover_ms" in t
    assert "uptime_pct" in t


def test_latency_targets_within_bounds():
    t = config.get_latency_targets()
    assert 0 < t["wake_to_reply_sec"] <= 5.0
    assert 0 < t["query_p95_sec"] <= 10.0
    assert 0 < t["provider_failover_ms"] <= 500
    assert 95.0 <= t["uptime_pct"] <= 100.0


def test_latency_targets_immutable_copy():
    t = config.get_latency_targets()
    t["wake_to_reply_sec"] = 999
    assert config.get_latency_targets()["wake_to_reply_sec"] != 999
