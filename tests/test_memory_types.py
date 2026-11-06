"""Unit tests for orbit/orbit/core/memory/types.py."""

import os
import sys
import unittest
from datetime import datetime, timedelta

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.memory.types import (
    ContextType, IntentType, MemoryEntry, MemoryMetadata, TaskEntry, MemoryContext,
)


class TestContextType(unittest.TestCase):
    def test_values(self):
        self.assertEqual(ContextType.CHAT.value, "chat")
        self.assertEqual(ContextType.SECURITY.value, "security")


class TestIntentType(unittest.TestCase):
    def test_values(self):
        self.assertEqual(IntentType.CHAT.value, "chat")
        self.assertEqual(IntentType.COUNCIL.value, "council")


class TestMemoryEntry(unittest.TestCase):
    def test_init(self):
        me = MemoryEntry(timestamp="2026-01-01", user="hi", assistant="hello")
        self.assertEqual(me.user, "hi")
        self.assertEqual(me.context, "chat")

    def test_to_dict(self):
        me = MemoryEntry(timestamp="2026-01-01", user="hi", assistant="hello")
        d = me.to_dict()
        self.assertEqual(d["user"], "hi")
        self.assertEqual(d["assistant"], "hello")

    def test_from_dict(self):
        d = {"timestamp": "2026-01-01", "user": "hi", "assistant": "hello", "context": "memory", "platform": "web", "session_id": "s1", "metadata": {"k": "v"}}
        me = MemoryEntry.from_dict(d)
        self.assertEqual(me.user, "hi")
        self.assertEqual(me.context, "memory")
        self.assertEqual(me.metadata, {"k": "v"})

    def test_from_dict_defaults(self):
        me = MemoryEntry.from_dict({})
        self.assertEqual(me.user, "")
        self.assertEqual(me.assistant, "")


class TestMemoryMetadata(unittest.TestCase):
    def test_not_expired(self):
        mm = MemoryMetadata(created_at=datetime.now(), last_accessed=datetime.now())
        self.assertFalse(mm.is_expired())

    def test_expired(self):
        mm = MemoryMetadata(created_at=datetime.now(), last_accessed=datetime.now(), expires_at=datetime.now() - timedelta(days=1))
        self.assertTrue(mm.is_expired())

    def test_should_cleanup(self):
        mm = MemoryMetadata(created_at=datetime.now(), last_accessed=datetime.now(), expires_at=datetime.now() - timedelta(days=1))
        self.assertTrue(mm.should_cleanup())


class TestTaskEntry(unittest.TestCase):
    def test_init(self):
        te = TaskEntry(id=1, title="t", description="d")
        self.assertEqual(te.id, 1)
        self.assertEqual(te.status, "pending")

    def test_to_dict(self):
        te = TaskEntry(id=1, title="t", description="d")
        d = te.to_dict()
        self.assertEqual(d["id"], 1)
        self.assertEqual(d["title"], "t")

    def test_from_dict(self):
        d = {"id": 2, "title": "t2", "description": "d2", "status": "done", "platforms": ["web"]}
        te = TaskEntry.from_dict(d)
        self.assertEqual(te.id, 2)
        self.assertEqual(te.status, "done")
        self.assertEqual(te.platforms, ["web"])

    def test_from_dict_defaults(self):
        te = TaskEntry.from_dict({})
        self.assertEqual(te.id, 0)
        self.assertEqual(te.title, "")


class TestMemoryContext(unittest.TestCase):
    def test_get_context_str(self):
        me = MemoryEntry(timestamp="2026-01-01", user="hi", assistant="hello")
        mc = MemoryContext(recent_conversations=[me], active_tasks=[], user_preferences={}, platform="desktop", session_id="s1")
        r = mc.get_context_str()
        self.assertIn("User: hi", r)
        self.assertIn("ORBIT: hello", r)

    def test_get_context_str_empty(self):
        mc = MemoryContext(recent_conversations=[], active_tasks=[], user_preferences={}, platform="desktop", session_id="s1")
        self.assertEqual(mc.get_context_str(), "")

    def test_get_context_str_limit(self):
        mes = [MemoryEntry(timestamp="2026-01-01", user=f"u{i}", assistant=f"a{i}") for i in range(10)]
        mc = MemoryContext(recent_conversations=mes, active_tasks=[], user_preferences={}, platform="desktop", session_id="s1")
        r = mc.get_context_str(limit=2)
        self.assertIn("u8", r)
        self.assertIn("u9", r)

    def test_to_dict(self):
        me = MemoryEntry(timestamp="2026-01-01", user="hi", assistant="hello")
        mc = MemoryContext(recent_conversations=[me], active_tasks=[], user_preferences={"k": "v"}, platform="desktop", session_id="s1")
        d = mc.to_dict()
        self.assertIsInstance(d, dict)
        self.assertEqual(d["platform"], "desktop")
        self.assertEqual(len(d["recent_conversations"]), 1)


if __name__ == "__main__":
    unittest.main()
