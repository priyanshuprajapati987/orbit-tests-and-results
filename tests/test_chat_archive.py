"""Chat Archive — export formatters, external parsers, API routes, import flow."""

from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flask import Flask

from orbit.orbit.core import chat_archive_bp as cab
from orbit.orbit.core import conversation_manager as cm

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

CHATGPT_CONV = {
    "title": "Math chat",
    "create_time": 1728000000,
    "mapping": {
        "root": {"parent": None, "children": ["a"], "message": None},
        "a": {
            "parent": "root",
            "children": ["b"],
            "message": {
                "author": {"role": "user"},
                "content": {"parts": ["What is 2+2?"], "content_type": "text"},
            },
        },
        "b": {
            "parent": "a",
            "children": [],
            "message": {
                "author": {"role": "assistant"},
                "content": {"parts": ["4"], "content_type": "text"},
            },
        },
    },
}


class FakeMemory:
    def __init__(self):
        self.calls = []

    def add_memory(self, content, category=None, importance=0.5, tags=None,
                   source=None, **kw):
        self.calls.append(
            {"content": content, "category": category, "importance": importance,
             "tags": tags, "source": source}
        )
        return {"ok": True}


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(cab, "_stats_path", tmp_path / "chat_archive" / "stats.json")
    monkeypatch.setattr(cm, "DATA_DIR", tmp_path / "conversations")
    mgr = cm.ConversationManager()
    mem = FakeMemory()
    monkeypatch.setattr(cab, "get_conversation_manager", lambda: mgr)
    monkeypatch.setattr(cab, "get_memory_consolidation", lambda: mem)
    application = Flask(__name__)
    application.register_blueprint(cab.chat_archive_bp)
    application.test_client().get("/api/chat-archive/status")  # init stats file
    application.extensions["mgr"] = mgr
    application.extensions["mem"] = mem
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


# ─────────────────────────────────────────────────────────────────────────────
# Parsers
# ─────────────────────────────────────────────────────────────────────────────

class TestParsers:
    def test_chatgpt_mapping_walk(self):
        sessions = cab.parse_chatgpt([CHATGPT_CONV])
        assert len(sessions) == 1
        s = sessions[0]
        assert s["title"] == "Math chat"
        assert [m["role"] for m in s["messages"]] == ["user", "assistant"]
        assert s["messages"][0]["content"] == "What is 2+2?"

    def test_claude_export(self):
        data = {
            "conversations": [
                {
                    "name": "Trip plans",
                    "chat_messages": [
                        {"sender": "human", "text": "Plan a trip"},
                        {"sender": "assistant", "content": [{"type": "text", "text": "Where to?"}]},
                    ],
                }
            ]
        }
        sessions = cab.parse_claude(data)
        assert len(sessions) == 1
        assert sessions[0]["title"] == "Trip plans"
        assert [m["role"] for m in sessions[0]["messages"]] == ["user", "assistant"]
        assert sessions[0]["messages"][1]["content"] == "Where to?"

    def test_orbit_archive_sessions(self):
        data = {
            "format": "orbit-chat-archive",
            "sessions": [
                {
                    "title": "Backup",
                    "messages": [
                        {"role": "user", "content": "hi"},
                        {"role": "agent", "content": "hello", "agent": "QUEEN"},
                    ],
                }
            ],
        }
        sessions = cab.parse_orbit(data)
        assert len(sessions) == 1
        assert sessions[0]["messages"][1]["role"] == "assistant"  # agent -> assistant
        assert sessions[0]["messages"][1]["agent"] == "QUEEN"

    def test_bare_message_list(self):
        sessions = cab.parse_orbit([
            {"role": "user", "content": "one"},
            {"role": "assistant", "content": "two"},
        ])
        assert len(sessions) == 1
        assert len(sessions[0]["messages"]) == 2

    def test_markdown_roles_multiline(self):
        md = "**You**: Hello\nHow are you?\n\n**ORBIT**: I am fine"
        sessions = cab.parse_markdown(md, title="MD chat")
        assert len(sessions) == 1
        msgs = sessions[0]["messages"]
        assert [m["role"] for m in msgs] == ["user", "assistant"]
        assert "How are you?" in msgs[0]["content"]

    def test_markdown_heading_style(self):
        md = "### User\nbuy milk\n\n### ORBIT\non it"
        sessions = cab.parse_markdown(md)
        assert sessions and len(sessions[0]["messages"]) == 2

    def test_markdown_no_roles_empty(self):
        assert cab.parse_markdown("just some notes, no chat") == []

    def test_detect_zip(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("conversations.json", json.dumps([CHATGPT_CONV]))
        sessions, source = cab.detect_and_parse("chatgpt-export.zip", buf.getvalue())
        assert source == "chatgpt"
        assert sessions[0]["title"] == "Math chat"

    def test_detect_orbit_json(self):
        raw = json.dumps({
            "sessions": [{"title": "A", "messages": [{"role": "user", "content": "x"}]}]
        }).encode()
        sessions, source = cab.detect_and_parse("archive.json", raw)
        assert source == "orbit"
        assert sessions[0]["title"] == "A"

    def test_detect_unknown_json_raises(self):
        with pytest.raises(ValueError):
            cab.detect_and_parse("weird.json", json.dumps({"foo": 1}).encode())

    def test_detect_invalid_json_raises(self):
        with pytest.raises(ValueError):
            cab.detect_and_parse("broken.json", b"{not json")

    def test_detect_markdown_file(self):
        raw = b"**You**: hey\n**ORBIT**: hi"
        sessions, source = cab.detect_and_parse("log.md", raw)
        assert source == "markdown"
        assert len(sessions[0]["messages"]) == 2

    def test_detect_text_without_roles_raises(self):
        with pytest.raises(ValueError):
            cab.detect_and_parse("notes.txt", b"no roles here")


# ─────────────────────────────────────────────────────────────────────────────
# Formatters
# ─────────────────────────────────────────────────────────────────────────────

SESSIONS = [
    {
        "title": "Demo",
        "messages": [
            {"role": "user", "content": "hello <b>x</b>"},
            {"role": "assistant", "content": "hi", "agent": "QUEEN"},
        ],
    }
]


class TestFormatters:
    def test_json_roundtrip(self):
        data = cab.format_sessions(SESSIONS, "json")
        parsed = json.loads(data)
        assert parsed["format"] == "orbit-chat-archive"
        assert parsed["session_count"] == 1
        assert parsed["sessions"][0]["messages"][0]["content"] == "hello <b>x</b>"

    def test_markdown(self):
        text = cab.format_sessions(SESSIONS, "md").decode()
        assert "# ORBIT Chat Archive" in text
        assert "**You**: hello" in text
        assert "**QUEEN**: hi" in text

    def test_txt(self):
        text = cab.format_sessions(SESSIONS, "txt").decode()
        assert "ORBIT CHAT ARCHIVE" in text
        assert "YOU:" in text

    def test_html_escapes_and_labels(self):
        html = cab.format_sessions(SESSIONS, "html").decode()
        assert "&lt;b&gt;x&lt;/b&gt;" in html
        assert "<script" not in html
        assert "QUEEN" in html

    def test_unknown_format_raises(self):
        with pytest.raises(ValueError):
            cab.format_sessions(SESSIONS, "pdf")


# ─────────────────────────────────────────────────────────────────────────────
# API — export
# ─────────────────────────────────────────────────────────────────────────────

class TestExportAPI:
    def test_export_md_attachment(self, client):
        res = client.post(
            "/api/chat-archive/export",
            json={"format": "md", "sessions": SESSIONS},
        )
        assert res.status_code == 200
        assert "attachment" in res.headers.get("Content-Disposition", "")
        assert "orbit-chat-demo.md" in res.headers.get("Content-Disposition", "")
        assert "# ORBIT Chat Archive" in res.data.decode()

    def test_export_bad_format(self, client):
        res = client.post(
            "/api/chat-archive/export",
            json={"format": "pdf", "sessions": SESSIONS},
        )
        assert res.status_code == 400
        assert "format" in res.get_json()["error"]

    def test_export_empty_sessions(self, client):
        res = client.post("/api/chat-archive/export", json={"format": "json", "sessions": []})
        assert res.status_code == 400

    def test_export_bumps_stats(self, client):
        before = client.get("/api/chat-archive/status").get_json()["stats"]["exports"]
        client.post("/api/chat-archive/export", json={"format": "json", "sessions": SESSIONS})
        after = client.get("/api/chat-archive/status").get_json()["stats"]["exports"]
        assert after == before + 1

    def test_export_server_empty_404(self, client):
        res = client.get("/api/chat-archive/export-server?format=json")
        assert res.status_code == 404

    def test_export_server_conversations(self, client, app):
        mgr = app.extensions["mgr"]
        conv = mgr.create(title="Server conv")
        mgr.send(conv["id"], "user", "question")
        mgr.send(conv["id"], "assistant", "answer")
        res = client.get("/api/chat-archive/export-server?format=txt")
        assert res.status_code == 200
        assert "SERVER CONV" in res.data.decode().upper()
        # single-session export
        res2 = client.get(f"/api/chat-archive/export-server?format=json&session={conv['id']}")
        assert res2.status_code == 200
        parsed = json.loads(res2.data)
        assert parsed["sessions"][0]["title"] == "Server conv"

    def test_export_server_unknown_session_404(self, client):
        res = client.get("/api/chat-archive/export-server?format=json&session=nope")
        assert res.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# API — import
# ─────────────────────────────────────────────────────────────────────────────

def _upload(client, filename, data):
    return client.post(
        "/api/chat-archive/import",
        data={"file": (io.BytesIO(data), filename)},
        content_type="multipart/form-data",
    )


class TestImportAPI:
    def test_import_orbit_json(self, client, app):
        payload = {
            "sessions": [
                {"title": "Trip talk", "messages": [
                    {"role": "user", "content": "book tickets"},
                    {"role": "agent", "content": "done"},
                ]},
                {"title": "Recipe", "messages": [
                    {"role": "user", "content": "pasta?"},
                    {"role": "assistant", "content": "boil water"},
                ]},
            ]
        }
        res = _upload(client, "archive.json", json.dumps(payload).encode())
        assert res.status_code == 200
        body = res.get_json()
        assert body["ok"] is True
        assert body["source"] == "orbit"
        assert body["conversations"] == 2
        assert body["messages"] == 4
        assert body["memories"] == 2
        assert "Trip talk" in body["titles"]

        mgr = app.extensions["mgr"]
        convs = mgr.list_all()
        assert len(convs) == 2
        full = mgr.get(convs[0]["id"])
        assert full["messages"][0]["role"] in ("user", "assistant")

        mem = app.extensions["mem"]
        assert len(mem.calls) == 2
        assert mem.calls[0]["category"] == "conversation"
        assert mem.calls[0]["source"] == "import:orbit"
        assert "Trip talk" in mem.calls[0]["content"]
        assert "book tickets" in mem.calls[0]["content"]

    def test_import_chatgpt_zip(self, client):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("conversations.json", json.dumps([CHATGPT_CONV]))
        res = _upload(client, "chatgpt.zip", buf.getvalue())
        assert res.status_code == 200
        body = res.get_json()
        assert body["source"] == "chatgpt"
        assert body["conversations"] == 1
        assert body["messages"] == 2

    def test_import_markdown(self, client):
        res = _upload(client, "log.md", b"**You**: hey\n**ORBIT**: hi")
        assert res.status_code == 200
        assert res.get_json()["source"] == "markdown"
        assert res.get_json()["messages"] == 2

    def test_import_no_file_400(self, client):
        res = client.post("/api/chat-archive/import", json={})
        assert res.status_code == 400

    def test_import_bad_extension_400(self, client):
        res = _upload(client, "evil.exe", b"MZ...")
        assert res.status_code == 400
        assert "Unsupported" in res.get_json()["error"]

    def test_import_empty_file_400(self, client):
        res = _upload(client, "empty.json", b"")
        assert res.status_code == 400

    def test_import_oversize_413(self, client, monkeypatch):
        monkeypatch.setattr(cab, "MAX_IMPORT_SIZE", 64)
        res = _upload(client, "big.json", b"x" * 100)
        assert res.status_code == 413

    def test_import_invalid_json_400(self, client):
        res = _upload(client, "broken.json", b"{nope")
        assert res.status_code == 400
        assert "error" in res.get_json()

    def test_import_updates_stats(self, client, app):
        payload = {"sessions": [{"title": "T", "messages": [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
        ]}]}
        client.post(
            "/api/chat-archive/import",
            data={"file": (io.BytesIO(json.dumps(payload).encode()), "a.json")},
            content_type="multipart/form-data",
        )
        stats = client.get("/api/chat-archive/status").get_json()["stats"]
        assert stats["imports"] == 1
        assert stats["conversations_imported"] == 1
        assert stats["messages_imported"] == 2
        assert stats["memories_added"] == 1
        assert stats["last_import"]

    def test_status_shape(self, client):
        body = client.get("/api/chat-archive/status").get_json()
        assert body["formats"] == ["html", "json", "md", "txt"]
        assert "chatgpt" in body["sources"]
        assert body["limits"]["max_import_mb"] == 25
