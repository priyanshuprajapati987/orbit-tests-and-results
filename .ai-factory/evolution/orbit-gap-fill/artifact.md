# ORBIT Gap Register — run orbit-gap-fill-20261019-205145

## Iteration 1 (phase A) — 2026-10-19T21:07:49

| Gap | Status | Owner | Evidence | Changes | Next step |
|---|---|---|---|---|---|
| G1 real battle vs live opponent | BLOCKED | user-side (upstream OmniRouter provider creds) | Gateway REVIVED via `cmd /c "omniroute serve"` (npm-global v3.8.48, PID 9412, ~10s boot): `GET /v1/models` **HTTP 200, 2045 models**, `auto/best-free` present; `GET /api/monitoring/health` 200 healthy. BUT `POST /v1/chat/completions` (auto/best-free) → **HTTP 503** body `{"error":{"message":"Maximum combo retry limit reached"...,"excluded":[{"provider":"kilocode","reason":"exhausted_connection"...}]}}` ×2 (20.1s/26.7s) = upstream free-provider auth/quota exhaustion, not a local fault | none needed locally (gateway restart command documented) | re-auth/refresh upstream providers in `C:\Users\VICTUS\.omniroute\.env` (kilocode + others) → retest one completion; OR add `OPPONENT_OPENAI_KEY=sk-...` to root `.env` to battle real ChatGPT (infra Day-33 already wires it) |
| G2 stale roadmap checkboxes | CLOSED | code | all 7 CONTEXT.md 6-month-roadmap items verified in code: `multimodal_agent.py:183` `analyze_screenshot` + `:239` `ocr_image`, `screen.py:241` `capture_and_analyze` + `:28` `_detect_vision_model` (8 modes quick/detailed/code/browser/terminal/document/ocr/ui_elements at `multimodal_agent.py:91-103`); `task_agents.py:574-579` CodeAgent→`CodeReviewer()` wiring + `core/code_debugger.py` exists; `tools/browser_tool.py:129/183/167` navigate/click/screenshot; `core/honest_metrics.py` + `HonestMetricsPanel.jsx` + `ScorecardPage.jsx`; `core/skills_marketplace.py` + `skills_bp.py` + `SkillsPanel.jsx` + `marketplace_bp.py`; `core/knowledge_base.py` + `knowledge_bp.py` + `KnowledgePanel.jsx`; `core/self_improver_v2.py` `SelfImproverV2` + `self_improvement.py` `Lesson`/`SelfImprovement` + lesson adoption tracking `learning_system.py:297 get_adoption_rate` (harvested/applied, `server.py:989` API) | CONTEXT.md: 7 checkboxes flipped `[ ]`→`[x]` (Multi-modal, Code generation+debugging, Browser automation, Self-improving, Honest metrics, Skills marketplace, Knowledge base); Voice cloning / Wake word / Natural conversation LEFT UNCHECKED (honest open) | — |
| G3 playwright singleton leak | CLOSED | code | **Recon verdict STILL-LEAK confirmed, then FIXED**: (1) `agents/executor_agent.py:129-152` browser branch now `try/.../finally: self.browser_tool.close()` — per-subtask start/stop, never process-lifetime (was: zero close calls, `_BROWSER_AVAILABLE` tool held from `__init__:58` forever); (2) `tools/smart_browser_bp.py:18-40` `_get_sb()` idle-close `_IDLE_CLOSE_SEC=600` on the **requesting thread** (cross-thread timer deliberately avoided — playwright sync objects must stop on a live request thread) + `_shutdown_close` registered via `core/shutdown.py get_shutdown_manager().register("smart_browser", ...)` (`smart_browser_bp.py:93-110`); close() was already null-safe `browser_tool.py:291-306`. **Tests**: `test_remaining_tools+test_smartbrowser_mcp+test_browser_reliability` = **99 passed 0 failed**; `test_agent_tool_integration` (ExecutorAgent) = **59 passed**; py_compile+ruff clean on both files (playwright not installed in orbit\.venv → tests exercise degraded path; fix is inert-until-installed + risk-free per recon) | `executor_agent.py` (try/finally close), `smart_browser_bp.py` (idle-close + shutdown hook) | — |
| G4 test skips audit | CLOSED | code | Static inventory of 87 skip-sites reconciled EXACTLY to observed 25 (suite log `3993 passed, 25 skipped`): **18 HONEST** (4× phoenix missing `emergency_recovery.py`, 8× hermetic provider-key strips — Day-41 policy, 6× module-fixture opt-in gates) + **6 env-opt-in S-fill** (`ORBIT_SMOKE_SERVER`/`ORBIT_REAL_AGENTS`/`ORBIT_TEST_FLASK`/`ORBIT_REAL_NET`/`ORBIT_OFFLINE` — deliberately NOT set in hermetic runs) + **1 FILLABLE: PyPDF2 missing** (`test_remaining_tools.py:268`) → **FILLED**: `pip install PyPDF2` → **3.0.1** installed in orbit\.venv; PyPDF2 is real product code (`core/chat_api.py:1172` PDF-upload path + `tools/pdf_reader.py:90`) so this was a runtime gap, not just a test skip; previously-skipped test now RUNS green (99-passed batch above) | venv: PyPDF2 3.0.1 installed (no repo changes) | — |
| G5 voice accuracy items | OPEN | code | Recon: mechanisms present but **eval harnesses MISSING** (→ unmeasurable today). Wake word: threshold/bandpass/N-of-M 3-of-5/confidence-gate/cooldown/persistent-Vosk all live (`wake_word.py:24-31,93-134,270`) but zero FAR/FRR benchmark (grep of test_wake_word/test_six_systems/test_streaming_voice = mechanism-only asserts); `generate_wake_word_data` (:404-445) = training-data synth, not eval. Clone: SNR gate `_estimate_quality` (`xtts.py:156`) measures reference cleanliness, NOT clone fidelity — no WER/speaker-similarity anywhere. Bonus finding: `voice_personality.adapt_tone` wired **Edge-TTS only** (`tts.py:186-194`) — XTTS/Kokoro branch returns earlier at `tts.py:178-181` | none yet (planned) | MVP next iteration: (a) wake-word offline replay harness (synth+real WAVs → `_process_frame`/`_check_confirmation` sweep OWW_THRESHOLD × CONFIDENCE × CONFIRMATION_MIN → FAR/FRR table); (b) clone-fidelity eval (STT-WER on clone output + ref/clone embedding similarity, sweep temperature/ref-count); (c) small fix: move personality hook into XTTS branch |
| G6 external blockers | CLOSED | user-side | GitHub CI live via `gh run list`: 12 latest runs all ≤2026-10-07; Lint/Tests/Security/Build all `conclusion=failure` in 4–8s with **empty `steps[]`** (jobs never executed); ZERO runs for pushes after 2026-10-07 (10-17 Tier-1.1 + 10-18 GT commits produced no runs) = billing-block state consistent with CONTEXT Day-48 "CI 4 workflows RED on GitHub Billing"; `OPPONENT_OPENAI_KEY` = **ABSENT** in root `.env` (OPPONENT_BASE_URL/MODEL/API_KEY present, non-secret gateway config) | CONTEXT.md (date/checkbox fixes only — no stale "Known Limitations" section found, Day-54 already records its retirement; Day-48/49 billing lines are historical log entries, left intact); README/METRICS/CHANGELOG/CLAIMS date fixes (see below) | user: fix `github.com/settings/billing` to unblock CI; user: add `OPPONENT_OPENAI_KEY=sk-...` to `.env` for real-ChatGPT battle |

### G2 — checkbox verdicts (proof per line, all in CONTEXT.md "6-MONTH ROADMAP")

| Item | Verdict | 1-line proof |
|---|---|---|
| Multi-modal (screen understanding) | ✅ now `[x]` | `orbit/orbit/agents/multimodal_agent.py:183` `analyze_screenshot`, `:239` `ocr_image`; `orbit/orbit/screen.py:241` `capture_and_analyze`, `:28` `_detect_vision_model`; 8 modes at multimodal_agent.py:91-103 |
| Code generation + debugging | ✅ now `[x]` | `agents/task_agents.py:574-579` imports+instantiates `CodeReviewer` after LLM generation; `core/code_debugger.py` + `code_debugger_bp.py` exist |
| Browser automation (Playwright) | ✅ now `[x]` | `orbit/orbit/tools/browser_tool.py` — `navigate:129`, `click:183`, `screenshot:167`, `type_text:194` (+ smart_browser.py + BrowserTool/EXE wiring) |
| Honest metrics dashboard | ✅ now `[x]` | `core/honest_metrics.py` + `ui_provided/src/components/HonestMetricsPanel.jsx` + `ScorecardPage.jsx` all exist |
| Skills marketplace | ✅ now `[x]` | `core/skills_marketplace.py` + `skills_bp.py` + `marketplace_bp.py` (RemoteSkillMarket) + `SkillsPanel.jsx` all exist |
| Knowledge base | ✅ now `[x]` | `core/knowledge_base.py` + `knowledge_bp.py` + `KnowledgePanel.jsx` all exist |
| Self-improving system | ✅ now `[x]` | `core/self_improver_v2.py:53` `SelfImproverV2`, `core/self_improvement.py:70` `SelfImprovement` (`Lesson` extraction) + adoption tracking `learning_system.py:297 get_adoption_rate` (harvested_count/applied_count → `/api/learning/adoption` server.py:989) |
| Voice cloning accuracy improvement | ⛔ stays `[ ]` | no accuracy-eval deliverable found (roadmap leftover, see .ai-factory/plans/2026-10-08-plan.md C) |
| Wake word accuracy improvement | ⛔ stays `[ ]` | Day-55 only added sounddevice fallback (py3.14 availability), not accuracy work |
| Natural conversation (zero latency) | ⛔ stays `[ ]` | no zero-latency deliverable; latency work is measurement/benchmark, not a shipped "zero latency" mode |

### G2b — ROADMAP.md "Known Follow-Ups" verification (no edits needed)

| FU | Verdict | Proof |
|---|---|---|
| FU1 consolidate routing config (3 sources) | still OPEN | `config.py:186 PROVIDER_ROUTING` + `core/config.py:144 PROVIDER_ROUTING` + `model_router.py:82 routing_table` — all three still exist |
| FU2 document `core/llm/__init__` exports | still OPEN | `core/llm/__init__.py` still exports modern `generate`/`generate_offline` only; module docstring unchanged ("Unified LLM interface"), no when-to-use-which doc |
| FU3 unify task classifiers | still OPEN | `model_router.py:250 analyze_task` AND `orchestrator.py:81 QueryClassifier` both still present |
| FU4 wire legacy-fallback through safety systems | ✅ already `[x]` | verified: `legacy_adapter.py:167 _safety_record`, called at `:240` from `_legacy_generate:216` + CONTEXT Day-54 entry (line ~1488) |

## Evidence log — date reconciliation (Deliverable 2)

**Ground truth collected first:**
- `git log -1 --format='%ci %h' b2be19c` → `2026-10-18 14:05:30 +0530 b2be19c` ("fix(eval+voice): GT gap closed 100% (103/103); wake word sounddevice fallback"; touches CHANGELOG/CLAIMS/CONTEXT/METRICS/README + ground_truth.py/prompts.py/wake_word.py)
- `git log -1 --format='%ci %h' d5f4878` → `2026-10-17 22:28:57 +0530 d5f4878` ("docs: post-integration counts - 3985 tests, 201 blueprints")
- `git log -1 --format='%ci %h' dfd02fe` → `2026-10-17 21:46:19` (Tier 1.1 playbook live routing — the 10-17 work)
- `(Get-Item orbit_data\ground_truth_eval.json).LastWriteTime` → `2026-10-18 12:25:03 PM`
- GT JSON internal `timestamp` field → **`2026-10-18T12:25:03`** (the rerun wrote the file itself — decisive)
- `(Get-Item orbit_data\ground_truth_eval_99of103_20261006.json)` → `2026-10-06 7:21:05 PM` (old 99/103 backup, consistent)
- `git log -1 -- <doc>` for README/METRICS/CHANGELOG/CLAIMS/CONTEXT → all `2026-10-18 14:05:30 b2be19c` (that commit wrote the GT-date docs)

**Verdicts:**

| Claim | Location | Verdict | Proof |
|---|---|---|---|
| GT row "2026-10-17" | README.md:32 | **FIXED → 2026-10-18** | GT JSON `timestamp=2026-10-18T12:25:03`; commit b2be19c 2026-10-18 |
| GT run "(2026-10-17)" + "2026-10-06 → 2026-10-17 gap" | README.md:273 | **FIXED → 2026-10-18 (both)** | same as above |
| "2026-10-18 | Full venv suite | 3993" | METRICS.md:12 | **KEPT** | matches b2be19c 2026-10-18 (3993 suite was that session's final gate) |
| "2026-10-17 | …103/103 (100%)" | METRICS.md:27 | **FIXED → 2026-10-18** | GT file timestamp 10-18 |
| "superseded by 2026-10-17 run" | METRICS.md:28 | **FIXED → 2026-10-18** | same row group |
| "Tier 1.1 routing/GT (17 Oct 2026)" | CHANGELOG.md:6 | **FIXED → routing (17 Oct) / GT closure (18 Oct 2026)** | routing commit dfd02fe 10-17; GT commit b2be19c 10-18 |
| "Added (Tier 1.1 — 17 Oct)" | CHANGELOG.md:8 | **KEPT** | routing work = dfd02fe 2026-10-17 21:46 |
| "GT gap closure — 17 Oct" | CHANGELOG.md:12 | **FIXED → 18 Oct** | GT file timestamp + b2be19c |
| "Blueprints 201 … 2026-10-17" | CLAIMS.md:15 | **KEPT** | d5f4878 (2026-10-17 22:28) documents "201 blueprints" |
| "Tests 3,985 … 2026-10-17" | CLAIMS.md:18 | **KEPT** | d5f4878 (2026-10-17) documents "3985 tests" |
| "Ground-truth accuracy … 2026-10-17" | CLAIMS.md:20 | **FIXED → 2026-10-18** | GT file timestamp 10-18 |
| "100% (103/103, 2026-10-17)" | CLAIMS.md:31 (RETIRED row) | **FIXED → 2026-10-18** | same |
| "Day 55 — October 17, 2026" header | CONTEXT.md:1501 | **FIXED → October 17–18, 2026 (+ note: GT closure committed 10-18 `b2be19c`)** | entry spans Tier-1.1 (10-17 commits) + GT closure/wake-word/3993-suite (10-18 commit) |
| Day-55 "Docs synced … 2026-10-17" | CONTEXT.md:1519 | **FIXED → 2026-10-18** | describes the same GT rows now dated 10-18 |
| "# Last Updated: October 17, 2026" | CONTEXT.md:2 | **FIXED → October 19, 2026** | last commit touching CONTEXT = b2be19c 2026-10-18; file edited again today 2026-10-19 |

## Evidence log — G6 (Deliverable 3)

- **GitHub CI** (gh CLI WORKS): `gh run list --repo priyanshuprajapati987/jarves --limit 12 --json ...` → 12/12 latest runs created ≤ **2026-10-07T16:00:50Z**; Lint/Tests/Security/Build on recent pushes = `conclusion: "failure"`, each **4–8 seconds**; `gh api .../runs/37646128134/jobs` → jobs `"steps":[]` (no step ever executed — job-startup-level failure, not test failures); **no runs at all** for the 10-17/10-18 pushes → CI remains in the documented billing-block state (CONTEXT Day-48: "CI 4 workflows RED on GitHub Billing — user must fix at github.com/settings/billing"). (Detail-note: `gh run view`/annotations endpoints returned HTTP 502/404 during this run — GitHub API flake, not a status change.)
- **Real-ChatGPT battle key**: `Select-String -Path .env -Pattern '^\s*OPPONENT_OPENAI_KEY\s*='` → **ABSENT** (checked presence only; no values read/printed). `OPPONENT_BASE_URL`/`OPPONENT_MODEL`/`OPPONENT_API_KEY` present = OmniRouter free-gateway config only → battle still falls back to free models/MockOpponent per README:271.
- **CONTEXT staleness check**: no live "Known Limitations" section exists (Day-54 entry records its retirement — accurate); Day-48/49 billing/CI lines are historical day-log entries (accurate as records) → **no stale gap claims edited** (deliverable item 3 = no change needed).

## Gate-fix round (AC4 first attempt → 4 failed → root-caused + fixed)

First full-suite run (bare-`python` bat): **4 failed, 3990 passed, 24 skipped (20:04)** — root causes:
1. **`tests.e2e` shadow (3 failures: `test_load_prompts_full` +`'general'` extra category = fallback dict, `test_load_prompts_quick_and_category` sizes, `test_120_prompts_6_categories` `ModuleNotFoundError: No module named 'tests.e2e'`)** — `scripts/run_full_tests.bat:7` used bare `python` → resolved to **system Python 3.12** (`C:\Users\VICTUS\AppData\Local\Programs\Python\Python312`), whose site-packages contains an **orphan `tests\__init__.py`** (regular package beats repo namespace `D:\JARVES\tests`) → `from tests.e2e.battle_prompts import BATTLE_PROMPTS` ImportError → `core/battle.py:81-83` silent fallback. Same failure class as Day-46 BUG A (hermes venv), different interpreter. **Fixes**: (a) bat pinned to `orbit\.venv\Scripts\python.exe`; (b) orphan renamed `site-packages\tests` → `tests_orphan_disabled` — system python now resolves `tests` → `D:\JARVES\tests` (verified).
2. **`test_first_get_metrics_does_not_deadlock` (timeout mislabeled as deadlock)** — `honest_metrics.py:36` already uses `threading.RLock` (fix present); the 5s guard tripped because `scan_now()` calls `get_api_validator().get_status()` = **live provider network probes** (slow scan under load, not a lock bug). **Fix**: test made hermetic (stubs `api_validator.get_api_validator`, timeout 5→15s) — pins the RLock regression only, no network.
- **Re-verify**: `test_honest_metrics_deadlock + test_battle_runner + test_phase2_orchestrator` = **41 passed** (venv py).
- Attempt 2 (venv-pinned): **1 failed, 3993 passed, 24 skipped (13:46)** — battle+deadlock green; new: `test_agi_wave2::test_satisfaction_update` = **persistence saturation flake** (EMA toward 1.0 in persisted `orbit_data/test_tom.json` across runs → strict-greater fails on float equality; passed 10-18 = file not yet saturated). **Fix**: test uses fresh `tempfile.TemporaryDirectory()` storage + asserts start < 1.0; stale `orbit_data/test_tom.json` deleted. Re-verify: `test_agi_wave2.py` **45 passed**.
- Attempt 3 launched under pinned venv; verdict below.

## Changed files

- `D:\JARVES\CONTEXT.md` — 7 roadmap checkboxes `[ ]`→`[x]`; Day-55 header date → October 17–18 (+ GT-commit note); Day-55 "Docs synced" GT date → 2026-10-18; `Last Updated` → October 19, 2026
- `D:\JARVES\README.md` — GT dates 2026-10-17 → 2026-10-18 at line 32 and line 273 (2 spots)
- `D:\JARVES\METRICS.md` — §3 rows: GT 100% run date → 2026-10-18 (line 27), superseded-reference → 2026-10-18 (line 28); line 12 (2026-10-18 suite) KEPT
- `D:\JARVES\CHANGELOG.md` — Unreleased header split (routing 17 Oct / GT 18 Oct); GT-gap Fixed section → 18 Oct
- `D:\JARVES\CLAIMS.md` — GT verified row + RETIRED-row replacement → 2026-10-18; rows 15/18 (blueprints/tests 2026-10-17) KEPT
- `D:\JARVES\.ai-factory\evolution\orbit-gap-fill\artifact.md` — this file (created)
- `.ai-factory/ROADMAP.md` — **NOT edited** (FU4 already `[x]`; FU1–FU3 verified genuinely still open)
- `D:\JARVES\orbit\orbit\agents\executor_agent.py` — G3: browser subtask branch wrapped in `try/finally: self.browser_tool.close()` (per-subtask start/stop)
- `D:\JARVES\orbit\orbit\tools\smart_browser_bp.py` — G3: `_get_sb()` idle-close (`_IDLE_CLOSE_SEC=600`, requesting-thread) + `ShutdownManager.register("smart_browser", _shutdown_close)`
- orbit\.venv — G4: PyPDF2 3.0.1 installed (runtime dep for `chat_api.py:1172` + `pdf_reader.py:90`)
- `D:\JARVES\scripts\run_full_tests.bat` — AC4 gate fix: pinned interpreter to `orbit\.venv\Scripts\python.exe` (bare `python` hit system py312 + orphan `tests` shadow)
- `D:\JARVES\tests\test_honest_metrics_deadlock.py` — hermeticity fix: stub `api_validator.get_api_validator`, guard timeout 5→15s (network-scan slowness ≠ deadlock; RLock fix at `honest_metrics.py:36` already present)
- `D:\JARVES\tests\test_agi_wave2.py` — `test_satisfaction_update` hermeticity fix: fresh `TemporaryDirectory` ToM storage (persisted EMA saturation flake); stale `orbit_data/test_tom.json` deleted
- system Python 3.12 env: `site-packages\tests` → `tests_orphan_disabled` (orphan neutralized; not a repo file)
- `D:\JARVES\orbit_data\logs\pytest_full.log` — full-suite gate evidence (written by EVALUATE step below)
