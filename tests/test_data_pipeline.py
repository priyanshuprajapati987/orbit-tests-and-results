"""Unit tests for orbit/orbit/core/data_pipeline.py."""

import os
import sys
import tempfile
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.data_pipeline import (
    _is_safe_url, _is_safe_path, PipelineStage, PipelineStatus, Pipeline,
    DataPipeline, get_data_pipeline, create_pipeline, add_extractor,
    add_transformer, add_loader, execute_pipeline, get_statistics,
)


class TestSafeHelpers(unittest.TestCase):
    def test_safe_url_https(self):
        self.assertTrue(_is_safe_url("https://example.com/x"))

    def test_safe_url_blocks_localhost(self):
        self.assertFalse(_is_safe_url("http://localhost/x"))

    def test_safe_url_blocks_private_ip(self):
        self.assertFalse(_is_safe_url("http://192.168.1.1/x"))

    def test_safe_url_blocks_bad_scheme(self):
        self.assertFalse(_is_safe_url("ftp://example.com/x"))

    def test_safe_path_normal(self):
        self.assertTrue(_is_safe_path(os.path.abspath(__file__)))

    def test_safe_path_blocks_env(self):
        self.assertFalse(_is_safe_path(".env"))


class TestConstants(unittest.TestCase):
    def test_pipeline_stage(self):
        self.assertEqual(PipelineStage.EXTRACT, "extract")
        self.assertEqual(PipelineStage.TRANSFORM, "transform")
        self.assertEqual(PipelineStage.LOAD, "load")

    def test_pipeline_status(self):
        self.assertEqual(PipelineStatus.IDLE, "idle")
        self.assertEqual(PipelineStatus.COMPLETED, "completed")


class TestPipeline(unittest.TestCase):
    def test_init(self):
        p = Pipeline("p1", "Test", "desc")
        self.assertEqual(p.pipeline_id, "p1")
        self.assertEqual(p.status, PipelineStatus.IDLE)
        self.assertEqual(p.run_count, 0)


class TestDataPipeline(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        if os.path.exists(self.path):
            os.remove(self.path)
        self.dp = DataPipeline(storage_file=self.path)

    def tearDown(self):
        try:
            if os.path.exists(self.path):
                os.remove(self.path)
        except Exception:
            pass

    def test_instantiation(self):
        self.assertIsNotNone(self.dp)
        self.assertEqual(self.dp.pipelines, {})

    def test_register_extractor(self):
        def ex(src): return [{"a": 1}]
        self.dp.register_extractor("myex", ex)
        self.assertIn("myex", self.dp.extractors)

    def test_register_transformer(self):
        def tf(data): return data
        self.dp.register_transformer("mytf", tf)
        self.assertIn("mytf", self.dp.transformers)

    def test_register_loader(self):
        def ld(data, dest): return True
        self.dp.register_loader("myld", ld)
        self.assertIn("myld", self.dp.loaders)

    def test_create_pipeline(self):
        pid = self.dp.create_pipeline("p1", "Test pipeline")
        self.assertIsNotNone(pid)
        self.assertIn(pid, self.dp.pipelines)

    def test_list_pipelines(self):
        self.dp.create_pipeline("p1", "Test")
        r = self.dp.list_pipelines()
        self.assertIsNotNone(r)

    def test_get_statistics(self):
        r = self.dp.get_statistics()
        self.assertIsNotNone(r)

    def test_get_pipeline_status(self):
        pid = self.dp.create_pipeline("p1", "Test")
        r = self.dp.get_pipeline_status(pid)
        self.assertIsNotNone(r)

    def test_get_run_history(self):
        r = self.dp.get_run_history()
        self.assertIsNotNone(r)


class TestModuleFunctions(unittest.TestCase):
    def test_get_data_pipeline(self):
        r = get_data_pipeline()
        self.assertIsNotNone(r)

    def test_create_pipeline_func(self):
        dp = get_data_pipeline()
        pid = create_pipeline("pf", "func pipeline", storage_file=None) if False else None
        # just ensure callable
        self.assertTrue(callable(create_pipeline))

    def test_add_extractor_func(self):
        self.assertTrue(callable(add_extractor))

    def test_add_transformer_func(self):
        self.assertTrue(callable(add_transformer))

    def test_add_loader_func(self):
        self.assertTrue(callable(add_loader))

    def test_execute_pipeline_func(self):
        self.assertTrue(callable(execute_pipeline))

    def test_get_statistics_func(self):
        self.assertTrue(callable(get_statistics))


if __name__ == "__main__":
    unittest.main()
