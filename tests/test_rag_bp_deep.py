"""Deep tests for orbit/orbit/core/rag_bp.py (Loop 12/3).

Covers every statement of the RAG Flask blueprint:
  * ``_get_rag`` — delegates to ``get_rag_engine``.
  * ``GET /api/rag/status``
  * ``POST /api/rag/ingest`` — missing content 400, size guard 400,
    success passthrough.
  * ``POST /api/rag/ingest/file`` — missing filepath 400, path-blocked 403,
    success 200, exception → 500.
  * ``POST /api/rag/ingest/directory`` — missing dirpath 400, blocked 403,
    success, exception → 500.
  * ``POST /api/rag/query`` — missing query 400, top_k parsing/clamping
    (int, invalid→5, min 1, max 20), result shaping (doc_id/content/
    score/source/metadata).
  * ``GET /api/rag/documents`` — passthrough.
  * ``POST /api/rag/delete`` — missing doc_id 400, success passthrough.
  * ``POST /api/rag/clear`` — passthrough.
  * ``register(server)`` — registers blueprint, returns True.
"""

import unittest
from types import SimpleNamespace
from unittest import mock

import flask

from orbit.orbit.core import rag_bp


def _rag():
    m = mock.MagicMock()
    m.get_status.return_value = {"status": "ok", "docs": 3}
    m.ingest.return_value = {"ingested": 1}
    m.ingest_file.return_value = {"ingested": 2}
    m.ingest_directory.return_value = {"ingested": 5}
    m.query.return_value = [
        SimpleNamespace(doc_id="d1", content="c1", score=0.987654,
                        source="s1", metadata={"k": "v"}),
        SimpleNamespace(doc_id="d2", content="c2", score=0.1234,
                        source="s2", metadata=None),
    ]
    m.get_documents.return_value = [{"id": "d1"}, {"id": "d2"}]
    m.delete.return_value = True
    m.clear.return_value = {"cleared": True}
    return m


class RagBpTests(unittest.TestCase):
    def setUp(self):
        app = flask.Flask(__name__)
        app.register_blueprint(rag_bp.rag_bp)
        self.client = app.test_client()

    # ── _get_rag ────────────────────────────────────────────────────

    def test_get_rag_delegates(self):
        rag = _rag()
        with mock.patch("orbit.orbit.core.rag_engine.get_rag_engine",
                        return_value=rag) as g:
            self.assertIs(rag_bp._get_rag(), rag)
        g.assert_called_once_with()

    # ── status ──────────────────────────────────────────────────────

    def test_status(self):
        with mock.patch.object(rag_bp, "_get_rag", return_value=_rag()):
            r = self.client.get("/api/rag/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"status": "ok", "docs": 3})

    # ── ingest ──────────────────────────────────────────────────────

    def test_ingest_missing_content_400(self):
        with mock.patch.object(rag_bp, "_get_rag"):
            r = self.client.post("/api/rag/ingest", json={})
            r2 = self.client.post("/api/rag/ingest", json={"content": ""})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r2.status_code, 400)
        self.assertEqual(r.get_json()["error"], "content required")

    def test_ingest_too_large_400(self):
        with mock.patch.object(rag_bp, "_get_rag") as g:
            r = self.client.post("/api/rag/ingest",
                                 json={"content": "x" * (10 * 1024 * 1024 + 1)})
        self.assertEqual(r.status_code, 400)
        self.assertIn("too large", r.get_json()["error"])
        g.assert_not_called()

    def test_ingest_success(self):
        rag = _rag()
        with mock.patch.object(rag_bp, "_get_rag", return_value=rag):
            r = self.client.post("/api/rag/ingest", json={
                "content": "hello", "metadata": {"a": 1}, "source": "src"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"ingested": 1})
        rag.ingest.assert_called_once_with("hello", metadata={"a": 1},
                                          source="src")

    def test_ingest_default_source_empty(self):
        rag = _rag()
        with mock.patch.object(rag_bp, "_get_rag", return_value=rag):
            self.client.post("/api/rag/ingest", json={"content": "hi"})
        rag.ingest.assert_called_once_with("hi", metadata=None, source="")

    # ── ingest/file ─────────────────────────────────────────────────

    def test_ingest_file_missing_filepath_400(self):
        with mock.patch.object(rag_bp, "_get_rag") as g, \
                mock.patch("orbit.orbit.core._security_utils.validate_path"):
            r = self.client.post("/api/rag/ingest/file", json={})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "filepath required")
        g.assert_not_called()

    def test_ingest_file_blocked_403(self):
        with mock.patch.object(rag_bp, "_get_rag") as g, \
                mock.patch("orbit.orbit.core.rag_bp.validate_path",
                           return_value=(False, "nope")):
            r = self.client.post("/api/rag/ingest/file",
                                 json={"filepath": "/etc/passwd"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.get_json()["error"], "path not allowed")
        self.assertEqual(r.get_json()["reason"], "nope")
        g.assert_not_called()

    def test_ingest_file_success(self):
        rag = _rag()
        with mock.patch.object(rag_bp, "_get_rag", return_value=rag), \
                mock.patch("orbit.orbit.core.rag_bp.validate_path",
                           return_value=(True, "ok")):
            r = self.client.post("/api/rag/ingest/file",
                                 json={"filepath": "/tmp/a.txt"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"ingested": 2})
        rag.ingest_file.assert_called_once_with("/tmp/a.txt")

    def test_ingest_file_exception_500(self):
        rag = _rag()
        rag.ingest_file.side_effect = RuntimeError("boom")
        with mock.patch.object(rag_bp, "_get_rag", return_value=rag), \
                mock.patch("orbit.orbit.core.rag_bp.validate_path",
                           return_value=(True, "ok")), \
                mock.patch.object(rag_bp, "logger"):
            r = self.client.post("/api/rag/ingest/file",
                                 json={"filepath": "/tmp/a.txt"})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "RAG ingest failed")

    # ── ingest/directory ────────────────────────────────────────────

    def test_ingest_dir_missing_dirpath_400(self):
        with mock.patch.object(rag_bp, "_get_rag") as g, \
                mock.patch("orbit.orbit.core._security_utils.validate_path"):
            r = self.client.post("/api/rag/ingest/directory", json={})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "dirpath required")
        g.assert_not_called()

    def test_ingest_dir_blocked_403(self):
        with mock.patch.object(rag_bp, "_get_rag") as g, \
                mock.patch("orbit.orbit.core.rag_bp.validate_path",
                           return_value=(False, "nope")):
            r = self.client.post("/api/rag/ingest/directory",
                                 json={"dirpath": "/etc"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.get_json()["error"], "path not allowed")

    def test_ingest_dir_success_with_extensions(self):
        rag = _rag()
        with mock.patch.object(rag_bp, "_get_rag", return_value=rag), \
                mock.patch("orbit.orbit.core.rag_bp.validate_path",
                           return_value=(True, "ok")):
            r = self.client.post("/api/rag/ingest/directory", json={
                "dirpath": "/tmp/d", "extensions": [".txt", ".md"]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"ingested": 5})
        rag.ingest_directory.assert_called_once_with("/tmp/d",
                                                    [".txt", ".md"])

    def test_ingest_dir_success_default_extensions(self):
        rag = _rag()
        with mock.patch.object(rag_bp, "_get_rag", return_value=rag), \
                mock.patch("orbit.orbit.core.rag_bp.validate_path",
                           return_value=(True, "ok")):
            self.client.post("/api/rag/ingest/directory",
                             json={"dirpath": "/tmp/d"})
        rag.ingest_directory.assert_called_once_with("/tmp/d", None)

    def test_ingest_dir_exception_500(self):
        rag = _rag()
        rag.ingest_directory.side_effect = RuntimeError("boom")
        with mock.patch.object(rag_bp, "_get_rag", return_value=rag), \
                mock.patch("orbit.orbit.core.rag_bp.validate_path",
                           return_value=(True, "ok")), \
                mock.patch.object(rag_bp, "logger"):
            r = self.client.post("/api/rag/ingest/directory",
                                 json={"dirpath": "/tmp/d"})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"],
                         "RAG ingest directory failed")

    # ── query ───────────────────────────────────────────────────────

    def test_query_missing_400(self):
        with mock.patch.object(rag_bp, "_get_rag") as g:
            r = self.client.post("/api/rag/query", json={})
            r2 = self.client.post("/api/rag/query", json={"query": ""})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r2.status_code, 400)
        self.assertEqual(r.get_json()["error"], "query required")
        g.assert_not_called()

    def test_query_default_top_k(self):
        rag = _rag()
        with mock.patch.object(rag_bp, "_get_rag", return_value=rag):
            r = self.client.post("/api/rag/query", json={"query": "hello"})
        self.assertEqual(r.status_code, 200)
        rag.query.assert_called_once_with("hello", 5)
        body = r.get_json()["results"]
        self.assertEqual(len(body), 2)
        self.assertEqual(body[0], {
            "doc_id": "d1", "content": "c1", "score": 0.9877,
            "source": "s1", "metadata": {"k": "v"}})
        self.assertEqual(body[1]["score"], 0.1234)

    def test_query_top_k_int(self):
        rag = _rag()
        with mock.patch.object(rag_bp, "_get_rag", return_value=rag):
            self.client.post("/api/rag/query",
                             json={"query": "q", "top_k": 7})
        rag.query.assert_called_once_with("q", 7)

    def test_query_top_k_invalid_falls_back_to_5(self):
        rag = _rag()
        with mock.patch.object(rag_bp, "_get_rag", return_value=rag):
            self.client.post("/api/rag/query",
                             json={"query": "q", "top_k": "abc"})
            self.client.post("/api/rag/query",
                             json={"query": "q", "top_k": None})
        for c in rag.query.call_args_list:
            self.assertEqual(c.args[1], 5)

    def test_query_top_k_clamped_min(self):
        rag = _rag()
        with mock.patch.object(rag_bp, "_get_rag", return_value=rag):
            self.client.post("/api/rag/query",
                             json={"query": "q", "top_k": 0})
            self.client.post("/api/rag/query",
                             json={"query": "q", "top_k": -5})
        for c in rag.query.call_args_list:
            self.assertEqual(c.args[1], 1)

    def test_query_top_k_clamped_max(self):
        rag = _rag()
        with mock.patch.object(rag_bp, "_get_rag", return_value=rag):
            self.client.post("/api/rag/query",
                             json={"query": "q", "top_k": 999})
        rag.query.assert_called_once_with("q", 20)

    # ── documents ───────────────────────────────────────────────────

    def test_documents(self):
        with mock.patch.object(rag_bp, "_get_rag", return_value=_rag()):
            r = self.client.get("/api/rag/documents")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"documents": [{"id": "d1"},
                                                     {"id": "d2"}]})

    # ── delete ──────────────────────────────────────────────────────

    def test_delete_missing_doc_id_400(self):
        with mock.patch.object(rag_bp, "_get_rag") as g:
            r = self.client.post("/api/rag/delete", json={})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "doc_id required")
        g.assert_not_called()

    def test_delete_success(self):
        rag = _rag()
        with mock.patch.object(rag_bp, "_get_rag", return_value=rag):
            r = self.client.post("/api/rag/delete", json={"doc_id": "d1"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"deleted": True})
        rag.delete.assert_called_once_with("d1")

    def test_delete_not_found(self):
        rag = _rag()
        rag.delete.return_value = False
        with mock.patch.object(rag_bp, "_get_rag", return_value=rag):
            r = self.client.post("/api/rag/delete", json={"doc_id": "nope"})
        self.assertEqual(r.get_json(), {"deleted": False})

    # ── clear ───────────────────────────────────────────────────────

    def test_clear(self):
        with mock.patch.object(rag_bp, "_get_rag", return_value=_rag()):
            r = self.client.post("/api/rag/clear")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"cleared": True})

    # ── register ────────────────────────────────────────────────────

    def test_register(self):
        server = mock.MagicMock()
        self.assertTrue(rag_bp.register(server))
        server.register_blueprint.assert_called_once_with(rag_bp.rag_bp)


if __name__ == "__main__":
    unittest.main()
