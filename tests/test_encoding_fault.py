"""Phase 21 - encoding axis: encoding-less text IO on a cp1252-default OS.

Scan (positional-arg aware): 10 genuine sites - text-mode open()/
read_text()/write_text() with neither encoding kwarg nor positional
encoding. Windows default (locale.getpreferredencoding) = cp1252 with
utf8_mode=0 in normal runs: reads of UTF-8 files mojibake silently
(Hindi/emoji -> corrupted), non-ASCII writes with ensure_ascii=False raise
UnicodeEncodeError (crash). Note: the pytest suite runs under -X utf8 so
behavioral defaults differ here - these tests lock the CONTRACT instead:
each site must pass encoding="utf-8" explicitly (spy on builtins.open).

Also fixed earlier in this axis' survey: positional-encoding calls
(151) were false positives; Path.open() attribute form and io.open()
had zero unencoded text sites.
"""
import builtins
import importlib.util
import json
import sys
from types import SimpleNamespace


def _spy_text_open(monkeypatch, watch):
    """Record (path, mode, encoding) for text opens under watch paths."""
    real_open = builtins.open
    watched = [str(w) for w in watch]
    records = []

    def spy(file, *args, **kwargs):
        try:
            target = str(file)
        except Exception:
            target = ""
        if any(target == w or target.startswith(w) for w in watched):
            mode = kwargs.get("mode", "r")
            if args and isinstance(args[0], str):
                mode = args[0]
            encoding = kwargs.get("encoding")
            if encoding is None and len(args) >= 4:
                encoding = args[3]  # positional: file, mode, buffering, encoding
            records.append((target, mode, encoding))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy)
    return records


def _assert_utf8(records, needle):
    hits = [r for r in records if needle in r[0]]
    assert hits, f"target file {needle!r} was never opened (spy missed or branch skipped): {records}"
    for path, mode, encoding in hits:
        assert "b" not in mode, f"unexpected binary mode {mode!r} for {path}"
        assert encoding == "utf-8", (
            f"{path} opened with encoding={encoding!r} - locale default (cp1252) "
            f"means mojibake on read / UnicodeEncodeError on non-ASCII write"
        )


def _load_script_module(name, rel_path):
    root = __import__("pathlib").Path(__file__).resolve().parent.parent
    path = root / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_orbit_manager_log_and_version_reads_utf8(tmp_path, monkeypatch):
    from orbit.bot.orbit_manager import OrbitManagerBot

    bot = OrbitManagerBot()
    bot.orbit_path = tmp_path
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "app.log").write_text("\U0001f680 boot done\n", encoding="utf-8")
    (tmp_path / "__init__.py").write_text('__version__ = "9.9.9"\n', encoding="utf-8")

    records = _spy_text_open(monkeypatch, [tmp_path])
    out = bot.show_logs()
    assert "9.9.9" in bot.get_version()
    assert "\U0001f680" in out  # real utf-8 read, not cp1252 mojibake
    _assert_utf8(records, "app.log")
    _assert_utf8(records, "__init__.py")


def test_desktop_launch_prefs_read_utf8(monkeypatch):
    # pre-seed the launcher's odd `orbit.core.pform` import path (orbit/core
    # does not exist as a top-level package) and neutralize set_platform
    fake_pform = SimpleNamespace(PLATFORM_DESKTOP="desktop", set_platform=lambda x: None)
    monkeypatch.setitem(sys.modules, "orbit.core", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "orbit.core.pform", fake_pform)

    import pathlib as _pt

    pref = _pt.Path(__file__).resolve().parent.parent / "orbit" / "orbit" / "orbit_prefs.json"
    created = False
    if not pref.exists():
        pref.write_text(json.dumps({"tts_engine": "xtts"}), encoding="utf-8")
        created = True

    saved_sys_path = list(sys.path)
    try:
        mod = _load_script_module("desktop_launch_p21", "orbit/orbit/launcher/jarves_desktop-launch.py")
        records = _spy_text_open(monkeypatch, [pref])
        assert mod.test_desktop_gui() is True
        _assert_utf8(records, "orbit_prefs.json")
    finally:
        sys.path[:] = saved_sys_path
        if created:
            pref.unlink(missing_ok=True)


def test_code_completion_reads_utf8(tmp_path, monkeypatch):
    from orbit.orbit.tools.code_completion import CodeCompletionEngine

    src = tmp_path / "sample.py"
    src.write_text("# \u0939\u093f\u0902\u0926\u0940 comment\nimport os\ndef hello():\n    pass\n", encoding="utf-8")

    records = _spy_text_open(monkeypatch, [tmp_path])
    eng = CodeCompletionEngine()
    result = eng._analyze_file(str(src))
    assert "hello" in result.get("functions", [])
    _assert_utf8(records, "sample.py")


def test_mcp_config_read_utf8(tmp_path, monkeypatch):
    from orbit.orbit.tools.mcp_tool import MCPManager

    cfg = tmp_path / "mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")

    records = _spy_text_open(monkeypatch, [tmp_path])
    mgr = MCPManager()
    mgr.load_config(str(cfg))
    _assert_utf8(records, "mcp.json")


def test_n8n_config_roundtrip_utf8(tmp_path, monkeypatch):
    import orbit.orbit.tools.n8n as n8n_mod

    monkeypatch.setattr(n8n_mod, "app_root", lambda: tmp_path)
    cfg = tmp_path / "n8n_config.json"
    cfg.write_text(
        json.dumps({"n8n_url": "http://localhost:5678", "n8n_api_key": "k"}), encoding="utf-8"
    )

    records = _spy_text_open(monkeypatch, [tmp_path])
    tool = n8n_mod.N8nTool()  # ctor may load config too - both opens must be utf-8
    tool._load_config()
    tool.save_config(url="http://localhost:5678", api_key="k2")
    _assert_utf8(records, "n8n_config.json")


def test_auto_review_summary_write_utf8(tmp_path, monkeypatch):
    mod = _load_script_module("auto_review_p21", "orbit/scripts/auto_review.py")
    monkeypatch.setattr(mod, "REPORT_PATH", tmp_path / "reports")
    monkeypatch.setattr(mod, "check_git_changes", lambda: ["M orbit/orbit/core/x.py"])

    fake_pkg = SimpleNamespace(__path__=[])
    fake_mod = SimpleNamespace(CodeReviewer=type("R", (), {"run_all_checks": lambda s: {"ok": 1}}))
    fake_pkg.code_review = fake_mod
    monkeypatch.setitem(sys.modules, "scripts", fake_pkg)
    monkeypatch.setitem(sys.modules, "scripts.code_review", fake_mod)

    records = _spy_text_open(monkeypatch, [tmp_path])
    assert mod.run_review() == {"ok": 1}
    _assert_utf8(records, "latest_review.json")


def test_code_review_req_read_and_report_write_utf8(tmp_path, monkeypatch):
    mod = _load_script_module("code_review_p21", "orbit/scripts/code_review.py")
    monkeypatch.setattr(mod, "ORBIT_PATH", tmp_path)
    monkeypatch.setattr(mod, "REPORT_PATH", tmp_path / "reports")
    (tmp_path / "requirements.txt").write_text("requests>=2.0\n", encoding="utf-8")

    records = _spy_text_open(monkeypatch, [tmp_path])
    reviewer = mod.CodeReviewer()
    reviewer.check_dependencies()  # reads requirements.txt
    reviewer.generate_report()  # writes review_*.json
    _assert_utf8(records, "requirements.txt")
    _assert_utf8(records, "review_")
