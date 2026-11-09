"""Unit tests for orbit/orbit/core/doc_pipeline_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.doc_pipeline_bp import doc_pipeline_bp


class TestDocPipelineBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(doc_pipeline_bp)
        self.client = self.app.test_client()
        self.fake_dp = MagicMock()
        sys.modules["orbit.orbit.core.doc_pipeline"] = self.fake_dp

    def tearDown(self):
        sys.modules.pop("orbit.orbit.core.doc_pipeline", None)

    def test_blueprint_name(self):
        self.assertEqual(doc_pipeline_bp.name, "doc_pipeline")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/docs/ingest", "/api/docs/ingest-file", "/api/docs/document/<doc_id>",
                  "/api/docs/search", "/api/docs/list", "/api/docs/<doc_id>", "/api/docs/stats"]:
            self.assertIn(p, rules)

    def test_ingest_missing_content_400(self):
        r = self.client.post("/api/docs/ingest", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_ingest_success(self):
        self.fake_dp.get_doc_pipeline.return_value.ingest_text.return_value = {"id": "d1"}
        r = self.client.post("/api/docs/ingest", json={"content": "hi", "filename": "f.txt", "doc_type": "text", "metadata": {"k": "v"}})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], "d1")
        self.fake_dp.get_doc_pipeline.return_value.ingest_text.assert_called_once_with("hi", "f.txt", "text", {"k": "v"})

    def test_ingest_defaults(self):
        self.fake_dp.get_doc_pipeline.return_value.ingest_text.return_value = {"id": "d2"}
        r = self.client.post("/api/docs/ingest", json={"content": "hi"})
        self.fake_dp.get_doc_pipeline.return_value.ingest_text.assert_called_once_with("hi", "untitled.txt", None, None)

    def test_ingest_no_body(self):
        r = self.client.post("/api/docs/ingest")
        self.assertEqual(r.status_code, 400)

    def test_ingest_file_missing_400(self):
        r = self.client.post("/api/docs/ingest-file", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_ingest_file_blocked_403(self):
        with patch("orbit.core.doc_pipeline_bp.validate_path", return_value=(False, "nope")):
            r = self.client.post("/api/docs/ingest-file", json={"filepath": "/etc/x"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("path not allowed", r.get_json()["error"])

    def test_ingest_file_success(self):
        self.fake_dp.get_doc_pipeline.return_value.ingest_file.return_value = {"id": "d3"}
        with patch("orbit.core.doc_pipeline_bp.validate_path", return_value=(True, "ok")):
            r = self.client.post("/api/docs/ingest-file", json={"filepath": "doc.txt"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], "d3")
        self.fake_dp.get_doc_pipeline.return_value.ingest_file.assert_called_once_with("doc.txt")

    def test_ingest_file_not_found_404(self):
        self.fake_dp.get_doc_pipeline.return_value.ingest_file.side_effect = FileNotFoundError("nf")
        with patch("orbit.core.doc_pipeline_bp.validate_path", return_value=(True, "ok")):
            r = self.client.post("/api/docs/ingest-file", json={"filepath": "doc.txt"})
        self.assertEqual(r.status_code, 404)
        self.assertIn("not found", r.get_json()["error"].lower())

    def test_ingest_file_error_500(self):
        self.fake_dp.get_doc_pipeline.return_value.ingest_file.side_effect = RuntimeError("boom")
        with patch("orbit.core.doc_pipeline_bp.validate_path", return_value=(True, "ok")):
            r = self.client.post("/api/docs/ingest-file", json={"filepath": "doc.txt"})
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_ingest_file_no_body(self):
        r = self.client.post("/api/docs/ingest-file")
        self.assertEqual(r.status_code, 400)

    def test_document_found(self):
        self.fake_dp.get_doc_pipeline.return_value.get_document.return_value = {"id": "d1"}
        r = self.client.get("/api/docs/document/d1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], "d1")
        self.fake_dp.get_doc_pipeline.return_value.get_document.assert_called_once_with("d1")

    def test_document_not_found_404(self):
        self.fake_dp.get_doc_pipeline.return_value.get_document.return_value = None
        r = self.client.get("/api/docs/document/d1")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_search_missing_q_400(self):
        r = self.client.get("/api/docs/search")
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_search_success(self):
        self.fake_dp.get_doc_pipeline.return_value.search_documents.return_value = [{"id": "d1"}]
        r = self.client.get("/api/docs/search?q=hi&limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["results"], [{"id": "d1"}])
        self.fake_dp.get_doc_pipeline.return_value.search_documents.assert_called_once_with("hi", 5)

    def test_search_default_limit(self):
        self.fake_dp.get_doc_pipeline.return_value.search_documents.return_value = []
        r = self.client.get("/api/docs/search?q=hi")
        self.fake_dp.get_doc_pipeline.return_value.search_documents.assert_called_once_with("hi", 10)

    def test_list(self):
        self.fake_dp.get_doc_pipeline.return_value.list_documents.return_value = [{"id": "d1"}]
        r = self.client.get("/api/docs/list")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["documents"], [{"id": "d1"}])

    def test_delete(self):
        self.fake_dp.get_doc_pipeline.return_value.delete_document.return_value = True
        r = self.client.delete("/api/docs/d1")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["deleted"])
        self.fake_dp.get_doc_pipeline.return_value.delete_document.assert_called_once_with("d1")

    def test_stats(self):
        self.fake_dp.get_doc_pipeline.return_value.get_stats.return_value = {"total": 3}
        r = self.client.get("/api/docs/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 3)


if __name__ == "__main__":
    unittest.main()
