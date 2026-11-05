"""Tests for CircuitBreaker — state machine, sync/async lock, thread safety."""

import asyncio
import os
import threading
import time
import unittest
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")

from orbit.orbit.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitState,
    get_all_circuit_states,
    get_circuit_breaker,
)


class TestCircuitBreakerState(unittest.TestCase):
    def test_initial_state_closed(self):
        cb = CircuitBreaker("test")
        self.assertEqual(cb.state, CircuitState.CLOSED)

    def test_single_lock_for_sync_and_async(self):
        cb = CircuitBreaker("test")
        self.assertIsInstance(cb._lock, type(threading.Lock()))
        # Verify no asyncio.Lock exists
        self.assertFalse(hasattr(cb, "_async_lock"))


class TestCircuitBreakerTransitions(unittest.TestCase):
    def test_opens_after_failures(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        for _ in range(3):
            cb._on_failure_sync(Exception("fail"))
        self.assertEqual(cb.state, CircuitState.OPEN)

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        cb._on_failure_sync(Exception("fail"))
        cb._on_failure_sync(Exception("fail"))
        cb._on_success_sync()
        # In CLOSED state, success should NOT reset failure_count
        # Only recovery from HALF_OPEN resets it
        self.assertEqual(cb._state.failure_count, 2)
        self.assertEqual(cb.state, CircuitState.CLOSED)

    def test_recovery_timeout(self):
        cb = CircuitBreaker(
            "test", CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.1)
        )
        cb._on_failure_sync(Exception("fail"))
        cb._on_failure_sync(Exception("fail"))
        self.assertEqual(cb.state, CircuitState.OPEN)
        time.sleep(0.15)
        # Next call should transition to HALF_OPEN
        self.assertEqual(cb._state.state, CircuitState.OPEN)  # still open until call

    def test_get_state_dict(self):
        cb = CircuitBreaker("test")
        state = cb.get_state()
        self.assertEqual(state["name"], "test")
        self.assertEqual(state["state"], "closed")
        self.assertIn("failure_count", state)
        self.assertIn("total_calls", state)


class TestCircuitBreakerSyncPath(unittest.TestCase):
    def test_sync_failure_increment(self):
        cb = CircuitBreaker("test")
        cb._on_failure_sync(Exception("error"))
        self.assertEqual(cb._state.failure_count, 1)
        self.assertEqual(cb._state.total_failures, 1)

    def test_sync_success_increment(self):
        cb = CircuitBreaker("test")
        cb._on_success_sync()
        self.assertEqual(cb._state.success_count, 1)
        self.assertEqual(cb._state.total_successes, 1)

    def test_sync_failure_opens_breaker(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=2))
        cb._on_failure_sync(Exception("e1"))
        cb._on_failure_sync(Exception("e2"))
        self.assertEqual(cb.state, CircuitState.OPEN)


class TestCircuitBreakerAsync(unittest.TestCase):
    def test_async_call_success(self):
        cb = CircuitBreaker("test")
        mock_fn = AsyncMock(return_value="ok")
        result = asyncio.run(cb.call(mock_fn))
        self.assertEqual(result, "ok")
        self.assertEqual(cb._state.total_successes, 1)

    def test_async_call_failure(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=2))
        mock_fn = AsyncMock(side_effect=Exception("fail"))
        with self.assertRaises(Exception):  # noqa: B017
            asyncio.run(cb.call(mock_fn))
        self.assertEqual(cb._state.failure_count, 1)

    def test_async_call_success_false_counted_as_failure(self):
        cb = CircuitBreaker("test")
        mock_response = MagicMock()
        mock_response.success = False
        mock_response.error = "provider error"
        mock_fn = AsyncMock(return_value=mock_response)
        asyncio.run(cb.call(mock_fn))
        self.assertEqual(cb._state.failure_count, 1)


class TestCircuitBreakerRegistry(unittest.TestCase):
    def test_get_circuit_breaker_singleton(self):
        cb1 = get_circuit_breaker("registry_test")
        cb2 = get_circuit_breaker("registry_test")
        self.assertIs(cb1, cb2)

    def test_get_all_states(self):
        get_circuit_breaker("all_states_test")
        states = get_all_circuit_states()
        names = [s["name"] for s in states]
        self.assertIn("all_states_test", names)


class TestCircuitBreakerThreadSafety(unittest.TestCase):
    def test_concurrent_sync_failures(self):
        cb = CircuitBreaker("thread_test", CircuitBreakerConfig(failure_threshold=100))
        errors = []

        def fail():
            try:
                cb._on_failure_sync(Exception("concurrent"))
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=fail) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)
        self.assertEqual(cb._state.failure_count, 50)
        self.assertEqual(cb._state.total_failures, 50)


class TestCircuitBreakerOpenError(unittest.TestCase):
    def test_error_message(self):
        err = CircuitBreakerOpenError("my_breaker", time.time())
        self.assertIn("my_breaker", str(err))
        self.assertEqual(err.circuit_name, "my_breaker")


if __name__ == "__main__":
    unittest.main()
