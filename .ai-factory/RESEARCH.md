# Research

Updated: 2026-08-02 10:30
Status: active

## Active Summary (input for /aif-plan)
<!-- aif:active-summary:start -->
Topic:
Gap-filling round for JARVES v3.5.1 — fix the documented-but-dead and split-brain gaps found in a full codebase exploration (5 threads: boot, routing, QueenAgent, doc drift, roadmap).

Goal:
Fill the gaps between what JARVES documents and what it actually does, in dependency order:
- Phase A: Boot wiring (call the dead 18-step StartupSequence + Ollama auto-start) + Agent stack upgrade (move 22 agents + assistant.py from legacy router to core/llm/router)
- Phase B: Desktop packaging (PyInstaller .exe)
- Phase C: Cross-device sync (greenfield, needs design spike first)

Constraints:
- Desktop app only — Flask is internal API, never a web server (CONTEXT.md CRITICAL WARNING)
- Inner package `jarves/jarves/` is canonical; outer `jarves/` is thin re-exports
- All tests must stay green: suite = 1279 passing / 9 skipped / 0 failures (1423 static test fns)
- Compile-check every edited file: `python -m py_compile <file>`
- Python 3.11 (project venv at `jarves/.venv/`)
- Single canonical root `.env`; no hardcoded secrets
- Human = final authority (ToolGate PolicyEngine) — do not weaken sandbox

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

Success signals:
- Boot: `data/startup/boot_*.json` reports appear on launch; Ollama auto-starts; splash/boot report live
- Agents: every agent call returns real content via modern router; battle benchmark still 10/10; ground-truth still >=90%
- Full suite stays green: 1279 passing / 9 skipped / 0 failures
- No dead "Ollama auto-start" claim in docs without working code behind it

Next step:
Run `/aif-plan full` for Phase A (boot wiring + agent stack upgrade) as the first plan.

## Sessions
<!-- aif:sessions:start -->

### 2026-08-02 10:30 — Full codebase exploration (5 threads)
What changed:
Explored JARVES v3.5.1 from source. Confirmed working stack (22 agents, 19 tools, 80 React panels, 250 core modules, honest 1279-test suite, objective ground-truth eval 90.3%, ToolGate sandbox, battle infra). Found the gaps below.

Key notes:
- **Boot is NOT the documented 18-step sequence.** `core/startup.py` `run_startup()` has ZERO call sites outside itself; `data/startup/boot_*.json` has no reports. Real boot: launch_desktop.main() → thread: create_app() → QWebEngineView loads http://127.0.0.1:5000 → React dist. "Ollama auto-start in boot sequence" is dead code too.
- **TWO parallel LLM routers.** Legacy `jarves/jarves/router.py` (Gemini→OpenRouter→Ollama→phi3, 646 lines) is used by ALL 22 agents + assistant.py + meeting.py. Modern `jarves/jarves/core/llm/router.py` (707 lines: orchestrator chains, circuit breakers, gateway net, 126 fact seeds, category prompts) is used ONLY by chat_api, benchmark, conversation_engine, integration_test. The Day-34 "ChatGPT Competition Killer" feature set never reached the agents.
- **QueenAgent loop** (queen.py): _detect_intent_simple → _generate_plan (LLM JSON, pinned force_offline=True → Ollama) → _execute_plan (parallel threads or sequential) → _critique_and_synthesize (CriticAgent reviews + LLM blend) → _submit_feedback (SelfImprover + AgentAwareness). Adaptive dispatch swaps in best-performing agent if accuracy < 0.5.
- **Doc drift:** numbers mostly right (1279 tests ✅, 105 blueprints ≈✅, 80 panels vs "58+" undercount), but ARCHITECTURE frozen at v3.0: gui.py is 14-line shim (was "2600+ lines"), launch_desktop.py hardcodes "v3.0" splash, README is the most accurate doc. CONTEXT.md worst offender.
- **Roadmap (docs/ROADMAP.md) frozen at v3.0 (Jul 26).** Most "Intelligence" items actually shipped (MoA, RAG, autonomous, battle prep, self-improver, multi-tier memory, context manager, skills, knowledge base all verified as real classes with methods).
- **Genuinely missing:** cross-device sync (zero code), desktop packaging/installer (source-only), boot wiring (dead code), agent stack on modern router, real ChatGPT battle (key-blocked), wake word/voice cloning accuracy (deferred).

Links (paths):
- jarves/jarves/core/startup.py (dead StartupSequence, 479 lines)
- jarves/launch_desktop.py (real boot shell, 636 lines, hardcodes v3.0)
- jarves/jarves/router.py (legacy router, used by agents)
- jarves/jarves/core/llm/router.py (modern router, chat+benchmark only)
- jarves/jarves/core/llm/orchestrator.py (QueryClassifier + route tables)
- jarves/jarves/agents/queen.py (Plan→Execute→Critique→Learn)
- jarves/jarves/core/policy_engine.py (ToolGate)
- VERSION.json (v3.5.1 "Bug-Free"), README.md (most accurate doc)
- tests/ (47 files, 1279 passing claimed)
<!-- aif:sessions:end -->
