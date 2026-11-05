"""
Unit tests for orbit.orbit.core.event_bus (previously 0% covered).

Covers pub/sub, wildcard subscribers, unsubscribe, async publishing,
event history and statistics.
"""

import time

import pytest

from orbit.orbit.core import event_bus as eb
from orbit.orbit.core.event_bus import Event, EventBus


@pytest.fixture
def bus():
    return EventBus()


class TestEvent:
    def test_defaults(self):
        event = Event("agent.started")
        assert event.event_type == "agent.started"
        assert event.data is None
        assert event.source == "system"
        assert event.handled is False

    def test_id_contains_event_type(self):
        assert Event("agent.started").id.startswith("agent.started_")

    def test_custom_data_and_source(self):
        event = Event("agent.done", {"ok": True}, source="orchestrator")
        assert event.data == {"ok": True}
        assert event.source == "orchestrator"


class TestPublishSubscribe:
    def test_subscriber_receives_event(self, bus):
        received = []
        bus.subscribe("task.done", received.append)
        bus.publish("task.done", {"id": 1})
        assert len(received) == 1
        assert received[0].data == {"id": 1}

    def test_publish_marks_event_handled(self, bus):
        bus.subscribe("task.done", lambda e: None)
        assert bus.publish("task.done").handled is True

    def test_publish_without_subscribers_is_unhandled(self, bus):
        assert bus.publish("task.done").handled is False

    def test_multiple_subscribers_all_called(self, bus):
        calls = []
        bus.subscribe("e", lambda ev: calls.append("a"))
        bus.subscribe("e", lambda ev: calls.append("b"))
        bus.publish("e")
        assert calls == ["a", "b"]

    def test_subscriber_only_receives_its_event_type(self, bus):
        received = []
        bus.subscribe("wanted", received.append)
        bus.publish("other")
        assert received == []

    def test_failing_handler_does_not_break_others(self, bus):
        calls = []

        def boom(event):
            raise RuntimeError("handler failed")

        bus.subscribe("e", boom)
        bus.subscribe("e", lambda ev: calls.append("ok"))
        bus.publish("e")
        assert calls == ["ok"]


class TestWildcardSubscribers:
    def test_wildcard_receives_every_event_type(self, bus):
        received = []
        bus.subscribe_all(received.append)
        bus.publish("a")
        bus.publish("b")
        assert [e.event_type for e in received] == ["a", "b"]

    def test_wildcard_does_not_mark_handled(self, bus):
        bus.subscribe_all(lambda e: None)
        assert bus.publish("a").handled is False

    def test_failing_wildcard_handler_is_swallowed(self, bus):
        bus.subscribe_all(lambda e: (_ for _ in ()).throw(RuntimeError("nope")))
        assert bus.publish("a").event_type == "a"


class TestUnsubscribe:
    def test_unsubscribe_removes_registered_callback(self, bus):
        received = []

        def handler(event):
            received.append(event)

        bus.subscribe("e", handler)
        bus.unsubscribe("e", handler)
        bus.publish("e")
        assert received == []

    def test_unsubscribe_unknown_event_type_is_noop(self, bus):
        bus.unsubscribe("ghost", lambda e: None)
        assert bus.get_subscribers() == {}

    def test_unsubscribe_all_clears_typed_and_wildcard(self, bus):
        received = []

        def handler(event):
            received.append(event)

        bus.subscribe("a", handler)
        bus.subscribe("b", handler)
        bus.subscribe_all(handler)
        bus.unsubscribe_all(handler)
        bus.publish("a")
        bus.publish("b")
        assert received == []
        assert bus.get_stats()["wildcard_subscribers"] == 0


class TestAsyncPublish:
    def test_async_event_is_delivered(self, bus):
        received = []
        bus.subscribe("e", received.append)
        bus.publish_async("e", {"n": 1})

        deadline = time.time() + 5
        while not received and time.time() < deadline:
            time.sleep(0.01)

        assert len(received) == 1
        assert received[0].data == {"n": 1}

    def test_async_queue_drains(self, bus):
        received = []
        bus.subscribe("e", received.append)
        for i in range(5):
            bus.publish_async("e", i)

        deadline = time.time() + 5
        while len(received) < 5 and time.time() < deadline:
            time.sleep(0.01)

        assert len(received) == 5
        assert bus.get_stats()["async_queue_size"] == 0


class TestHistory:
    def test_history_records_published_events(self, bus):
        bus.publish("a", "payload", source="tester")
        entry = bus.get_history()[-1]
        assert entry["event_type"] == "a"
        assert entry["source"] == "tester"
        assert entry["data"] == "payload"

    def test_history_filtered_by_event_type(self, bus):
        bus.publish("a")
        bus.publish("b")
        history = bus.get_history(event_type="b")
        assert [e["event_type"] for e in history] == ["b"]

    def test_history_respects_limit(self, bus):
        for i in range(10):
            bus.publish("a", i)
        assert len(bus.get_history(limit=3)) == 3

    def test_history_truncated_to_max(self, bus):
        bus.max_history = 5
        for i in range(12):
            bus.publish("a", i)
        assert len(bus.event_history) == 5

    def test_large_payload_is_truncated(self, bus):
        bus.publish("a", "x" * 500)
        assert len(bus.get_history()[-1]["data"]) == 200

    def test_none_payload_recorded_as_none(self, bus):
        bus.publish("a")
        assert bus.get_history()[-1]["data"] is None


class TestIntrospection:
    def test_get_subscribers_counts_per_type(self, bus):
        bus.subscribe("a", lambda e: None)
        bus.subscribe("a", lambda e: None)
        bus.subscribe("b", lambda e: None)
        assert bus.get_subscribers() == {"a": 2, "b": 1}

    def test_get_subscribers_for_single_type(self, bus):
        bus.subscribe("a", lambda e: None)
        assert bus.get_subscribers("a") == {"a": 1}

    def test_get_subscribers_for_unknown_type(self, bus):
        assert bus.get_subscribers("ghost") == {"ghost": 0}

    def test_stats(self, bus):
        bus.subscribe("a", lambda e: None)
        bus.subscribe_all(lambda e: None)
        bus.publish("a")
        stats = bus.get_stats()
        assert stats["total_events"] == 1
        assert stats["total_subscribers"] == 1
        assert stats["wildcard_subscribers"] == 1
        assert stats["event_types"] == ["a"]


class TestModuleLevelApi:
    @pytest.fixture(autouse=True)
    def _isolated_singleton(self, monkeypatch):
        monkeypatch.setattr(eb, "_event_bus", EventBus())

    def test_get_event_bus_is_singleton(self):
        assert eb.get_event_bus() is eb.get_event_bus()

    def test_subscribe_and_publish(self):
        received = []
        eb.subscribe("e", received.append)
        eb.publish("e", 1)
        assert [e.data for e in received] == [1]

    def test_subscribe_all_and_history(self):
        received = []
        eb.subscribe_all(received.append)
        eb.publish("e")
        assert len(received) == 1
        assert len(eb.get_history()) == 1

    def test_publish_async_delivered(self):
        received = []
        eb.subscribe("e", received.append)
        eb.publish_async("e")

        deadline = time.time() + 5
        while not received and time.time() < deadline:
            time.sleep(0.01)

        assert len(received) == 1

    def test_stats(self):
        eb.publish("e")
        assert eb.get_stats()["total_events"] == 1
