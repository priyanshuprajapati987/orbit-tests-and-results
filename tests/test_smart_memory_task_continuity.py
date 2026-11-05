"""Tests for smart_memory, task_continuity, proactive_context, security_guard, bugfixer."""

import os
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")


class TestSmartMemory(unittest.TestCase):
    def test_set_preference(self):
        from orbit.orbit.core.smart_memory import get_smart_memory

        mem = get_smart_memory()
        mem.set_preference("test_lang", "hinglish", confidence=0.9)
        val = mem.get_preference("test_lang")
        self.assertEqual(val, "hinglish")

    def test_learn_preference(self):
        from orbit.orbit.core.smart_memory import get_smart_memory

        mem = get_smart_memory()
        mem.learn_preference("python code query", "COD", True)
        stats = mem.get_stats()
        self.assertIn("preferences", stats)

    def test_record_correction(self):
        from orbit.orbit.core.smart_memory import get_smart_memory

        mem = get_smart_memory()
        mem.record_correction("test search query unique", "RES", "SEO")
        pattern = mem.get_correction_pattern("test search query unique")
        self.assertIsNotNone(pattern)

    def test_record_agent_usage(self):
        from orbit.orbit.core.smart_memory import get_smart_memory

        mem = get_smart_memory()
        mem.record_agent_usage("TAS", "file operation unique", True, 100.0)
        stats = mem.get_stats()
        self.assertIn("agent_patterns", stats)

    def test_get_best_agent(self):
        from orbit.orbit.core.smart_memory import get_smart_memory

        mem = get_smart_memory()
        # get_best_agent_for_topic needs 3+ successful uses of an agent on the same topic
        for _ in range(5):
            mem.record_agent_usage("COD", "topic_xyz_pattern", True, 100.0)
        best = mem.get_best_agent_for_topic("topic_xyz_pattern")
        self.assertIsNotNone(best)
        self.assertEqual(best, "COD")

    def test_singleton(self):
        from orbit.orbit.core.smart_memory import get_smart_memory

        m1 = get_smart_memory()
        m2 = get_smart_memory()
        self.assertIs(m1, m2)


class TestTaskContinuity(unittest.TestCase):
    def test_start_task(self):
        from orbit.orbit.core.task_continuity import get_task_continuity

        tc = get_task_continuity()
        task_id = tc.start_task("write a script unique", ["step1", "step2"])
        self.assertIsNotNone(task_id)
        self.assertIsInstance(task_id, str)

    def test_get_current_task(self):
        from orbit.orbit.core.task_continuity import get_task_continuity

        tc = get_task_continuity()
        tc.start_task("test task unique", ["a", "b"])
        current = tc.get_current_task()
        self.assertIsNotNone(current)
        self.assertEqual(current["goal"], "test task unique")

    def test_is_continuation(self):
        from orbit.orbit.core.task_continuity import get_task_continuity

        tc = get_task_continuity()
        tc.start_task("build website unique", ["design", "code", "deploy"])
        self.assertTrue(tc.is_continuation("then add styling"))
        self.assertTrue(tc.is_continuation("next step please"))

    def test_get_task_summary(self):
        from orbit.orbit.core.task_continuity import get_task_continuity

        tc = get_task_continuity()
        tc.start_task("summary test unique", ["x"])
        summary = tc.get_task_summary()
        self.assertIsInstance(summary, str)

    def test_get_next_step(self):
        from orbit.orbit.core.task_continuity import get_task_continuity

        tc = get_task_continuity()
        tc.start_task("multi step task unique", ["first", "second", "third"])
        step = tc.get_next_step()
        self.assertIsNotNone(step)

    def test_singleton(self):
        from orbit.orbit.core.task_continuity import get_task_continuity

        t1 = get_task_continuity()
        t2 = get_task_continuity()
        self.assertIs(t1, t2)


class TestProactiveContext(unittest.TestCase):
    def test_get_suggestions(self):
        from orbit.orbit.core.proactive_context import get_proactive_context

        ctx = get_proactive_context()
        suggestions = ctx.get_suggestions("hello", [])
        self.assertIsInstance(suggestions, list)

    def test_record_action(self):
        from orbit.orbit.core.proactive_context import get_proactive_context

        ctx = get_proactive_context()
        ctx.record_action("COD", "write code unique")
        stats = ctx.get_stats()
        self.assertIn("recent_actions", stats)

    def test_detect_patterns(self):
        from orbit.orbit.core.proactive_context import get_proactive_context

        ctx = get_proactive_context()
        for _ in range(5):
            ctx.record_action("TAS", "run tests unique")
        patterns = ctx.detect_patterns()
        self.assertIsInstance(patterns, list)

    def test_singleton(self):
        from orbit.orbit.core.proactive_context import get_proactive_context

        p1 = get_proactive_context()
        p2 = get_proactive_context()
        self.assertIs(p1, p2)


class TestSecurityGuard(unittest.TestCase):
    def test_get_security_guard(self):
        from orbit.orbit.core.security_guard import get_security_guard

        guard = get_security_guard()
        self.assertIsNotNone(guard)

    def test_check_defenses(self):
        from orbit.orbit.core.security_guard import get_security_guard

        guard = get_security_guard()
        defenses = guard.check_defenses()
        self.assertIsInstance(defenses, dict)

    def test_singleton(self):
        from orbit.orbit.core.security_guard import get_security_guard

        g1 = get_security_guard()
        g2 = get_security_guard()
        self.assertIs(g1, g2)


class TestBugFixer(unittest.TestCase):
    def test_get_bugfixer(self):
        from orbit.orbit.core.bugfixer import get_bugfixer

        bf = get_bugfixer()
        self.assertIsNotNone(bf)

    def test_singleton(self):
        from orbit.orbit.core.bugfixer import get_bugfixer

        b1 = get_bugfixer()
        b2 = get_bugfixer()
        self.assertIs(b1, b2)


if __name__ == "__main__":
    unittest.main()
