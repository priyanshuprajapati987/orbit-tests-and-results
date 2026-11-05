"""
Unit tests for orbit.orbit.core.message_queue (previously 0% covered).

Covers publishing, consuming, delayed messages, retries, the dead letter
queue, the background processor loop and statistics.
"""

import json
import time
from datetime import datetime, timedelta

import pytest

from orbit.orbit.core import message_queue as mq
from orbit.orbit.core.message_queue import (
    Message,
    MessagePriority,
    MessageQueue,
    MessageStatus,
)


@pytest.fixture
def queue(tmp_path):
    q = MessageQueue(storage_file=str(tmp_path / "mq.json"))
    yield q
    q.stop()


class TestMessage:
    def test_defaults(self):
        message = Message("jobs", {"x": 1})
        assert message.queue_name == "jobs"
        assert message.priority == MessagePriority.NORMAL
        assert message.status == MessageStatus.PENDING
        assert message.retry_count == 0
        assert message.delay_until is None

    def test_delay_sets_future_timestamp(self):
        message = Message("jobs", None, delay_seconds=60)
        assert message.delay_until > datetime.now()

    def test_higher_priority_sorts_first(self):
        urgent = Message("jobs", None, priority=MessagePriority.URGENT)
        low = Message("jobs", None, priority=MessagePriority.LOW)
        assert min([low, urgent]) is urgent

    def test_same_priority_sorts_by_creation_time(self):
        first = Message("jobs", None)
        second = Message("jobs", None)
        second.created_at = first.created_at + timedelta(seconds=1)
        assert min([second, first]) is first


class TestQueueCreation:
    def test_create_queue(self, queue):
        assert queue.create_queue("jobs") is True
        assert "jobs" in queue.queues

    def test_create_existing_queue_returns_false(self, queue):
        queue.create_queue("jobs")
        assert queue.create_queue("jobs") is False

    def test_publish_autocreates_queue(self, queue):
        queue.publish("jobs", {"x": 1})
        assert "jobs" in queue.queues

    def test_max_size_caps_queue(self, queue):
        queue.create_queue("jobs", max_size=2)
        for i in range(5):
            queue.publish("jobs", i)
        assert len(queue.queues["jobs"]) == 2


class TestPublishConsume:
    def test_publish_returns_message_id(self, queue):
        message_id = queue.publish("jobs", {"x": 1})
        assert queue.consume("jobs").id == message_id

    def test_consume_marks_processing(self, queue):
        queue.publish("jobs", {"x": 1})
        message = queue.consume("jobs")
        assert message.status == MessageStatus.PROCESSING
        assert message.processed_at is not None
        assert queue.processing[message.id] is message

    def test_consume_is_fifo(self, queue):
        queue.publish("jobs", 1)
        queue.publish("jobs", 2)
        assert [queue.consume("jobs").data, queue.consume("jobs").data] == [1, 2]

    def test_consume_empty_queue_returns_none(self, queue):
        queue.create_queue("jobs")
        assert queue.consume("jobs") is None

    def test_consume_unknown_queue_returns_none(self, queue):
        assert queue.consume("ghost") is None

    def test_delayed_message_is_not_consumed_yet(self, queue):
        queue.publish("jobs", 1, delay_seconds=60)
        assert queue.consume("jobs") is None
        assert len(queue.queues["jobs"]) == 1

    def test_dead_message_is_skipped(self, queue):
        queue.publish("jobs", 1)
        queue.queues["jobs"][0].status = MessageStatus.DEAD
        queue.publish("jobs", 2)
        assert queue.consume("jobs").data == 2


class TestCompleteAndFail:
    def test_complete_removes_from_processing(self, queue):
        message_id = queue.publish("jobs", 1)
        queue.consume("jobs")
        queue.complete(message_id)
        assert message_id not in queue.processing
        assert queue.message_history[-1]["action"] == "completed"

    def test_complete_unknown_message_is_noop(self, queue):
        queue.complete("missing")
        assert queue.message_history == []

    def test_fail_requeues_for_retry(self, queue):
        message_id = queue.publish("jobs", 1, max_retries=2)
        queue.consume("jobs")
        queue.fail(message_id, "boom")
        message = queue.queues["jobs"][0]
        assert message.status == MessageStatus.PENDING
        assert message.retry_count == 1
        assert message.error == "boom"
        assert queue.message_history[-1]["action"] == "retried"

    def test_fail_beyond_max_retries_goes_to_dead_letter(self, queue):
        message_id = queue.publish("jobs", 1, max_retries=1)
        queue.consume("jobs")
        queue.fail(message_id, "boom")
        assert len(queue.dead_letter_queue) == 1
        assert queue.dead_letter_queue[0].status == MessageStatus.DEAD
        assert queue.message_history[-1]["action"] == "dead"

    def test_retries_exhaust_into_dead_letter(self, queue):
        message_id = queue.publish("jobs", 1, max_retries=2)
        for _ in range(2):
            message = queue.consume("jobs")
            queue.fail(message.id, "boom")
        assert message_id == queue.dead_letter_queue[0].id
        assert len(queue.queues["jobs"]) == 0

    def test_fail_unknown_message_is_noop(self, queue):
        queue.fail("missing", "boom")
        assert queue.message_history == []

    def test_history_is_capped(self, queue):
        queue.message_history = [{"i": i} for i in range(1000)]
        message_id = queue.publish("jobs", 1)
        queue.consume("jobs")
        queue.complete(message_id)
        assert len(queue.message_history) == 1000


class TestProcessorLoop:
    def test_consumer_receives_published_message(self, queue):
        received = []
        queue.subscribe("jobs", received.append)
        queue.create_queue("jobs")
        queue.publish("jobs", {"x": 1})
        queue.start()

        deadline = time.time() + 5
        while not received and time.time() < deadline:
            time.sleep(0.02)

        assert [m.data for m in received] == [{"x": 1}]

    def test_failing_consumer_moves_message_to_dead_letter(self, queue):
        def boom(message):
            raise RuntimeError("consumer failed")

        queue.subscribe("jobs", boom)
        queue.publish("jobs", 1, max_retries=1)
        queue.start()

        deadline = time.time() + 5
        while not queue.dead_letter_queue and time.time() < deadline:
            time.sleep(0.02)

        assert len(queue.dead_letter_queue) == 1

    def test_start_is_idempotent(self, queue):
        queue.start()
        thread = queue._thread
        queue.start()
        assert queue._thread is thread

    def test_stop_halts_processor(self, queue):
        queue.start()
        queue.stop()
        assert queue.running is False
        assert queue._thread.is_alive() is False


class TestStatusAndStats:
    def test_status_for_single_queue(self, queue):
        queue.publish("jobs", 1)
        queue.publish("jobs", 2)
        queue.consume("jobs")
        status = queue.get_queue_status("jobs")
        assert status == {"queue_name": "jobs", "pending": 1, "processing": 1}

    def test_status_for_unknown_queue(self, queue):
        assert queue.get_queue_status("ghost")["pending"] == 0

    def test_global_status(self, queue):
        queue.publish("a", 1)
        queue.publish("b", 2)
        status = queue.get_queue_status()
        assert status["queues"] == {"a": 1, "b": 1}
        assert status["total_pending"] == 2
        assert status["total_processing"] == 0
        assert status["dead_letter"] == 0

    def test_statistics(self, queue):
        queue.subscribe("jobs", lambda m: None)
        message_id = queue.publish("jobs", 1)
        queue.consume("jobs")
        queue.complete(message_id)
        stats = queue.get_statistics()
        assert stats["total_queues"] == 1
        assert stats["total_consumers"] == 1
        assert stats["total_messages"] == 0
        assert stats["processing"] == 0
        assert stats["history_size"] == 1


class TestPersistence:
    def test_history_saved_and_reloaded(self, tmp_path):
        path = tmp_path / "mq.json"
        first = MessageQueue(storage_file=str(path))
        message_id = first.publish("jobs", 1)
        first.consume("jobs")
        first.complete(message_id)
        first._save_data()

        assert json.loads(path.read_text(encoding="utf-8"))["history"]
        assert MessageQueue(storage_file=str(path)).get_statistics()["history_size"] == 1

    def test_corrupt_storage_file_is_tolerated(self, tmp_path):
        path = tmp_path / "mq.json"
        path.write_text("{broken", encoding="utf-8")
        assert MessageQueue(storage_file=str(path)).message_history == []


class TestModuleLevelApi:
    @pytest.fixture(autouse=True)
    def _isolated_singleton(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mq, "_message_queue",
                            MessageQueue(storage_file=str(tmp_path / "mq.json")))

    def test_get_message_queue_is_singleton(self):
        assert mq.get_message_queue() is mq.get_message_queue()

    def test_create_publish_and_status(self):
        assert mq.create_queue("jobs") is True
        mq.publish("jobs", {"x": 1}, priority=MessagePriority.HIGH)
        assert mq.get_queue_status("jobs")["pending"] == 1

    def test_subscribe_counted_in_statistics(self):
        mq.subscribe("jobs", lambda m: None)
        assert mq.get_statistics()["total_consumers"] == 1
