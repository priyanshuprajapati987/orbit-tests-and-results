"""Tests for Batch 5 Overkill Features: Code Interpreter, Memory Graph, Anomaly Detector, Scheduler, Doc Pipeline."""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestCodeInterpreter(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.core.code_interpreter import (
            get_code_interpreter,
        )

        self.assertTrue(callable(get_code_interpreter))

    def test_execute_basic(self):
        from orbit.orbit.core.code_interpreter import CodeInterpreter

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ci = CodeInterpreter(storage_file=path)
            r = ci.execute("print(2 + 2)")
            self.assertEqual(r.output.strip(), "4")
            self.assertEqual(r.status, "success")
        finally:
            os.unlink(path)

    def test_blocked_import(self):
        from orbit.orbit.core.code_interpreter import CodeInterpreter

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ci = CodeInterpreter(storage_file=path)
            r = ci.execute("import os; os.system('ls')")
            self.assertEqual(r.status, "blocked")
        finally:
            os.unlink(path)

    def test_blocked_dangerous_call(self):
        from orbit.orbit.core.code_interpreter import CodeInterpreter

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ci = CodeInterpreter(storage_file=path)
            r = ci.execute("__import__('os')")
            self.assertEqual(r.status, "blocked")
        finally:
            os.unlink(path)

    def test_error_handling(self):
        from orbit.orbit.core.code_interpreter import CodeInterpreter

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ci = CodeInterpreter(storage_file=path)
            r = ci.execute("1 / 0")
            self.assertEqual(r.status, "error")
            self.assertIn("ZeroDivisionError", r.error)
        finally:
            os.unlink(path)

    def test_session_persistence(self):
        from orbit.orbit.core.code_interpreter import CodeInterpreter

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ci = CodeInterpreter(storage_file=path)
            ci.execute("x = 42", session_id="s1")
            r = ci.execute("print(x)", session_id="s1")
            self.assertEqual(r.output.strip(), "42")
        finally:
            os.unlink(path)

    def test_history(self):
        from orbit.orbit.core.code_interpreter import CodeInterpreter

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ci = CodeInterpreter(storage_file=path)
            ci.execute("print(1)")
            ci.execute("print(2)")
            h = ci.get_history()
            self.assertEqual(len(h), 2)
        finally:
            os.unlink(path)

    def test_stats(self):
        from orbit.orbit.core.code_interpreter import CodeInterpreter

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ci = CodeInterpreter(storage_file=path)
            ci.execute("print('hi')")
            s = ci.get_stats()
            self.assertEqual(s["total_executions"], 1)
        finally:
            os.unlink(path)


class TestMemoryGraph(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.core.memory_graph import get_memory_graph

        self.assertTrue(callable(get_memory_graph))

    def test_add_entity(self):
        from orbit.orbit.core.memory_graph import MemoryGraph

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            mg = MemoryGraph(storage_file=path)
            e = mg.add_entity("Python", "TECH")
            self.assertEqual(e.entity_id, "python")
        finally:
            os.unlink(path)

    def test_add_relation(self):
        from orbit.orbit.core.memory_graph import MemoryGraph

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            mg = MemoryGraph(storage_file=path)
            mg.add_entity("Python", "TECH")
            mg.add_entity("Flask", "TECH")
            r = mg.add_relation("Python", "Flask", "USES")
            self.assertEqual(r.source_id, "python")
        finally:
            os.unlink(path)

    def test_neighbors(self):
        from orbit.orbit.core.memory_graph import MemoryGraph

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            mg = MemoryGraph(storage_file=path)
            mg.add_entity("Python", "TECH")
            mg.add_entity("Flask", "TECH")
            mg.add_relation("Python", "Flask", "USES")
            n = mg.neighbors("Python")
            self.assertEqual(len(n), 1)
        finally:
            os.unlink(path)

    def test_find_path(self):
        from orbit.orbit.core.memory_graph import MemoryGraph

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            mg = MemoryGraph(storage_file=path)
            mg.add_entity("A", "X")
            mg.add_entity("B", "X")
            mg.add_entity("C", "X")
            mg.add_relation("A", "B", "LINK")
            mg.add_relation("B", "C", "LINK")
            p = mg.find_path("A", "C")
            self.assertEqual(len(p), 3)
        finally:
            os.unlink(path)

    def test_ingest_text(self):
        from orbit.orbit.core.memory_graph import MemoryGraph

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            mg = MemoryGraph(storage_file=path)
            result = mg.ingest_text(
                "Python is a language. Python uses Flask framework."
            )
            self.assertIn("entities_added", result)
        finally:
            os.unlink(path)

    def test_communities(self):
        from orbit.orbit.core.memory_graph import MemoryGraph

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            mg = MemoryGraph(storage_file=path)
            mg.add_entity("X", "T")
            mg.add_entity("Y", "T")
            mg.add_relation("X", "Y", "LINK")
            c = mg.communities()
            self.assertGreater(len(c), 0)
        finally:
            os.unlink(path)

    def test_stats(self):
        from orbit.orbit.core.memory_graph import MemoryGraph

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            mg = MemoryGraph(storage_file=path)
            mg.add_entity("Test", "CONCEPT")
            s = mg.get_stats()
            self.assertEqual(s["total_entities"], 1)
        finally:
            os.unlink(path)


class TestAnomalyDetector(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.core.anomaly_detector import (
            get_anomaly_detector,
        )

        self.assertTrue(callable(get_anomaly_detector))

    def test_record_normal(self):
        from orbit.orbit.core.anomaly_detector import AnomalyDetector

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ad = AnomalyDetector(storage_file=path)
            for i in range(15):
                result = ad.record("latency", 50 + i)
            self.assertIsNone(result)
        finally:
            os.unlink(path)

    def test_record_anomaly(self):
        from orbit.orbit.core.anomaly_detector import AnomalyDetector

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ad = AnomalyDetector(storage_file=path)
            for i in range(15):
                ad.record("latency", 50)
            a = ad.record("latency", 500)
            self.assertIsNotNone(a)
            self.assertIn(a.severity, ["low", "medium", "high", "critical"])
        finally:
            os.unlink(path)

    def test_batch(self):
        from orbit.orbit.core.anomaly_detector import AnomalyDetector

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ad = AnomalyDetector(storage_file=path)
            for i in range(15):
                ad.record_batch({"cpu": 50, "mem": 60})
            anomalies = ad.record_batch({"cpu": 999, "mem": 5})
            self.assertEqual(len(anomalies), 2)
        finally:
            os.unlink(path)

    def test_acknowledge(self):
        from orbit.orbit.core.anomaly_detector import AnomalyDetector

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ad = AnomalyDetector(storage_file=path)
            for i in range(15):
                ad.record("x", 10)
            a = ad.record("x", 999)
            self.assertTrue(ad.acknowledge(a.anomaly_id))
        finally:
            os.unlink(path)

    def test_baselines(self):
        from orbit.orbit.core.anomaly_detector import AnomalyDetector

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ad = AnomalyDetector(storage_file=path)
            for i in range(15):
                ad.record("m", 10 + i)
            bl = ad.get_baselines()
            self.assertEqual(len(bl), 1)
            self.assertGreater(bl[0]["samples"], 0)
        finally:
            os.unlink(path)

    def test_stats(self):
        from orbit.orbit.core.anomaly_detector import AnomalyDetector

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ad = AnomalyDetector(storage_file=path)
            ad.record("m", 10)
            s = ad.get_stats()
            self.assertEqual(s["total_baselines"], 1)
        finally:
            os.unlink(path)


class TestSmartScheduler(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.core.smart_scheduler import get_smart_scheduler

        self.assertTrue(callable(get_smart_scheduler))

    def test_add_cron(self):
        from orbit.orbit.core.smart_scheduler import SmartScheduler

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ss = SmartScheduler(storage_file=path)
            t = ss.add_cron("test", "0 * * * *")
            self.assertIsNotNone(t.task_id)
        finally:
            os.unlink(path)

    def test_add_interval(self):
        from orbit.orbit.core.smart_scheduler import SmartScheduler

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ss = SmartScheduler(storage_file=path)
            t = ss.add_interval("test", 60)
            self.assertGreater(t.next_run, 0)
        finally:
            os.unlink(path)

    def test_add_natural(self):
        from orbit.orbit.core.smart_scheduler import SmartScheduler

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ss = SmartScheduler(storage_file=path)
            t = ss.add_natural("test", "in 5 minutes")
            self.assertGreater(t.next_run, 0)
        finally:
            os.unlink(path)

    def test_check_due(self):
        from orbit.orbit.core.smart_scheduler import SmartScheduler

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ss = SmartScheduler(storage_file=path)
            ss.add_interval("test", 0)
            time.sleep(0.01)
            due = ss.check_due()
            self.assertEqual(len(due), 1)
        finally:
            os.unlink(path)

    def test_cancel(self):
        from orbit.orbit.core.smart_scheduler import SmartScheduler

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ss = SmartScheduler(storage_file=path)
            t = ss.add_interval("test", 60)
            self.assertTrue(ss.cancel(t.task_id))
        finally:
            os.unlink(path)

    def test_stats(self):
        from orbit.orbit.core.smart_scheduler import SmartScheduler

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ss = SmartScheduler(storage_file=path)
            ss.add_interval("a", 60)
            ss.add_cron("b", "0 * * * *")
            s = ss.get_stats()
            self.assertEqual(s["total"], 2)
        finally:
            os.unlink(path)


class TestDocumentPipeline(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.core.doc_pipeline import get_doc_pipeline

        self.assertTrue(callable(get_doc_pipeline))

    def test_ingest_text(self):
        from orbit.orbit.core.doc_pipeline import DocumentPipeline

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            dp = DocumentPipeline(storage_file=path)
            r = dp.ingest_text("This is a test document about AI.", "test.txt")
            self.assertIn("doc_id", r)
            self.assertGreater(r["chunks"], 0)
        finally:
            os.unlink(path)

    def test_ingest_markdown(self):
        from orbit.orbit.core.doc_pipeline import DocumentPipeline

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            dp = DocumentPipeline(storage_file=path)
            r = dp.ingest_text("# Title\n\nSome content.", "doc.md")
            self.assertEqual(r["type"], "markdown")
        finally:
            os.unlink(path)

    def test_ingest_csv(self):
        from orbit.orbit.core.doc_pipeline import DocumentPipeline

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            dp = DocumentPipeline(storage_file=path)
            csv_data = "name,age\nAlice,30\nBob,25"
            r = dp.ingest_text(csv_data, "data.csv")
            self.assertEqual(r["type"], "csv")
        finally:
            os.unlink(path)

    def test_search(self):
        from orbit.orbit.core.doc_pipeline import DocumentPipeline

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            dp = DocumentPipeline(storage_file=path)
            dp.ingest_text("Python is a great programming language.", "py.txt")
            results = dp.search_documents("Python")
            self.assertGreater(len(results), 0)
        finally:
            os.unlink(path)

    def test_delete(self):
        from orbit.orbit.core.doc_pipeline import DocumentPipeline

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            dp = DocumentPipeline(storage_file=path)
            r = dp.ingest_text("to delete", "del.txt")
            self.assertTrue(dp.delete_document(r["doc_id"]))
        finally:
            os.unlink(path)

    def test_stats(self):
        from orbit.orbit.core.doc_pipeline import DocumentPipeline

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            dp = DocumentPipeline(storage_file=path)
            dp.ingest_text("Test.", "t.txt")
            s = dp.get_stats()
            self.assertEqual(s["total_documents"], 1)
        finally:
            os.unlink(path)


class TestBatch5Blueprints(unittest.TestCase):
    def test_all_registered(self):
        from orbit.orbit.server import create_app

        app = create_app()
        names = list(app.blueprints)
        for bp in [
            "code_interpreter",
            "memory_graph",
            "anomaly_detector",
            "smart_scheduler",
            "doc_pipeline",
        ]:
            self.assertIn(bp, names, f"Blueprint '{bp}' missing")


if __name__ == "__main__":
    unittest.main()
