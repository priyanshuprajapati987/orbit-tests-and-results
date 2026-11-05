"""Tests for ConversationEngine — state machine, locking, streaming context."""

import os
import threading
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")

from orbit.orbit.core.conversation_engine import (
    VALID_TRANSITIONS,
    ConversationEngine,
    ConversationState,
    TurnResult,
    get_engine,
)


class TestConversationState(unittest.TestCase):
    def test_valid_transitions_complete(self):
        """All states have defined transitions."""
        for state in ConversationState:
            self.assertIn(state, VALID_TRANSITIONS)

    def test_idle_can_route(self):
        self.assertIn(
            ConversationState.ROUTING, VALID_TRANSITIONS[ConversationState.IDLE]
        )

    def test_complete_can_reset(self):
        self.assertIn(
            ConversationState.ROUTING, VALID_TRANSITIONS[ConversationState.COMPLETE]
        )
        self.assertIn(
            ConversationState.IDLE, VALID_TRANSITIONS[ConversationState.COMPLETE]
        )

    def test_error_can_reset(self):
        self.assertIn(
            ConversationState.ROUTING, VALID_TRANSITIONS[ConversationState.ERROR]
        )
        self.assertIn(
            ConversationState.IDLE, VALID_TRANSITIONS[ConversationState.ERROR]
        )

    def test_invalid_transition_raises(self):
        engine = ConversationEngine()
        with self.assertRaises(ValueError):
            engine._transition(
                ConversationState.COMPLETE
            )  # IDLE -> COMPLETE is invalid

    def test_error_to_routing_recovery(self):
        engine = ConversationEngine()
        engine._state = ConversationState.ERROR
        engine._transition(ConversationState.ROUTING)  # Should not raise
        self.assertEqual(engine._state, ConversationState.ROUTING)

    def test_complete_to_routing_recovery(self):
        engine = ConversationEngine()
        engine._state = ConversationState.COMPLETE
        engine._transition(ConversationState.ROUTING)
        self.assertEqual(engine._state, ConversationState.ROUTING)


class TestTurnResult(unittest.TestCase):
    def test_to_dict(self):
        result = TurnResult(
            content="hello",
            state=ConversationState.COMPLETE,
            query_type="general",
            complexity="simple",
            provider="ollama",
            model="qwen3:8b",
            latency_ms=100.0,
            confidence=0.8,
            token_estimate=10,
        )
        d = result.to_dict()
        self.assertEqual(d["content"], "hello")
        self.assertEqual(d["state"], "complete")
        self.assertEqual(d["provider"], "ollama")
        self.assertFalse(d["error"])

    def test_to_dict_with_error(self):
        result = TurnResult(
            content="[error]",
            state=ConversationState.ERROR,
            query_type="general",
            complexity="simple",
            provider="none",
            model="none",
            latency_ms=50.0,
            confidence=0.0,
            token_estimate=0,
            error="timeout",
        )
        d = result.to_dict()
        self.assertTrue(d["error"])


class TestEngineSingleton(unittest.TestCase):
    def test_get_engine_returns_same_instance(self):
        e1 = get_engine()
        e2 = get_engine()
        self.assertIs(e1, e2)

    def test_engine_starts_idle(self):
        engine = get_engine()
        engine.reset()
        self.assertEqual(engine.state, ConversationState.IDLE)


class TestEngineRecordResult(unittest.TestCase):
    def test_record_result_thread_safe(self):
        engine = ConversationEngine()
        engine.reset()
        result = TurnResult(
            content="test",
            state=ConversationState.COMPLETE,
            query_type="general",
            complexity="simple",
            provider="test",
            model="test",
            latency_ms=100.0,
            confidence=0.5,
            token_estimate=10,
        )
        # Record from multiple threads
        errors = []

        def record():
            try:
                engine._record_result(result, "test message")
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=record) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)
        self.assertEqual(engine._turn_count, 10)

    def test_set_plan_and_topic_thread_safe(self):
        engine = ConversationEngine()
        engine.reset()
        errors = []

        def set_plan():
            try:
                engine._set_plan_and_topic({"type": "general"}, "hello world test")
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=set_plan) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)
        self.assertEqual(len(engine._topic_history), 10)


class TestEngineReset(unittest.TestCase):
    def test_reset_clears_state(self):
        engine = ConversationEngine()
        engine._state = ConversationState.COMPLETE
        engine._turn_count = 5
        engine._last_plan = {"foo": "bar"}
        engine._topic_history.append("test")

        engine.reset()

        self.assertEqual(engine._state, ConversationState.IDLE)
        self.assertEqual(engine._turn_count, 0)
        self.assertIsNone(engine._last_plan)
        self.assertEqual(len(engine._topic_history), 0)

    def test_reset_thread_safe(self):
        engine = ConversationEngine()
        engine._turn_count = 100
        errors = []

        def reset_engine():
            try:
                engine.reset()
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=reset_engine) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)
        self.assertEqual(engine._turn_count, 0)


class TestEngineGetStats(unittest.TestCase):
    def test_get_stats_returns_dict(self):
        engine = ConversationEngine()
        engine.reset()
        stats = engine.get_stats()
        self.assertIn("state", stats)
        self.assertIn("turn_count", stats)
        self.assertIn("latency", stats)
        self.assertEqual(stats["turn_count"], 0)

    def test_get_stats_thread_safe(self):
        engine = ConversationEngine()
        engine.reset()
        results = []

        def read_stats():
            results.append(engine.get_stats())

        threads = [threading.Thread(target=read_stats) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 10)
        for r in results:
            self.assertIn("state", r)


class TestEngineFollowupDetection(unittest.TestCase):
    def test_is_followup_with_overlap(self):
        engine = ConversationEngine()
        engine._topic_history.append("python programming language")
        self.assertTrue(engine._is_followup("tell me more about python programming"))

    def test_is_followup_no_overlap(self):
        engine = ConversationEngine()
        engine._topic_history.append("cooking recipes")
        self.assertFalse(engine._is_followup("quantum physics explained"))

    def test_is_followup_empty_history(self):
        engine = ConversationEngine()
        self.assertFalse(engine._is_followup("anything"))


class TestEngineTokenEstimation(unittest.TestCase):
    def test_estimate_tokens_basic(self):
        result = ConversationEngine._estimate_tokens(
            "hello world", "this is a response"
        )
        self.assertGreater(result, 0)

    def test_estimate_tokens_empty(self):
        result = ConversationEngine._estimate_tokens("", "")
        self.assertGreaterEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
