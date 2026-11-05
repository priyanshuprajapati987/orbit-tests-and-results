"""Tests for Batch 6 Overkill Features: Plugin Bridge, Conv Analytics, Model Benchmark, File Watcher, Context Manager."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestPluginBridge(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.core.plugin_bridge import get_plugin_bridge

        self.assertTrue(callable(get_plugin_bridge))

    def test_scan_directory(self):
        from orbit.orbit.core.plugin_bridge import PluginBridge

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            pb = PluginBridge(storage_file=path)
            result = pb.scan_directory("nonexistent_dir")
            self.assertEqual(result["discovered"], [])
        finally:
            os.unlink(path)

    def test_events(self):
        from orbit.orbit.core.plugin_bridge import PluginBridge

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            pb = PluginBridge(storage_file=path)
            pb._emit("test_event", "test_plugin", {"key": "val"})
            events = pb.get_events()
            self.assertEqual(len(events), 1)
        finally:
            os.unlink(path)

    def test_listener(self):
        from orbit.orbit.core.plugin_bridge import PluginBridge

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            received = []
            pb = PluginBridge(storage_file=path)
            pb.on_event("test", lambda et, pn, d: received.append(pn))
            pb._emit("test", "my_plugin")
            self.assertEqual(len(received), 1)
        finally:
            os.unlink(path)

    def test_stats(self):
        from orbit.orbit.core.plugin_bridge import PluginBridge

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            pb = PluginBridge(storage_file=path)
            pb._emit("x", "y")
            s = pb.get_stats()
            self.assertEqual(s["total_events"], 1)
        finally:
            os.unlink(path)


class TestConversationAnalytics(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.core.conversation_analytics import ConversationAnalytics

        self.assertTrue(ConversationAnalytics)

    def test_add_turn(self):
        from orbit.orbit.core.conversation_analytics import ConversationAnalytics

        with tempfile.TemporaryDirectory() as td:
            ca = ConversationAnalytics(data_dir=Path(td))
            ca.start_session("c1")
            ca.add_turn("c1", "user", "Hello, this is great!")
            ca.add_turn("c1", "assistant", "Hi there! How can I help?")
            ca.end_session("c1")
            qa = ca.get_quality_metrics()
            self.assertGreaterEqual(qa["total_turns"], 2)

    def test_sentiment(self):
        from orbit.orbit.core.conversation_analytics import ConversationAnalytics

        with tempfile.TemporaryDirectory() as td:
            ca = ConversationAnalytics(data_dir=Path(td))
            ca.add_turn("c1", "user", "This is terrible and awful!")
            trend = ca.get_satisfaction_trend()
            self.assertIsInstance(trend, list)

    def test_engagement(self):
        from orbit.orbit.core.conversation_analytics import ConversationAnalytics

        with tempfile.TemporaryDirectory() as td:
            ca = ConversationAnalytics(data_dir=Path(td))
            ca.start_session("c1")
            for i in range(10):
                ca.add_turn("c1", "user", f"Turn {i} with some content here")
                ca.add_turn("c1", "assistant", f"Response {i} with detailed info")
            ca.end_session("c1")
            qa = ca.get_quality_metrics()
            self.assertGreater(qa["avg_turns_per_session"], 0)

    def test_overview(self):
        from orbit.orbit.core.conversation_analytics import ConversationAnalytics

        with tempfile.TemporaryDirectory() as td:
            ca = ConversationAnalytics(data_dir=Path(td))
            ca.add_turn("c1", "user", "test")
            dashboard = ca.get_dashboard()
            self.assertIn("quality", dashboard)
            self.assertIn("topics", dashboard)

    def test_end_session(self):
        from orbit.orbit.core.conversation_analytics import ConversationAnalytics

        with tempfile.TemporaryDirectory() as td:
            ca = ConversationAnalytics(data_dir=Path(td))
            ca.start_session("c1")
            ca.add_turn("c1", "user", "test")
            ca.end_session("c1")
            topics = ca.get_topic_distribution()
            self.assertIsInstance(topics, list)

    def test_stats(self):
        from orbit.orbit.core.conversation_analytics import ConversationAnalytics

        with tempfile.TemporaryDirectory() as td:
            ca = ConversationAnalytics(data_dir=Path(td))
            ca.add_turn("c1", "user", "AI is great")
            s = ca.get_quality_metrics()
            self.assertIn("total_sessions", s)


class TestModelBenchmark(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.core.model_benchmark import get_model_benchmark

        self.assertTrue(callable(get_model_benchmark))

    def test_add_task(self):
        from orbit.orbit.core.model_benchmark import ModelBenchmark

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            mb = ModelBenchmark(storage_file=path)
            t = mb.add_task("test", "Say hello", expected_keywords=["hello"])
            self.assertIsNotNone(t.task_id)
        finally:
            os.unlink(path)

    def test_record_result(self):
        from orbit.orbit.core.model_benchmark import ModelBenchmark

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            mb = ModelBenchmark(storage_file=path)
            t = mb.add_task("test", "Say hello", expected_keywords=["hello"])
            r = mb.record_result(
                t.task_id, "openrouter", "gpt-4o", "Hello world!", 100, 10
            )
            self.assertGreater(r.overall_score, 0)
        finally:
            os.unlink(path)

    def test_leaderboard(self):
        from orbit.orbit.core.model_benchmark import ModelBenchmark

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            mb = ModelBenchmark(storage_file=path)
            t = mb.add_task("t", "prompt")
            mb.record_result(t.task_id, "A", "m1", "response", 50)
            mb.record_result(t.task_id, "B", "m2", "response", 100)
            lb = mb.get_leaderboard()
            self.assertEqual(len(lb), 2)
        finally:
            os.unlink(path)

    def test_compare(self):
        from orbit.orbit.core.model_benchmark import ModelBenchmark

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            mb = ModelBenchmark(storage_file=path)
            t = mb.add_task("t", "p")
            mb.record_result(t.task_id, "A", "m", "good response")
            mb.record_result(t.task_id, "B", "m", "ok")
            result = mb.compare_providers("A", "B")
            self.assertIn("winner", result)
        finally:
            os.unlink(path)

    def test_stats(self):
        from orbit.orbit.core.model_benchmark import ModelBenchmark

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            mb = ModelBenchmark(storage_file=path)
            mb.add_task("t", "p")
            s = mb.get_stats()
            self.assertEqual(s["total_tasks"], 1)
        finally:
            os.unlink(path)


class TestSmartFileWatcher(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.core.smart_file_watcher import (
            get_file_watcher,
        )

        self.assertTrue(callable(get_file_watcher))

    def test_add_watch(self):
        from orbit.orbit.core.smart_file_watcher import SmartFileWatcher

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            fw = SmartFileWatcher(storage_file=path)
            w = fw.add_watch("nonexistent_path")
            self.assertIsNotNone(w.watch_id)
        finally:
            os.unlink(path)

    def test_remove_watch(self):
        from orbit.orbit.core.smart_file_watcher import SmartFileWatcher

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            fw = SmartFileWatcher(storage_file=path)
            w = fw.add_watch("some_path")
            self.assertTrue(fw.remove_watch(w.watch_id))
        finally:
            os.unlink(path)

    def test_scan(self):
        from orbit.orbit.core.smart_file_watcher import SmartFileWatcher

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            fw = SmartFileWatcher(storage_file=path)
            result = fw.scan_all()
            self.assertIn("created", result)
        finally:
            os.unlink(path)

    def test_stats(self):
        from orbit.orbit.core.smart_file_watcher import SmartFileWatcher

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            fw = SmartFileWatcher(storage_file=path)
            fw.add_watch("x")
            s = fw.get_stats()
            self.assertEqual(s["total_watches"], 1)
        finally:
            os.unlink(path)


class TestContextWindowManager(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.core.context_window_manager import (
            get_context_manager,
        )

        self.assertTrue(callable(get_context_manager))

    def test_register_agent(self):
        from orbit.orbit.core.context_window_manager import ContextWindowManager

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            cwm = ContextWindowManager(storage_file=path)
            a = cwm.register_agent("QUEEN")
            self.assertEqual(a.priority, 10)
        finally:
            os.unlink(path)

    def test_request_tokens(self):
        from orbit.orbit.core.context_window_manager import ContextWindowManager

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            cwm = ContextWindowManager(storage_file=path)
            cr = cwm.request_tokens("COD", 5000)
            self.assertEqual(cr.status, "granted")
            self.assertGreater(cr.granted_tokens, 0)
        finally:
            os.unlink(path)

    def test_release(self):
        from orbit.orbit.core.context_window_manager import ContextWindowManager

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            cwm = ContextWindowManager(storage_file=path)
            cwm.request_tokens("TAS", 2000)
            cwm.release("TAS")
            overview = cwm.get_overview()
            self.assertEqual(overview["allocated"], 0)
        finally:
            os.unlink(path)

    def test_overview(self):
        from orbit.orbit.core.context_window_manager import ContextWindowManager

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            cwm = ContextWindowManager(storage_file=path)
            cwm.register_agent("PLN")
            ov = cwm.get_overview()
            self.assertIn("total_limit", ov)
            self.assertIn("available", ov)
        finally:
            os.unlink(path)

    def test_stats(self):
        from orbit.orbit.core.context_window_manager import ContextWindowManager

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            cwm = ContextWindowManager(storage_file=path)
            cwm.request_tokens("X", 1000)
            s = cwm.get_stats()
            self.assertEqual(s["total_requests"], 1)
        finally:
            os.unlink(path)


class TestBatch6Blueprints(unittest.TestCase):
    def test_all_registered(self):
        from orbit.orbit.server import create_app

        app = create_app()
        names = list(app.blueprints)
        for bp in [
            "plugin_bridge",
            "conv_analytics",
            "model_benchmark",
            "file_watcher",
            "context_mgr",
        ]:
            self.assertIn(bp, names, f"Blueprint '{bp}' missing")


if __name__ == "__main__":
    unittest.main()
