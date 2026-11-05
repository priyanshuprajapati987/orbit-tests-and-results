"""Phase 16 - subprocess/process fault injection (exit-status + spawn layer).

Static scan: 63 subprocess call sites / ~25 files, two-pass AST (spawn-axis:
stdout/returncode/communicate consumption vs enclosing handlers; parse-axis:
taint-propagation into json.loads/int/splitlines subscripts). Crash-coverage is
ALREADY thorough (85/86 covered - past hardening rounds wrapped almost every
site in `except Exception`), so the surviving class is ADEQUACY, not presence:

  "subprocess.run(check=False) NEVER raises on a failing command" - callers
  that ignore returncode fabricate success / keep dead fallbacks even though
  their try/except looks complete.

Genuine sites (16 / 3 files), all stash-verifiable:
  1. tools/github_tool.py - git_status/git_log/git_branches/git_diff always
     returned success=True (rc ignored) -> non-repo / missing-git (PyInstaller
     dist) reported as clean tree with 0 commits / 0 branches / empty diff
  2. core/commander.py (11 sites) - volume x4, brightness x2, power,
     screenshot, clipboard copy/paste/clear all returned CommandResult
     success=True without ever reading rc (helper _run_action added;
     screenshot additionally verifies the PNG was actually written because PS
     non-terminating errors exit 0)
  3. tts.py _play_mp3 - rc ignored -> the `except Exception -> _play_wav_fallback`
     path NEVER fired on PS refusal; playback silently did nothing

Triaged FALSE POSITIVES (kept as regression pins below):
  - naturo_tool L98/99 str-slice subscripts (text=True -> stderr always str)
  - code_interpreter Popen/returncode with NO inner handler - the CALLER
    execute() wraps _run_sandboxed in `except Exception` (cross-function)
  - security_guard git ls-files rc is inverted semantics (rc1 = no tracked
    env files = the honest [] answer)
  - voice_bp ffmpeg failure propagates to an outer except -> friendly 400

Graceful consumers are runtime-pinned (they pass WITH and WITHOUT the fixes -
that is the point: proof the existing `except Exception` coverage is adequate).
"""
import subprocess
from types import SimpleNamespace

import pytest

from orbit.orbit.core.commander import Commander
from orbit.orbit.core.dep_scanner import _run_cmd
from orbit.orbit.core.version import VersionSystem
from orbit.orbit.tools.github_tool import GITHUB_AVAILABLE, GitHubTool


def _ok(stdout="", stderr=""):
    return SimpleNamespace(returncode=0, stdout=stdout, stderr=stderr)


def _fail(rc=1, stdout="", stderr=""):
    return SimpleNamespace(returncode=rc, stdout=stdout, stderr=stderr)


def _raising(exc):
    def _r(*args, **kwargs):
        raise exc

    return _r


@pytest.fixture
def patch_run(monkeypatch):
    """Patch the stdlib subprocess.run (every module shares the object)."""
    calls = []

    def _install(fn):
        calls.append(fn)
        monkeypatch.setattr(subprocess, "run", fn)

    def _install_ok(rc=0, stdout="", stderr=""):
        _install(lambda *a, **k: SimpleNamespace(returncode=rc, stdout=stdout, stderr=stderr))

    return SimpleNamespace(install=_install, install_ok=_install_ok, calls=calls)


# ---------------------------------------------- fabricated-success: git (x4)
@pytest.mark.skipif(not GITHUB_AVAILABLE, reason="PyGithub not installed")
class TestGitExitStatus:
    def test_git_status_nonzero_exit_is_failure(self, patch_run):
        patch_run.install_fail = None
        patch_run.install(lambda *a, **k: _fail(rc=128, stderr="fatal: not a git repository"))
        result = GitHubTool(token="fake-token").git_status()
        assert result["success"] is False
        assert "not a git repository" in result["error"]

    def test_git_log_nonzero_exit_is_failure(self, patch_run):
        patch_run.install(lambda *a, **k: _fail(rc=128, stdout="", stderr="fatal: bad revision"))
        result = GitHubTool(token="fake-token").git_log()
        assert result["success"] is False
        assert "bad revision" in result["error"]

    def test_git_branches_nonzero_exit_is_failure(self, patch_run):
        patch_run.install(lambda *a, **k: _fail(rc=128, stderr="fatal: not a git repository"))
        result = GitHubTool(token="fake-token").git_branches()
        assert result["success"] is False

    def test_git_diff_nonzero_exit_is_failure(self, patch_run):
        patch_run.install(lambda *a, **k: _fail(rc=128, stderr="fatal: not a git repository"))
        result = GitHubTool(token="fake-token").git_diff()
        assert result["success"] is False

    def test_git_status_zero_exit_is_success(self, patch_run):
        patch_run.install_ok(stdout="M main.py\n")
        result = GitHubTool(token="fake-token").git_status()
        assert result["success"] is True
        assert "main.py" in result["status"]

    def test_git_status_missing_binary(self, patch_run):
        patch_run.install(_raising(FileNotFoundError("git")))
        result = GitHubTool(token="fake-token").git_status()
        assert result["success"] is False


# --------------------------------------- fabricated-success: commander (x11)
class TestCommanderExitStatus:
    def test_volume_up_nonzero_exit_is_failure(self, patch_run):
        patch_run.install(lambda *a, **k: _fail(rc=1, stderr="COM failure"))
        result = Commander()._volume("volume_up")
        assert result.success is False
        assert "COM failure" in result.message

    def test_volume_mute_spawn_failure(self, patch_run):
        patch_run.install(_raising(FileNotFoundError("powershell")))
        result = Commander()._volume("volume_mute")
        assert result.success is False

    def test_brightness_up_nonzero_exit_is_failure(self, patch_run):
        patch_run.install(lambda *a, **k: _fail(rc=1, stderr="WMI access denied"))
        result = Commander()._brightness("brightness_up")
        assert result.success is False
        assert "WMI access denied" in result.message

    def test_power_shutdown_nonzero_exit_is_failure(self, patch_run):
        patch_run.install(lambda *a, **k: _fail(rc=1, stderr="Access is denied"))
        result = Commander()._system_power("shutdown")
        assert result.success is False

    def test_power_shutdown_zero_exit_is_success(self, patch_run):
        patch_run.install_ok()
        result = Commander()._system_power("shutdown")
        assert result.success is True

    def test_clipboard_copy_nonzero_exit_is_failure(self, patch_run):
        patch_run.install(lambda *a, **k: _fail(rc=1, stderr="clipboard session error"))
        result = Commander()._clipboard_copy()
        assert result.success is False

    def test_clipboard_clear_nonzero_exit_is_failure(self, patch_run):
        patch_run.install(lambda *a, **k: _fail(rc=1, stderr="access denied"))
        result = Commander()._clipboard_clear()
        assert result.success is False

    def test_clipboard_paste_zero_exit_keeps_content(self, patch_run):
        patch_run.install_ok(stdout="hello clip")
        result = Commander()._clipboard_paste()
        assert result.success is True
        assert result.data["text"] == "hello clip"


class TestCommanderScreenshot:
    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch, tmp_path, patch_run):
        # Fall through to the PowerShell branch (capture_screen would short-circuit)
        import orbit.orbit.screen as screen_mod

        monkeypatch.setattr(screen_mod, "capture_screen", lambda *a, **k: None)
        monkeypatch.setattr("orbit.orbit.core.commander.orbit_data_dir", lambda: tmp_path)
        self._patch_run = patch_run

    def test_screenshot_nonzero_exit_is_failure(self):
        self._patch_run.install(lambda *a, **k: _fail(rc=1, stderr="drawing error"))
        result = Commander()._screenshot()
        assert result.success is False

    def test_screenshot_zero_exit_without_file_is_failure(self):
        # PS non-terminating errors exit 0 and write nothing - rc alone lies
        self._patch_run.install_ok(stdout="")
        result = Commander()._screenshot()
        assert result.success is False
        assert "not written" in result.message

    def test_screenshot_zero_exit_with_file_is_success(self):
        def _fake_run(cmd, **kwargs):
            # Emulate PS saving the file the command string asked for:
            # extract the path between single quotes in the Save('...') clause
            marker = "$bmp.Save('"
            for part in cmd:
                if marker in part:
                    seg = part.split(marker, 1)[1]
                    path = seg.split("')", 1)[0].replace("''", "'")
                    open(path, "wb").write(b"PNG")
                    break
            return _ok()

        self._patch_run.install(_fake_run)
        result = Commander()._screenshot()
        assert result.success is True


# --------------------------------------------- fabricated-success: tts (x1)
class TestTtsPlaybackFallback:
    def test_ps_failure_triggers_fallback(self, monkeypatch, tmp_path):
        import orbit.orbit.tts as tts

        fallbacks = []
        monkeypatch.setattr(tts, "_play_wav_fallback", lambda p: fallbacks.append(p))
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _fail(rc=1, stderr="MediaPlayer refused"))
        path = str(tmp_path / "out.mp3")
        tts._play_mp3(path)
        assert fallbacks == [path], "PS returned rc!=0 but wav fallback never ran"

    def test_ps_spawn_exception_triggers_fallback(self, monkeypatch, tmp_path):
        import orbit.orbit.tts as tts

        fallbacks = []
        monkeypatch.setattr(tts, "_play_wav_fallback", lambda p: fallbacks.append(p))
        monkeypatch.setattr(subprocess, "run", _raising(FileNotFoundError("powershell")))
        path = str(tmp_path / "out.mp3")
        tts._play_mp3(path)
        assert fallbacks == [path]

    def test_ps_success_does_not_fallback(self, monkeypatch, tmp_path):
        import orbit.orbit.tts as tts

        fallbacks = []
        monkeypatch.setattr(tts, "_play_wav_fallback", lambda p: fallbacks.append(p))
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _ok())
        tts._play_mp3(str(tmp_path / "out.mp3"))
        assert fallbacks == []


# ------------------------- graceful consumers (pass WITH and WITHOUT fixes)
class TestGracefulConsumers:
    def test_gpu_temp_missing_binary(self, patch_run):
        import orbit.orbit.system_monitor as sm

        patch_run.install(_raising(FileNotFoundError("nvidia-smi")))
        assert sm.get_gpu_temp() is None

    def test_gpu_temp_garbage_stdout(self, patch_run):
        import orbit.orbit.system_monitor as sm

        patch_run.install_ok(stdout="N/A\n")
        assert sm.get_gpu_temp() is None

    def test_gpu_temp_nonzero_exit(self, patch_run):
        import orbit.orbit.system_monitor as sm

        patch_run.install(lambda *a, **k: _fail(rc=1, stdout="75"))
        assert sm.get_gpu_temp() is None

    def test_gpu_name_spawn_failure(self, patch_run):
        import orbit.orbit.system_monitor as sm

        patch_run.install(_raising(FileNotFoundError("nvidia-smi")))
        assert sm.get_gpu_name() is None

    def test_wifi_list_networks_spawn_failure(self, patch_run):
        from orbit.orbit.core.wifi_manager import WiFiManager

        patch_run.install(_raising(FileNotFoundError("netsh")))
        out = WiFiManager().list_networks()
        assert isinstance(out, list) and out and "error" in out[0]

    def test_wifi_connect_reports_failed_without_success_token(self, patch_run):
        from orbit.orbit.core.wifi_manager import WiFiManager

        patch_run.install(lambda *a, **k: _fail(rc=1, stdout="Profile not found"))
        out = WiFiManager().connect("TestNet")
        assert out["status"] == "failed"

    def test_wifi_disconnect_spawn_failure(self, patch_run):
        from orbit.orbit.core.wifi_manager import WiFiManager

        patch_run.install(_raising(FileNotFoundError("netsh")))
        assert "error" in WiFiManager().disconnect()

    def test_gateway_spawn_failure_returns_empty(self, patch_run):
        import orbit.orbit.network as network

        patch_run.install(_raising(FileNotFoundError("powershell")))
        assert network.get_gateway() == ""

    def test_dns_garbage_stdout_does_not_raise(self, patch_run):
        import orbit.orbit.network as network

        patch_run.install_ok(stdout="\n\n")
        assert network.get_dns() == []

    def test_music_powershell_spawn_failure(self, patch_run):
        import orbit.orbit.music_ctrl as music

        patch_run.install(_raising(FileNotFoundError("powershell")))
        assert music._powershell("Get-Item") is None

    def test_naturo_nonzero_exit_returns_error_dict(self, patch_run):
        from orbit.orbit.naturo_tool import NaturoTool

        tool = NaturoTool()
        tool._available = True
        tool._naturo_path = "naturo"
        patch_run.install(lambda *a, **k: _fail(rc=2, stderr="unknown command"))
        out = tool._run(["status"])
        assert isinstance(out, dict) and out.get("error") == "unknown command"

    def test_naturo_garbage_json_returns_output_fallback(self, patch_run):
        from orbit.orbit.naturo_tool import NaturoTool

        tool = NaturoTool()
        tool._available = True
        tool._naturo_path = "naturo"
        patch_run.install_ok(stdout="not-json{{")
        out = tool._run(["status"])
        assert out == {"output": "not-json{{"}

    def test_naturo_missing_binary_disables_tool(self, patch_run):
        from orbit.orbit.naturo_tool import NaturoTool

        tool = NaturoTool()
        tool._available = True
        tool._naturo_path = "py -m naturo"
        patch_run.install(_raising(FileNotFoundError("py")))
        assert tool._run(["status"]) is None
        assert tool._available is False

    def test_cua_nonzero_exit_returns_error(self, monkeypatch, patch_run):
        import orbit.orbit.tools.cua_computer as cua

        monkeypatch.setattr(cua, "_get_binary", lambda: "cua-driver")
        # cua runs WITHOUT text=True -> stdout/stderr are bytes
        patch_run.install(lambda *a, **k: _fail(rc=3, stdout=b"", stderr=b"driver crashed"))
        out = cua._call_tool("click", {})
        assert "error" in out and "driver crashed" in out["error"]

    def test_cua_garbage_json_returns_error(self, monkeypatch, patch_run):
        import orbit.orbit.tools.cua_computer as cua

        monkeypatch.setattr(cua, "_get_binary", lambda: "cua-driver")
        patch_run.install_ok(stdout=b"garbage{}")
        out = cua._call_tool("click", {})
        assert "error" in out

    def test_code_integrator_pytest_missing(self, patch_run):
        from orbit.orbit.core.code_integrator import CodeIntegrator

        patch_run.install(_raising(FileNotFoundError("python")))
        out = CodeIntegrator()._run_tests(__file__)
        assert out == ["pytest not found"]

    def test_bugfixer_runner_failure_is_false(self, patch_run):
        from orbit.orbit.core.bugfixer import BugFixTestRunner

        patch_run.install(_raising(FileNotFoundError("python")))
        passed, output = BugFixTestRunner().run_tests(["tests/test_subprocess_fault.py"])
        assert passed is False
        assert "error" in output.lower()

    def test_version_git_hash_unknown_on_failure(self, patch_run):
        patch_run.install(_raising(FileNotFoundError("git")))
        assert VersionSystem()._get_git_hash() == "unknown"

    def test_auto_updater_short_sha_returns_empty(self, patch_run):
        from orbit.orbit.core.auto_updater import AutoUpdater

        patch_run.install_ok(stdout="abc123\n")
        assert AutoUpdater()._local_sha() == ""

    def test_security_guard_untracked_env_is_empty_list(self, patch_run):
        from orbit.orbit.core.security_guard import SecurityGuard

        patch_run.install(lambda *a, **k: _fail(rc=1, stdout=""))
        assert SecurityGuard()._git_tracked_env() == []

    def test_dep_scanner_missing_binary_maps_to_error_tuple(self, patch_run):
        patch_run.install(_raising(FileNotFoundError("nope")))
        out, err, rc = _run_cmd(["nope", "--version"])
        assert out == "" and rc == -1 and "command not found" in err

    def test_computer_powershell_timeout_is_graceful(self, patch_run):
        from orbit.orbit.tools.computer import ComputerTool

        patch_run.install(_raising(subprocess.TimeoutExpired(cmd="powershell", timeout=30)))
        out = ComputerTool()._run_powershell("Get-Clipboard")
        assert out["success"] is False and "timed out" in out["error"]


# --------------------------- cross-function coverage (scan GAPs were FPs)
class TestCrossFunctionCoverage:
    def test_code_interpreter_spawn_failure_is_caught_by_caller(self, monkeypatch, tmp_path):
        """Scan saw handlers=NONE at proc.returncode - but execute() wraps
        _run_sandboxed in except Exception, so nothing escapes."""
        from orbit.orbit.core.code_interpreter import CodeInterpreter

        ci = CodeInterpreter(storage_file=str(tmp_path / "interp.json"))
        monkeypatch.setattr(subprocess, "Popen", _raising(OSError("spawn refused")))
        result = ci.execute("1 + 1")
        assert result.status == "error"
        assert "spawn refused" in result.error

    def test_code_interpreter_nonzero_exit_is_error_status(self, monkeypatch, tmp_path):
        from orbit.orbit.core.code_interpreter import CodeInterpreter

        ci = CodeInterpreter(storage_file=str(tmp_path / "interp.json"))

        class _Proc:
            returncode = 3

            def communicate(self, *a, **k):
                return ("child output", "child failed")

            def kill(self):
                pass

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: _Proc())
        result = ci.execute("1 + 1")
        assert result.status == "error"
        assert result.output == "child output"
