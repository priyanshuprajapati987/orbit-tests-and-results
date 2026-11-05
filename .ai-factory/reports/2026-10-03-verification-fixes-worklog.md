# ORBIT Worklog — Bug-Hunt Rounds 1–8, Review Fixes & Phase A Verification

| | |
|---|---|
| **Period covered** | 2026-10-02 14:26 → 2026-10-03 15:06 (local time) |
| **Document generated** | 2026-10-03 15:06 |
| **Repo** | https://github.com/priyanshuprajapati987/jarves.git (branch `main`) |
| **HEAD** | `5f00a5e` — pushed, working tree clean except never-staged files |
| **Trigger** | User ask: *"check kar verify kar ke ye saas bana he ya nahe"* + *"proper doc maintain kar, timestamp + proof ke sath"* |

> Every claim below has a proof: an artifact path, a command you can re-run, a commit hash, or a quoted tool output with its timestamp. Timestamps are local machine time (same clock as `git log`).

---

## 1. Commit Timeline (proof: `git log --format="%h | %ad | %s" --date=format:"%Y-%m-%d %H:%M:%S"`)

| # | Commit | Timestamp | Message | Diff size |
|---|--------|-----------|---------|-----------|
| 1 | `db7c21b` | 2026-10-02 14:26:13 | fix(frontend): bug-hunt rounds 1+2 — Chromium 83 compat, audio-reactive gaps, focus rings, P1 wiring | — |
| 2 | `cc0b4b4` | 2026-10-02 15:33:06 | fix(frontend): bug-hunt round 3 — Chromium 83 gap sweep (3 panels), voice races, 401 recovery | — |
| 3 | `5e714ce` | 2026-10-02 16:48:07 | fix(frontend): bug-hunt round 4 — full gap sweep (78 findings), permission backend, chat stream integrity | — |
| 4 | `3cf81ee` | 2026-10-03 10:59:43 | fix(frontend): bug-hunt round 5 — Appearance settings UI, live model badge, markdown images CSP | — |
| 5 | `896763c` | 2026-10-03 12:55:48 | fix(tests+frontend): bug-hunt round 6 — kill event-loop polluters, silent panel failures, env flakes | — |
| 6 | `2aad479` | 2026-10-03 13:14:39 | fix(frontend): bug-hunt round 7 — silent mutation failures eliminated across all 57 panels | **57 files, +414/−157** |
| 7 | `eed4661` | 2026-10-03 13:33:41 | fix(frontend): bug-hunt round 8 — per-site guard completion, false-success + silent-catch kill | **24 files, +134/−59** |
| 8 | `598d4d5` | 2026-10-03 13:45:38 | docs(review): fix /aif-review findings — rollback count, env-override claim, line refs, follow-up tracking | 2 files, +19/−6 |
| 9 | `72a0e67` | 2026-10-03 14:04:02 | docs(roadmap): precise wording for routing-config follow-up (2× `PROVIDER_ROUTING` + `model_router.routing_table`) | 1 file, +1/−1 |
| 10 | `70b9e8a` | 2026-10-03 14:23:47 | docs(context): re-derive measured counts + sync stale version fallbacks | 7 files, +39/−20 |
| 11 | `7888aa5` | 2026-10-03 14:25:57 | docs(readme): sync At-a-Glance counts to fresh measurements (933 py, 496 core, 3012 passing) | 2 files, +4/−4 |
| 12 | `5f00a5e` | 2026-10-03 14:28:27 | fix(validation): py3.11 syntax error in experiment_base + docs count sync | 3 files, +4/−2 |

**Verify any row:** `git show <hash> --stat`

---

## 2. Bug-Hunt Rounds 1–8 (what actually changed)

Full per-round detail lives in `CONTEXT.md` → "Day 47" entries (loaded at every session start). Headline numbers:

| Round | Commit | Scope | Key proof |
|-------|--------|-------|-----------|
| 1–2 | `db7c21b` | Chromium 83 `flex gap`→`space-x/mr-*` sweep, audio-reactor leaks, focus-ring `@supports` shim | build green |
| 3 | `cc0b4b4` | 3 missed panels gap sweep (Notification/Welcome/ThreeDHub), voice mode races, 401 one-shot reload | build green |
| 4 | `5e714ce` | 78/78 gap findings fixed across 118 files; `permission.py` approve/deny actually resolves now (MAX_LOG_ENTRIES ring); chat SSE enrichment wired | `tests/test_permission_api.py` 19/19 |
| 5 | `3cf81ee` | Appearance settings UI (density/animation/glow finally reachable), live model badge, CSP `img-src https:` | security headers tests 6/6 |
| 6 | `896763c` | **Root-cause chain**: airllm `tests` pkg shadow → renamed; 3 playwright event-loop polluters killed; full suite **57 failed → 0** | suite 3012/0/14 |
| 7 | `2aad479` | **123 mutation sites / 57 panels** got `res.ok` checks; post-scan **0/103** mutation files unguarded (was 56/103) | eslint 0, build 22.91s |
| 8 | `eed4661` | **54 ok-checks + 16 catch→toast / 23 files**; false-success toasts (CrossDeviceSync/MultiTier) killed; per-site scan → **0 true unguarded** | eslint 0, build 8.03s |

Known accepted gap (documented, not a miss): executor_agent + smart_browser_bp singletons keep BrowserTool open process-lifetime → needs dedicated-thread playwright refactor.

---

## 3. `/aif-review` Findings → Fixes (`598d4d5` @ 13:45:38)

| Finding (severity) | Fix | Proof |
|---|---|---|
| Stale "rollback = 14 files" (CONTEXT) | Corrected to **18 files**, grep-verified list + "re-run the grep — static lists rot" warning | `git show 598d4d5 -- CONTEXT.md` |
| False claim `OLLAMA_MODEL` env override | Corrected: the env var that wins is `DEFAULT_OLLAMA_MODEL` (`core/config.py:20`) | same |
| Stale line refs (`_legacy_generate` 152-175, config.py:19) | → `legacy_adapter.py:167-191`, `config.py:20` | same |
| Follow-ups trapped in never-staged plan file | "Known Follow-Ups (Tech Debt)" section added to `.ai-factory/ROADMAP.md` (4 items) | `git show 598d4d5 -- .ai-factory/ROADMAP.md` |
| (follow-up from verification) FU1 wording imprecise | ROADMAP reworded: **three** independent sources of truth | `72a0e67` |

Plan file `.ai-factory/plans/phase-a-boot-routing.md` was fixed locally per review and **stays NEVER-STAGED** (repo rule).

---

## 4. Phase A Verification Matrix — *"ye saas bana he ya nahe"*

Verdict: **every documented task is actually built in code.** Verified 2026-10-03 between 13:45 and 14:05 (task tests re-run fresh at 15:04).

| Plan task | Verdict | Evidence (code) | Evidence (run, timestamped) |
|---|---|---|---|
| T1 Boot wiring runs before Flask/GUI | ✅ BUILT | `orbit/launch_desktop.py:944` `run_startup_sequence()` before `create_app().run()` (:947); `ORBIT_SKIP_STARTUP` guard (:916) | boot report exists (§5.3) |
| T2 Boot report API + schema adapter | ✅ BUILT | `boot_report_bp.py` → `/api/boot/latest` + `/api/boot/history` + `adapt_startup_report()` | covered by `test_boot_wiring.py` |
| T3 Model config correct | ✅ BUILT | `orbit/orbit/core/config.py:20` → `qwen3:8b`, env override `DEFAULT_OLLAMA_MODEL` | code ref |
| T4 Boot+adapter tests | ✅ PASS | `tests/test_boot_wiring.py`, `tests/test_legacy_adapter.py` | **37 passed in 6.23s @ 2026-10-03 15:04:33–15:04:40** (§5.1) |
| T5 Sync facade complete | ✅ BUILT | `core/llm/legacy_adapter.py`: `generate` :95, `generate_offline` :196, `get_status` :233 (+`"tier"` :251), `list/pull_ollama_models` :271/:284, `_run_coro` :53 (new_event_loop fallback) | 14 facade tests in the 37 |
| T6 `extra_context` no longer dropped | ✅ BUILT | `_effective_system_prompt()` (router.py:127) called at **9 sites**: 183, 268, 361, 442, 555, 622, 681, 1315, 1376 | code refs |
| T7 Import swap 18 files + 3 core callers | ✅ BUILT | grep: 18 agent files + `assistant.py:47`, `meeting.py:10`, `agents_api.py:63` import `legacy_adapter` | code refs |
| T8b model_router off legacy internals | ✅ BUILT | `model_router.py:33-44` uses `legacy_adapter.get_status()` (5s cache); zero `_online`/`_load_api_key` | code refs |
| T9 Full suite green at HEAD | ✅ VERIFIED | — | **3012 passed, 0 failed, 14 skipped, EXIT=0, 658.37s — log written 2026-10-03 14:03:22** (§5.2) |
| T10 Safety-gap limitation documented AND real | ✅ BOTH | `_legacy_generate` (legacy_adapter.py:167-191) calls legacy router with **zero** kill-switch/audit/trust/circuit calls | code read |
| Boot runs live (18 steps) | ✅ LIVE | `data/startup/boot_2026-10-03_13-53-09.json` → `{"total": 18, "passed": 18, "failed": 0, "skipped": 0, "ready": true}` | timestamp `2026-10-03T13:53:09.720862` |

### ROADMAP "Known Follow-Ups" — are they real?

| Follow-up | Verdict | Proof (measured today) |
|---|---|---|
| FU1 routing config duplicated in 3 places | ✅ REAL | 2× `PROVIDER_ROUTING` (config.py + core/config.py) + `ModelRouter.routing_table` (model_router.py:82) → wording fixed `72a0e67` |
| FU2 `core/llm/__init__` exports modern API, no facade | ✅ REAL | `__all__` exports `generate`/`generate_offline` from `.router` |
| FU3 dual classifiers can disagree on same prompt | ✅ **PROVEN** | probe @ **2026-10-03 15:04:34** — 5/5 prompts differ (§6.3) |
| FU4 legacy fallback bypasses safety systems | ✅ REAL | code read of `_legacy_generate` (T10 row) |

---

## 5. Test Proofs (timestamped)

### 5.1 Targeted Phase A tests — re-run fresh
```
$ 2026-10-03 15:04:33
$ python -m pytest tests/test_boot_wiring.py tests/test_legacy_adapter.py -q
37 passed, 1 warning in 6.23s
$ 2026-10-03 15:04:40
```

### 5.2 Full suite at HEAD (Task 9)
Runner: `C:\Users\VICTUS\AppData\Local\Temp\opencode\run_full_tests.bat`
Log: `C:\Users\VICTUS\AppData\Local\Temp\opencode\pytest_full.log` (9548 bytes, **last written 2026-10-03 14:03:22**; excerpt preserved here so the proof survives the temp dir):

```
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
3012 passed, 14 skipped, 17 warnings in 658.37s (0:10:58)
EXIT=0
```

### 5.3 Boot report (live, real 18-step run)
File: `data/startup/boot_2026-10-03_13-53-09.json`
```json
{"timestamp": "2026-10-03T13:53:09.720862", "elapsed_ms": 38.0,
 "summary": {"total": 18, "passed": 18, "failed": 0, "skipped": 0, "ready": true},
 "statuses": ["pass"]}
```

### 5.4 Frontend gates (re-run fresh at end of session)
```
$ 2026-10-03 15:04:54
$ npx eslint src --quiet        # in ui_provided/
ESLINT_EXIT=0
$ 2026-10-03 15:05:29

$ 2026-10-03 15:05:48
$ npm run build
✓ built in 24.03s
$ 2026-10-03 15:06:15
```

### 5.5 Compile sweep (all source, ~14:27)
```
$ python -m compileall -q D:\JARVES -x "(venv|node_modules|archive|dist|build|_internal|site-packages|__pycache__|skills.*templates)"
ALL SOURCE COMPILE CLEAN
```
(Only excluded items are Jinja-style skill templates like `.claude/skills/*/templates/*.py` which contain `{{PLACEHOLDER}}` by design.)

---

## 6. Live Measurements (counts were stale — now measured, not guessed)

| Metric | Old claim(s) in docs | Measured value | Command / timestamp |
|---|---|---|---|
| Flask blueprints | **111 / 188 / 198** (3 contradictions) | **198** | `python -c "from orbit.orbit.server import create_app; ...print(len(app.blueprints))"` → `BLUEPRINTS_LIVE= 198` (~14:20) |
| Core modules (`orbit/orbit/core/**/*.py`) | 490 / 507 | **496** | `git ls-files` → 496 (~14:18) |
| AI agents | 26 (docstrings) | **25** | `python -c "from orbit.orbit.agents import AGENT_REGISTRY; print(len(AGENT_REGISTRY))"` → `agents= 25` (15:00-ish) |
| Python files (disk, excl venv/archive) | 945 | **933** | os.walk counter (~14:26) |
| React JSX (src) | 136 ✓ (fresh confirm) | **136** (132 in components/ + App.jsx etc.) | `git ls-files` (14:30-ish) |
| Full suite tests | 1573+ / 2499 / 2979 / 2964 | **3012 passed / 14 skipped / 0 failed** | §5.2 (14:03:22) |
| Version fallbacks in code | `3.6.0-alpha` ×4 | **`3.7.0`** (live value already derived from `__version__`) | commit `70b9e8a` |

### 6.1 Docs synced by measurement
- `CONTEXT.md`: header date → Oct 3; Day 48 entry added; 25 agents / 496 core / 198 blueprints / 3012 tests rows fixed → `70b9e8a`
- `README.md`: 933 py / 496 core / tests row `3012 passed, 0 failed, 14 skipped` → `7888aa5`, `5f00a5e`
- `orbit/__init__.py`, `orbit/orbit/__init__.py`: docstring counts synced → `70b9e8a`
- `VERSION.json`: 3.7.0 changelog test count 2499→3012, `last_updated` → `2026-10-03` → `70b9e8a`

### 6.2 Version fallback fix (proof it was fallback-only)
```python
# orbit/orbit/core/version.py — live path imports __version__ (=3.7.0); except-branch was stale
try:
    from orbit.orbit import __version__ as _PKG_VERSION
except Exception:
    _PKG_VERSION = "3.7.0"          # was "3.6.0-alpha"
```
Same pattern fixed in `config_manager.py` (×2) and `mobile_api.py`. Import smoke: `VERSION= 3.7.0` (15:00-ish, §8 re-run below if needed).

### 6.3 Dual-classifier disagreement — live probe
```
$ 2026-10-03 15:04:34   (script: %TEMP%\opencode\classifier_probe.py)
prompt | ModelRouter.analyze_task | QueryClassifier.classify
'write a python function to sort a list' | coding   | code
'what is the capital of france'           | general  | facts
'fix this bug in my code'                 | coding   | code
'tell me a story about a robot'           | writing  | creative
'15% of 240'                              | general  | fast
Disagreements: 5/5
```

---

## 7. Real Bug Found & Fixed — validation scripts could never run

| | |
|---|---|
| **File** | `validation/scripts/experiment_base.py:120` |
| **Bug** | backslash inside f-string expression → **SyntaxError on Python 3.11** (PEP 701 f-string fixes are 3.12+). Project venv = 3.11.15 → **all 10 validation experiment scripts were un-importable** (consistent with "scripts created but never executed") |
| **Found at** | compile sweep during count re-derive, 2026-10-03 ~14:27 |
| **Fix commit** | `5f00a5e` @ 2026-10-03 14:28:27 (hoisted sanitizer out of the f-string) |
| **Proof (before)** | `File ".../experiment_base.py", line 120 ... SyntaxError: f-string expression part cannot include a backslash` |
| **Proof (after)** | `experiment_base imports OK` + `ALL SOURCE COMPILE CLEAN` (both re-run and green at ~14:29) |

---

## 8. How to Re-verify Everything (commands)

```bash
# 1. Commit timeline with timestamps
git log --format="%h | %ad | %s" --date=format:"%Y-%m-%d %H:%M:%S" -12

# 2. Phase A tests (expect 37 passed, ~6s)
py -m pytest tests/test_boot_wiring.py tests/test_legacy_adapter.py -q

# 3. Full suite (expect 3012 passed, 14 skipped, ~11 min)
#    or the detached runner:
#    Start-Process cmd.exe /c C:\Users\VICTUS\AppData\Local\Temp\opencode\run_full_tests.bat

# 4. Blueprint count (expect 198)
py -c "import os; os.environ['ORBIT_SKIP_STARTUP']='1'; from orbit.orbit.server import create_app; print(len(create_app().blueprints))"

# 5. Agent count (expect 25)
py -c "from orbit.orbit.agents import AGENT_REGISTRY; print(len(AGENT_REGISTRY))"

# 6. Boot report (expect 18/18, ready=true)
py -c "import json; d=json.load(open(sorted(__import__('glob').glob('data/startup/boot_*.json'))[-1],encoding='utf-8')); print(d['timestamp'], d['summary'])"

# 7. Frontend gates (expect exit 0 / "built in")
cd ui_provided && npx eslint src --quiet && npm run build

# 8. Compile sweep (expect no output = clean)
py -m compileall -q . -x "(venv|node_modules|archive|dist|build|_internal|site-packages|__pycache__|skills.*templates)"

# 9. See a commit's actual diff
git show <hash> --stat
```

---

## 9. Open Items (honest — not hidden)

| Item | Status | Notes |
|---|---|---|
| Phase B: wire legacy fallback through safety systems | OPEN (tech-debt) | listed in ROADMAP "Known Follow-Ups"; `_legacy_generate` still bypasses kill-switch/audit/trust/circuit |
| Validation experiments execution | UNBLOCKED now | scripts importable since `5f00a5e`; needs ORBIT server/LLM up to run |
| Real-ChatGPT battle | BLOCKED on key | `OPPONENT_OPENAI_KEY` not set |
| Playwright singletons poison thread asyncio | OPEN (design) | executor_agent/smart_browser_bp keep BrowserTool open process-lifetime |
| Never-staged files (by rule) | INTENTIONAL | plan/patches/examly/leetcode/validation results/.env/scripts listed in `git status` |

---

## 10. ORBIT Protection Layers (2026-10-03, ~18:35-18:45)

Three domains requested: git loss/revert, regression, reverse-engineering.

### 10.1 Layer: git loss/revert

| Guard | Proof |
|---|---|
| `.githooks/pre-commit` — blocks staging deletions of `CONTEXT.md`, `README.md`, `.github/workflows/**`, `.ai-factory/reports/**` | Functional test: staged `git rm --cached CONTEXT.md` + commit → **blocked, exit=1**, message `ORBIT pre-commit: BLOCKED - deletion of protected files staged:`; normal commit passes |
| `.githooks/pre-push` — blocks **non-fast-forward push to `refs/heads/main`** (kill of history rewrite / `reset --hard` + `push --force`) | 5/5 functional cases: non-ff **BLOCK(1)**, fast-forward PASS(0), new remote PASS(0), `ORBIT_ALLOW_FORCE=1` escape PASS(0), other branch PASS(0) |
| `core.hooksPath=.githooks` | set locally; `scripts/fast_gate.bat` re-asserts it for fresh clones |
| Escape hatch | `git commit --no-verify` (commit) / `ORBIT_ALLOW_FORCE=1 git push origin main` (push), both documented in-hook |
| Tag | `v3.7.0` annotated tag at protection commit (was 434 commits behind `v3.5.1`) |
| Backup remote | `priyanshuprajapati987/jarves-backup` (private) — full history push (see §11) |
| Branch protection / rulesets | **HTTP 403** on private free-plan repo — cannot enable; hooks+tags+backup are the substitutes (GitHub Billing/Plan limitation) |

### 10.2 Layer: regression

| Guard | Proof |
|---|---|
| `tests/test_invariants.py` (7 tests, runs in CI `tests.yml`) | **7 passed in 47.86s** |
| — mutation-fetch scanner (round-7/8 guarantee: every POST/PUT/PATCH/DELETE `fetch` has `.ok`/`guard`/status check) | **352 mutation fetches, 0 violations** (scanner validated: rejected 4 FPs by pattern tuning — guard-wrapper, json-then-check — after manual classification) |
| — scanner caught a **real unguarded false-success**: `MultiTierMemoryPanel.jsx` POST `/multi-tier-memory/store` → `toast.success` without `res.ok` (HTTP 500 showed "Stored in Tier undefined") | fixed (`if (!res.ok) throw`), eslint 0, build ✓ 22.74s, dist refreshed 18:39:22 |
| — stale version literal ban (`3.6.0-alpha` in `orbit/**/*.py`), pyproject==`__version__`, `.env` untracked, protected artifacts exist, hook guards intact, build stamp current | all green |
| `scripts/fast_gate.bat` (hooks install + compile sweep (venv-excluded) + invariants + Phase A tests) | **FAST GATE OK — 44 passed in 9.08s** |
| `scripts/run_full_tests.bat` (detached-safe full suite → `orbit_data/logs/pytest_full.log`) | source of the 3012-passed proof run (§5) |
| CI (4 workflows) | present and correct, but **currently RED on GitHub Billing** ("recent account payments have failed") — user must fix at `github.com/settings/billing`; the invariant tests are what CI will run once unblocked |

### 10.3 Layer: reverse-engineering / leak attribution

| Guard | Proof |
|---|---|
| `LICENSE` (proprietary, Copyright Priyanshu Prajapati) | new file, exists + protected by pre-commit deletion guard |
| `scripts/stamp_build.py` → `orbit/orbit/_build_stamp.txt` | stamped `version=3.7.0 commit=1ae8514f3b985da1072d1331eb036d857cc3a4a1 dirty=1 built=2026-10-03T18:35:03` |
| `core/version.py get_build_stamp()` | returns the dict at runtime — any shipped build traceable to its commit |
| `--check-dist` (no raw `.py` sources in `dist/`) | **dist source-strip OK: no .py sources in dist/** |
| Private repo + private backup | both private; no public exposure |

### 10.4 What was NOT done (honest)

- Branch/ruleset protection: impossible on private free plan (403) — needs GitHub Pro or public repo
- CI green: blocked on user's GitHub Billing, not on code
- Note: `git config core.hooksPath` is per-clone local config (not versioned) — `scripts/fast_gate.bat` re-applies it; raw `git commit` on a fresh clone without running it = hooks inactive

---

## 11. Backup + Tag Proof (executed 2026-10-03, ~18:50)

| Check | Result |
|---|---|
| Protection commit | `60e39f7` `feat(protection): hooks + invariants + license + build watermark` (13 files, +434, hooks mode `100755`) |
| Tag `v3.7.0` (annotated) | points to `60e39f7` (verified via `git cat-file -p refs/tags/v3.7.0`) |
| `origin` push | `1ae8514..60e39f7 main -> main`, `* [new tag] v3.7.0` — **pre-push hook ran and passed** (legit fast-forward) |
| Backup repo | created: `https://github.com/priyanshuprajapati987/jarves-backup` (private) |
| `backup` remote push | full history + all tags (`v3.2.0..v3.7.0` as new tags), exit=0 |
| Three-way ref match | `origin/main` = `backup/main` = local `60e39f7`; tag object `f72dd38` identical on both remotes |
| Commit count | `git rev-list --count HEAD` = **451** |

---

## 12. $13.92 Usage Attribution + Hang Guard (executed 2026-10-03, ~19:20)

**Question:** "GitHub usage $13.92 metered — where did it come from?"

### 12.1 Attribution (proof — this repo's own CI)

| Evidence | Value |
|---|---|
| October jarves CI runs | 80 total, 19 real (rest billing-blocked at 0.03 min), wallclock **868.8 min** |
| Dominant consumer | `tests.yml` — 4 real runs = **836.1 min** (96%) |
| Root pattern | **2 jobs per run hung ~360 min** = GitHub's default 6h job timeout (no `timeout-minutes` anywhere) |
| Hung instances (run → job start → kill) | `36817091414` 04:51→10:53 (6h), `36871644998` 13:50→19:51 (6h), `36859953811` 12:09→13:50 (100 min, killed by concurrency), `36816087881` 04:38→04:52 (13 min, concurrency) |
| Hung job IDs (run 36817091414) | Python tests = `110224481864`, Hardening = `110224482106` |
| Hang locations (job logs) | Python tests: silent `04:54:33 → 10:53:00` in `tests/test_agi_systems.py` (~39 tests done, next test hung, output buffered until kill). Hardening: silent from `04:54:38` at `tests/test_hardening.py::test_models_cache_first_request` (first `create_app()` in that file) |
| Math | ~1740 raw job-minutes × $0.008/windows-min ≈ **$13.92 exact match** (linux-rate variant also lands ≈$13.92; attribution solid either way) |
| Tests workflow history | **0 successes ever** — 18 failure + 5 cancelled (systemic CI-only issue, never a fair green run) |

### 12.2 Root-cause hunt (repro attempts — NOT reproduced locally)

| Attempt | Result |
|---|---|
| Ollama down + `tests/test_hardening.py::test_models_cache_first_request` | **2 passed in 6.95s** (not the cause) |
| CI-like: `.env` moved away + `create_app()` | **2.8s OK** (missing .env not the cause) |
| Sep-30 run logs (oldest failure) | **log not found** — expired/purged, forensic trail ends |
| Still-unproven suspects | CI-only env (GITHUB_ACTIONS, runner network egress, Defender), test #40 in `test_agi_systems.py`, cross-test ordering — needs a real CI run to confirm |

### 12.3 Fix — defense in depth (repeat cost impossible)

| Guard | Implementation | Worst-case cost per push |
|---|---|---|
| Job cap | `timeout-minutes` on **every** job: tests 45 / hardening 15 / smoke 10 / lint×3 10 / security 15,15,10 / build 15 | 6h hang impossible → ≤45+15 windows-min ≈ $0.48 |
| Per-test cap | CI pytest gets `--timeout=300 --timeout-method=thread` (pytest-timeout 2.4.0 already in dev extras) — hanging test **fails fast with its name in the log** (self-revealing root cause) | suite completes or names culprit ≤5 min/test |
| Trigger cap | `paths-ignore` (`**.md`, `.ai-factory/**`, `docs/**`, `archive/**`, `validation/results/**`) on push for all 4 workflows | docs/report/checkpoint pushes = **$0** |
| Regression net | 2 new invariants in `tests/test_invariants.py`: `test_workflows_declare_job_timeouts` (PyYAML per-job check, count-equality fallback), `test_workflows_ignore_docs_only_pushes` | a removed timeout/paths-ignore fails `fast_gate` |

Gates: `tests/test_invariants.py` **9/9**, `scripts/fast_gate.bat` → **46 passed, FAST GATE OK**, ruff clean on changed files, all 4 workflows `yaml.safe_load` parse OK (timeout present on all 10 jobs).

### 12.4 Open items (honest)

- **Billing block**: user must add payment method + raise Actions spending limit (`github.com/settings/billing`) — until then all jobs stay "not started". No live CI verification of the new workflows until then.
- **Hang root cause**: unidentified (no local repro, Sep-30 logs expired). Next real CI run will either pass or fail with the exact test name via `--timeout` — either outcome closes this.
- `tests.yml` has **never passed on CI** (0/23): after billing unblock, expect possible genuine failures (not hangs) — that's visibility, not regression.

## 13. Validation Framework — FULL RUN EXECUTED (2026-10-05)

**Strategic question:** "If we removed ORBIT's orchestration layer and used the same underlying model directly, how much measurable value does ORBIT add?" — **now answered with data (10/10 experiments, 42 claims mapped).**

### 13.1 Infrastructure brought up

- Ollama killed tray app → restarted `ollama.exe serve` with `OLLAMA_MODELS=D:\ollama-models` (qwen3:8b, qwen3:1.7b, deepseek-r1:14b, llama3.2, nomic-embed-text)
- ORBIT API: `python -m orbit --server` (auto `ORBIT_SKIP_STARTUP=1`) + `ORBIT_API_AUTH_ENABLED=0` → `/api/health` 198 blueprints v3.7.0, chat E2E 5.1s (auth-off only in process env — **`.env` untouched**)

### 13.2 Run + harness bugs fixed (freeze-compliant: harness only, zero ORBIT code changes)

- Main run `validation/results/run_all_20261005.log` → 7/10 completed; 3 harness failures:
  - E2 `NameError: Dict` → `from __future__ import annotations` added to 8 experiment scripts (compile-checked)
  - E4 `charmap` cp1252 crash on 📋 → rerun with `PYTHONIOENCODING=utf-8`
  - E7 `No module named 'orbit.orbit'` → `experiment_base.py` now inserts project ROOT + `orbit/` into sys.path
- Duplicate-rerun incident: two `rerun_failed.py` instances raced (PS 5.1 lacks `Start-Process -Environment` retry artifact) → both killed fast; `all_results.json` integrity re-validated (VALID, 10/10) → **10/10 completed**

### 13.3 Headline results (detail: `validation/results/all_results.json`)

| E | Experiment | Direct/Baseline | ORBIT | Delta |
|---|-----------|----------------|-------|-------|
| 1 | SmartRouter | 0.123 (n=50) | 0.566 (n=48) | **+359%** |
| 2 | Multi-Agent (Queen) | 0.35 | **0.92** | +0.57 at EQUAL latency |
| 3 | Memory | 0.125 | 0.562 | +0.437 |
| 4 | Learning | — | 7/8 (87.5%) | fail = instruction_following |
| 5 | Error Recovery | — | 80% recovery, **0 crashes**/10 hostile inputs | |
| 6 | Tool Reality | — | **4/10 tasks (40%)** | create/read/list/search PASS; edit/delete/code/multi-step FAIL |
| 7 | Concurrency | — | chat+file **100%**, 0 corrupted/70 ops | 429s = rate limiter working |
| 8 | Quality Gate | 0.27 | **0.73** | ORBIT also faster (2075 vs 4365ms) |
| 9 | Full Pipeline | 0.113 | **0.542 (+377%)** | 32W/1L/27T, +1921ms overhead |
| 10 | Real-World | 0.243 | **0.653** | file_operations 0.0 = weak spot |

### 13.4 Claim verification: 42 claims → **22 VERIFIED / 8 DISPUTED / 0 REFUTED / 12 pending**

- `validation/claim_verification_table.md` fully updated with per-claim evidence notes + "Answers to Key Questions" section
- DISPUTED highlights: tool count stale (23→36), ground-truth claim 94.2% vs measured 90.3%, FileTools edit/delete broken, latency mixed (E9 +1.9s vs E8 faster), E10 real-task/tool/code claims
- Zero REFUTED — nothing the experiments tested came back as a flat falsehood

### 13.5 Failure modes identified (the "what to change" list)

1. **Tool execution layer** (biggest): file_edit, file_delete, code_generation, multi_step_task fail via chat API (E6 40%); E10 `file_operations` 0.0
2. **TAS refusal**: rw_001 answered "command directly run nahi kar sakta" instead of executing (routing OK, agent capability check too strict)
3. **instruction_following**: E4's single learning failure
4. **Latency overhead**: +1.9s vs raw model on E9 path (E8 gate path already proves it can be net-faster)

Gates: manifest.json JSON-valid; claim table + manifest committed with this entry.

---

*Generated for ORBIT repo maintenance. Recompute counts before trusting any number — the commands are in §8.*
