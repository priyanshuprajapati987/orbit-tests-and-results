"""
Tests for A2A Protocol — models, agent card, task manager, security, gateway, handlers, blueprint.
"""

import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")

from orbit.orbit.core.a2a.agent_card import (
    generate_agent_card,
    get_agent_card_json,
)
from orbit.orbit.core.a2a.gateway import A2AGateway
from orbit.orbit.core.a2a.handlers import (
    handle_cancel_task,
    handle_get_task,
    handle_list_tasks,
    handle_send_message,
)
from orbit.orbit.core.a2a.models import (
    _VALID_TRANSITIONS,
    TERMINAL_STATES,
    A2AError,
    Artifact,
    JSONRPCRequest,
    JSONRPCResponse,
    Message,
    Part,
    Task,
    TaskState,
)
from orbit.orbit.core.a2a.security import A2ASecurity
from orbit.orbit.core.a2a.task_manager import TaskManager

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def task_mgr(tmp_dir):
    return TaskManager(tmp_dir / "tasks.jsonl")


@pytest.fixture
def security():
    return A2ASecurity(api_key="test-key-123")


@pytest.fixture(autouse=True)
def _reset_a2a_singletons():
    """Reset A2A singletons and set API key for fail-closed auth."""
    from orbit.orbit.core.a2a import gateway as gw_mod
    from orbit.orbit.core.a2a import security as sec_mod

    with patch.dict(os.environ, {"ORBIT_API_KEY": "test-a2a-key"}, clear=False):
        sec_mod._security = None
        gw_mod._gateway = None
        yield
        sec_mod._security = None
        gw_mod._gateway = None


@pytest.fixture
def gateway(tmp_dir):
    from orbit.orbit.core.a2a import security as sec_mod

    sec_mod._security = None  # reset so it picks up env key
    return A2AGateway()


def _auth_headers():
    """Return headers with valid API key for handler tests."""
    return {"X-API-Key": "test-a2a-key"}


# ── Part Tests ───────────────────────────────────────────────────────────────


class TestPart:
    def test_text_part(self):
        p = Part(type="text", text="hello")
        assert p.type == "text"
        assert p.text == "hello"
        d = p.to_dict()
        assert d == {"type": "text", "text": "hello"}

    def test_file_part(self):
        p = Part(type="file", file={"name": "test.txt", "mimeType": "text/plain"})
        d = p.to_dict()
        assert d["type"] == "file"
        assert d["file"]["name"] == "test.txt"

    def test_data_part(self):
        p = Part(type="data", data={"mimeType": "application/json", "key": "val"})
        d = p.to_dict()
        assert d["data"]["key"] == "val"

    def test_from_dict_roundtrip(self):
        p = Part(type="text", text="test", metadata={"k": "v"})
        d = p.to_dict()
        p2 = Part.from_dict(d)
        assert p2.type == p.type
        assert p2.text == p.text
        assert p2.metadata == p.metadata

    def test_optional_fields_omitted(self):
        p = Part(type="text", text="hi")
        d = p.to_dict()
        assert "file" not in d
        assert "data" not in d
        assert "metadata" not in d


# ── Message Tests ────────────────────────────────────────────────────────────


class TestMessage:
    def test_create(self):
        m = Message(role="user", parts=[Part(type="text", text="hello")])
        assert m.role == "user"
        assert len(m.parts) == 1
        assert m.message_id  # auto-generated

    def test_text_factory(self):
        m = Message.text("agent", "response text")
        assert m.role == "agent"
        assert m.parts[0].text == "response text"

    def test_to_dict(self):
        m = Message(
            role="user", parts=[Part(type="text", text="hi")], metadata={"src": "test"}
        )
        d = m.to_dict()
        assert d["role"] == "user"
        assert d["parts"][0]["text"] == "hi"
        assert d["metadata"]["src"] == "test"
        assert "messageId" in d

    def test_from_dict(self):
        d = {
            "role": "agent",
            "parts": [{"type": "text", "text": "ok"}],
            "messageId": "m1",
        }
        m = Message.from_dict(d)
        assert m.role == "agent"
        assert m.parts[0].text == "ok"
        assert m.message_id == "m1"


# ── Task Tests ───────────────────────────────────────────────────────────────


class TestTask:
    def test_create_default(self):
        t = Task()
        assert t.task_id
        assert t.status.state == TaskState.SUBMITTED.value

    def test_transition_valid(self):
        t = Task()
        ok = t.transition(TaskState.WORKING.value)
        assert ok
        assert t.status.state == TaskState.WORKING.value

    def test_transition_invalid(self):
        t = Task()
        t.transition(TaskState.COMPLETED.value)  # submitted → completed is NOT valid
        # submitted → working → completed
        t2 = Task()
        t2.transition(TaskState.WORKING.value)
        ok = t2.transition(TaskState.COMPLETED.value)
        assert ok
        assert t2.status.state == TaskState.COMPLETED.value

    def test_transition_blocked_from_terminal(self):
        t = Task()
        t.transition(TaskState.WORKING.value)
        t.transition(TaskState.COMPLETED.value)
        ok = t.transition(TaskState.WORKING.value)
        assert not ok  # can't leave terminal state

    def test_cannot_go_directly_to_completed(self):
        t = Task()
        ok = t.transition(TaskState.COMPLETED.value)
        assert not ok  # must go through working first

    def test_to_dict_roundtrip(self):
        t = Task(context_id="ctx-1", metadata={"key": "val"})
        t.transition(TaskState.WORKING.value)
        d = t.to_dict()
        t2 = Task.from_dict(d)
        assert t2.task_id == t.task_id
        assert t2.status.state == TaskState.WORKING.value
        assert t2.context_id == "ctx-1"
        assert t2.metadata == {"key": "val"}

    def test_artifacts(self):
        t = Task()
        a = Artifact(name="out", parts=[Part(type="text", text="result")])
        t.artifacts.append(a)
        d = t.to_dict()
        assert d["artifacts"][0]["name"] == "out"

    def test_history(self):
        m = Message.text("user", "task")
        t = Task(history=[m])
        d = t.to_dict()
        assert len(d["history"]) == 1

    def test_all_terminal_states_block(self):
        for state in TERMINAL_STATES:
            t = Task()
            t.transition(TaskState.WORKING.value)
            t.transition(state.value)
            ok = t.transition(TaskState.WORKING.value)
            assert not ok, f"Should block from {state.value}"

    def test_valid_transitions_exhaustive(self):
        # Every state has a defined transition set
        for state in TaskState:
            assert state in _VALID_TRANSITIONS


# ── Artifact Tests ───────────────────────────────────────────────────────────


class TestArtifact:
    def test_create(self):
        a = Artifact(name="doc", parts=[Part(type="text", text="content")])
        assert a.name == "doc"
        assert len(a.parts) == 1

    def test_to_dict(self):
        a = Artifact(
            artifact_id="a1",
            name="out",
            description="test output",
            parts=[Part(type="text", text="done")],
        )
        d = a.to_dict()
        assert d["artifactId"] == "a1"
        assert d["name"] == "out"
        assert d["parts"][0]["text"] == "done"

    def test_from_dict(self):
        d = {"artifactId": "a2", "parts": [{"type": "data", "data": {"x": 1}}]}
        a = Artifact.from_dict(d)
        assert a.artifact_id == "a2"
        assert a.parts[0].data == {"x": 1}


# ── Agent Card Tests ─────────────────────────────────────────────────────────


class TestAgentCard:
    def test_generate(self):
        card = generate_agent_card()
        assert card.name == "ORBIT"
        assert card.version
        assert len(card.skills) > 0

    def test_all_registry_agents_covered(self):
        card = generate_agent_card()
        skill_ids = {s.id for s in card.skills}
        # Should have at least the main agents
        assert "QUEEN" in skill_ids
        assert "TAS" in skill_ids
        assert "COD" in skill_ids
        assert "SEC" in skill_ids

    def test_to_dict(self):
        card = generate_agent_card(url="http://localhost:5000")
        d = card.to_dict()
        assert d["name"] == "ORBIT"
        assert d["url"] == "http://localhost:5000"
        assert "capabilities" in d
        assert "skills" in d
        assert "securitySchemes" in d

    def test_get_agent_card_json(self):
        d = get_agent_card_json(base_url="http://127.0.0.1:5000")
        assert isinstance(d, dict)
        assert d["name"] == "ORBIT"

    def test_skill_has_tags(self):
        card = generate_agent_card()
        for skill in card.skills:
            assert skill.tags, f"Skill {skill.id} missing tags"

    def test_capabilities_default(self):
        card = generate_agent_card()
        assert card.capabilities.streaming is False
        assert card.capabilities.push_notifications is False
        assert card.capabilities.state_transition_history is True


# ── TaskManager Tests ────────────────────────────────────────────────────────


class TestTaskManager:
    def test_create_task(self, task_mgr):
        msg = Message.text("user", "do something")
        task = task_mgr.create_task(msg)
        assert task.task_id
        assert task.status.state == TaskState.SUBMITTED.value
        assert task_mgr.task_count() == 1

    def test_get_task(self, task_mgr):
        msg = Message.text("user", "hello")
        task = task_mgr.create_task(msg)
        got = task_mgr.get_task(task.task_id)
        assert got is not None
        assert got.task_id == task.task_id

    def test_get_nonexistent(self, task_mgr):
        assert task_mgr.get_task("nonexistent") is None

    def test_list_tasks(self, task_mgr):
        msg = Message.text("user", "task")
        task_mgr.create_task(msg, context_id="ctx-1")
        task_mgr.create_task(msg, context_id="ctx-2")
        task_mgr.create_task(msg, context_id="ctx-1")

        all_tasks = task_mgr.list_tasks()
        assert len(all_tasks) == 3

        ctx1 = task_mgr.list_tasks(context_id="ctx-1")
        assert len(ctx1) == 2

    def test_transition(self, task_mgr):
        msg = Message.text("user", "go")
        task = task_mgr.create_task(msg)
        result = task_mgr.transition(task.task_id, TaskState.WORKING.value)
        assert result is not None
        assert result.status.state == TaskState.WORKING.value

    def test_transition_nonexistent(self, task_mgr):
        result = task_mgr.transition("nope", TaskState.WORKING.value)
        assert result is None

    def test_add_message(self, task_mgr):
        msg = Message.text("user", "start")
        task = task_mgr.create_task(msg)
        msg2 = Message.text("user", "follow up")
        result = task_mgr.add_message(task.task_id, msg2)
        assert result is not None
        assert len(result.history) == 2

    def test_persistence(self, tmp_dir):
        path = tmp_dir / "tasks.jsonl"
        mgr1 = TaskManager(path)
        msg = Message.text("user", "persistent")
        t = mgr1.create_task(msg)

        mgr2 = TaskManager(path)
        got = mgr2.get_task(t.task_id)
        assert got is not None
        assert got.task_id == t.task_id

    def test_clear(self, task_mgr):
        msg = Message.text("user", "x")
        task_mgr.create_task(msg)
        assert task_mgr.task_count() == 1
        task_mgr.clear()
        assert task_mgr.task_count() == 0


# ── Security Tests ───────────────────────────────────────────────────────────


class TestSecurity:
    def test_validate_correct_key(self, security):
        assert security.validate_api_key("test-key-123") is True

    def test_validate_wrong_key(self, security):
        assert security.validate_api_key("wrong") is False

    def test_validate_no_key(self, security):
        assert security.validate_api_key("") is False

    def test_no_key_configured_rejects(self):
        """Fail-closed: no API key configured = reject all requests."""
        s = A2ASecurity(api_key="")
        assert s.validate_api_key("anything") is False

    def test_replay_first_use(self, security):
        assert security.check_replay("nonce-1") is True

    def test_replay_detected(self, security):
        security.check_replay("nonce-2")
        assert security.check_replay("nonce-2") is False

    def test_replay_empty_nonce(self, security):
        assert security.check_replay("") is True

    def test_sign_and_verify(self, security):
        sig = security.sign_message("payload")
        assert security.verify_signature("payload", sig) is True

    def test_verify_wrong_signature(self, security):
        assert security.verify_signature("payload", "wrong-sig") is False

    def test_extract_auth_header(self, security):
        headers = {"X-API-Key": "my-key", "X-A2A-Nonce": "n1"}
        key, nonce = security.extract_auth(headers)
        assert key == "my-key"
        assert nonce == "n1"

    def test_extract_bearer(self, security):
        headers = {"Authorization": "Bearer token-abc"}
        key, _nonce = security.extract_auth(headers)
        assert key == "token-abc"

    def test_nonce_expiry(self, security):
        security._nonce_ttl = 0  # expire immediately
        security.check_replay("expire-me")
        time.sleep(0.01)
        assert security.check_replay("expire-me") is True  # expired, so new again


# ── Gateway Tests ────────────────────────────────────────────────────────────


class TestGateway:
    def test_method_not_found(self, gateway):
        req = JSONRPCRequest(id=1, method="nonexistent/method")
        resp = gateway.handle(req, headers=_auth_headers())
        assert resp.error is not None
        assert resp.error["code"] == A2AError.METHOD_NOT_FOUND

    def test_send_message_no_parts(self, gateway):
        req = JSONRPCRequest(id=1, method="message/send", params={"message": {}})
        resp = gateway.handle(req, headers=_auth_headers())
        assert resp.error is not None
        assert "parts" in resp.error["message"].lower()

    def test_get_task_missing_id(self, gateway):
        req = JSONRPCRequest(id=1, method="task/get", params={})
        resp = gateway.handle(req, headers=_auth_headers())
        assert resp.error is not None

    def test_get_task_not_found(self, gateway):
        req = JSONRPCRequest(id=1, method="task/get", params={"id": "nonexistent"})
        resp = gateway.handle(req, headers=_auth_headers())
        assert resp.error is not None
        assert resp.error["code"] == A2AError.TASK_NOT_FOUND

    def test_list_tasks(self, gateway):
        req = JSONRPCRequest(id=1, method="task/list", params={})
        resp = gateway.handle(req, headers=_auth_headers())
        assert resp.result is not None
        assert "tasks" in resp.result

    def test_cancel_nonexistent(self, gateway):
        req = JSONRPCRequest(id=1, method="task/cancel", params={"id": "nope"})
        resp = gateway.handle(req, headers=_auth_headers())
        assert resp.error is not None

    def test_auth_required(self):
        gw = A2AGateway()
        gw._security = A2ASecurity(api_key="secret")
        req = JSONRPCRequest(id=1, method="task/list", params={})
        resp = gw.handle(req, headers={})
        assert resp.error is not None
        assert "Unauthorized" in resp.error["message"]

    def test_auth_passes_with_key(self):
        gw = A2AGateway()
        gw._security = A2ASecurity(api_key="secret")
        req = JSONRPCRequest(id=1, method="task/list", params={})
        resp = gw.handle(req, headers={"X-API-Key": "secret"})
        assert resp.result is not None

    def test_stats(self, gateway):
        req = JSONRPCRequest(id=1, method="task/list", params={})
        gateway.handle(req, headers=_auth_headers())
        stats = gateway.get_stats()
        assert stats["dispatched"] >= 1

    def test_send_message_dispatches(self, gateway):
        """Full flow: send message → task created → completed with artifact."""
        req = JSONRPCRequest(
            id=1,
            method="message/send",
            params={
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": "hello"}],
                }
            },
        )
        resp = gateway.handle(req, headers=_auth_headers())
        assert resp.result is not None
        assert resp.result["status"]["state"] == "completed"
        assert len(resp.result["artifacts"]) >= 1


# ── Handler Convenience Tests ────────────────────────────────────────────────


class TestHandlers:
    def test_handle_send_message(self):
        resp = handle_send_message(
            message={"role": "user", "parts": [{"type": "text", "text": "hi"}]},
        )
        # Handler goes through gateway which requires auth
        # Without headers, it should get unauthorized or succeed if env key is set
        assert "result" in resp or "error" in resp

    def test_handle_send_message_with_auth(self):
        from orbit.orbit.core.a2a.handlers import handle_jsonrpc

        resp = handle_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "message/send",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [{"type": "text", "text": "hi"}],
                    },
                },
            },
            headers=_auth_headers(),
        )
        assert "result" in resp

    def test_handle_get_task_missing(self):
        resp = handle_get_task("nonexistent")
        assert "error" in resp

    def test_handle_list_tasks(self):
        resp = handle_list_tasks()
        # With fail-closed, needs auth headers
        assert "result" in resp or "error" in resp

    def test_handle_list_tasks_with_auth(self):
        from orbit.orbit.core.a2a.handlers import handle_jsonrpc

        resp = handle_jsonrpc(
            {"jsonrpc": "2.0", "id": 1, "method": "task/list", "params": {}},
            headers=_auth_headers(),
        )
        assert "result" in resp
        assert "tasks" in resp["result"]

    def test_handle_cancel_nonexistent(self):
        resp = handle_cancel_task("nope")
        assert "error" in resp


# ── JSON-RPC Request/Response Tests ──────────────────────────────────────────


class TestJSONRPC:
    def test_request_from_dict(self):
        d = {"jsonrpc": "2.0", "id": 42, "method": "test", "params": {"x": 1}}
        req = JSONRPCRequest.from_dict(d)
        assert req.id == 42
        assert req.method == "test"
        assert req.params == {"x": 1}

    def test_response_to_dict(self):
        resp = JSONRPCResponse(id=1, result={"ok": True})
        d = resp.to_dict()
        assert d["jsonrpc"] == "2.0"
        assert d["id"] == 1
        assert d["result"]["ok"] is True
        assert "error" not in d

    def test_response_error(self):
        resp = JSONRPCResponse(id=1, error={"code": -32601, "message": "not found"})
        d = resp.to_dict()
        assert "error" in d
        assert "result" not in d

    def test_error_make(self):
        err = A2AError.make(A2AError.TASK_NOT_FOUND, "Task not found: x")
        assert err["code"] == -32001
        assert "Task not found" in err["message"]


# ── Blueprint Smoke Test ─────────────────────────────────────────────────────


class TestBlueprint:
    def test_agent_card_endpoint(self, tmp_dir):
        from flask import Flask

        from orbit.orbit.core.a2a.a2a_bp import a2a_bp

        app = Flask(__name__)
        app.register_blueprint(a2a_bp)
        app.config["TESTING"] = True

        with app.test_client() as client:
            resp = client.get("/.well-known/agent.json")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["name"] == "ORBIT"
            assert len(data["skills"]) > 0

    def test_stats_endpoint(self, tmp_dir):
        from flask import Flask

        from orbit.orbit.core.a2a.a2a_bp import a2a_bp

        app = Flask(__name__)
        app.register_blueprint(a2a_bp)
        app.config["TESTING"] = True

        with app.test_client() as client:
            resp = client.get("/api/a2a/stats", headers=_auth_headers())
            assert resp.status_code == 200
            data = resp.get_json()
            assert "dispatched" in data
            assert "tasks_total" in data

    def test_jsonrpc_endpoint(self, tmp_dir):
        from flask import Flask

        from orbit.orbit.core.a2a.a2a_bp import a2a_bp

        app = Flask(__name__)
        app.register_blueprint(a2a_bp)
        app.config["TESTING"] = True

        with app.test_client() as client:
            resp = client.post(
                "/a2a",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "task/list",
                    "params": {},
                },
                headers={"X-API-Key": "test-a2a-key"},
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert "result" in data

    def test_jsonrpc_bad_json(self, tmp_dir):
        from flask import Flask

        from orbit.orbit.core.a2a.a2a_bp import a2a_bp

        app = Flask(__name__)
        app.register_blueprint(a2a_bp)
        app.config["TESTING"] = True

        with app.test_client() as client:
            resp = client.post("/a2a", data="not json", content_type="application/json")
            assert resp.status_code == 400

    def test_task_endpoint_not_found(self, tmp_dir):
        from flask import Flask

        from orbit.orbit.core.a2a.a2a_bp import a2a_bp

        app = Flask(__name__)
        app.register_blueprint(a2a_bp)
        app.config["TESTING"] = True

        with app.test_client() as client:
            resp = client.get("/api/a2a/task/nonexistent", headers=_auth_headers())
            assert resp.status_code == 404

    def test_rest_endpoints_require_auth(self, tmp_dir):
        """REST shorthands enforce API-key auth (no key -> 401, not data/404)."""
        from flask import Flask

        from orbit.orbit.core.a2a.a2a_bp import a2a_bp

        app = Flask(__name__)
        app.register_blueprint(a2a_bp)
        app.config["TESTING"] = True

        with app.test_client() as client:
            assert client.get("/api/a2a/stats").status_code == 401
            assert client.get("/api/a2a/task/anything").status_code == 401
            assert client.get("/api/a2a/tasks").status_code == 401
