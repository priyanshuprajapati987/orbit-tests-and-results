"""Deep tests for orbit/agentmemory_bp.py (Loop 11/2).

Covers every statement of the agent-memory blueprint:
  * ``_request_user_id`` — authenticated id, empty/None id -> "local",
    any exception -> "local".
  * ``POST /save`` — validation 400, share_memory success (id passthrough),
    access-control deny -> 403, exception -> 500.
  * ``GET|POST /recall`` — both verb styles, missing agent_id -> 400,
    empty query default, exception -> 500.
  * ``GET /stats`` — stats passthrough, exception -> 500.
  * ``DELETE /memories/<id>`` — missing agent_id -> 400, ok, not-found
    -> 404, exception -> 500.
"""

import unittest
from types import SimpleNamespace
from unittest import mock

import flask

from orbit.agentmemory_bp import agentmemory_bp, _request_user_id


class AgentMemoryBpTests(unittest.TestCase):
    def setUp(self):
        app = flask.Flask(__name__)
        app.register_blueprint(agentmemory_bp)
        self.client = app.test_client()

    # ── _request_user_id ────────────────────────────────────────────

    def test_user_id_from_session(self):
        with mock.patch("orbit.orbit.core.auth.guards.current_user",
                        return_value={"id": "user-9"}):
            self.assertEqual(_request_user_id(), "user-9")

    def test_user_id_empty_becomes_local(self):
        with mock.patch("orbit.orbit.core.auth.guards.current_user",
                        return_value={"id": ""}):
            self.assertEqual(_request_user_id(), "local")

    def test_user_id_missing_key_becomes_local(self):
        with mock.patch("orbit.orbit.core.auth.guards.current_user",
                        return_value={}):
            self.assertEqual(_request_user_id(), "local")

    def test_user_id_none_becomes_local(self):
        with mock.patch("orbit.orbit.core.auth.guards.current_user",
                        return_value={"id": None}):
            self.assertEqual(_request_user_id(), "local")

    def test_user_id_exception_becomes_local(self):
        with mock.patch("orbit.orbit.core.auth.guards.current_user",
                        side_effect=RuntimeError("no session")):
            self.assertEqual(_request_user_id(), "local")

    # ── POST /save ──────────────────────────────────────────────────

    def test_save_missing_fields_400(self):
        for payload in ({}, {"agent_id": "a1"}, {"key": "k1"}):
            with self.subTest(payload=payload):
                r = self.client.post("/api/agent-memory/save",
                                     json=payload)
                self.assertEqual(r.status_code, 400)
                self.assertIn("agent_id and key required",
                              r.get_json()["error"])

    def test_save_success(self):
        entry = SimpleNamespace(id=42)
        with mock.patch("orbit.orbit.core.memory_store.share_memory",
                        return_value=entry) as share, \
                mock.patch("orbit.orbit.core.auth.guards.current_user",
                           return_value={"id": "user-9"}):
            r = self.client.post("/api/agent-memory/save", json={
                "agent_id": "a1", "key": "k1", "value": {"x": 1}})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"success": True, "id": 42})
        share.assert_called_once_with(agent_id="a1", namespace="agent",
                                      key="k1", value={"x": 1},
                                      user_id="user-9")

    def test_save_denied_403(self):
        with mock.patch("orbit.orbit.core.memory_store.share_memory",
                        return_value=None):
            r = self.client.post("/api/agent-memory/save", json={
                "agent_id": "a1", "key": "k1"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("write denied", r.get_json()["error"])

    def test_save_exception_500(self):
        with mock.patch("orbit.orbit.core.memory_store.share_memory",
                        side_effect=RuntimeError("db down")):
            r = self.client.post("/api/agent-memory/save", json={
                "agent_id": "a1", "key": "k1"})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "db down")

    def test_save_non_json_body_defaults(self):
        # force=True parses whatever arrives; empty body -> {} -> 400
        r = self.client.post("/api/agent-memory/save", data="",
                             content_type="application/json")
        self.assertEqual(r.status_code, 400)

    # ── GET|POST /recall ────────────────────────────────────────────

    def test_recall_post(self):
        rows = [{"id": 1}, {"id": 2}]
        with mock.patch("orbit.orbit.core.memory_store.recall_shared",
                        return_value=rows) as recall:
            r = self.client.post("/api/agent-memory/recall", json={
                "agent_id": "a1", "q": "topic"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"results": rows, "count": 2})
        recall.assert_called_once_with(agent_id="a1", query="topic",
                                       limit=10, user_id="local")

    def test_recall_get(self):
        with mock.patch("orbit.orbit.core.memory_store.recall_shared",
                        return_value=[]) as recall:
            r = self.client.get(
                "/api/agent-memory/recall?agent_id=a1&q=hello")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"results": [], "count": 0})
        recall.assert_called_once_with(agent_id="a1", query="hello",
                                       limit=10, user_id="local")

    def test_recall_get_without_query_defaults_empty(self):
        with mock.patch("orbit.orbit.core.memory_store.recall_shared",
                        return_value=[]) as recall:
            r = self.client.get("/api/agent-memory/recall?agent_id=a1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(recall.call_args.kwargs["query"], "")

    def test_recall_missing_agent_id_400(self):
        with mock.patch("orbit.orbit.core.memory_store.recall_shared") as rc:
            r = self.client.get("/api/agent-memory/recall")
            r2 = self.client.post("/api/agent-memory/recall", json={"q": "x"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r2.status_code, 400)
        rc.assert_not_called()

    def test_recall_exception_500(self):
        with mock.patch("orbit.orbit.core.memory_store.recall_shared",
                        side_effect=RuntimeError("db down")):
            r = self.client.post("/api/agent-memory/recall", json={
                "agent_id": "a1"})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "db down")

    def test_recall_non_json_post_defaults(self):
        with mock.patch("orbit.orbit.core.memory_store.recall_shared",
                        return_value=[]) as recall:
            r = self.client.post("/api/agent-memory/recall", data="",
                                 content_type="application/json")
        self.assertEqual(r.status_code, 400)
        recall.assert_not_called()

    # ── GET /stats ──────────────────────────────────────────────────

    def test_stats_success(self):
        store = mock.MagicMock()
        store.stats.return_value = {"entries": 7, "agents": 2}
        with mock.patch("orbit.orbit.core.memory_store.get_shared_memory",
                        return_value=store):
            r = self.client.get("/api/agent-memory/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"entries": 7, "agents": 2})
        store.stats.assert_called_once_with()

    def test_stats_exception_500(self):
        with mock.patch("orbit.orbit.core.memory_store.get_shared_memory",
                        side_effect=RuntimeError("db down")):
            r = self.client.get("/api/agent-memory/stats")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "db down")

    # ── DELETE /memories/<id> ───────────────────────────────────────

    def test_delete_missing_agent_id_400(self):
        with mock.patch("orbit.orbit.core.memory_store.get_shared_memory") as g:
            r = self.client.delete("/api/agent-memory/memories/5")
        self.assertEqual(r.status_code, 400)
        g.assert_not_called()

    def test_delete_success(self):
        store = mock.MagicMock()
        store.delete_by_id.return_value = True
        with mock.patch("orbit.orbit.core.memory_store.get_shared_memory",
                        return_value=store) as get_store, \
                mock.patch("orbit.orbit.core.auth.guards.current_user",
                           return_value={"id": "user-9"}):
            r = self.client.delete(
                "/api/agent-memory/memories/5?agent_id=a1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"success": True})
        store.delete_by_id.assert_called_once_with("a1", "5",
                                                   user_id="user-9")
        get_store.assert_called_once_with()

    def test_delete_not_found_404(self):
        store = mock.MagicMock()
        store.delete_by_id.return_value = False
        with mock.patch("orbit.orbit.core.memory_store.get_shared_memory",
                        return_value=store):
            r = self.client.delete(
                "/api/agent-memory/memories/5?agent_id=a1")
        self.assertEqual(r.status_code, 404)
        self.assertIn("not found", r.get_json()["error"])

    def test_delete_exception_500(self):
        store = mock.MagicMock()
        store.delete_by_id.side_effect = RuntimeError("db down")
        with mock.patch("orbit.orbit.core.memory_store.get_shared_memory",
                        return_value=store):
            r = self.client.delete(
                "/api/agent-memory/memories/5?agent_id=a1")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "db down")


if __name__ == "__main__":
    unittest.main()
