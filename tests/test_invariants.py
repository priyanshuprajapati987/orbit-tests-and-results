"""ORBIT protection invariants — regression net for the guarantees we proved.

Runs locally (scripts/fast_gate.bat) and in CI (tests.yml full suite).
Red here = a protected invariant of the repo was reversed:
  - silent mutation failures reintroduced (bug-hunt rounds 7/8 guarantee)
  - stale version literals back in source
  - pyproject / __version__ drift
  - .env tracked (secret leak)
  - proof reports, workflows, hooks or license deleted
  - build watermark missing/stale
  - CI jobs without timeout-minutes (6h-hang cost guard)
  - docs-only pushes triggering paid CI runs
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "ui_provided" / "src"

MUTATION_FETCH = re.compile(r"fetch\s*\(")
MUTATION_METHOD = re.compile(
    r"""["'](POST|PUT|PATCH|DELETE)["']|method\s*:\s*["'](post|put|patch|delete)["']""",
    re.I,
)
# .ok guard, guard helper (any position), json-then-check (=== 'ok'), status checks
MUTATION_GUARD = re.compile(r"\.ok\b|\bguard\b|===\s*['\"]ok['\"]|\.status\b")

PROTECTED_FILES = [
    "CONTEXT.md",
    "README.md",
    "LICENSE",
    ".githooks/pre-commit",
    ".githooks/pre-push",
    ".github/workflows/lint.yml",
    ".github/workflows/tests.yml",
    ".github/workflows/build.yml",
    ".github/workflows/security.yml",
    ".ai-factory/reports/2026-10-03-verification-fixes-worklog.md",
    "scripts/run_full_tests.bat",
    "scripts/fast_gate.bat",
    "scripts/stamp_build.py",
    "scripts/recovery_drill.py",
    "RELEASE_CHECKLIST.md",
]

# The security gates (P0-P5) fast_gate.bat must run every time.
REQUIRED_SECURITY_GATES = [
    "test_dead_hand.py",
    "test_deadhand_authz.py",
    "test_atomic_write_fault.py",
    "test_self_healer_gate.py",
    "test_hash_audit.py",
    "test_api_auth_security.py",
]

BANNED_LITERALS = ["3.6.0-alpha"]


def test_mutation_fetches_guarded():
    """Every POST/PUT/PATCH/DELETE fetch must have an error/status guard.

    Guarantee from bug-hunt rounds 7+8: 0 unguarded mutation sites.
    A failure here means a new silent-failure (or false-success) was introduced.
    """
    violations: dict[str, list[int]] = {}
    total = 0
    files = sorted(SRC.rglob("*.jsx")) + sorted(SRC.rglob("*.js"))
    assert files, f"no frontend sources found under {SRC}"

    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        for m in MUTATION_FETCH.finditer(text):
            head = text[m.start(): m.start() + 500]
            if not MUTATION_METHOD.search(head):
                continue
            total += 1
            window = text[max(0, m.start() - 300): m.start() + 900]
            if not MUTATION_GUARD.search(window):
                line = text[: m.start()].count("\n") + 1
                violations.setdefault(str(f.relative_to(SRC)), []).append(line)

    assert total > 100, f"scanner found only {total} mutation fetches — scanner broken?"
    assert not violations, (
        f"unguarded mutation fetches (silent-failure regression): {violations}"
    )


def test_no_stale_version_literals():
    """Old release literals must not survive in Python source (docs may keep history)."""
    banned = BANNED_LITERALS
    hits: list[str] = []
    pkg = ROOT / "orbit"
    for f in pkg.rglob("*.py"):
        if "archive" in f.parts or "__pycache__" in f.parts:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for b in banned:
            if b in text:
                hits.append(f"{f.relative_to(ROOT)}: {b}")
    assert not hits, f"stale version literals found: {hits}"


def test_versions_in_sync():
    """pyproject.toml version == orbit.orbit.__version__ (single source of truth)."""
    import orbit.orbit as pkg

    pyproject = (ROOT / "orbit" / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.M)
    assert m, "version not found in orbit/pyproject.toml"
    assert m.group(1) == pkg.__version__, (
        f"version drift: pyproject={m.group(1)} __version__={pkg.__version__}"
    )


def test_env_not_tracked():
    """.env (secrets) must never enter git history."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "--", ".env"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git unavailable")
    if out.returncode != 0:
        pytest.skip(f"git ls-files failed: {out.stderr.strip()}")
    assert not out.stdout.strip(), f".env is tracked by git: {out.stdout!r}"


def test_protected_artifacts_exist():
    """Proof reports, CI workflows, hooks, license and runners must exist."""
    missing = [p for p in PROTECTED_FILES if not (ROOT / p).is_file()]
    assert not missing, f"protected files missing: {missing}"


def test_hooks_contain_guards():
    """Hook scripts must still carry their guard logic (not emptied out)."""
    pre_commit = (ROOT / ".githooks" / "pre-commit").read_text(encoding="utf-8", errors="replace")
    pre_push = (ROOT / ".githooks" / "pre-push").read_text(encoding="utf-8", errors="replace")
    assert "diff-filter=D" in pre_commit and "BLOCKED" in pre_commit
    assert "refs/heads/main" in pre_push and "BLOCKED" in pre_push
    assert "ORBIT_ALLOW_FORCE" in pre_push


def test_fast_gate_runs_security_gates():
    """fast_gate.bat must include every P0-P5 security gate test file.

    A failure here means a security gate was dropped from the fast lane
    (regression protection for the 2026-10-22 hardening plan, P5.1).
    """
    gate = (ROOT / "scripts" / "fast_gate.bat").read_text(encoding="utf-8", errors="replace")
    missing = [t for t in REQUIRED_SECURITY_GATES if t not in gate]
    assert not missing, f"fast_gate.bat missing security gates: {missing}"


def test_build_stamp_present_and_current():
    """Release watermark: commit hash + matching version for leak traceability."""
    stamp = ROOT / "orbit" / "orbit" / "_build_stamp.txt"
    assert stamp.is_file(), (
        "missing orbit/orbit/_build_stamp.txt — run: python scripts/stamp_build.py"
    )
    text = stamp.read_text(encoding="utf-8")
    commit = re.search(r"commit=([0-9a-f]{40})", text)
    version = re.search(r"version=([0-9.]+)", text)
    assert commit, "stamp missing commit=<40-hex>"
    assert version, "stamp missing version=x.y.z"
    import orbit.orbit as pkg

    assert version.group(1) == pkg.__version__, (
        f"stamp version {version.group(1)} != __version__ {pkg.__version__} — re-stamp"
    )


def test_workflows_declare_job_timeouts():
    """Every CI job must declare timeout-minutes (cost cap for hangs).

    Oct-2026 incident: two windows-latest test jobs hung for GitHub's 6h
    default (no timeout-minutes) across two runs ~= $13.92 metered usage.
    A failure here means a hang can again burn 6h of runner time per job.
    """
    wf_dir = ROOT / ".github" / "workflows"
    files = sorted(wf_dir.glob("*.yml")) + sorted(wf_dir.glob("*.yaml"))
    assert files, "no workflow files found under .github/workflows"
    try:
        import yaml
    except ImportError:
        yaml = None  # fallback below keeps the guard active without PyYAML

    problems: list[str] = []
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        if "runs-on:" not in text:
            continue
        if yaml is not None:
            data = yaml.safe_load(text) or {}
            jobs = data.get("jobs") or {}
            assert jobs, f"{f.name}: runs-on present but no jobs parsed"
            for jname, job in jobs.items():
                if isinstance(job, dict) and "timeout-minutes" not in job:
                    problems.append(f"{f.name}:{jname}")
        else:
            n_run = len(re.findall(r"^\s*runs-on:", text, re.M))
            n_to = len(re.findall(r"^\s*timeout-minutes:", text, re.M))
            if n_run == 0 or n_run != n_to:
                problems.append(f"{f.name}: runs-on={n_run} timeout-minutes={n_to}")

    assert not problems, (
        f"workflow jobs missing timeout-minutes (6h-hang cost guard): {problems}"
    )


def test_workflows_ignore_docs_only_pushes():
    """Docs-only pushes must not start paid CI runs (cost guard).

    This repo's heaviest push traffic is markdown/report/checkpoint commits;
    paths-ignore keeps those at $0 instead of spinning windows runners.
    """
    wf_dir = ROOT / ".github" / "workflows"
    files = sorted(wf_dir.glob("*.yml")) + sorted(wf_dir.glob("*.yaml"))
    assert files, "no workflow files found under .github/workflows"
    missing = []
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        if "push:" not in text:
            continue
        if "paths-ignore" not in text or "**.md" not in text:
            missing.append(f.name)
    assert not missing, (
        f"workflows triggering paid runs on docs-only pushes: {missing}"
    )


def test_readme_core_module_count_matches_reality():
    """README/CONTEXT claim of core module count must match the actual file count.

    Catches stale docs (this drift happened on 2026-10-20: README said 496,
    reality was 508 after new modules landed).
    """
    core_dir = ROOT / "orbit" / "orbit" / "core"
    actual = sum(1 for p in core_dir.glob("*.py") if p.is_file())
    for doc in ("README.md", "CONTEXT.md"):
        text = (ROOT / doc).read_text(encoding="utf-8", errors="replace")
        m = re.search(r"(\d+)\s+modules", text)
        if m:
            claimed = int(m.group(1))
            assert claimed == actual, (
                f"{doc} claims {claimed} core modules, actual is {actual}"
            )


def test_readme_blueprint_count_matches_live_app():
    """README blueprint count must match the live create_app() registration count.

    Catches stale docs (this drift happened on 2026-10-20: README said 201,
    live was 202 after status_bp landed).
    """
    import sys

    sys.path.insert(0, str(ROOT / "orbit"))
    try:
        from orbit.orbit.server import create_app

        app = create_app()
        actual = len(app.blueprints)
    except Exception:
        pytest.skip("create_app() unavailable in this environment")
    text = (ROOT / "README.md").read_text(encoding="utf-8", errors="replace")
    m = re.search(r"(\d+)\s+registered", text) or re.search(
        r"Flask \((\d+) blueprints\)", text
    )
    if m:
        claimed = int(m.group(1))
        assert claimed == actual, (
            f"README claims {claimed} blueprints, live create_app() registers {actual}"
        )
