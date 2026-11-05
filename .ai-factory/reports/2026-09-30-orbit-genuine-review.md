# ORBIT — Genuine Fresh-Eyes Review

**Date:** 2026-09-30 (evening) · **Reviewer approach:** independent re-review as if new to the codebase — full test run + boot verification + two read-only reviewers, then **manual verification of every critical claim** (one reviewer claim was disproven in this step and is corrected below).
**Scope:** backend (`orbit/orbit/`), frontend (`ui_provided/`), docs truth, security, tests, packaging.

---

## 1. Verified Snapshot (measured today, not claimed)

| Fact | Measured value | How |
|---|---|---|
| Version | **3.7.0** (pyproject, both `__init__`, package.json, VERSION.json — all in sync) | direct read |
| App boots | yes — `create_app()` OK | import + create_app |
| Blueprints registered | **198** (1,317 routes) | `len(app.blueprints)` on live app |
| Python files | **958** project files (excl. `.venv`) | count |
| Test files / test functions | 147 files / **3,003** `def test_` | count |
| Full suite (9 min 51 s) | **2,944 passed · 4 failed · 14 skipped** | `pytest -q` |
| The 4 failures | the same 4 **pre-existing** (2× chat-streaming lambda signature, 2× tier1 orchestrator routing) | matches known baseline |
| React components | **136** `.jsx/.tsx` (119 wired to 121 registry keys) | count + registry read |
| UI build state | valid config, overrides pin nanoid/postcss/esbuild; last build green | read (build not re-run) |

---

## 2. Verdict by Area

### 🟢 Tests — REAL (with one honesty gap)
- 3,003 test functions, ~5,400 assertions, **0 `assert True` tautologies**; sampled 10 files across billing/security/core — real behavior assertions.
- Hermetic `conftest.py` strips real keys from the session — good hygiene.
- **Gap:** `tests/conftest.py:69` permanently ignores `test_tier3_reliability.py` (**47 tests never run**) because `create_app()` starts blocking daemons — while docs count them as passing.

### 🔴 Security — strong machinery, one critical hole
- **ToolGate is genuinely enforced**: FileTools gates all 11 ops (`file_tools.py:38-43`), Desktop 20+, GitHub 18, strict mode default ON (`policy_engine.py:193`).
- **API auth is fail-closed and careful**: `server.py:463-508` (hmac compare, ephemeral UI token, CSP/no-store — the 304/nonce fix is real), 19 targeted tests.
- **CRITICAL — live `ORBIT_API_KEY` is hardcoded in tracked files.** Verified by byte-comparison with `.env`: **11 files contain the real key**, ≥5 are git-tracked: `tests/stress_test.py`, `archive/stress_test.py`, `tests/test_all_11_fixes.py`, `tests/test_file_create.py`, **`tests/load/load_test.py` (committed today)** + 6 more untracked. The key is therefore in **git history** (private repo, but still).
- **HIGH — Stripe webhook will 401 in production:** `/api/billing/webhook` (`billing_bp.py:139`) is not in `ORBIT_API_PUBLIC_PATHS` (`config.py:239`), so real Stripe POSTs are blocked by API-key auth. Tests miss it because they build a bare Flask app without the auth hook (`test_stripe_e2e.py:216`).
- Console logs: `ColoredFormatter` has no secret redaction (JSON file handlers do — via `SecretRedactor`).
- **LLM safety partial:** audit logging + circuit breaker ARE on the main router path (`router.py:797-819, 1117`), but the **kill switch / agent trust (`can_act()`) is never called for chat/agents** — only autonomous/A2A paths. The CONTEXT-documented "legacy fallback bypass" gap is honest; the bigger unmentioned gap is that trust limits aren't enforced even on the good path.

### 🟡 Blueprints — works today, failures are silent
- 198 registered and resolving now, but **92 of 198 registration points can fail invisibly**: 74 via `_try_import` (any Exception → single `logger.warning`, `server.py:195-200`) + 18 at `logger.debug` (`server.py:841-859`). `honest_metrics` only counts `len(app.blueprints)` — no aggregation of what silently vanished.

### 🟡 Dead/duplicate code — real
- **`orbit/orbit/core/tools/` is 100% dead** (0 external refs; duplicates `orbit/orbit/tools/` — e.g. 25 KB `computer.py`).
- 8 orphan core modules with zero refs incl. `battle_v2.py` — notably the module behind the headline **"56/60 (93%)"** claim is imported by nothing; the shipped path is `core/battle.py`. Two SSRF implementations (live `ssrf_guard.py`, orphan `ssrf_protection.py`).

### 🔴 Packaging — genuinely broken
- `orbit/requirements.txt:65`: **`mypy>=1.5.0waitress>=3.0.0`** — missing newline → invalid spec → `pip install -r requirements.txt` fails. *(Introduced with the M7 waitress addition.)*
- `orbit/pyproject.toml` omits `defusedxml`, `stripe`, `sqlalchemy`, `psycopg2-binary` although server import-time code needs them (`tools/news.py:1`, billing Stripe path); CI installs only `.[dev]` → clean-install path cannot boot the full server.

### 🟢 Frontend — structurally sound
- 121 registry keys ↔ 119 rendered components + notifications slide-over — **no orphan panels**; every component file imported; **0** missing `Fi*` imports; **0** `console.log`; **0** hardcoded secrets/URLs; Suspense-wrapped lazy loads.
- **5 dead nav/command entries** (`navRegistry.jsx:357-359,396-397`): `code-gen`, `code-review`, `code-integrate`, `agent-memory`, `skill-library` have no `ACTION_ITEMS` entry → click = no-op (110/115 resolve).
- 15 empty `catch {}` blocks (8 in App.jsx) silently swallow fetch failures — violates the project's own aif-fix skill-context rule.
- **BillingPanel endpoints are FINE** — reviewer claimed 7 dead `/api/plans…` URLs; manual check disproved: `API='/api/billing'` + blueprint `url_prefix="/api/billing"` + `/plans` etc. ⇒ `/api/billing/plans` ✓ (this is why manual verification matters).
- Weight note: MUI + emotion installed but essentially unused; 1.9 MB single JS chunk warning.

---

## 3. Documentation Truth Audit

| Claim (source) | Verdict | Reality |
|---|---|---|
| Version 3.7.0 (README/CONTEXT/pyproject/pkg) | ✅ VERIFIED | all synced |
| 25 agents in AGENT_REGISTRY | ✅ VERIFIED | 25 keys |
| Battle v2 56/60 = 93% | ✅ VERIFIED | `orbit_data/battle_v2_latest.json` = 0.9333 |
| Fact-cache 126 pre-seed | ✅ VERIFIED | `FACT_CACHE_SEED` = 126 |
| 126 → "180 blueprints" (README:25) | ❌ FALSE | **198** registered |
| "188 blueprints" (CONTEXT:37) / "111" (CONTEXT:314) | ❌ FALSE | 198 — three different numbers in docs |
| "112 JSX / 93 panels" (README:24), "116/138 components" | ❌ FALSE | **136** files / 119 wired (4 wrong numbers) |
| "23 tools all wired" vs "37 tools" (README:201) | ❌ CONTRADICTS ITSELF | no `TOOL_REGISTRY` exists; `honest_metrics.py:51` hardcodes 23 |
| "~1986 / 1967 Python files" (README:23,243) | ❌ FALSE | 958 (excl. venv) |
| "438 core modules" (README:28) | ❌ FALSE | 507 `.py` in `orbit/orbit/core` |
| "85% vs 20 curated keys" (README:32) vs "90.3% / 103 items" (CONTEXT) | ⚠️ STALE/CONFLICT | eval file shows 17/20; suite now has 103 items — two "objective metrics" fighting |
| Battle import `orbit.core.battle_v2` (README:268) | ❌ WRONG PATH | real path `orbit.orbit.core.*`, and that module is dead |
| "1573+ passing (2499 collected)" (CONTEXT:407) | ⚠️ STALE | today: 2,962 collected / 2,944 passing |
| "100% original code" (CONTEXT:408) | ⚠️ UNVERIFIABLE | needs provenance audit; not re-checked here |

**Pattern:** the code is more honest than the docs — numbers drifted as the project grew and were never re-derived from a single source (`honest_metrics.py` is the obvious home).

---

## 4. What's Genuinely Good (evidence-backed)
1. **ToolGate + fail-closed auth** are real, deep, and tested — not security theater.
2. **Test suite scale & honesty** — ~3,000 tests with real assertions; hermetic session key-stripping; the pre-existing 4 failures are stable and known, not flaky surprises.
3. **Frontend wiring discipline** — single-source nav registry, zero missing imports/secrets/console-noise, per-panel 1:1 render map.
4. **Today's loop quality** — 7 bugs found were all reproducible, fixed minimal, failing-first (this review re-verified their test batch).

## 5. Top Problems (priority order)
| # | Sev | Problem | Evidence |
|---|---|---|---|
| 1 | 🔴 CRITICAL | Live `ORBIT_API_KEY` in ≥5 tracked files → **in git history** | byte-match scan (11 files) |
| 2 | 🔴 HIGH | `requirements.txt:65` corrupted spec → `pip install -r` fails | `mypy>=1.5.0waitress>=3.0.0` |
| 3 | 🔴 HIGH | pyproject missing runtime deps (defusedxml/stripe/sqlalchemy/psycopg2) → clean install can't boot server | `tools/news.py:1`, `tests.yml:30` |
| 4 | 🟠 HIGH | Stripe webhook 401 behind API-key auth | `config.py:239`, `billing_bp.py:139` |
| 5 | 🟠 MED-HIGH | Kill switch/trust never gates chat/agents LLM calls | 0 hits in `core/llm/` |
| 6 | 🟠 MED-HIGH | 92/198 blueprint registrations fail silently | `server.py:195-200,841-859` |
| 7 | 🟡 MED | 47 reliability tests permanently ignored but counted in docs | `conftest.py:69` |
| 8 | 🟡 MED | Docs numbers false/self-contradictory (blueprints, components, tools, files, two conflicting accuracy metrics) | §3 table |
| 9 | 🟡 MED | 5 dead frontend nav entries + 15 empty catches | `navRegistry.jsx:357-359,396-397`, App.jsx ×8 |
| 10 | 🟡 MED | Dead code mass: `core/tools/` (100%), 8 orphans incl. headline `battle_v2.py`, dup SSRF | `git grep` 0 refs |

## 6. Suggested Fix Order (not applied — report only)
1. **Rotate `ORBIT_API_KEY`** → replace in all 11 files with `os.environ`/conftest fixture reads; then decide on history purge (filter-repo) vs accept rotation.
2. One-char fix `requirements.txt:65` (newline) + add missing deps to pyproject.
3. Add `/api/billing/webhook` to `ORBIT_API_PUBLIC_PATHS` (+ test through an auth-enabled app, not a bare Flask).
4. Fix the 4 pre-existing test failures or xfail-with-reason; un-ignore tier3 (daemon-thread fixture fix) or stop counting them.
5. Wire `kill_switch.can_act()` + trust check into `LLMRouter.generate()` main path.
6. Aggregate optional-blueprint failures into boot report; fail CI if a previously-loaded blueprint disappears.
7. Single-source docs numbers from `honest_metrics.py`; delete the conflicting accuracy claim (keep 103-item suite).
8. Frontend: add 5 missing `ACTION_ITEMS`; replace empty catches with logged toasts (aif-fix rule).
9. Remove/archive dead `core/tools/`, orphan modules, and stale README import paths.

---
**Overall grade: B−** — engineering core (tests, ToolGate, auth, frontend wiring) is genuinely strong and mostly honest; the cracks are **security hygiene (committed key), packaging integrity, silent failure paths, and documentation that overstates/stales** — all fixable within a day or two.
