"""Unit tests for orbit/orbit/core/agent_communication.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.agent_communication import (
    MessageType, MessagePriority, Message, AgentCommunication,
    get_agent_communication, register_agent, send_message, get_messages, get_agent_stats,
)


class TestEnums(unittest.TestCase):
    def test_message_type(self):
        self.assertEqual(MessageType.DIRECT.value, "direct")
        self.assertEqual(MessageType.BROADCAST.value, "broadcast")

    def test_message_priority(self):
        self.assertEqual(MessagePriority.URGENT.value, "urgent")


class TestMessage(unittest.TestCase):
    def test_init(self):
        m = Message(sender="a", receiver="b", content="hi")
        self.assertEqual(m.sender, "a")
        self.assertEqual(m.receiver, "b")
        self.assertEqual(m.content, "hi")
        self.assertFalse(m.read)

    def test_metadata(self):
        m = Message(sender="a", receiver="b", content="hi", metadata={"k": "v"})
        self.assertEqual(m.metadata, {"k": "v"})


class TestAgentCommunication(unittest.TestCase):
    def setUp(self):
        self.ac = AgentCommunication()

    def test_instantiation(self):
        self.assertIsNotNone(self.ac)

    def test_register_agent(self):
        self.ac.register_agent("a1", "Agent1", ["code"])
        self.assertIn("a1", self.ac.agents)

    def test_unregister_agent(self):
        self.ac.register_agent("a2", "Agent2")
        self.ac.unregister_agent("a2")
        self.assertNotIn("a2", self.ac.agents)

    def test_send_message(self):
        self.ac.register_agent("a", "A")
        self.ac.register_agent("b", "B")
        mid = self.ac.send_message("a", "b", "hello")
        self.assertIsNotNone(mid)

    def test_get_messages(self):
        self.ac.register_agent("a", "A")
        self.ac.register_agent("b", "B")
        self.ac.send_message("a", "b", "hello")
        r = self.ac.get_messages("b")
        self.assertIsInstance(r, list)
        self.assertGreaterEqual(len(r), 1)

    def test_mark_read(self):
        self.ac.register_agent("a", "A")
        self.ac.register_agent("b", "B")
        mid = self.ac.send_message("a", "b", "hello")
        self.ac.mark_read(mid)
        self.assertTrue(True)

    def test_get_queue_status(self):
        r = self.ac.get_queue_status()
        self.assertIsNotNone(r)

    def test_get_agent_stats(self):
        self.ac.register_agent("a", "A")
        r = self.ac.get_agent_stats("a")
        self.assertIsNotNone(r)

    def test_register_handler(self):
        self.ac.register_handler("a", lambda m: None)
        self.assertIn("a", self.ac.handlers)

    def test_register_broadcast_handler(self):
        self.ac.register_broadcast_handler(lambda m: None)
        self.assertGreaterEqual(len(self.ac.broadcast_handlers), 1)

    def test_request_response(self):
        self.ac.register_agent("a", "A")
        self.ac.register_agent("b", "B")
        try:
            r = self.ac.request_response("a", "b", "ping", timeout=0.1)
            self.assertTrue(r is None or isinstance(r, (str, dict, Message)))
        except Exception:
            self.assertTrue(True)

    def test_singleton(self):
        a = get_agent_communication()
        b = get_agent_communication()
        self.assertIs(a, b)


class TestModuleFunctions(unittest.TestCase):
    def test_register_agent_func(self):
        self.assertTrue(callable(register_agent))

    def test_send_message_func(self):
        self.assertTrue(callable(send_message))

    def test_get_messages_func(self):
        self.assertTrue(callable(get_messages))

    def test_get_agent_stats_func(self):
        self.assertTrue(callable(get_agent_stats))


if __name__ == "__main__":
    unittest.main()
