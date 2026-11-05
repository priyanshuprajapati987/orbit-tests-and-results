# 🔬 ORBIT — Tests & Results (Public Evidence Repo)

> **Public evidence repository for the ORBIT AI platform.**
> This repo contains **only tests, test results, validation experiments and reports** —
> **no application source code and no blueprints** live here.

The ORBIT source code resides in a **private repository**; this repo exists so that
anyone can independently inspect *what* is tested, *how* it is verified, and *what*
the recorded results actually were.

---

## 📦 What's inside

| Path | What it is | Count |
|------|------------|-------|
| `tests/` | Full pytest test-suite of the ORBIT platform | **231 files / 4,521 tests** |
| `results/` | Machine-readable run evidence (JUnit XML, logs, coverage) | see [Evidence index](#-evidence-index) |
| `validation/` | 15 experiment scripts + their raw result JSONs/logs | 20 result artifacts |
| `.ai-factory/` | QA reports, evolution logs, patch history, plans | 49 documents |
| `ORBIT_COMPARISON.md` | Head-to-head comparison vs 7 free AI providers (live-run results) | 1 |

---

## ✅ Headline test results

| Suite | Passed | Failed | Skipped | Evidence file |
|-------|--------|--------|---------|---------------|
| **ORBIT full suite** | **4,494** | **0** | 27 | `results/full_suite_junit.xml` + `results/full_suite_run.log` |
| ORBIT fast-lane (smoke) | 52 | 0 | 0 | `results/fast_lane_junit.xml` |
| agentverse-hub (ecosystem) | 173 | 0 | 0 | `results/agentverse_hub_junit.xml` |
| omnicheat-pro (ecosystem) | 135 | 0 | 0 | `results/omnicheat_pro_junit.xml` |
| **Line coverage (core)** | **54%** (39,874 / 86,984 stmts) | — | — | `results/coverage.xml` |

> **Zero code failures.** The 27 skipped tests are *environment-gated* (see below),
> not hidden failures.

### ⏭️ Why 27 tests skip (by design)

These tests need external services that are intentionally not running on a
developer machine. They are **wired to start** via `docker-compose.yml`
(Postgres, Redis, Ollama, etc.) and skip cleanly when the service is absent:

- **Ollama / local LLM** tests → require an Ollama server
- **Network integration** tests → require outbound HTTP to live providers
- **Optional service** tests → require Docker-backed Redis/Postgres

Run `docker compose up -d` on the source repo and they execute instead of skipping.

---

## 🗂️ Evidence index

| File | Description |
|------|-------------|
| `results/full_suite_junit.xml` | Full-suite results in JUnit XML (CI-parsable) |
| `results/full_suite_run.log` | Complete raw pytest stdout/stderr of the full run |
| `results/fast_lane_junit.xml` | Smoke-suite results (battle runner + phase audit/orchestrator) |
| `results/agentverse_hub_junit.xml` | agentverse-hub backend suite |
| `results/omnicheat_pro_junit.xml` | omnicheat-pro backend suite |
| `results/coverage.xml` | Coverage.py XML report (54% line coverage) |
| `validation/results/*.json` | Raw output of 15 validation experiments (memory, learning, concurrency, quality-gate, multi-agent value, error-recovery, full-pipeline …) |
| `validation/results/*.log` | Full run logs of the validation harness |
| `validation/claim_verification_table.md` | Every product claim → verification status |
| `.ai-factory/qa/` | Full-system QA reports |
| `.ai-factory/evolution/`, `.ai-factory/patches/` | Iteration history: bugs found → fixes applied |

---

## 🔁 How to reproduce

```bash
# Full suite (≈20 min, Windows note: set TEMP inside the workspace)
export TEMP="$PWD/.pytest_tmp" TMP="$PWD/.pytest_tmp"
python -m pytest tests/ -q --junitxml=results/full_suite_junit.xml

# Smoke suite (≈20 s)
python -m pytest tests/test_battle_runner.py tests/test_phase1_audit.py \
                 tests/test_phase2_orchestrator.py -q

# Coverage
python -m pytest tests/ -q --cov=orbit --cov-report=xml:results/coverage.xml
```

*Prerequisite:* the ORBIT source tree (private repo) must be present, since these
are its test-suite. This repo carries the tests + recorded evidence only.

---

## 🧪 Validation experiments

`validation/` contains reproducible experiments with raw results:

- **Memory effectiveness** — retrieval quality with/without ORBIT memory store
- **Learning effectiveness** — does the agent improve over repeated tasks
- **Concurrency stress** — parallel agent runs, lock behaviour
- **Error recovery** — injected failures, graceful degradation
- **Multi-agent / smartrouter value** — routing vs direct model calls
- **Quality gate** — output gating pass rates
- **Real-world task suite** — 10 end-to-end task benchmark

> Honest read of `validation/results/validation_summary.json`: read-only tools
> pass reliably, some write-path issues were found **and** logged — this repo
> keeps the raw data, including the not-flattering parts.

---

## 🔐 Security / secret-scanning policy

- This repo is scanned by **GitHub secret scanning + push protection**.
- Test fixtures use **fake, non-flaggable credentials** (sanitized so they never
  match real-key patterns of Google/Stripe/AWS/GitHub/OpenAI/Slack).
- Published JUnit XML uses stable scanner-safe **`ids=` labels** for parametrized
  tests, so fixture literals never appear inside results files either.
- **No real API keys, tokens or secrets** are — or ever were intended to be — here.
  A flagged Google-format fixture and a Stripe-format fixture were found during the
  initial publish, sanitized, and the history was rewritten; the alert was resolved
  as `used_in_tests`.

---

## 🔗 Links

- **Source (private):** https://github.com/priyanshuprajapati987/jarves
- **This repo (public):** https://github.com/priyanshuprajapati987/orbit-tests-and-results
- **AI comparison write-up:** [`ORBIT_COMPARISON.md`](./ORBIT_COMPARISON.md)

---

*Last updated: 2026-11-05 — full suite: 4,494 passed / 0 failed / 27 env-skipped.*
