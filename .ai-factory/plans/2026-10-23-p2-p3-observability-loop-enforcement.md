# ORBIT P2-finalize + P3-enforcement plan (2026-10-23)

> Roadmap P2 (Observability) and P3 (Loop Detection) were largely built by the
> Phase 0-22 parallel workstream (execution_trace 411 lines wired into
> queen/chat/router/policy + TracePanel UI; loop_detector 511 lines with
> storm/retry/stall detection + recovery). Recon verdict: P2 90% done,
> P3 50% done. This phase CLOSES the remaining gaps — no rebuild.

## S1 — TaskBudget (P3 core gap)
NEW `core/task_budget.py`: per-task_id counters (iterations, runtime_s,
retries, cost_usd, tool_calls, agent_hops) with limits from env
(ORBIT_BUDGET_MAX_*). `check(task_id)` -> allowed + reason + remaining.
`record_*(task_id)` increments. Fail-open on internal errors. Singleton
`get_task_budget()`.

## S2 — Semantic loop detection (P3 gap)
In task_budget: `record_action(task_id, agent, action, result_text)` —
sha256 of (agent|action|result) hashed; same hash >= 3x in a task ->
loop_detected=True (same task + same agent + same action + same result).
`check()` also consults this.

## S3 — Orchestrator enforcement (the only real autonomous loop)
`agents/orchestrator.py` execute(): budget_id = task_id;
- before each subtask dispatch: `check()` -> if blocked, mark step
  blocked + break (emit status "budget_exhausted")
- after each dispatch: record iteration + agent_hop + action/result
- retry loop: record_retry before each retry attempt
Fail-open: budget module exception -> continue (never brick a task).

## S4 — Observability wiring (P2 dead-island fix)
- chat_api end: `get_observability().record_task(task_id, success,
  latency_ms, agent)` + `record_routing(query, agent, correct,
  confidence)` (correct = not Error; confidence from result if present)
- policy_engine `_finalize`: `record_tool(decision.action,
  decision.allowed, 0, "")` (latency unknown -> 0, honest)
- queen trace end: already traced; add record_task too (cheap, fail-open)

## S5 — API
Extend loop_detector_bp: GET /api/loops/budget/<task_id>,
GET /api/loops/budget (all active), POST /api/loops/budget/reset,
GET /api/loops/budget/limits. (observability_bp already has 9 routes.)

## S6 — Tests + gates
tests/test_task_budget.py (~20): counters, limits, semantic loop x3,
check reasons, orchestrator enforcement (mocked agents), observability
wiring presence, bp routes. Then ruff, fast gate, full suite, docs
(ROADMAP P2/P3 checkboxes, CONTEXT Day-61, README counts), ONE commit.
