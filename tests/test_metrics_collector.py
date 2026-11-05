"""
Unit tests for orbit.orbit.core.metrics_collector (previously 0% covered).

Covers counters, gauges, histograms, metric history/stats, custom
collectors, system metric collection and persistence.
"""

import json
import time
from datetime import datetime, timedelta

import pytest

from orbit.orbit.core import metrics_collector as mc
from orbit.orbit.core.metrics_collector import MetricsCollector


@pytest.fixture
def collector(tmp_path):
    c = MetricsCollector(storage_file=str(tmp_path / "metrics.json"))
    yield c
    c.stop()


class TestRecording:
    def test_record_metric_stores_value_and_tags(self, collector):
        collector.record_metric("latency", 12.5, tags={"agent": "coder"})
        entry = collector.metrics["latency"][0]
        assert entry["value"] == 12.5
        assert entry["tags"] == {"agent": "coder"}
        assert entry["timestamp"]

    def test_record_metric_appends_history(self, collector):
        for value in (1, 2, 3):
            collector.record_metric("latency", value)
        assert [e["value"] for e in collector.metrics["latency"]] == [1, 2, 3]

    def test_history_trimmed_to_max(self, collector):
        collector.max_history = 5
        for value in range(12):
            collector.record_metric("latency", value)
        values = [e["value"] for e in collector.metrics["latency"]]
        assert values == [7, 8, 9, 10, 11]

    def test_increment_counter_accumulates(self, collector):
        collector.increment_counter("requests")
        collector.increment_counter("requests", 4)
        assert collector.counters["requests"] == 5
        assert collector.metrics["requests"][-1]["value"] == 5

    def test_set_gauge_overwrites(self, collector):
        collector.set_gauge("queue_depth", 3)
        collector.set_gauge("queue_depth", 7)
        assert collector.gauges["queue_depth"] == 7
        assert len(collector.metrics["queue_depth"]) == 2

    def test_record_histogram_keeps_values(self, collector):
        for value in (1.0, 2.0):
            collector.record_histogram("duration", value)
        assert collector.histograms["duration"] == [1.0, 2.0]

    def test_histogram_capped_at_1000(self, collector):
        for value in range(1005):
            collector.record_histogram("duration", value)
        assert len(collector.histograms["duration"]) == 1000
        assert collector.histograms["duration"][-1] == 1004


class TestQueries:
    def test_metric_stats(self, collector):
        for value in (2, 8, 5):
            collector.record_metric("latency", value)
        stats = collector.get_metric_stats("latency")
        assert stats["count"] == 3
        assert stats["min"] == 2
        assert stats["max"] == 8
        assert stats["avg"] == 5
        assert stats["latest"] == 5

    def test_metric_stats_for_unknown_metric(self, collector):
        assert collector.get_metric_stats("ghost") == {"name": "ghost", "count": 0}

    def test_metric_stats_for_empty_series(self, collector):
        collector.metrics["latency"] = []
        assert collector.get_metric_stats("latency")["count"] == 0

    def test_history_filters_by_age(self, collector):
        collector.record_metric("latency", 1)
        collector.metrics["latency"][0]["timestamp"] = (
            datetime.now() - timedelta(hours=48)).isoformat()
        collector.record_metric("latency", 2)
        recent = collector.get_metric_history("latency", hours=24)
        assert [e["value"] for e in recent] == [2]

    def test_history_for_unknown_metric(self, collector):
        assert collector.get_metric_history("ghost") == []

    def test_all_metrics_summary(self, collector):
        collector.record_metric("a", 1)
        collector.record_metric("b", 2)
        summary = collector.get_all_metrics_summary()
        assert set(summary) == {"a", "b"}
        assert summary["a"]["latest"] == 1


class TestCustomCollectors:
    def test_registered_collector_is_invoked(self, collector):
        collector.register_collector("open_files", lambda: 42)
        assert collector.collect_custom_metrics() == {"open_files": 42}
        assert collector.metrics["custom.open_files"][-1]["value"] == 42

    def test_failing_collector_is_skipped(self, collector):
        collector.register_collector("bad", lambda: 1 / 0)
        collector.register_collector("good", lambda: 1)
        assert collector.collect_custom_metrics() == {"good": 1}

    def test_no_collectors_returns_empty(self, collector):
        assert collector.collect_custom_metrics() == {}

    def test_collectors_listed_in_statistics(self, collector):
        collector.register_collector("open_files", lambda: 1)
        assert collector.get_statistics()["custom_collectors"] == 1


class TestSystemMetrics:
    def test_collect_system_metrics_records_values(self, collector):
        metrics = collector.collect_system_metrics()
        assert metrics["cpu_count"] >= 1
        assert 0 <= metrics["memory_percent"] <= 100
        assert collector.metrics["system.cpu_percent"]

    def test_collect_system_metrics_survives_psutil_errors(self, collector, monkeypatch):
        monkeypatch.setattr(mc.psutil, "cpu_percent",
                            lambda interval=0.1: (_ for _ in ()).throw(OSError("nope")))
        assert collector.collect_system_metrics() == {}

    def test_system_dashboard_shape(self, collector):
        collector.increment_counter("requests")
        collector.set_gauge("queue_depth", 2)
        collector.register_collector("open_files", lambda: 1)
        dashboard = collector.get_system_dashboard()
        assert dashboard["counters"] == {"requests": 1}
        assert dashboard["gauges"] == {"queue_depth": 2}
        assert dashboard["custom_collectors"] == ["open_files"]
        assert dashboard["timestamp"]

    def test_dashboard_copies_are_detached(self, collector):
        collector.set_gauge("queue_depth", 2)
        dashboard = collector.get_system_dashboard()
        collector.set_gauge("queue_depth", 9)
        assert dashboard["gauges"] == {"queue_depth": 2}


class TestLifecycle:
    @pytest.fixture(autouse=True)
    def _fast_collection(self, collector, monkeypatch):
        """Keep the background loop cheap so stop() joins immediately."""
        monkeypatch.setattr(collector, "collect_system_metrics", dict)
        monkeypatch.setattr(collector, "_save_data", lambda: None)

    def test_start_sets_running_and_interval(self, collector):
        collector.start(interval=0.01)
        assert collector.running is True
        assert collector.collection_interval == 0.01
        assert collector.get_statistics()["running"] is True

    def test_start_is_idempotent(self, collector):
        collector.start(interval=0.01)
        thread = collector._thread
        collector.start(interval=0.01)
        assert collector._thread is thread

    def test_background_loop_collects_custom_metrics(self, collector):
        calls = []

        def probe():
            calls.append(1)
            return len(calls)

        collector.register_collector("probe", probe)
        collector.start(interval=0.01)

        deadline = time.time() + 5
        while not calls and time.time() < deadline:
            time.sleep(0.01)

        assert calls

    def test_stop_halts_thread(self, collector):
        collector.start(interval=0.01)
        collector.stop()
        assert collector.running is False
        assert collector._thread.is_alive() is False

    def test_statistics(self, collector):
        collector.increment_counter("requests")
        collector.set_gauge("queue_depth", 1)
        stats = collector.get_statistics()
        assert stats["total_metrics"] == 2
        assert stats["total_counters"] == 1
        assert stats["total_gauges"] == 1
        assert stats["running"] is False


class TestPersistence:
    def test_counters_and_gauges_survive_reload(self, tmp_path):
        path = str(tmp_path / "metrics.json")
        first = MetricsCollector(storage_file=path)
        first.increment_counter("requests", 3)
        first.set_gauge("queue_depth", 5)
        first._save_data()

        reloaded = MetricsCollector(storage_file=path)
        assert reloaded.counters == {"requests": 3}
        assert reloaded.gauges == {"queue_depth": 5}

    def test_saved_metrics_are_trimmed(self, tmp_path):
        path = tmp_path / "metrics.json"
        collector = MetricsCollector(storage_file=str(path))
        collector.max_history = 3
        collector.metrics["latency"] = [{"value": i} for i in range(10)]
        collector._save_data()
        saved = json.loads(path.read_text(encoding="utf-8"))["metrics"]["latency"]
        assert [e["value"] for e in saved] == [7, 8, 9]

    def test_corrupt_storage_file_is_tolerated(self, tmp_path):
        path = tmp_path / "metrics.json"
        path.write_text("{broken", encoding="utf-8")
        assert MetricsCollector(storage_file=str(path)).metrics == {}


class TestModuleLevelApi:
    @pytest.fixture(autouse=True)
    def _isolated_singleton(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mc, "_metrics_collector",
                            MetricsCollector(storage_file=str(tmp_path / "m.json")))

    def test_get_metrics_collector_is_singleton(self):
        assert mc.get_metrics_collector() is mc.get_metrics_collector()

    def test_record_increment_and_gauge(self):
        mc.record_metric("latency", 1)
        mc.increment_counter("requests", 2)
        mc.set_gauge("queue_depth", 4)
        stats = mc.get_statistics()
        assert stats["total_metrics"] == 3
        assert stats["total_counters"] == 1
        assert stats["total_gauges"] == 1

    def test_system_dashboard(self):
        assert "system" in mc.get_system_dashboard()
