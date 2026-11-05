"""
Comprehensive tests for ORBIT new modules.
Tests agents, tools, wake word, voice cloning, and memory.
"""

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestConfig(unittest.TestCase):
    def test_config_imports(self):
        from orbit.config import MEM0_CONFIG, MEMORY_DIR, QDRANT_URL

        self.assertTrue(MEMORY_DIR)
        self.assertIsInstance(MEM0_CONFIG, dict)
        self.assertTrue(QDRANT_URL)


class TestProceduralMemory(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.core.procedural_memory import ProceduralMemory

        pm = ProceduralMemory()
        self.assertTrue(callable(pm.store_procedure))
        self.assertTrue(callable(pm.search_procedures))

    def test_save_and_recall(self):
        from orbit.orbit.core.procedural_memory import ProceduralMemory

        pm = ProceduralMemory()
        proc_id = pm.store_procedure(
            name="test_proc",
            steps=["step1", "step2"],
            category="test",
            tags=["test"],
        )
        self.assertTrue(proc_id.startswith("proc_"))
        results = pm.search_procedures("test_proc")
        self.assertGreater(len(results), 0)


class TestMemory(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.memory import get_all, save_conversation, search

        self.assertTrue(callable(search))
        self.assertTrue(callable(save_conversation))
        self.assertTrue(callable(get_all))

    def test_save_and_search(self):
        from orbit.orbit.memory import save_conversation, search

        save_conversation("test user msg", "test assistant msg", "test")
        results = search("test", limit=5)
        self.assertIsInstance(results, list)


class TestWebSearch(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.tools.web_search import WebSearchTool

        tool = WebSearchTool()
        self.assertTrue(hasattr(tool, "search"))

    def test_search(self):
        from orbit.orbit.tools.web_search import WebSearchTool

        tool = WebSearchTool()
        result = tool.search("what is python programming")
        self.assertIn("results", result)


class TestFileTools(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.tools.file_tools import FileTools

        tool = FileTools()
        self.assertTrue(hasattr(tool, "list_dir"))
        self.assertTrue(hasattr(tool, "read"))

    def test_list_dir(self):
        from orbit.orbit.tools.file_tools import FileTools

        tool = FileTools()
        result = tool.list_dir(".")
        self.assertIn("items", result)
        self.assertIsInstance(result.get("items"), list)

    def test_write_and_read(self):
        from orbit.orbit.tools.file_tools import FileTools

        tool = FileTools()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("test content")
            tmp_path = f.name
        try:
            result = tool.read(tmp_path)
            self.assertIn("test content", result.get("content", ""))
        finally:
            os.unlink(tmp_path)

    def test_blocked_dirs(self):
        from orbit.orbit.tools.file_tools import FileTools

        tool = FileTools()
        result = tool.write("C:\\Windows\\System32\\test.txt", "blocked")
        self.assertIn("error", result)


class TestEmailTool(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.tools.email_tool import EmailTool

        tool = EmailTool()
        self.assertTrue(hasattr(tool, "check_config"))

    def test_config_check(self):
        from orbit.orbit.tools.email_tool import EmailTool

        tool = EmailTool()
        result = tool.check_config()
        self.assertIn("configured", result)


class TestCalendarTool(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.tools.calendar_tool import CalendarTool

        tool = CalendarTool()
        self.assertTrue(hasattr(tool, "create_event"))
        self.assertTrue(hasattr(tool, "list_events"))

    def test_create_event(self):
        from orbit.orbit.tools.calendar_tool import CalendarTool

        tool = CalendarTool()
        result = tool.create_event(
            title="Test Meeting",
            date="2025-01-01",
            time="10:00",
            duration_minutes=60,
        )
        self.assertTrue(result.get("success"))
        self.assertIn("event", result)

    def test_list_events(self):
        from orbit.orbit.tools.calendar_tool import CalendarTool

        tool = CalendarTool()
        result = tool.list_events()
        self.assertIsInstance(result, list)


class TestWakeWord(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.wake_word import WakeWordDetector

        detector = WakeWordDetector()
        self.assertTrue(hasattr(detector, "start"))
        self.assertTrue(hasattr(detector, "stop"))
        self.assertTrue(hasattr(detector, "get_info"))

    def test_get_info(self):
        from orbit.orbit.wake_word import get_wake_word_detector

        detector = get_wake_word_detector()
        info = detector.get_info()
        self.assertIn("available", info)
        self.assertIn("engine", info)


class TestVoiceCloner(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.xtts import VoiceCloner

        cloner = VoiceCloner()
        self.assertTrue(hasattr(cloner, "clone_voice"))
        self.assertTrue(hasattr(cloner, "list_samples"))

    def test_list_samples_empty(self):
        from orbit.orbit.xtts import VoiceCloner

        cloner = VoiceCloner()
        samples = cloner.list_samples()
        self.assertIsInstance(samples, list)

    def test_get_info(self):
        from orbit.orbit.xtts import get_voice_cloner

        cloner = get_voice_cloner()
        info = cloner.get_info()
        self.assertIn("available", info)
        self.assertIn("model", info)


class TestAgents(unittest.TestCase):
    def test_import_all(self):
        from orbit.agents import (
            CodeAgent,
            FineTuneAgent,
            LogAnalystAgent,
            QuarantineAgent,
            QueenAgent,
            SEOAgent,
            ThumbnailAgent,
        )

        self.assertTrue(QueenAgent)
        self.assertTrue(CodeAgent)
        self.assertTrue(FineTuneAgent)
        self.assertTrue(ThumbnailAgent)
        self.assertTrue(SEOAgent)
        self.assertTrue(QuarantineAgent)
        self.assertTrue(LogAnalystAgent)

    def test_agent_registry(self):
        from orbit.agents import AGENT_REGISTRY

        self.assertIn("TAS", AGENT_REGISTRY)
        self.assertIn("COD", AGENT_REGISTRY)
        self.assertIn("FTN", AGENT_REGISTRY)
        self.assertIn("THB", AGENT_REGISTRY)
        self.assertIn("SEO", AGENT_REGISTRY)
        self.assertIn("QNT", AGENT_REGISTRY)
        self.assertIn("LOG", AGENT_REGISTRY)
        self.assertIn("CRT", AGENT_REGISTRY)

    def test_new_agents_can_handle(self):
        from orbit.orbit.agents.specialized import (
            FineTuneAgent,
            LogAnalystAgent,
            QuarantineAgent,
            SEOAgent,
            ThumbnailAgent,
        )

        ft = FineTuneAgent()
        self.assertTrue(ft.can_handle("fine-tune training data"))
        self.assertFalse(ft.can_handle("hello world"))

        tb = ThumbnailAgent()
        self.assertTrue(tb.can_handle("design a thumbnail image"))

        seo = SEOAgent()
        self.assertTrue(seo.can_handle("optimize seo keywords"))

        qn = QuarantineAgent()
        self.assertTrue(qn.can_handle("quarantine suspicious file"))

        la = LogAnalystAgent()
        self.assertTrue(la.can_handle("analyze error logs"))


class TestRouter(unittest.TestCase):
    def test_import(self):
        from orbit.router import check_internet, generate, get_status

        self.assertTrue(callable(generate))
        self.assertTrue(callable(get_status))
        self.assertTrue(callable(check_internet))

    def test_status(self):
        from orbit.router import get_status

        status = get_status()
        self.assertIn("online", status)


class TestMCPTool(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.tools.mcp_tool import (
            MCPClient,
            MCPManager,
            ORBITMCPServer,
            get_manager,
        )

        self.assertTrue(MCPManager)
        self.assertTrue(MCPClient)
        self.assertTrue(ORBITMCPServer)
        self.assertTrue(callable(get_manager))

    def test_mcp_manager_init(self):
        from orbit.orbit.tools.mcp_tool import get_manager

        mgr = get_manager()
        self.assertIsNotNone(mgr)
        self.assertTrue(hasattr(mgr, "list_tools"))
        self.assertTrue(hasattr(mgr, "call_tool"))
        self.assertTrue(hasattr(mgr, "get_status"))

    def test_mcp_manager_status(self):
        from orbit.orbit.tools.mcp_tool import get_manager

        mgr = get_manager()
        status = mgr.get_status()
        self.assertIsInstance(status, list)

    def test_mcp_server_init(self):
        from orbit.orbit.tools.mcp_tool import ORBITMCPServer

        server = ORBITMCPServer(port=9999)
        self.assertTrue(hasattr(server, "start"))
        self.assertTrue(hasattr(server, "stop"))


class TestCodeCompletion(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.tools.code_completion import (
            CodeCompletionEngine,
            detect_language,
            get_engine,
        )

        self.assertTrue(CodeCompletionEngine)
        self.assertTrue(callable(get_engine))
        self.assertTrue(callable(detect_language))

    def test_detect_language(self):
        from orbit.orbit.tools.code_completion import detect_language

        self.assertEqual(detect_language("test.py"), "python")
        self.assertEqual(detect_language("test.js"), "javascript")
        self.assertEqual(detect_language("test.ts"), "typescript")
        self.assertEqual(detect_language("test.java"), "java")
        self.assertEqual(detect_language("test.xyz"), "text")

    def test_complete_line_pattern(self):
        from orbit.orbit.tools.code_completion import get_engine

        engine = get_engine()
        suggestion = engine.complete_line("test.py", "def hello():", 1)
        self.assertEqual(suggestion, "    pass\n")

    def test_suggest_completions_type(self):
        from orbit.orbit.tools.code_completion import get_engine

        engine = get_engine()
        completions = engine.suggest_completions("test.py", 1, 0, [])
        self.assertIsInstance(completions, list)

    def test_suggest_next_edits(self):
        from orbit.orbit.tools.code_completion import get_engine

        engine = get_engine()
        lines = ["def hello():\n"]
        predictions = engine.suggest_next_edits("test.py", lines)
        self.assertIsInstance(predictions, list)

    def test_clear_cache(self):
        from orbit.orbit.tools.code_completion import get_engine

        engine = get_engine()
        engine.clear_cache()
        engine.clear_cache("test.py")


class TestSmartActions(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.tools.smart_actions import SmartActions

        sa = SmartActions()
        self.assertTrue(hasattr(sa, "run_action"))
        self.assertTrue(hasattr(sa, "quick_fix"))
        self.assertTrue(hasattr(sa, "list_actions"))

    def test_list_actions(self):
        from orbit.orbit.tools.smart_actions import SmartActions

        sa = SmartActions()
        actions = sa.list_actions()
        self.assertIn("actions", actions)
        self.assertIn("explain", actions["actions"])
        self.assertIn("fix", actions["actions"])

    def test_run_action_invalid(self):
        from orbit.orbit.tools.smart_actions import SmartActions

        sa = SmartActions()
        result = sa.run_action("invalid_action", "print('hi')")
        self.assertFalse(result["success"])
        self.assertIn("error", result)

    def test_quick_fix_invalid_error(self):
        from orbit.orbit.tools.smart_actions import SmartActions

        sa = SmartActions()
        result = sa.quick_fix("", "")
        self.assertIn("success", result)


class TestWatchdogLocks(unittest.TestCase):
    """Tests for Watchdog PID-Liveness Lock mechanism."""

    def test_lock_acquire_release(self):
        from orbit.orbit.core.watchdog import ProcessLockManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = ProcessLockManager(Path(tmpdir) / "locks")
            self.assertTrue(mgr.acquire("test_resource"))
            self.assertTrue(mgr.is_locked("test_resource"))
            self.assertTrue(mgr.release("test_resource"))
            self.assertFalse(mgr.is_locked("test_resource"))

    def test_lock_contention(self):
        from orbit.orbit.core.watchdog import ProcessLockManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = ProcessLockManager(Path(tmpdir) / "locks")
            self.assertTrue(mgr.acquire("resource"))
            # Second acquire should fail (resource already locked)
            self.assertFalse(mgr.acquire("resource"))
            mgr.release("resource")
            # Now second acquire should succeed
            self.assertTrue(mgr.acquire("resource"))
            mgr.release("resource")

    def test_dead_pid_reclaim(self):
        from orbit.orbit.core.watchdog import ProcessLockManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = ProcessLockManager(Path(tmpdir) / "locks")

            # Use a PID that is dead — on Windows, use a small unlikely PID
            # On Unix, 999999 is unlikely to exist
            dead_pid = 999999
            # Manually inject a lock with a dead PID
            lock_file = Path(tmpdir) / "locks" / "dead_proc.json"
            lock_file.parent.mkdir(parents=True, exist_ok=True)
            lock_file.write_text(
                json.dumps(
                    {
                        "pid": dead_pid,
                        "acquired_at": time.time() - 600,
                        "component": "test_component",
                    }
                ),
                encoding="utf-8",
            )
            mgr._locks["dead_proc"] = {
                "pid": dead_pid,
                "acquired_at": time.time() - 600,
                "component": "test_component",
            }

            # Verify the PID is actually dead first
            self.assertFalse(ProcessLockManager._is_process_alive(dead_pid))

            # Verify is_locked returns False for dead process
            self.assertFalse(mgr.is_locked("dead_proc"))

            # Acquire should reclaim the dead lock immediately
            self.assertTrue(mgr.acquire("dead_proc", "test_component"))
            # Should be locked by current process now
            self.assertTrue(mgr.is_locked("dead_proc"))
            mgr.release("dead_proc")

    def test_reclaim_dead_locks(self):
        from orbit.orbit.core.watchdog import ProcessLockManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = ProcessLockManager(Path(tmpdir) / "locks")
            # Add a dead process lock
            dead_pid = 999999
            mgr._locks["dead1"] = {
                "pid": dead_pid,
                "acquired_at": time.time() - 300,
                "component": "a",
            }
            mgr._locks["dead2"] = {
                "pid": dead_pid,
                "acquired_at": time.time() - 200,
                "component": "b",
            }
            mgr._locks["alive"] = {
                "pid": os.getpid(),
                "acquired_at": time.time(),
                "component": "c",
            }

            reclaimed = mgr.reclaim_dead_locks()
            self.assertIn("dead1", reclaimed)
            self.assertIn("dead2", reclaimed)
            self.assertNotIn("alive", reclaimed)
            # alive should still be locked
            self.assertTrue(mgr.is_locked("alive"))
            mgr.release("alive")

    def test_get_all_locks(self):
        from orbit.orbit.core.watchdog import ProcessLockManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = ProcessLockManager(Path(tmpdir) / "locks")
            mgr.acquire("res1", "comp1")
            mgr.acquire("res2", "comp2")
            all_locks = mgr.get_all_locks()
            self.assertIn("res1", all_locks)
            self.assertIn("res2", all_locks)
            self.assertTrue(all_locks["res1"]["alive"])
            self.assertTrue(all_locks["res2"]["alive"])
            mgr.release("res1")
            mgr.release("res2")

    def test_is_process_alive(self):
        from orbit.orbit.core.watchdog import ProcessLockManager

        # Current process should be alive
        self.assertTrue(ProcessLockManager._is_process_alive(os.getpid()))
        # Dead PID should be not alive (use reasonable PID that doesn't exist)
        self.assertFalse(ProcessLockManager._is_process_alive(999999))
        # Invalid PID should be not alive
        self.assertFalse(ProcessLockManager._is_process_alive(0))
        self.assertFalse(ProcessLockManager._is_process_alive(-1))

    def test_watchdog_uses_lock_manager(self):
        from orbit.orbit.core.watchdog import get_watchdog

        wd = get_watchdog()
        # Should be able to acquire/release through watchdog
        self.assertTrue(wd.acquire_lock("wd_test", "test"))
        locks = wd.get_all_locks()
        self.assertIn("wd_test", locks)
        status = wd.get_lock_status("wd_test")
        self.assertIsNotNone(status)
        self.assertTrue(status["alive"])
        self.assertTrue(wd.release_lock("wd_test"))


class TestAdoptionRate(unittest.TestCase):
    """Tests for SelfImprover Adoption Rate metric."""

    def test_lesson_store_adoption_rate_empty(self):
        from orbit.orbit.core.learning_system import LessonStore

        store = LessonStore()
        rate = store.get_adoption_rate()
        self.assertEqual(rate["overall_harvested"], 0)
        self.assertEqual(rate["overall_applied"], 0)
        self.assertEqual(rate["overall_adoption_rate"], 0.0)
        self.assertFalse(rate["warning"])

    def test_adoption_rate_calculation(self):
        from orbit.orbit.core.learning_system import Lesson, LessonStore

        store = LessonStore()

        # Add 5 lessons: 3 with applied_count=0, 2 with applied_count=3
        for i in range(3):
            lesson = Lesson(
                subject=f"unapplied lesson {i}", harvested_count=5, applied_count=0
            )
            store.add(lesson)

        for i in range(2):
            lesson = Lesson(
                subject=f"applied lesson {i}", harvested_count=5, applied_count=5
            )
            store.add(lesson)

        rate = store.get_adoption_rate()
        # total_harvested = 3*5 + 2*5 = 25
        # total_applied = 3*0 + 2*5 = 10
        self.assertEqual(rate["overall_harvested"], 25)
        self.assertEqual(rate["overall_applied"], 10)
        self.assertAlmostEqual(rate["overall_adoption_rate"], 0.4, places=2)
        self.assertFalse(rate["warning"])
        self.assertEqual(rate["total_lessons"], 5)

    def test_low_adoption_warning(self):
        from orbit.orbit.core.learning_system import Lesson, LessonStore

        store = LessonStore()

        # Add 10 lessons all unapplied — adoption rate = 0%
        for i in range(10):
            lesson = Lesson(
                subject=f"dead lesson {i}", harvested_count=5, applied_count=0
            )
            store.add(lesson)

        rate = store.get_adoption_rate()
        self.assertEqual(rate["overall_adoption_rate"], 0.0)
        self.assertTrue(rate["warning"])
        self.assertIn("below 20%", rate["warning_message"])
        self.assertEqual(rate["low_adoption_lessons"], 10)

    def test_per_lesson_adoption(self):
        from orbit.orbit.core.learning_system import Lesson, LessonStore

        store = LessonStore()

        store.add(Lesson(subject="well used", harvested_count=10, applied_count=8))
        store.add(Lesson(subject="never used", harvested_count=10, applied_count=0))

        rate = store.get_adoption_rate()
        per = rate["per_lesson"]
        self.assertEqual(len(per), 2)
        # Per-lesson sorted by adoption_rate ascending
        self.assertEqual(per[0]["subject"], "never used")
        self.assertEqual(per[0]["adoption_rate"], 0.0)
        self.assertEqual(per[1]["subject"], "well used")
        self.assertEqual(per[1]["adoption_rate"], 0.8)

    def test_improver_increments_applied_count(self):
        from orbit.orbit.core.learning_system import (
            FailureCategory,
            LearningSystem,
            Lesson,
        )

        ls = LearningSystem()
        ls.lesson_store._lessons.clear()

        # Add a lesson with a known topic
        lesson = Lesson(
            agent_id="general",
            subject="tool timeout handling",
            mistake_summary="did not handle timeout",
            correct_approach="use retry with backoff",
            category=FailureCategory.TOOL_FAILURE,
        )
        ls.lesson_store.add(lesson)

        # get_improvement_context should increment applied_count
        context = ls.get_improvement_context(
            "test_agent", "general", "tool timeout error occurred"
        )
        self.assertIn("Self-Improvement Context", context)

        updated = ls.lesson_store.get(lesson.id)
        self.assertEqual(updated.applied_count, 1)
        self.assertEqual(updated.use_count, 1)

    def test_non_matching_query_does_not_increment(self):
        from orbit.orbit.core.learning_system import LearningSystem, Lesson

        ls = LearningSystem()
        ls.lesson_store._lessons.clear()

        lesson = Lesson(
            subject="quantum physics", mistake_summary="...", correct_approach="..."
        )
        ls.lesson_store.add(lesson)

        # Unrelated query should not retrieve or apply this lesson
        context = ls.get_improvement_context(
            "test_agent", "general", "what is the weather today"
        )
        self.assertEqual(context, "")
        updated = ls.lesson_store.get(lesson.id)
        self.assertEqual(updated.applied_count, 0)

    def test_dashboard_includes_adoption(self):
        from orbit.orbit.core.learning_system import LearningSystem

        ls = LearningSystem()
        dashboard = ls.get_dashboard()
        self.assertIn("adoption_rate", dashboard)
        adoption = dashboard["adoption_rate"]
        self.assertIn("overall_adoption_rate", adoption)
        self.assertIn("warning", adoption)

    def test_convenience_function(self):
        from orbit.orbit.core.learning_system import get_adoption_rate

        rate = get_adoption_rate()
        self.assertIn("overall_adoption_rate", rate)
        self.assertIn("overall_harvested", rate)


class TestSEOTool(unittest.TestCase):
    """Tests for the new SEOTool."""

    def test_import(self):
        from orbit.orbit.tools.seo_tool import SEOTool

        tool = SEOTool()
        self.assertTrue(hasattr(tool, "analyze_page"))
        self.assertTrue(hasattr(tool, "check_meta_tags"))
        self.assertTrue(hasattr(tool, "audit_headings"))
        self.assertTrue(hasattr(tool, "analyze_images"))
        self.assertTrue(hasattr(tool, "check_technical"))
        self.assertTrue(hasattr(tool, "keyword_density"))
        self.assertTrue(hasattr(tool, "full_audit"))

    def test_parse_html_meta_tags(self):
        from orbit.orbit.tools.seo_tool import SEOTool

        tool = SEOTool()
        html = """
        <html>
        <head>
            <title>Test Page Title Here Is Long Enough</title>
            <meta name="description" content="This is a test meta description for SEO purposes that is long enough to pass the check.">
            <meta name="keywords" content="seo, test, page">
            <link rel="canonical" href="https://example.com/test">
            <meta property="og:title" content="Test OG Title">
            <meta property="og:description" content="Test OG Description">
            <meta property="og:image" content="https://example.com/image.jpg">
            <meta name="twitter:card" content="summary_large_image">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <link rel="icon" href="/favicon.ico">
        </head>
        <body>
            <h1>Main Heading</h1>
            <h2>Sub Heading</h2>
            <p>Content here</p>
        </body>
        </html>
        """
        result = tool.check_meta_tags(html)
        self.assertEqual(result["title"], "Test Page Title Here Is Long Enough")
        self.assertTrue(any("Title length OK" in p for p in result["pass"]))
        self.assertEqual(
            result["meta_description"],
            "This is a test meta description for SEO purposes that is long enough to pass the check.",
        )
        self.assertEqual(result["canonical"], "https://example.com/test")
        self.assertIn("og:title", result["og_tags"])

    def test_audit_headings(self):
        from orbit.orbit.tools.seo_tool import SEOTool

        tool = SEOTool()
        html = """
        <html><head><title>Test</title></head>
        <body>
            <h1>Main Title</h1>
            <h2>Section 1</h2>
            <h3>Subsection</h3>
            <h2>Section 2</h2>
        </body></html>
        """
        result = tool.audit_headings(html)
        self.assertEqual(result["h1_count"], 1)
        self.assertIn("Single H1 tag (good)", result["pass"])
        self.assertEqual(len(result["h1_texts"]), 1)
        self.assertEqual(result["h1_texts"][0], "Main Title")

    def test_audit_headings_multiple_h1(self):
        from orbit.orbit.tools.seo_tool import SEOTool

        tool = SEOTool()
        html = """
        <html><body>
            <h1>First H1</h1>
            <h1>Second H1</h1>
        </body></html>
        """
        result = tool.audit_headings(html)
        self.assertEqual(result["h1_count"], 2)
        self.assertTrue(any("Multiple H1" in w for w in result["warn"]))

    def test_audit_headings_missing_h1(self):
        from orbit.orbit.tools.seo_tool import SEOTool

        tool = SEOTool()
        html = "<html><body><h2>Only H2</h2></body></html>"
        result = tool.audit_headings(html)
        self.assertEqual(result["h1_count"], 0)
        self.assertTrue(any("No H1" in f for f in result["fail"]))

    def test_analyze_images(self):
        from orbit.orbit.tools.seo_tool import SEOTool

        tool = SEOTool()
        html = """
        <html><body>
            <img src="a.jpg" alt="Image A">
            <img src="b.jpg" alt="">
            <img src="c.jpg">
        </body></html>
        """
        result = tool.analyze_images(html)
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["missing_alt"], 2)

    def test_analyze_images_all_have_alt(self):
        from orbit.orbit.tools.seo_tool import SEOTool

        tool = SEOTool()
        html = """
        <html><body>
            <img src="a.jpg" alt="Description A">
            <img src="b.jpg" alt="Description B">
        </body></html>
        """
        result = tool.analyze_images(html)
        self.assertEqual(result["missing_alt"], 0)
        self.assertTrue(any("All" in p and "alt" in p for p in result["pass"]))

    def test_check_technical_https(self):
        from orbit.orbit.tools.seo_tool import SEOTool

        tool = SEOTool()
        html = '<html><head><meta name="viewport" content="width=device-width"></head><body></body></html>'
        result = tool.check_technical("https://example.com", html)
        self.assertTrue(any("HTTPS" in p for p in result["pass"]))
        self.assertTrue(any("Viewport" in p for p in result["pass"]))

    def test_check_technical_no_https(self):
        from orbit.orbit.tools.seo_tool import SEOTool

        tool = SEOTool()
        html = "<html><body></body></html>"
        result = tool.check_technical("http://example.com", html)
        self.assertTrue(any("HTTPS" in f for f in result["fail"]))

    def test_check_technical_noindex(self):
        from orbit.orbit.tools.seo_tool import SEOTool

        tool = SEOTool()
        html = '<html><head><meta name="robots" content="noindex"></head><body></body></html>'
        result = tool.check_technical("https://example.com", html)
        self.assertTrue(any("noindex" in f for f in result["fail"]))

    def test_keyword_density_basic(self):
        from orbit.orbit.tools.seo_tool import SEOTool

        tool = SEOTool()
        text = "the quick brown fox jumps over the lazy dog the fox"
        result = tool.keyword_density(text)
        self.assertIn("total_words", result)
        self.assertIn("unique_words", result)
        self.assertIn("top_words", result)
        self.assertGreater(result["total_words"], 0)

    def test_keyword_density_with_target(self):
        from orbit.orbit.tools.seo_tool import SEOTool

        tool = SEOTool()
        text = "python is great. python is powerful. python is easy. javascript is also good."
        result = tool.keyword_density(text, "python")
        self.assertEqual(result["target_keyword"], "python")
        self.assertEqual(result["keyword_count"], 3)
        self.assertIn("keyword_density_pct", result)
        self.assertIn("advice", result)

    def test_analyze_page_error_handling(self):
        from orbit.orbit.tools.seo_tool import SEOTool

        tool = SEOTool()
        result = tool.analyze_page("http://localhost:19999/invalid")
        self.assertTrue("score" in result or "error" in result)

    def test_full_audit_structure(self):
        from orbit.orbit.tools.seo_tool import SEOTool

        tool = SEOTool()
        result = tool.full_audit("http://localhost:19999/invalid")
        self.assertTrue("report" in result or "error" in result)


class TestSEOWorkflow(unittest.TestCase):
    """Integration tests for SEO workflow."""

    def test_seo_agent_uses_seo_tool(self):
        from orbit.orbit.agents.specialized import SEOAgent

        agent = SEOAgent()
        self.assertTrue(hasattr(agent, "_get_seo_tool"))
        tool = agent._get_seo_tool()
        self.assertIsNotNone(tool)
        self.assertTrue(hasattr(tool, "analyze_page"))

    def test_seo_agent_can_handle_seo(self):
        from orbit.orbit.agents.specialized import SEOAgent

        agent = SEOAgent()
        self.assertTrue(agent.can_handle("analyze page https://example.com"))
        self.assertTrue(agent.can_handle("seo audit my website"))
        self.assertTrue(agent.can_handle("keyword research for python"))
        self.assertTrue(agent.can_handle("check meta tags"))

    def test_social_agent_platform_detection(self):
        from orbit.orbit.agents.specialized import SocialAgent

        agent = SocialAgent()
        platforms = agent._detect_platforms("post to instagram about my day")
        self.assertIn("instagram", platforms)
        platforms = agent._detect_platforms("tweet about AI news")
        self.assertIn("twitter", platforms)
        platforms = agent._detect_platforms("share on linkedin")
        self.assertIn("linkedin", platforms)


class TestMobileDeviceVerification(unittest.TestCase):
    """Test mobile device connection status, verification, and pairing."""

    def test_device_registration_with_verification(self):
        from orbit.orbit.core.mobile_api import MobileAPI

        ma = MobileAPI()
        result = ma.register_device("TestPhone", "ios", "push_token_here")
        self.assertIn("device_id", result)
        self.assertIn("session_token", result)
        # Newly registered device should not be verified
        status = ma.get_connection_status()
        device = next(d for d in status["devices"] if d["id"] == result["device_id"])
        self.assertFalse(device["verified"])

    def test_heartbeat_marks_online(self):
        from orbit.orbit.core.mobile_api import MobileAPI

        ma = MobileAPI()
        result = ma.register_device("TestDevice", "android")
        ok = ma.heartbeat(result["device_id"])
        self.assertTrue(ok)
        status = ma.get_connection_status()
        device = next(d for d in status["devices"] if d["id"] == result["device_id"])
        self.assertTrue(device["online"])

    def test_pairing_code_generation_and_verification(self):
        from orbit.orbit.core.mobile_api import MobileAPI

        ma = MobileAPI()
        result = ma.register_device("PairDevice", "ios")
        code = ma.generate_pairing_code(result["device_id"])
        self.assertIsNotNone(code)
        # Verify with correct code
        verified = ma.verify_device(result["device_id"], code)
        self.assertTrue(verified)
        # Check verified status
        status = ma.get_connection_status()
        device = next(d for d in status["devices"] if d["id"] == result["device_id"])
        self.assertTrue(device["verified"])

    def test_find_device_by_name(self):
        from orbit.orbit.core.mobile_api import MobileAPI

        ma = MobileAPI()
        ma.register_device("MyPhone", "ios")
        ma.register_device("MyTablet", "android")
        found = ma.find_device_by_name("MyPhone", "ios")
        self.assertIsNotNone(found)
        self.assertEqual(found["name"], "MyPhone")
        self.assertEqual(found["platform"], "ios")

    def test_unverified_device_rejected(self):
        from orbit.orbit.core.mobile_api import MobileAPI

        ma = MobileAPI()
        result = ma.register_device("UnverifiedDevice", "ios")
        task_id = ma.assign_task(result["device_id"], "test task")
        self.assertIsNone(task_id)

    def test_verified_device_accepts_task(self):
        from orbit.orbit.core.mobile_api import MobileAPI

        ma = MobileAPI()
        result = ma.register_device("VerifiedDevice", "android")
        ma.generate_pairing_code(result["device_id"])
        from orbit.orbit.core.mobile_api import get_mobile_api

        stored_ma = get_mobile_api()
        stored_ma._devices = ma._devices
        stored_ma._sessions = ma._sessions
        stored_ma._offline_cache = ma._offline_cache
        code = stored_ma._devices[result["device_id"]].pairing_code
        stored_ma.verify_device(result["device_id"], code)
        task_id = stored_ma.assign_task(result["device_id"], "do something")
        self.assertIsNotNone(task_id)

    def test_connection_status_all_fields(self):
        from orbit.orbit.core.mobile_api import MobileAPI

        ma = MobileAPI()
        ma.register_device("StatusCheck", "ios")
        ma.heartbeat("dev_fake")  # should be False
        status = ma.get_connection_status()
        self.assertIn("total", status)
        self.assertIn("online", status)
        self.assertIn("devices", status)
        self.assertGreaterEqual(status["total"], 1)

    def test_platform_preference_storage(self):
        from orbit.orbit.core.mobile_api import MobileAPI

        ma = MobileAPI()
        result = ma.register_device("PlatformTest", "android")
        ok = ma.set_platform_preference(result["device_id"], "coding", "pc-first")
        self.assertTrue(ok)
        status = ma.get_connection_status()
        device = next(d for d in status["devices"] if d["id"] == result["device_id"])
        self.assertIn("platform_preferences", device)
        self.assertEqual(device["platform_preferences"].get("coding"), "pc-first")


if __name__ == "__main__":
    unittest.main(verbosity=2)
