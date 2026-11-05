"""Phase 20 - hang axis: blocking subprocess calls without deadlines.

Scan: 16 subprocess spawn sites without timeout kwarg. Triage: 9 are
Popen fire-and-forget / bounded-poll daemon spawns (no blocking wait - no
hang possible; code_interpreter already uses communicate(timeout=) and
mcp_tool joins its reader thread with a 10s deadline). Genuine hang risks
= 7 blocking calls (run/check_call) across 4 files.

Fix: subprocess timeout= deadline on every blocking call (pip installs
600s/1800s, git 30s, py_compile/ast 60s, ruff 180s, pip show 30s) +
graceful degradation where the call was previously unguarded (setup
pip installs catch TimeoutExpired/CalledProcessError; code_review
check_dependencies wraps per-package probes).
"""
import importlib.util
import pathlib
import subprocess
import sys
from types import SimpleNamespace


def _load_script_module(name, rel_path):
    root = pathlib.Path(__file__).resolve().parent.parent
    path = root / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _recorder(fake_calls, result=None):
    """Recording run() that never executes a child process."""

    def fake_run(cmd, *args, **kwargs):
        fake_calls.append({"cmd": cmd, **kwargs})
        if result is None:
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        return result

    return fake_run


def _raiser(fake_calls):
    def fake_run(cmd, *args, **kwargs):
        fake_calls.append({"cmd": cmd, **kwargs})
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 0))

    return fake_run


def test_setup_voice_installs_have_deadlines(monkeypatch, capsys):
    import orbit.orbit.launcher.setup_jarvis_voice as sjv

    calls = []
    monkeypatch.setitem(sys.modules, "kokoro", None)  # force ImportError -> install path
    monkeypatch.setitem(sys.modules, "torch", None)
    monkeypatch.setattr(
        sjv,
        "subprocess",
        SimpleNamespace(
            check_call=lambda cmd, **kw: calls.append({"cmd": cmd, **kw}) or 0,
            TimeoutExpired=subprocess.TimeoutExpired,
            CalledProcessError=subprocess.CalledProcessError,
        ),
    )
    sjv.check_deps()
    timeouts = [c["timeout"] for c in calls if "timeout" in c]
    assert timeouts == [600, 1800], f"pip installs missing deadlines: {calls}"


def test_setup_voice_installs_timeout_graceful(monkeypatch, capsys):
    import orbit.orbit.launcher.setup_jarvis_voice as sjv

    def boom(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kw.get("timeout", 0))

    monkeypatch.setitem(sys.modules, "kokoro", None)
    monkeypatch.setitem(sys.modules, "torch", None)
    monkeypatch.setattr(
        sjv,
        "subprocess",
        SimpleNamespace(
            check_call=boom,
            TimeoutExpired=subprocess.TimeoutExpired,
            CalledProcessError=subprocess.CalledProcessError,
        ),
    )
    sjv.check_deps()  # must not raise
    out, _ = capsys.readouterr()
    assert "Kokoro install failed" in out and "PyTorch install failed" in out


def test_auto_review_git_has_deadline():
    mod = _load_script_module("auto_review_p20", "orbit/scripts/auto_review.py")
    calls = []
    fake_ns = SimpleNamespace(
        run=_recorder(calls),
        TimeoutExpired=subprocess.TimeoutExpired,
    )
    try:
        mod.subprocess = fake_ns  # module-local swap (loaded fresh, not reused)
        mod.check_git_changes()
    finally:
        del mod.subprocess  # drop the local binding; module is throwaway
    assert calls and calls[0].get("timeout") == 30, f"git status missing deadline: {calls}"


def test_auto_review_git_timeout_graceful():
    mod = _load_script_module("auto_review_p20b", "orbit/scripts/auto_review.py")
    calls = []
    fake_ns = SimpleNamespace(run=_raiser(calls), TimeoutExpired=subprocess.TimeoutExpired)
    try:
        mod.subprocess = fake_ns
        assert mod.check_git_changes() == []
    finally:
        del mod.subprocess


def test_code_review_checks_have_deadlines(tmp_path, monkeypatch):
    mod = _load_script_module("code_review_p20", "orbit/scripts/code_review.py")
    monkeypatch.setattr(mod, "ORBIT_PATH", tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("requests>=2.0\n", encoding="utf-8")

    calls = []
    monkeypatch.setattr(
        mod,
        "subprocess",
        SimpleNamespace(run=_recorder(calls), TimeoutExpired=subprocess.TimeoutExpired),
    )
    reviewer = mod.CodeReviewer()
    reviewer.check_python_syntax()
    reviewer.check_imports()
    reviewer.check_code_quality()
    reviewer.check_dependencies()
    timeouts = [c.get("timeout") for c in calls]
    assert 60 in timeouts, f"py_compile/ast probes missing deadline: {calls}"
    assert 180 in timeouts, f"ruff probe missing deadline: {calls}"
    assert 30 in timeouts, f"pip show probe missing deadline: {calls}"
    assert None not in timeouts, f"one of the probes lost its deadline: {calls}"


def test_code_review_timeout_graceful(tmp_path, monkeypatch):
    mod = _load_script_module("code_review_p20b", "orbit/scripts/code_review.py")
    monkeypatch.setattr(mod, "ORBIT_PATH", tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("requests>=2.0\n", encoding="utf-8")

    calls = []
    monkeypatch.setattr(
        mod,
        "subprocess",
        SimpleNamespace(run=_raiser(calls), TimeoutExpired=subprocess.TimeoutExpired),
    )
    reviewer = mod.CodeReviewer()
    reviewer.run_all_checks()  # must not raise
    # timed-out pip probe recorded as check-failed, not as a missing package
    types_ = [w["type"] for w in reviewer.report["warnings"]]
    assert "package_check_failed" in types_, reviewer.report["warnings"]
    assert "missing_package" not in types_, "timeout must not count as missing dep"
