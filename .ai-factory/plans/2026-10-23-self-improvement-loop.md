# ORBIT Self-Improvement Loop — Roadmap P0 wiring plan (2026-10-23)

> Milestone: "P0: Self-Improvement System — failure analysis, lesson extraction,
> skill generation, validation, rollback, human approval gate, regression tests
> from failures. ORBIT must learn from experience (currently static)."
> Recon verdict: components EXIST in `self_improvement_v2.py` (1057 lines,
> full orchestrator) but the loop is a DEAD ISLAND — zero production callers,
> no API routes, no regression executor, no UI. Phase = WIRE the loop, don't
> rebuild it.

## S1 — Failure capture service (loop intake)
NEW `core/failure_capture.py`: `capture()` — fail-open, per-key dedup + 60s
cooldown (repeated identical errors don't flood lessons), error category
detect (timeout/empty/provider/refusal/tool/unknown), calls
`orchestrator.process_failure()`. Status counters.

## S2 — Production hooks (real failures enter the loop)
- `chat_api.py` step 6.6: final response Error/[Error/empty -> capture
  (guardrail blocks are INTENTIONAL, not failures — excluded)
- `agents/orchestrator.py` "All steps failed" -> capture
- chat_api step 6.7: inject `get_improvement_context()` (lessons+skills)
  as system suffix — closes learn -> apply direction

## S3 — API surface (loop operable + honest)
Extend `self_improvement_bp.py` under `/api/self-improvement/v2/`:
status, failures, lessons, skills, approvals, approve/<id>, reject/<id>,
regression-tests, regression/run, report (manual, for demos/e2e).

## S4 — Regression executor (tests actually RUN)
`RegressionTestGenerator.run_tests()` — bounded (default 5), executes via
legacy_adapter (short max_tokens), scores must_contain / must_not_contain /
non-empty, `record_result` pass/fail. Fail-open (LLM error = fail + logged).

## S5 — UI (zero-hidden rule)
NEW `SelfImprovementPanel.jsx` (tabs: Status/Approvals/Lessons/Skills/
Regression) + navRegistry + App wiring.

## S6 — Gates
`tests/test_self_improvement_loop.py` (capture/dedup/category/hooks/bp/
runner mocked/approve-reject), compile, ruff, fast gate, full suite,
docs (roadmap checkbox + CONTEXT + README), ONE commit.
