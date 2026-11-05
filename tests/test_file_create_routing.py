"""Regression tests: file-create routing via SmartRouter + TaskAgent.

Fixes a real gap: "write file 'path' with 'content'" commands fell through
to the LLM (which narrates instead of calling the tool) because SmartRouter
had no file-create TOOL_PATTERN and the message was >60 chars. Now the
command is routed deterministically to TaskAgent which invokes FileTools.
"""


def _route(text):
    from orbit.orbit.core.smart_router import auto_route

    return auto_route(text)


def test_write_file_routes_to_tas():
    r = _route("write file 'notes.txt' with 'hello'")
    assert r.is_tool_command is True
    assert r.best_agent() == "TAS"
    assert r.intent == "file"


def test_create_file_routes_to_tas():
    r = _route("create file 'todo.txt' with '- a\n- b'")
    assert r.is_tool_command is True
    assert r.best_agent() == "TAS"
    assert r.intent == "file"


def test_save_to_file_routes_to_tas():
    r = _route("save to file 'out.md' with '# Title'")
    assert r.is_tool_command is True
    assert r.best_agent() == "TAS"
    assert r.intent == "file"


def test_task_agent_write_file_uses_tool(tmp_path, monkeypatch):
    """TaskAgent.write-file path returns a FileTools result dict, no LLM."""
    # ToolGate sandbox only allows writes inside the workspace (repo root),
    # so create the target file inside the repo and clean up afterwards.
    import os

    from orbit.orbit.agents.task_agents import TaskAgent

    target = os.path.abspath(os.path.join(os.getcwd(), "_file_create_test.txt"))
    try:
        agent = TaskAgent(assistant=object())
        text = f"write file '{target}' with 'hello world'"
        out = agent.execute(text)
        assert "success" in str(out) or "bytes_written" in str(out)
        assert os.path.exists(target)
        with open(target, encoding="utf-8") as f:
            assert f.read() == "hello world"
    finally:
        if os.path.exists(target):
            os.remove(target)


def test_task_agent_can_handle_file_intent():
    from orbit.orbit.agents.task_agents import TaskAgent

    agent = TaskAgent()
    assert agent.can_handle("write file 'x' with 'y'", intent="file") is True


def test_chat_api_routes_file_create_deterministically():
    """End-to-end: chat message -> TAS + tool, no LLM provider."""
    import pathlib

    from orbit.orbit.core.chat_api import _try_tool_execution

    text = "write file 'x.txt' with 'hello'"
    try:
        reply, tool = _try_tool_execution(text)
        assert reply is not None
        assert tool == "file"
    finally:
        # real tool execution writes x.txt into CWD - never leave it behind
        pathlib.Path("x.txt").unlink(missing_ok=True)
