# Project Roadmap

> ORBIT v3.7.0 -- AI Operating System ("The Demons Army")
> Build a world-class AI assistant that is reliable, self-improving, and production-ready.
> Deadline: January 2027

## Milestones

- [x] **P0: Self-Improvement System** -- Failure analysis, lesson extraction, skill generation, validation, rollback, human approval gate, regression tests from failures. ORBIT must learn from experience (currently static). *(2026-10-23: components existed in `self_improvement_v2.py` but were a dead island — wired the closed loop: `failure_capture.py` intake (chat_api + agent orchestrator hooks + 60s dedup), context injection into next prompt, 11 v2 API routes, regression executor, `SelfImprovementPanel.jsx`.)*
- [x] **P1: A2A Protocol** -- Agent Card, identity, capability discovery, task submission/status/results, authentication, authorization, message signing, replay protection, multi-tenant isolation. Gateway architecture: External Agent -> A2A Gateway -> Auth -> Permission/Trust -> ToolGate -> ORBIT Agent.
- [x] **P2: Observability -- Execution Traces** -- Full execution trace per task: agent, model, tool, input/output, duration, tokens, cost, error, retry, security decision, parent/child tasks. Task -> Execution Trace UI. 25 agents + 20 tools = debugging is impossible without this. *(Done: execution_trace.py + TracePanel UI already wired by Phase 0-22; closed 2026-10-23 — observability dashboard feed wired into chat_api [task+routing] and policy_engine [tool success], previously a dead island with zero callers.)*
- [x] **P3: Loop Detection** -- Per-task limits: max_iterations, max_runtime, max_retries, max_cost, max_tool_calls, max_agent_hops. Semantic loop detection: same task + same agent + same action + same result = stop/replan. 25-agent autonomous system needs this as basic safety. *(loop_detector.py storm/retry/stall detection existed from Phase 0-22; closed 2026-10-23 — new core/task_budget.py: per-task budgets + semantic loop detection, enforced in PipelineOrchestrator [check before each dispatch, blocked steps report reason, status budget_exhausted/loop_detected], fail-open; budget API at /api/loops/budget*; wired record_agent_dispatch callers.)*
- [ ] **P4: Agent Permission Hardening** -- Per-agent capability allowlist, per-task permissions, privilege escalation prevention, expiring permissions, permission audit, cross-agent authorization. Every agent call must pass: Identity -> Trust -> Requested Capability -> ToolGate -> Risk -> Policy -> Execution.
- [ ] **P5: Memory Poisoning Protection** -- Memory entries need: source, timestamp, confidence, provenance, agent, verification status. Don't auto-treat user claims as facts. Unverified -> Memory pipeline. Protects against bad information persisting into future context.
- [ ] **P6: MCP Server Mode** -- Expose ORBIT's 20 tools as MCP server. External AI -> MCP -> ORBIT -> ToolGate -> Agent/Tool. Exposable: Search, Files, Code, Browser, Research, Memory, Tasks, GitHub, PDF, Automation. Every MCP request must pass through ToolGate.
- [ ] **P7: Supply Chain Security** -- Integrate dependency scanner into pipeline: Dependency -> Version -> Vuln scan -> License check -> Package reputation -> Approval -> Install. Same system for MCP servers/plugins/skills. Critical because ORBIT will use MCP server + self-improving skills.
- [ ] **P8: Human-Agent Trust Protection** -- Confidence indicators, evidence provenance, uncertainty disclosure, high-risk confirmation, no fake authority claims. Replace "I am 100% sure" with "Confidence: 62%, Evidence: 3 sources, Verification: Partial". OWASP ASI09 gap.
- [ ] **P9: Evaluation System Upgrade** -- Static benchmark -> dynamic benchmark. Production failures -> regression tests -> benchmark dataset. Track: accuracy, reliability, latency, cost, tool success rate, agent success rate, regression rate. Connects directly to self-improvement system.
- [ ] **P10: Learned Router Benchmarking** -- Actual benchmark: 100/500/1000 queries through static router vs learned router. Measure: accuracy, cost, latency, strong/weak model usage, failure rate. Don't assume 35-85% savings -- prove it.

## Known Follow-Ups (Tech Debt)

Carried over from Phase A refinement (2026-09-21) -- recorded here because `.ai-factory/plans/phase-a-boot-routing.md` is never staged/committed:

- [ ] Consolidate routing config -- three independent sources of truth: `PROVIDER_ROUTING` in `config.py`, `PROVIDER_ROUTING` in `core/config.py`, and `ModelRouter.routing_table` in `model_router.py` (route the same task types differently); needs one source of truth.
- [ ] Document `core/llm/__init__.py` exports -- it exports modern `generate`/`generate_offline`, NOT the facade; agents must explicitly import `legacy_adapter`. No doc says when to use which.
- [ ] Unify task classifiers -- `ModelRouter.analyze_task()` (model_router.py:217-261) and `QueryClassifier` (orchestrator.py) use different keywords and can classify the same prompt differently.
- [x] Wire legacy-fallback through safety systems -- DONE Day 54: kill switch / trust checks at adapter entry (Day-46) + audit / trust usage / breaker recorded by `_safety_record()` in `_legacy_generate()` (record-only, fail-open). See CONTEXT.md "Legacy Fallback Safety Gap — CLOSED".

## Deferred (NOT now)

- **P11: Cross-Platform Architecture** -- Core UI-independent. Web + Desktop + API. React frontend already partially there. No full rewrite needed yet.
- **P12: TypeScript SDK** -- ORBIT API -> Python SDK + TypeScript SDK. Useful for web apps, third-party integrations, plugins. Abhi mat karo.
- **Extra agents, extra UI panels, random new tools** -- 25 agents + 20 tools + 147 blueprints already enough breadth. Go deeper, not wider.

## Completed

| Milestone | Date |
|-----------|------|
| RouteLLM integration | 2026-08-25 |
| 3 bug fixes (mobile_api, device_manager, incident_actions) | 2026-08-25 |
| Dead code removal (fused_senses, pform, sim_lab, ambient_bp, lab_bp) | 2026-08-25 |
| Dependency scanner | 2026-08-25 |
| Providers status caching (60s TTL, 2325x speedup) | 2026-08-25 |
| Security audit (no hardcoded secrets, eval safe, CSP active) | 2026-08-25 |
| Stress test (1160 requests, 0 errors) | 2026-08-25 |
| Full API smoke test (21 GET + 3 POST + 14 specific) | 2026-08-25 |
| Layout fixes (inverted prefixes, right panel, chat No response) | 2026-08-25 |
| .env cleanup + .env.example | 2026-08-25 |
| Cookie-based auth fallback | 2026-08-25 |
| Voice fixes (pydub, edge_tts lazy import, ffmpeg) | 2026-08-25 |
| 3 panels theme fix (LearnedRouter, MCP, SmartBrowser) | 2026-08-25 |
| Suggestion chips clickable | 2026-08-25 |
| voice_bp.py error handling (all 9 endpoints) | 2026-08-25 |
| 7 missing panel close buttons | 2026-08-25 |
| Shared agent colors (agents.js constant) | 2026-08-25 |
| Escape key close any panel | 2026-08-25 |
| Dead components removed (StatusBar, AgentActivityFeed, CommandCenter, AppShell) | 2026-08-25 |
| Auth tests fixed (/api/agents public, /api/watchdog/status) | 2026-08-25 |
| Agentic AI Research Report (4 parts) | 2026-08-25 |
| ORBIT vs Industry Gap Analysis PDF | 2026-08-25 |
| ToolGate security (PolicyEngine, 76 actions, sandbox, audit) | 2026-08-16 |
| Kill Switch + Agent Trust Manager + LLM Audit | 2026-08-06 |
| Hand Gesture Control | 2026-08-06 |
| Security Guard (codebase scan, defense checks) | 2026-08-16 |
| Boot wiring (18-step StartupSequence) | 2026-08-02 |
| Unified LLM Router (legacy_adapter facade) | 2026-08-02 |
| PyInstaller desktop packaging | 2026-08-02 |
| CSP fix (fonts + inline styles) | 2026-08-02 |
| Smart Memory + Task Continuity + Proactive Context | 2026-08-09 |
| Voice-Screen vertical | 2026-08-16 |
| Battle benchmarking (A/B vs ChatGPT) | 2026-07-31 |
| Ground-truth eval (103 items, 90.3%) | 2026-08-01 |
| Fact cache seed (126 items) | 2026-08-01 |
| Optimization engine (playbooks, weak prompts) | 2026-08-01 |
| Reliability engine (quota, rate-limit, death detection) | 2026-07-31 |
| Fallback chain (speculative parallel, 100ms stagger) | 2026-07-31 |
| Monitoring (uptime, crash recovery, auto-restart) | 2026-07-31 |
| Autonomous conversation runner | 2026-07-31 |
| Context manager (3-layer: live/chunks/summary) | 2026-07-31 |
| Conversation engine (state machine, CoT, web-grounding) | 2026-07-31 |
| Semantic similarity (TF-IDF + char n-gram + embeddings) | 2026-07-31 |
| Circuit breaker (3 states, threshold=5) | 2026-07-31 |
| QueenAgent Plan->Execute->Critique loop | 2026-07-30 |
| CriticAgent (compile checks + fact verification) | 2026-07-30 |
| ExecutorAgent (WebSearch + FileTools + GitHub + Browser) | 2026-07-30 |
| 22 agents fully wired | 2026-07-19 |
| 20 tools with API + frontend + tests | 2026-07-19 |
| 147 Flask blueprints | 2026-07-18 |
| 99 React components | 2026-07-18 |
| Voice pipeline (Edge-TTS + XTTS + Vosk) | 2026-07-18 |
| Memory system (3-layer) | 2026-07-18 |
| Personality system (Tony Stark) | 2026-07-18 |
