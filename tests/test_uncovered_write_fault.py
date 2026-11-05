"""Phase 19 - crash-axis fault injection: unguarded non-_save write sites.

Static scan (same write-receiver matcher as Phases 17/18, excluding _save /
save / export-family fns): 28 unguarded write sites; triage dropped 4
false-positives (webbrowser.open attr FP, server readiness probe, contained
code_interpreter write, fail-loud ZipSlip guard) leaving 24 genuine sites
across 19 files.

Fix: statement/fn-level try / except OSError with log + safe failure signal
(return False / error-dict / continue) - each site keeps its functional
contract while no longer raising on disk-full.

Fault model: OSError("disk full (phase19)") raised at WRITE-mode opens only
(reads pass through) - pre-fix each call raises out of the caller
(stash-verifiable), post-fix it logs (or prints) the injected error.
"""
import base64
import builtins
import importlib.util
import io
import json
import logging
import pathlib
import sys
import tempfile
import types
from types import SimpleNamespace

_PHASE = "disk full (phase19)"


def _explode_writes(monkeypatch):
    real_builtins_open = builtins.open
    real_io_open = io.open
    real_path_open = pathlib.Path.open

    def _make_boom(real):
        def boom(*args, **kwargs):
            mode = kwargs.get("mode")
            if mode is None and len(args) >= 2 and isinstance(args[1], str):
                mode = args[1]
            mode = mode or "r"
            if any(c in mode for c in "wax+"):
                raise OSError(_PHASE)
            return real(*args, **kwargs)

        return boom

    monkeypatch.setattr(builtins, "open", _make_boom(real_builtins_open))
    monkeypatch.setattr(io, "open", _make_boom(real_io_open))
    monkeypatch.setattr(pathlib.Path, "open", _make_boom(real_path_open))


def _explode_writes_except(monkeypatch, allowed_paths):
    """Explode write-mode opens except targets under any allowed path."""
    real_builtins_open = builtins.open
    real_io_open = io.open
    real_path_open = pathlib.Path.open
    allowed = [str(p) for p in allowed_paths]

    def _is_allowed(args, kwargs):
        target = kwargs.get("file")
        if target is None and args:
            target = args[0]
        if target is None:
            return False
        text = str(target)
        return any(text.startswith(prefix) for prefix in allowed)

    def _make_boom(real):
        def boom(*args, **kwargs):
            mode = kwargs.get("mode")
            if mode is None and len(args) >= 2 and isinstance(args[1], str):
                mode = args[1]
            mode = mode or "r"
            if any(c in mode for c in "wax+") and not _is_allowed(args, kwargs):
                raise OSError(_PHASE)
            return real(*args, **kwargs)

        return boom

    monkeypatch.setattr(builtins, "open", _make_boom(real_builtins_open))
    monkeypatch.setattr(io, "open", _make_boom(real_io_open))
    monkeypatch.setattr(pathlib.Path, "open", _make_boom(real_path_open))


def _messages(caplog, minlevel):
    return [r.getMessage() for r in caplog.records if r.levelno >= minlevel]


def _assert_logged(caplog, snippet, minlevel=logging.ERROR):
    messages = _messages(caplog, minlevel)
    hits = [m for m in messages if snippet in m and _PHASE in m]
    assert hits, (
        f"write failure CRASHED or never reached the write - no log with "
        f"{snippet!r} + {_PHASE!r}; got: {messages}"
    )


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_a2a_task_append_write_crash(tmp_path, monkeypatch, caplog):
    from orbit.orbit.core.a2a.models import Task
    from orbit.orbit.core.a2a.task_manager import TaskManager

    tm = TaskManager(storage=str(tmp_path / "tasks.jsonl"))
    _explode_writes(monkeypatch)
    with caplog.at_level(logging.ERROR):
        assert tm._append(Task()) is False
    _assert_logged(caplog, "A2A task append persistence failed")


def test_a2a_task_rewrite_write_crash(tmp_path, monkeypatch, caplog):
    from orbit.orbit.core.a2a.task_manager import TaskManager

    tm = TaskManager(storage=str(tmp_path / "tasks.jsonl"))
    _explode_writes(monkeypatch)
    with caplog.at_level(logging.ERROR):
        assert tm._rewrite() is False
    _assert_logged(caplog, "A2A task rewrite persistence failed")


def test_adaptive_cooldown_write_crash(tmp_path, monkeypatch, caplog):
    from orbit.orbit.core.adaptive_rate_limiter import AdaptiveRateLimiter

    lr = AdaptiveRateLimiter(data_dir=tmp_path)
    _explode_writes(monkeypatch)
    with caplog.at_level(logging.ERROR):
        lr.record_request("openrouter", False)
    _assert_logged(caplog, "cooldown file persistence failed")


def test_boot_report_persist_write_crash(tmp_path, monkeypatch, caplog):
    from orbit.orbit.core.boot_report import BootReport

    br = BootReport()
    _explode_writes(monkeypatch)
    with caplog.at_level(logging.ERROR):
        report = br.generate_report()
    assert isinstance(report, dict) and report.get("id")
    _assert_logged(caplog, "boot report persistence failed")


def test_image_dalle_write_crash(tmp_path, monkeypatch, caplog):
    import urllib.request

    from orbit.orbit.core.image_generator import ImageGenerator, ImageRequest

    gen = ImageGenerator()
    gen._openai_key = "sk-test"
    gen._output_dir = tmp_path / "imgs"
    gen._output_dir.mkdir()
    payload = json.dumps(
        {"data": [{"b64_json": base64.b64encode(b"PNG").decode()}]}
    ).encode()
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Resp(payload))
    _explode_writes(monkeypatch)
    with caplog.at_level(logging.ERROR):
        res = gen._generate_dalle3(ImageRequest(prompt="a cat"))
    assert not res.error and not res.images
    _assert_logged(caplog, "DALL-E image persistence failed")


def test_image_flux_write_crash(tmp_path, monkeypatch, caplog):
    import urllib.request

    from orbit.orbit.core.image_generator import ImageGenerator, ImageRequest

    gen = ImageGenerator()
    gen._replicate_key = "tok"
    gen._output_dir = tmp_path / "imgs"
    gen._output_dir.mkdir()
    gen._validate_image_url = lambda url: True
    create = _Resp(
        json.dumps(
            {"id": "pred1", "status": "succeeded", "output": ["http://x/img.png"]}
        ).encode()
    )
    download = _Resp(b"PNGDATA")
    calls = iter([create, download])
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: next(calls))
    _explode_writes(monkeypatch)
    with caplog.at_level(logging.ERROR):
        res = gen._generate_flux(ImageRequest(prompt="a cat"))
    assert not res.error and not res.images
    _assert_logged(caplog, "Flux image persistence failed")


def test_mobile_task_output_write_crash(tmp_path, monkeypatch, caplog):
    import orbit.orbit.core.mobile_api as ma

    monkeypatch.setattr(ma, "DATA_DIR", tmp_path)
    api = ma.MobileAPI()
    _explode_writes(monkeypatch)
    with caplog.at_level(logging.ERROR):
        assert api.submit_task_output("dev1", "task1", {"ok": True}) is False
    _assert_logged(caplog, "task output persistence failed")


def test_permission_log_write_crash(tmp_path, monkeypatch, caplog):
    from orbit.orbit.core.permission import PermissionManager

    pm = PermissionManager(log_file=str(tmp_path / "perm.json"))
    _explode_writes(monkeypatch)
    with caplog.at_level(logging.ERROR):
        entries = pm._write_log_unlocked([{"action": "test", "ts": 1}])
    assert entries == [{"action": "test", "ts": 1}]
    _assert_logged(caplog, "permission log persistence failed")


def test_provider_vault_key_write_crash(tmp_path, monkeypatch, caplog):
    import orbit.orbit.core.provider_keys as pk

    monkeypatch.setattr(pk, "_VAULT_DIR", tmp_path)
    monkeypatch.setattr(pk, "_KEY_FILE", tmp_path / ".vault.key")
    _explode_writes(monkeypatch)
    with caplog.at_level(logging.WARNING):
        key = pk._fernet()
    assert key is not None
    _assert_logged(caplog, "vault key persistence failed", logging.WARNING)


def test_remote_install_write_crash(tmp_path, monkeypatch, caplog):
    import orbit.orbit.core.policy_engine as pe
    from orbit.orbit.core.remote_skill_marketplace import RemoteSkillMarketplace

    market = RemoteSkillMarketplace()
    monkeypatch.setenv("ORBIT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        pe,
        "get_policy_engine",
        lambda: SimpleNamespace(
            check=lambda *a, **k: SimpleNamespace(allowed=True, reason="")
        ),
    )
    monkeypatch.setattr(
        market,
        "get_skill",
        lambda sid: {
            "code": "def run(**kwargs):\n    return {}",
            "name": sid,
            "version": "1.0.0",
            "source": "test",
        },
    )
    _explode_writes(monkeypatch)
    with caplog.at_level(logging.ERROR):
        out = market.install("p19_test")
    assert "Failed to write skill file" in out.get("error", "")
    _assert_logged(caplog, "skill file persistence failed")


def test_security_default_key_write_crash(tmp_path, monkeypatch, caplog):
    import orbit.orbit.core.security_hardening as sh_mod

    monkeypatch.setattr(sh_mod, "DATA_DIR", tmp_path)
    sh = sh_mod.SecurityHardening()
    (tmp_path / "api_keys.json").unlink(missing_ok=True)
    sh._api_keys = {}
    _explode_writes(monkeypatch)
    with caplog.at_level(logging.ERROR):
        sh._generate_default_key()
    assert sh._api_keys.get("default")
    _assert_logged(caplog, "api key persistence failed")


def test_self_extend_validation_write_crash(tmp_path, monkeypatch):
    import orbit.orbit.core.llm.router as router_mod
    import orbit.orbit.core.self_extend as se

    monkeypatch.setattr(
        router_mod,
        "get_router",
        lambda: SimpleNamespace(generate=lambda req: None),
        raising=False,
    )
    monkeypatch.setattr(
        se,
        "run_llm_sync",
        lambda x: SimpleNamespace(
            success=True, content="def run(**kwargs):\n    return {}"
        ),
    )
    _explode_writes(monkeypatch)
    out = se.propose("a new tool", name="p19tool")
    assert out["ok"] is False
    assert "validation write failed" in out["error"]
    assert _PHASE in out["error"]


def test_self_extend_staging_write_crash(tmp_path, monkeypatch):
    import orbit.orbit.core.llm.router as router_mod
    import orbit.orbit.core.self_extend as se

    monkeypatch.setattr(
        router_mod,
        "get_router",
        lambda: SimpleNamespace(generate=lambda req: None),
        raising=False,
    )
    monkeypatch.setattr(
        se,
        "run_llm_sync",
        lambda x: SimpleNamespace(
            success=True, content="def run(**kwargs):\n    return {}"
        ),
    )
    # pin the validation mkdtemp dir; only THAT path may write - the staging
    # dest explodes even if a leaked env var relocates it (full-suite parity)
    vtmp = tmp_path / "vtmp"

    def _fake_mkdtemp(*args, **kwargs):
        vtmp.mkdir(parents=True, exist_ok=True)
        return str(vtmp)

    monkeypatch.setattr(tempfile, "mkdtemp", _fake_mkdtemp)
    # pin the staging dest OUTSIDE the allowlist: it must always explode
    monkeypatch.setattr(se, "_proposed_dir", lambda: str(tmp_path / "proposed"))
    _explode_writes_except(monkeypatch, [vtmp])
    out = se.propose("a new tool", name="p19tool")
    assert out["ok"] is False
    assert "proposal staging failed" in out["error"]
    assert _PHASE in out["error"]


def test_skills_builtin_create_write_crash(tmp_path, monkeypatch, caplog):
    import orbit.orbit.core.skills_marketplace as skm

    m = skm.SkillsMarketplace()
    monkeypatch.setattr(skm, "PLUGINS_DIR", tmp_path / "plugins")
    skill = skm.Skill(
        id="newp",
        name="NewP",
        description="d",
        version="1.0.0",
        author="a",
        category="general",
        filename="newp.py",
    )
    _explode_writes(monkeypatch)
    with caplog.at_level(logging.ERROR):
        m._create_builtin_plugin(skill)
    _assert_logged(caplog, "builtin plugin persistence failed")


def test_skills_builtin_upgrade_write_crash(tmp_path, monkeypatch, caplog):
    import orbit.orbit.core.skills_marketplace as skm

    m = skm.SkillsMarketplace()
    monkeypatch.setattr(skm, "PLUGINS_DIR", tmp_path / "plugins")
    (tmp_path / "plugins").mkdir()
    (tmp_path / "plugins" / "t.py").write_text(
        '"""x"""\n# {"status": "ready"}\n', encoding="utf-8"
    )
    skill = skm.Skill(
        id="t",
        name="T",
        description="d",
        version="1.0.0",
        author="a",
        category="general",
        filename="t.py",
    )
    _explode_writes(monkeypatch)
    with caplog.at_level(logging.ERROR):
        m._create_builtin_plugin(skill)
    _assert_logged(caplog, "builtin plugin upgrade persistence failed")


def test_skills_install_write_crash(tmp_path, monkeypatch, caplog):
    import orbit.orbit.core.skills_marketplace as skm

    monkeypatch.setattr(skm, "PLUGINS_DIR", tmp_path / "plugins")
    _explode_writes(monkeypatch)
    with caplog.at_level(logging.ERROR):
        m = skm.SkillsMarketplace()
        out = m.install("p19_stub", name="Stub")
    assert "Failed to write plugin file" in out.get("error", "")
    assert "p19_stub" not in m._registry
    _assert_logged(caplog, "skill plugin persistence failed")


def test_token_secret_write_crash(tmp_path, monkeypatch, caplog):
    from orbit.orbit.core.token_manager import TokenManager

    storage = tmp_path / "tok.json"
    tm = TokenManager(storage_file=str(storage))
    key_file = tmp_path / ".token_secret"
    assert key_file.exists()
    key_file.unlink()
    _explode_writes(monkeypatch)
    with caplog.at_level(logging.WARNING):
        key = tm._generate_secret_key()
    assert key and len(key) == 64
    _assert_logged(caplog, "token secret persistence failed", logging.WARNING)


def test_watchdog_lock_write_crash(tmp_path, monkeypatch, caplog):
    from orbit.orbit.core.watchdog import ProcessLockManager

    m = ProcessLockManager(lock_dir=tmp_path / "locks")
    _explode_writes(monkeypatch)
    with caplog.at_level(logging.ERROR):
        ok = m.acquire("p19_resource", component="test")
    assert ok
    _assert_logged(caplog, "lock file persistence failed")


def test_setup_kokoro_write_crash(tmp_path, monkeypatch, capsys):
    import orbit.orbit.launcher.setup_jarvis_voice as sjv

    monkeypatch.setattr(sjv, "PREFS_FILE", tmp_path / "orbit_prefs.json")
    _explode_writes(monkeypatch)
    assert sjv.enable_kokoro() is False
    out, _ = capsys.readouterr()
    assert "Failed to save voice prefs" in out and _PHASE in out


def test_wake_metadata_write_crash(tmp_path, monkeypatch, caplog):
    from orbit.orbit.wake_word import generate_wake_word_data

    _explode_writes(monkeypatch)
    with caplog.at_level(logging.ERROR):
        meta = generate_wake_word_data(
            wake_phrase="hey orbit",
            output_dir=str(tmp_path / "wt"),
            num_samples=0,
            duration_sec=0.5,
        )
    assert meta["positive_samples"] == 0
    _assert_logged(caplog, "wake training metadata persistence failed")


def test_server_placeholder_write_crash(monkeypatch, caplog):
    import orbit.orbit.core.runtime_paths as rp
    import orbit.orbit.server as server_mod

    monkeypatch.setattr(rp, "frontend_dist", lambda: pathlib.Path("no_such_dist_p19"))
    _explode_writes(monkeypatch)
    with caplog.at_level(logging.WARNING):
        app = server_mod.create_app()
    assert app is not None
    _assert_logged(caplog, "placeholder index.html persistence failed", logging.WARNING)


def test_server_flask_secret_write_crash(monkeypatch, caplog):
    import orbit.orbit.core.runtime_paths as rp
    import orbit.orbit.server as server_mod

    monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)
    monkeypatch.setattr(rp, "frontend_dist", lambda: pathlib.Path("no_such_dist_p19"))
    real_exists = pathlib.Path.exists

    def lying_exists(self, *args, **kwargs):
        if self.name == ".flask_secret":
            return False
        return real_exists(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "exists", lying_exists)
    _explode_writes(monkeypatch)
    with caplog.at_level(logging.WARNING):
        app = server_mod.create_app()
    assert app is not None
    _assert_logged(caplog, "flask secret persistence failed", logging.WARNING)


def _load_script_module(name, rel_path):
    root = pathlib.Path(__file__).resolve().parent.parent
    path = root / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_auto_review_summary_write_crash(tmp_path, monkeypatch, capsys):
    mod = _load_script_module("auto_review_p19", "orbit/scripts/auto_review.py")
    monkeypatch.setattr(mod, "REPORT_PATH", tmp_path / "reports")
    monkeypatch.setattr(mod, "check_git_changes", lambda: ["M orbit/orbit/x.py"])

    fake_pkg = types.ModuleType("scripts")
    fake_pkg.__path__ = []
    fake_mod = types.ModuleType("scripts.code_review")

    class FakeReviewer:
        def run_all_checks(self):
            return {"files_checked": 0}

    fake_mod.CodeReviewer = FakeReviewer
    fake_pkg.code_review = fake_mod
    monkeypatch.setitem(sys.modules, "scripts", fake_pkg)
    monkeypatch.setitem(sys.modules, "scripts.code_review", fake_mod)

    _explode_writes(monkeypatch)
    report = mod.run_review()
    assert report == {"files_checked": 0}
    out, _ = capsys.readouterr()
    assert "Failed to save review summary" in out and _PHASE in out


def test_code_review_report_write_crash(tmp_path, monkeypatch, capsys):
    mod = _load_script_module("code_review_p19", "orbit/scripts/code_review.py")
    monkeypatch.setattr(mod, "REPORT_PATH", tmp_path / "reports")
    (tmp_path / "reports").mkdir()
    reviewer = mod.CodeReviewer()
    _explode_writes(monkeypatch)
    reviewer.generate_report()
    out, _ = capsys.readouterr()
    assert "Failed to save review report" in out and _PHASE in out
