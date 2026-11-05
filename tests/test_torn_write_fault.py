"""Phase 22 - torn-write fault injection.

A crash/kill between truncate and write-complete leaves a JSON state file
half-written; the next _load then silently resets user data.  Atomic saves
(tmp file + os.replace) must keep the OLD bytes intact when the final
replace fails.

Contains:
  * a static class lock: no direct-overwrite state save anywhere in orbit/
  * behavioural tests that block os.replace and assert old state survives
"""

import ast
import os
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]

# --------------------------------------------------------------------------
# Static class lock - mirrors the phase 22 scanner
# --------------------------------------------------------------------------

# Deliberate non-atomic writes (triage, phase 22):
#   stress_test      - contention test/harness report by design
#   server.readyz    - readiness probe (kept from phase 19)
#   code_interpreter - sandbox IPC handoff (transient per-call files)
#   tokens/_fernet   - chmod 0600 one-shot boot key files
#   apply_update     - binary artifact lifecycle
_SKIP = {
    ("orbit/orbit/core/stress_test.py", None),
    ("orbit/orbit/server.py", "readyz"),
    ("orbit/orbit/server.py", "_data_dir"),  # nested readiness probe inside readyz
    ("orbit/orbit/core/code_interpreter.py", "_run_sandboxed"),
    ("orbit/orbit/core/auth/tokens.py", "_secret"),
    ("orbit/orbit/core/provider_keys.py", "_fernet"),
    ("orbit/orbit/core/auto_updater.py", "apply_update"),
}
_ATOMIC_HELPERS = ("atomic_write_text", "atomic_write_json", "atomic_write")
_SKIP_DIRS = {"__pycache__", "node_modules", "dist", ".git", ".venv", "venv"}


def _classify(call: ast.Call):
    """Return (kind, target) for a truncating overwrite call, else None."""
    func = call.func
    name = func.id if isinstance(func, ast.Name) else (
        func.attr if isinstance(func, ast.Attribute) else None
    )
    if name is None:
        return None
    kws = {k.arg: k.value for k in call.keywords if k.arg}
    pos = call.args
    if name == "open" and not isinstance(func, ast.Attribute):
        mode = None
        if len(pos) >= 2 and isinstance(pos[1], ast.Constant) and isinstance(pos[1].value, str):
            mode = pos[1].value
        if "mode" in kws and isinstance(kws["mode"], ast.Constant) and isinstance(kws["mode"].value, str):
            mode = kws["mode"].value
        mode = mode or "r"
        if "w" not in mode:
            return None
        target = pos[0] if pos else kws.get("file")
        return ("open-w", ast.unparse(target) if target else "?")
    if name == "write_text":
        return ("write_text", ast.unparse(func.value))
    if name == "write_bytes":
        return ("write_bytes", ast.unparse(func.value))
    return None


def _skipped_fn(rel: str, node) -> bool:
    for f, n in _SKIP:
        if rel == f and (n is None or n == node.name):
            return True
    seg = ast.unparse(node)
    if ".replace(" in seg or "os.replace" in seg:
        return True
    if any(h in seg for h in _ATOMIC_HELPERS):
        return True
    return False


def _scan_violations():
    violations = []
    for p in sorted((REPO / "orbit").rglob("*.py")):
        if any(x in p.parts for x in _SKIP_DIRS):
            continue
        rel = p.relative_to(REPO).as_posix()
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if _skipped_fn(rel, node):
                continue
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    c = _classify(sub)
                    if c:
                        violations.append(
                            f"{rel}:{sub.lineno} {node.name}() {c[0]} -> {c[1][:60]}"
                        )
    return violations


def test_no_direct_overwrite_state_saves():
    violations = _scan_violations()
    assert not violations, (
        "direct-overwrite state saves found (use tmp+os.replace):\n"
        + "\n".join(violations)
    )


# --------------------------------------------------------------------------
# Behavioural tests - block the final os.replace, old bytes must survive
# --------------------------------------------------------------------------

def _boom_replace(src, dst):  # noqa: ARG001
    raise OSError("disk full (phase22)")


def _assert_atomic_save(monkeypatch, target: pathlib.Path, save_fn):
    target.parent.mkdir(parents=True, exist_ok=True)
    seed = '{"seeded": "old-state"}'
    target.write_text(seed, encoding="utf-8")

    # 1) normal save must still rewrite the target with fresh state
    save_fn()
    updated = target.read_text(encoding="utf-8")
    assert updated != seed, "normal save did not rewrite target"

    # 2) replace blocked -> previous bytes must survive untouched
    target.write_text(seed, encoding="utf-8")
    monkeypatch.setattr(os, "replace", _boom_replace)
    try:
        save_fn()
    except OSError:
        pass  # some stores let it propagate; corruption is what matters
    assert target.read_text(encoding="utf-8") == seed, (
        "target lost or corrupted old state when final replace failed"
    )


def test_calendar_save_is_atomic(tmp_path, monkeypatch):
    from orbit.orbit.tools.calendar_tool import CalendarTool

    target = tmp_path / "calendar.json"
    tool = CalendarTool(storage_file=str(target))
    _assert_atomic_save(monkeypatch, target, tool._save)


def test_billing_users_save_is_atomic(tmp_path, monkeypatch):
    from orbit.orbit.core.billing import BillingManager

    target = tmp_path / "users.json"
    manager = BillingManager(data_dir=str(tmp_path))
    _assert_atomic_save(monkeypatch, target, manager._save_users)


def test_task_tracker_save_is_atomic(tmp_path, monkeypatch):
    from orbit.orbit.core.task_tracker import TaskTracker

    target = tmp_path / "tasks.json"
    tracker = TaskTracker(storage_dir=str(tmp_path))
    _assert_atomic_save(monkeypatch, target, tracker._save)


def test_file_tools_write_is_atomic(tmp_path, monkeypatch):
    from orbit.orbit.tools.file_tools import FileTools

    monkeypatch.setattr(FileTools, "_gate", lambda *a, **k: None)
    target = tmp_path / "note.txt"
    tools = FileTools()
    outputs = []

    def save_fn():
        outputs.append(tools.write(str(target), "fresh-content"))

    _assert_atomic_save(monkeypatch, target, save_fn)
    assert outputs[0].get("success"), outputs[0]
    assert "error" in outputs[-1], outputs[-1]  # graceful failure on torn write


def test_file_tools_append_is_atomic(tmp_path, monkeypatch):
    from orbit.orbit.tools.file_tools import FileTools

    monkeypatch.setattr(FileTools, "_gate", lambda *a, **k: None)
    target = tmp_path / "log.txt"
    tools = FileTools()
    target.write_text("line1", encoding="utf-8")

    # normal append works (separator + trailing newline by design)
    out = tools.append(str(target), "line2")
    assert "error" not in out, out
    assert target.read_text(encoding="utf-8") == "line1\nline2\n"

    # replace blocked -> old single-line content must survive
    target.write_text("line1", encoding="utf-8")
    monkeypatch.setattr(os, "replace", _boom_replace)
    torn_out = tools.append(str(target), "line3")
    assert "error" in torn_out, torn_out
    assert target.read_text(encoding="utf-8") == "line1", (
        "append corrupted target when final replace failed"
    )


def test_task_manager_rewrite_is_atomic(tmp_path, monkeypatch):
    from orbit.orbit.core.a2a.task_manager import TaskManager

    target = tmp_path / "tasks.jsonl"
    manager = TaskManager(storage=target)
    _assert_atomic_save(monkeypatch, target, manager._rewrite)


def test_alert_system_save_is_atomic(tmp_path, monkeypatch):
    from orbit.orbit.core.alert_system import AlertSystem

    target = tmp_path / "alerts.json"
    system = AlertSystem(storage_file=str(target))
    _assert_atomic_save(monkeypatch, target, system._save_alerts)


def test_agent_awareness_save_is_atomic(tmp_path, monkeypatch):
    from orbit.orbit.core import agent_awareness as aa_mod

    monkeypatch.setattr(aa_mod, "DATA_DIR", tmp_path)
    target = tmp_path / "journals.json"
    manager = aa_mod.AgentAwarenessManager()
    _assert_atomic_save(monkeypatch, target, manager._save)


def test_quick_notes_save_is_atomic(tmp_path, monkeypatch):
    from orbit.orbit.core import quick_notes as qn_mod

    monkeypatch.setattr(qn_mod, "DATA_DIR", tmp_path)
    target = tmp_path / "notes.json"
    notes = qn_mod.QuickNotes()
    _assert_atomic_save(monkeypatch, target, notes._save)
