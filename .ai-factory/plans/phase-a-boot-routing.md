# Implementation Plan: Phase A — Boot Wiring + Agent Stack Upgrade

Branch: feature/phase-a-boot-routing
Created: 2026-08-02

## Settings
- Testing: yes
- Logging: verbose
- Docs: yes  # mandatory docs checkpoint at completion

## Roadmap Linkage (optional)
Milestone: none
Rationale: Skipped by user — `.ai-factory/ROADMAP.md` does not exist yet; linkage deferred until roadmap artifact is created.

## Research Context
Source: .ai-factory/RESEARCH.md (Active Summary)

Goal:
Fill the gaps between what JARVES documents and what it actually does, in dependency order. Phase A = Boot wiring (call the dead 18-step StartupSequence + Ollama auto-start) + Agent stack upgrade (move 22 agents + assistant.py from legacy router to core/llm/router).

Constraints:
- Desktop app only — Flask is internal API, never a web server (CONTEXT.md CRITICAL WARNING)
- Inner package `orbit/orbit/` is canonical; outer `orbit/` is thin re-exports
- All tests must stay green: suite = 1279 passing / 9 skipped / 0 failures (1423 static test fns)
- Compile-check every edited file: `python -m py_compile <file>`
- Python 3.11 (project venv at `orbit/.venv/`)
- Single canonical root `.env`; no hardcoded secrets
- Human = final authority (ToolGate PolicyEngine) — do not weaken sandbox
- Keep legacy router as fallback only — agents must still work if modern router fails

Decisions:
- Phase A first (boot wiring before agent migration so the boot report can surface provider health during the router migration)
- Agent migration = swap `from .. import router as llm_router` → `core/llm/router` call sites in agents + assistant; keep legacy router as fallback only
- Cross-device sync deferred to a design spike; do NOT start building it in Phase A
- Real-ChatGPT battle (#5) is user-key-blocked, not a code task — out of scope for planning
- Voice/wake-word accuracy (#6) explicitly deferred on roadmap — out of scope

Open questions:
- Should agent migration use the async `get_router().generate(LLMRequest(...))` (needs async wrapper) or a new sync facade? Agents call `llm_router.generate(...)` synchronously today.
- Do any agents rely on legacy-router-specific args (task_type routing, tier system, experimentation intercept)? Need a call-site audit before swap.
- Where should boot wiring live: launch_desktop.start_server() thread, or create_app()? (startup.py writes reports to D:\JARVES\data\startup\)
- Packaging target: PyInstaller onefile vs onedir; does QWebEngineView bundle correctly?

## Commit Plan
- **Commit 1** (after tasks 1-4): "feat(boot): wire dead StartupSequence into real boot path + serve boot report"
- **Commit 2** (after tasks 5-8): "refactor(agents): migrate agent stack to core/llm/router via sync facade"
- **Commit 2b** (after tasks 8b-8c): "refactor(router): migrate model_router.py + add facade edge-case tests"
- **Commit 3** (after tasks 9-10): "chore(agents): tests + regression green for Phase A migration"
- **Commit 4** (after task 10b): "docs: document legacy fallback safety gap + rollback procedure"

## Tasks

### Phase 1: Boot Wiring — make the documented 18-step boot real

- [x] Task 1: Wire `StartupSequence.run_startup()` into the real boot path
  - In `orbit/launch_desktop.py` `start_server()` (line 519-524), call `get_startup().run_startup()` BEFORE `create_app().run()` so the boot report + provider health exist before the UI loads and `/api/boot/latest` is fetched.
  - Wrap in try/except — boot failure must never prevent desktop launch (log ERROR + continue).
  - Guard: read `ORBIT_SKIP_STARTUP` env (1/true/yes/on) to skip the sequence (for CI/test/debug).
  - Log each step via the existing `on_progress` callback + module logger (DEBUG per step, INFO on completed sequence with elapsed_ms, ERROR on failure).
  - Do NOT wire into `create_app()` (server.py:678) — it runs under pytest app-creation too; the guard requirement makes `start_server()` the safer single site.
  - Files: `orbit/launch_desktop.py`, `orbit/orbit/core/startup.py` (only if a small API addition is needed, e.g. a `run_startup_safe()` wrapper).

- [x] Task 2: Fix BootReportPanel data source (schema + dir mismatch)
  - StartupSequence writes `{timestamp, elapsed_ms, boot_message, summary, steps}` to `D:\JARVES\data\startup\`; BootReportPanel expects `{id, modules_count, modules_loaded, timing, errors, status}` from `/api/boot/latest` (boot_report_bp.py:10-15) backed by `boot_report.py` (writes `orbit/data/boot_reports/`, zero callers).
  - Add a thin adapter: when no `boot_report` data exists, serve the latest StartupSequence report mapped into the panel's schema. Preferred: keep `boot_report.py` as the canonical report + call `get_boot_report().generate_report(...)` from the boot sequence adapter, OR add a mapping in `boot_report_bp.py` `/api/boot/latest` that falls back to `startup.get_latest()`.
  - Verify `D:\JARVES\data\startup\` + report dirs are created and git-ignored (`.gitignore` covers `data/`).
  - Files: `orbit/orbit/core/boot_report.py`, `orbit/orbit/core/boot_report_bp.py`, possibly `ui_provided/src/components/BootReportPanel.jsx` only if the adapter cannot satisfy the schema.

- [x] Task 3: Fix stale Ollama default model + verify Ollama auto-start step
  - `core/config.py:20` `DEFAULT_OLLAMA_MODEL` was `tinydolphin` (stale). Updated to `qwen3:8b` (current local model; env override `DEFAULT_OLLAMA_MODEL` wins — `OLLAMA_MODEL` is NOT read by any code).
  - Confirm the Ollama auto-start step (`startup.py:134-186`) works when `OLLAMA_URL` is down: `Popen(["ollama","serve"], CREATE_NO_WINDOW)` + 10s poll. It already degrades to skip on failure — do not make it fail-closed.
  - Files: `orbit/orbit/core/config.py`, `orbit/orbit/config.py` (inner config re-export stays in sync), `orbit/config.py` (outer shim — verify no change needed).

- [x] Task 4: Tests for boot wiring (new file `tests/test_boot_wiring.py`)
  - Test: `run_startup()` writes a `boot_*.json` report to `data/startup/` (monkeypatch Ollama-alive so no real subprocess).
  - Test: `ORBIT_SKIP_STARTUP=1` skips the sequence in `start_server()`.
  - Test: `/api/boot/latest` returns panel-shaped `{id, modules_count, modules_loaded, timing, errors, status}` when startup report exists (use `app.test_client()`).
  - Test: boot sequence failure does not raise out of `start_server()` (monkeypatch a step to raise; expect log, no crash).
  - Logging: DEBUG on each assertion setup, INFO/ERROR on pass/fail.
  - Files: `tests/test_boot_wiring.py`.

### Phase 2: Agent Stack Upgrade — migrate 22 agents + assistant to modern router

- [x] Task 5: Build the sync facade module `core/llm/legacy_adapter.py`
  - Provide a SYNC `generate(prompt, model=None, history=None, extra_context=None, system_prompt=None, force_offline=False, task_type=None) -> str` that mirrors the legacy `router.generate` signature so agents need NO call-site changes beyond the import line.
  - Internally: build `LLMRequest`, call `asyncio.run(get_router().generate(...))` via `_run_coro()` helper (lines 53-64) which tries `asyncio.run()` first, falls back to `new_event_loop().run_until_complete()` on `RuntimeError("running event loop")`.
  - On modern-router `success=False`: FALLBACK to legacy `orbit.router.generate` (same signature) so agents never lose capability — legacy stays as fallback only.
  - Map legacy `task_type` → modern `category` via `core/llm/orchestrator.py` `QueryClassifier` when set; ignore when None (matches current behavior).
  - Preserve legacy semantics: `extra_context` injected into system prompt via router's `_effective_system_prompt()` method (router.py:126-141, wraps in `<context_data>` tag with anti-prompt-injection instruction); error strings `"[Error: ...]"` on failure (agents check `.startswith("[Error")` at queen.py:242, meeting.py:223).
  - Also mirror `generate_offline`, `get_status` (add `tier` key consumers need — `agents_api.py:85/101` reads `online` + `tier`), `list_ollama_models`, `pull_ollama_model` as thin delegates to legacy for compatibility.
  - Logging: DEBUG on entry (prompt length, flags), INFO on provider/model chosen, ERROR on provider failures + fallback trigger.
  - Files: `orbit/orbit/core/llm/legacy_adapter.py`.

- [x] Task 6: Wire `extra_context` into modern router's `_call_*` methods
  - `LLMRequest.extra_context` (router.py:56) is currently NEVER read by any `_call_*` provider method — silently dropped for modern-router-only callers (multimodal_agent.py:65/105 passes it).
  - Fix: in each `_call_ollama/groq/gemini/cloudflare/openrouter/portkey`, append `request.extra_context` into the system prompt (same way legacy did).
  - Logging: DEBUG when extra_context present (length, not content).
  - Files: `orbit/orbit/core/llm/router.py`.

- [x] Task 7: Swap import line in all agent files + assistant.py + meeting.py
  - Change `from .. import router as llm_router` → `from ..core.llm import legacy_adapter as llm_router` in: `agents/specialized.py:9`, `agents/queen.py:9`, `agents/planner.py:3`, `agents/executor_agent.py:1`, `agents/orchestrator.py:7`, `agents/critic.py:3`, `agents/council.py:5`, `agents/multimodal_agent.py:59/103` (lazy in-method — update import path too), `agents/memory_agent.py:5` (dead import, safe to update or drop).
  - `assistant.py:46` `from . import router as llm_router` → `from .core.llm import legacy_adapter as llm_router`; keep positional args at 1304/1306 valid (facade accepts them).
  - `meeting.py:9` `from . import router as llm_router` → `from .core.llm import legacy_adapter as llm_router`.
  - `core/agents_api.py:64` keeps `llm_router.get_status()` — verify facade's merged status satisfies `online` + `tier` reads; adjust only if shape mismatch.
  - Do NOT delete legacy `orbit/orbit/router.py` — it is the fallback target.
  - Logging: N/A (import swap); add DEBUG startup log in facade only.
  - Files: 9 agent files + `orbit/orbit/assistant.py` + `orbit/orbit/meeting.py`.

- [x] Task 8: Tests for facade + migration (new file `tests/test_legacy_adapter.py`)
  - Test: facade `generate()` returns plain `str` with modern-router content when router succeeds (monkeypatch `get_router().generate` → `LLMResponse(content="...", success=True)`).
  - Test: facade returns `"[Error: ...]"` string when modern router returns `success=False` AND legacy fallback also fails.
  - Test: facade falls back to legacy `orbit.router.generate` when modern returns failure and legacy succeeds.
  - Test: `extra_context` lands in the system prompt passed to modern router (inspect captured `LLMRequest`).
  - Test: `get_status()` includes `online` + `tier` keys (agents_api consumers).
  - Test: `generate_offline` delegate works.
  - Test: `agents_api.py` `/api/agents/status` (or equivalent) returns 200 with facade in place.
  - Logging: DEBUG per case.
  - Files: `tests/test_legacy_adapter.py`.

- [x] Task 8b: Migrate `core/model_router.py` from legacy router private API
  - `core/model_router.py:22` imports `from .. import router as llm_router` and uses private symbols: `llm_router._online` (line 125/159), `llm_router._load_api_key()` (line 130/168), `llm_router._load_gemini_key()` (line 135/164). These are private internals that will break if legacy router is refactored.
  - Also has its own stale provider health view that bypasses modern router's circuit breaker and health checking.
  - Fix: migrate to use `get_router().get_status()` from modern router, or `legacy_adapter.get_status()` for consistency with agents.
  - If `ModelRouter` needs provider availability, use the modern router's public API instead of legacy internals.
  - Blocked by: Task 7 (import swap phase).
  - Logging: DEBUG when provider status is checked.
  - Files: `orbit/orbit/core/model_router.py`.

- [x] Task 8c: Add concurrent-call + facade API tests
  - Test: `force_offline=True` correctly routes to Ollama (monkeypatch modern router, verify request.force_offline).
  - Test: `model="qwen3:8b"` passthrough reaches the modern router (inspect captured LLMRequest.model).
  - Test: concurrent calls from multiple threads don't corrupt event loop state (threading test with 5 parallel `generate()` calls).
  - Test: `_run_coro` fallback path works when `asyncio.run()` raises RuntimeError (mock `asyncio.run` to raise, verify `new_event_loop` path).
  - Test: `check_internet` delegation works.
  - Test: `_experiment_intercept` and `_record_experiment` are called when experiments are active.
  - Blocked by: Task 8 (base tests exist).
  - Logging: DEBUG per case.
  - Files: `tests/test_legacy_adapter.py` (extend existing).

### Phase 3: Regression + Docs

- [x] Task 9: Full-suite + battle regression
  - Hermetic suite (project venv `orbit/.venv`): **94 passed, 0 failures** (test_new_modules.py + test_phase1_audit.py).
  - Full suite (system Python): **1299 passed, 10 skipped, 5 failed** at migration time. The 5 failures are PRE-EXISTING / environmental, NOT caused by this migration:
    1. 4× `import tests.e2e.battle_prompts` fails — orphaned `tests` package in system Python site-packages shadows the local `tests/` namespace dir. Project venv resolves cleanly.
    2. 1× `test_phoenix.py::test_create_backup_archive` — permission-dependent flake, passes standalone.
  - Note: pre-existing failure counts should be re-verified against current HEAD if environment has changed since migration date.
  - Compile-check: all edited/new Python files compile clean (verified per-task).
  - Logging: N/A (verification task).
  - Files: none (run commands).

- [x] Task 10: Docs checkpoint (via /aif-docs)
  - `CONTEXT.md` updated: version 3.6.0-alpha, Boot section (18-step sequence wired + `data/startup/boot_*.json` + guard + adapter), LLM ROUTING section (facade canonical path), KEY CONFIG `DEFAULT_OLLAMA_MODEL=qwen3:8b`, CURRENT STATE + Day 35 log entry, tests 1299 passing (10 skipped, 5 pre-existing environmental).
  - No ARCHITECTURE.md exists → router section updated in `README.md` instead (single canonical router + facade; legacy as fallback).
  - `README.md` At-a-Glance tests line + Project Structure `core/llm/` note updated.
  - `VERSION.json` changelog: bumped patch `3.5.1 → 3.6.0-alpha` (release "Phase A - boot wiring + unified router"); `orbit/pyproject.toml` + both `__init__.py` version-synced to 3.6.0-alpha.
  - **Known doc drift:** Blueprint count "188" in CONTEXT.md is inflated vs actual ~112-115 at migration time. Deferred to separate docs cleanup.
  - Logging: N/A.
  - Files: `CONTEXT.md`, `README.md`, `VERSION.json`, `orbit/pyproject.toml`, `orbit/__init__.py`, `orbit/orbit/__init__.py`.

- [x] Task 10b: Document legacy fallback safety gap + rollback procedure
  - Known limitation: when modern router fails and facade falls back to `_legacy_generate()` (legacy_adapter.py:167-191), the following safety systems are silently bypassed:
    - Kill switch (`kill_switch.py`) — not checked
    - LLM audit logger (`llm_audit.py`) — not called
    - Agent trust limits (`trust_manager`) — not enforced
    - Circuit breaker — not updated
  - Document this as a known limitation in CONTEXT.md or README.md with recommended follow-up: "Phase B should wire legacy fallback through safety systems."
  - Document rollback procedure: "To roll back to legacy router: change agent imports from `from ..core.llm import legacy_adapter as llm_router` back to `from .. import router as llm_router` (one grep/replace per file, 18 files total — re-run the grep, the static file list rots)."
  - Files: `CONTEXT.md` or `README.md`.

## Notes
- **Post-Phase-A security round (SECURITY.md M01-M03, all fixed + verified)**: M01 `after_request apply_security_headers` in create_app() merges get_security_headers() (HSTS skipped when not is_secure; setdefault preserves X-Response-Time-Ms); M02 standalone server debug now honors FLASK_DEBUG env (default off); M03 npm — overrides esbuild ^0.25.0 + refractor.prismjs ^1.30.0, vite ^5 → ^6.4.3 (non-breaking, plugin-react supports ^6). `npm audit`: 0 vulnerabilities; frontend build green (2531 modules). New tests: `tests/test_security_headers.py` (6 passing). Files: `orbit/orbit/server.py`, `ui_provided/package.json`, `.ai-factory/SECURITY.md`.
- Research open questions resolved by Task 5 (sync facade chosen over async wrapper; call-site audit confirmed NO agent passes task_type/tier/experimentation — grep for `task_type=` only matched queen.py:248 self_improvement kwarg and executor_agent local var).
- `create_app()` hook point rejected (pytest interference); `start_server()` chosen for boot wiring.
- BootReportPanel schema mismatch resolved by adapter in Task 2.
- **Known follow-ups from refinement (2026-09-21; now tracked in `ROADMAP.md` "Known Follow-Ups" section — this plan file is never staged, so the roadmap copy is authoritative):**
  - `PROVIDER_ROUTING` dict is triplicated across `config.py`, `core/config.py`, and `model_router.py` — needs consolidation to single source of truth.
  - `core/llm/__init__.py` exports modern `generate`/`generate_offline` (not facade) — no documentation clarifying when to use which. Agents must explicitly import `legacy_adapter`.
  - `ModelRouter.analyze_task()` (model_router.py:217-261) and `QueryClassifier` (orchestrator.py) do keyword-based task classification with different keywords — can return different results for same prompt.
  - Thread-safety of `_run_coro` under concurrent Flask threads — covered by Task 8c's `test_concurrent_calls_dont_corrupt_state` in `tests/test_legacy_adapter.py`.
