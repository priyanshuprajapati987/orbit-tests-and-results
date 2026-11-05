# ORBIT Bug-Fix Loop Report

Run: `orbit-bugfix-loop-20260930-181615` | Iterations 1-2 | Phase A+B (PRODUCE)

## Summary

Found and fixed **4 real bugs** in `orbit/orbit/core/*.py`. Each bug was reproduced first with a concrete failing scenario, then fixed with a minimal, scoped diff, then locked in with regression tests in `tests/test_loop_fixes_iter1.py` (12 tests, all passing).

| metric | value |
|---|---|
| bugs_found | 4 |
| bugs_fixed | 4 |
| regression tests added | 12 |
| tests_run | 247 |
| tests_passed | 247 |
| tests_failed | 0 |
| bugs found (cumulative, iter 1+2) | 7 |
| bugs fixed (cumulative, iter 1+2) | 7 |
| regression batch (cumulative, iter 1+2) | 142 passed / 0 failed |

Bug classes covered: wrong constant (1000x unit error), wrong calendar convention (cron day-of-week), state that never rolls over (habit streak frozen forever), and destructive error recovery (silent data loss on corrupt JSON).

No unrelated reformatting, no refactors, no version bump, no commits.

## Bugs

### BUG-1: Unit converter milligram factor is 1000x wrong (mass base unit is kg)

- **File:** `orbit/orbit/core/unit_converter.py:21`
- **Root cause:** `CONVERSIONS["mass"]` uses `kg` as the base unit (`kg=1`, `g=0.001`, `oz=0.0283495`, `lb=0.453592`), but `mg` was declared as `0.001` — identical to `g`. Milligrams were therefore treated as grams. Measured before the fix: `convert(1000, "mg", "g") -> 1000.0` (should be `1.0`), `convert(1, "g", "mg") -> 1.0` (should be `1000.0`), `convert(1, "mg", "kg") -> 0.001` (should be `0.000001`). Reachable through the public API (`unit_converter_bp.py` `/api/converter/convert`) and the chat assistant's conversion intent path.
- **Fix:** `"mg": 0.001` -> `"mg": 0.000001`. One-line change to the constant; no other unit was wrong (length/speed/data/time factors verified against their base units).
- **Verification:** `py -m pytest tests/test_loop_fixes_iter1.py -k unit_converter -q` -> `2 passed`. Failing-first: both tests failed before the fix.

### BUG-2: Cron day-of-week matched Python weekday() (0=Monday) instead of cron convention (0=Sunday)

- **File:** `orbit/orbit/core/smart_scheduler.py:47` (`_cron_matches`), new helpers at `smart_scheduler.py:95` (`_cron_dow_part`) and `smart_scheduler.py:120` (`_cron_dow_matches`)
- **Root cause:** `_cron_matches` put `("dow", dt.weekday())` in its field list and compared cron pattern integers straight against `datetime.weekday()` (Monday=0..Sunday=6). Cron defines day-of-week as Sunday=0..Saturday=6 (7 also = Sunday), so every `dow` pattern was shifted by one day. Measured before the fix: `0 0 * * 0` matched Monday and **not** Sunday; `0 0 * * 6` (Saturday) never matched anything; `0 0 * * 5` (Friday) never matched. The sibling scheduler `task_scheduler._cron_next_run` already remaps cron dow -> Python weekday, so the two schedulers disagreed about the same cron syntax. Exposed via `smart_scheduler_bp.py` `POST /api/scheduler/cron`.
- **Fix:** Removed `dow` from the shared field loop and added `_cron_dow_matches` / `_cron_dow_part`, which convert the timestamp to cron dow with `(dt.weekday() + 1) % 7` and handle the full cron dow grammar: plain values, `7`->Sunday, comma lists (OR-joined, as cron requires), ranges with `7` expansion (`5-7` = Fri,Sat,Sun), and steps (`*/2`, `6/2`). Minute/hour/day/month handling is untouched.
- **Verification:** `py -m pytest tests/test_loop_fixes_iter1.py -k "cron or smart_scheduler" -q` -> `3 passed`. Failing-first: all 3 failed before the fix (`0 0 * * 0` on Sunday returned `False`).

### BUG-3: `completed_today` never rolls over — a daily habit can only be completed once ever (streak frozen at 1)

- **File:** `orbit/orbit/core/habit_tracker.py:204` (`complete_habit`), fixed by `habit_tracker.py:142` (`_sync_completed_flags`) / `habit_tracker.py:136` (`_completed_on`); also `uncomplete_habit` (`habit_tracker.py:232`), `get_report` (`:279`), `reset_daily` (`:314`)
- **Root cause:** `completed_today` was a sticky boolean that nothing ever cleared. The only code that set it back to `False` was `reset_daily()`, and `POST /api/habits/reset-daily` has **no caller anywhere in the repo** (backend or frontend), so after the first completion the flag stayed `True` forever and every later `complete_habit` early-returned — the habit could never be marked on day 2, and `streak`/`best_streak` were permanently frozen at 1. A second, related defect: the `already_today` history guard ran *after* the `streak += 1`, so `complete -> reset-daily -> complete` on the same day produced `streak=2` with a single history row (measured: `streak 2`, `history` length 1). `uncomplete_habit` had the same stale-flag dependency and silently no-oped. The flag was also displayed stale on a new day (`get_habit().completed_today == True` when history only held yesterday's entry).
- **Fix:** History is now the source of truth. Added `_completed_on(habit, date)` and `_sync_completed_flags()` (re-derives `completed_today` from today's history rows), called under the existing lock from `list_habits`, `get_habit`, `complete_habit`, `uncomplete_habit` and `get_report`; `reset_daily()` now performs that rollover instead of blindly clearing flags. `complete_habit` and `uncomplete_habit` gate on `_completed_on(h, today)` instead of the flag, which makes same-day completion idempotent (streak no longer inflates) and un-blocking on the next day. Streak/history writes are now copied before mutation so the guard and the increment can never disagree.
- **Verification:** `py -m pytest tests/test_loop_fixes_iter1.py -k habit -q` -> `3 passed`. Failing-first: all 3 failed before the fix (streak frozen, `streak=2` after duplicate completion, `uncomplete` no-op).

### BUG-4: Corrupt `ideas.json` is silently replaced by stock ideas (user data loss), wrong-shaped JSON crashes every call

- **File:** `orbit/orbit/core/idea_vault.py:91` (`_load`), `idea_vault.py:133` (`_save`)
- **Root cause:** `_load()` did `json.loads(...)` into `self._ideas`, then `if not self._ideas: seed PRELOADED_IDEAS`. So (a) unparseable/truncated content became `[]` and was immediately overwritten with the 5 stock ideas — the user's file vanished with no trace (measured: a file containing `[{"id":"user1","title":"MY IDEA"` came back as the 5 stock ideas, and `ideas.json.corrupt` was never created); (b) an explicitly empty `[]` (user deleted all ideas) was reseeded too; (c) a *valid but wrong-shaped* JSON value such as `{"not":"a list"}` was stored as a dict, after which `list_ideas()` raised `AttributeError: 'str' object has no attribute 'get'` and `add_idea()` raised `AttributeError: 'dict' object has no attribute 'append'` on every call — the API 500'd permanently. `goal_tracker._load` and `habit_tracker._load` were already hardened against exactly this class of failure (isinstance check + quarantine), `idea_vault` was not. `_save()` additionally used a non-atomic `write_text` (truncate-then-fill), so a crash mid-write is what produces the truncated file in the first place.
- **Fix:** `_load()` now only accepts `isinstance(data, list)` (an empty list is preserved), and any unparseable or wrong-shaped file is renamed to `ideas.json.corrupt` for evidence and never reseeded over — matching the policy already used by the goal and habit trackers. `_save()` now writes through `atomic_write_text` (tmp file in the same dir + `os.replace`), the same helper `goal_tracker`/`habit_tracker` use, so a torn write can no longer destroy the file.
- **Verification:** `py -m pytest tests/test_loop_fixes_iter1.py -k idea_vault -q` -> `4 passed`. Failing-first: all 4 failed before the fix (reseeded stock ideas, `AttributeError` on wrong-shaped input, empty list reseeded, `atomic_write_text` not used).

## Test Results

**Modified files:**
- `orbit/orbit/core/unit_converter.py` (+1 / -1)
- `orbit/orbit/core/smart_scheduler.py` (+44 / -2)
- `orbit/orbit/core/habit_tracker.py` (+52 / -12)
- `orbit/orbit/core/idea_vault.py` (+19 / -4)
- `tests/test_loop_fixes_iter1.py` (new, 12 regression tests)

`git diff --numstat -- orbit/orbit/core` -> `4 files changed, 116 insertions(+), 19 deletions(-)`. Diffs reviewed: only bug-fix hunks, no reformatting, no unrelated files touched (pre-existing user changes to `ChatInput.jsx`/`ThreeDOrbitCore.jsx`/`.ai-factory/plans/` were left untouched).

**py_compile:**
```
py -c "import py_compile; [py_compile.compile(f, doraise=True) for f in unit_converter, smart_scheduler, habit_tracker, idea_vault, tests/test_loop_fixes_iter1.py]"
-> COMPILE OK (exit 0)
```

**Regression batch:**
```
py -m pytest tests/test_stripe_e2e.py tests/test_billing.py tests/test_deploy_probes.py tests/test_api_auth_security.py tests/test_tenancy_isolation.py tests/test_auth.py tests/test_security_headers.py tests/test_security_guard.py -q
-> 112 passed, 13 warnings in 50.72s
```

**Baseline comparison:**

| | passed | failed |
|---|---|---|
| baseline (run start, `run.json` `baseline`) | 112 | 0 |
| after fixes | 112 | 0 |
| delta | 0 | **0 new failures** |

Additional verification runs (all green):

| scope | command | result |
|---|---|---|
| new regression tests | `py -m pytest tests/test_loop_fixes_iter1.py -q` | 12 passed |
| adjacent suites (scheduler/habits/unit-converter/torture) | `py -m pytest tests/test_overkill_batch5.py tests/test_torture_regressions.py tests/test_hardening.py tests/test_overkill_batch7.py -q` | 123 passed |
| lint on changed files | `py -m ruff check orbit/orbit/core/{unit_converter,smart_scheduler,habit_tracker,idea_vault}.py tests/test_loop_fixes_iter1.py` | All checks passed |
| API smoke (habit + idea blueprints via Flask test client) | complete/idempotent/uncomplete/report + add/list/search ideas | SMOKE OK |

Total: **247 tests run, 247 passed, 0 failed**.

---

# Iteration 2 — Phase B (PRODUCE)

Hunt areas this round (not covered by iteration 1): date/time arithmetic in core modules, HTTP blueprint input validation, persistence/atomicity, numeric edge cases, lock discipline. Quality bar applied: concrete defect + minimal fix + failing-first regression test. Rejected as non-bugs after measurement: `relationship_tracker.get_reminders` cutoff (its `strftime` drops the time component, so the day boundary is correct), `core/scheduler.py._calculate_next_run` (module is unreachable dead code), and the corrupt-JSON-reseed pattern outside `idea_vault` (same class as BUG-4, would be padding).

## Iteration 2 Summary

| metric | value |
|---|---|
| bugs_found (iter 2) | 3 |
| bugs_fixed (iter 2) | 3 |
| regression tests added (iter 2) | 10 (`tests/test_loop_fixes_iter2.py`) |
| load tool + tests | 1 tool (`tests/load/load_test.py`) + 8 tests (`tests/test_load_tool.py`) |
| load runs | 2 × 60 s (paced) |
| stress ramp | 10→50→100→200→400, 30 s/level, 129,400 requests |
| regression batch | 142 passed / 0 failed |
| new failures | **0** |

Bug classes covered: time-of-day arithmetic on a date-only value (reminder silently missing on the day it matters), missing input type validation at an HTTP boundary (500 instead of 400), and a blocking sleep inside a polled health endpoint (100 ms per call).

No unrelated reformatting, no refactors, no version bump, no commits. Pre-existing user changes to `ChatInput.jsx` / `ThreeDOrbitCore.jsx` / `.ai-factory/plans/phase-a-boot-routing.md` left untouched.

## Bugs (Iteration 2)

### BUG-5: Birthday reminder is missing on the birthday itself, and leap-day contacts are never reminded in non-leap years

- **File:** `orbit/orbit/core/relationship_tracker.py:284` (`get_birthday_reminders`)
- **Root cause:** Part 1 (midnight math) — `today = datetime.now()` keeps the time-of-day while `bday_dt` from `strptime` is midnight, so on the birthday `(bday_dt - today)` is negative for 24 h and `timedelta.days` floors to `-1` — the guard `0 <= days_until <= 14` fails and no reminder is emitted. Measured with a frozen clock: at `2026-10-05 14:30` with a contact born `2026-10-05`, `get_birthday_reminders()` returned `[]`; at `2026-10-04 14:30` (the day before) it returned `days_until: 0` instead of `1`. So the reminder is wrong on both days: absent when it is due, one day early otherwise.
- **Root cause:** Part 2 (Feb 29) — `datetime.strptime(bday, "%Y-%m-%d").replace(year=today.year)` raises `ValueError` in non-leap years; the `"%m-%d"` fallback then parses `"2000-02-29"` and raises again, so the `continue` drops the contact — a leap-day contact is silently skipped every non-leap year. Measured: at `2027-02-27` with birthday `2000-02-29` → `[]`.
- **Fix:** normalise `today` to midnight, parse the birthday first, then map it onto the current year inside its own `try/except` with a Feb 29 → Feb 28 fallback (`replace(year=today.year, day=28)`). `get_reminders` (the day-boundary reminder) is intentionally untouched.
- **Verification:** `py -m pytest tests/test_loop_fixes_iter2.py -k birthday -q` → `4 passed`. Failing-first: 3 of the 4 failed before the fix; the 4th (birthday outside the 14-day window) is a control that passed both before and after.

### BUG-6: `POST /api/notes` and `PUT /api/notes/<id>` return 500 instead of 400 on wrong-typed JSON fields

- **File:** `orbit/orbit/core/quick_notes_bp.py:17` (`add_note`), `orbit/orbit/core/quick_notes_bp.py:42` (`update_note`); crash site `orbit/orbit/core/quick_notes.py` (`add`/`update`)
- **Root cause:** the blueprint did `data.get("content", "").strip()` with no type check and passed `tags` straight to a list comprehension (`t.strip()`), while `QuickNotes.update` does `note.content = content.strip()`. A non-string therefore escapes as an unhandled `AttributeError`. Verified live against the running server (API key, PID 20272): `POST {"content": null}` → **500**, `POST {"content": 123}` → **500**, `POST {"content":"x","tags":5}` → **500**, `PUT {"content": 42}` → **500** with `AttributeError: 'int' object has no attribute 'strip'`. Every other blueprint in the repo validates or traps before reaching `.strip()`, so this is the one that leaks a 5xx to the client.
- **Fix:** type-validate at the HTTP boundary — `content` must be a non-empty `str`, `tags` must be a `list` of `str` (shared `_valid_tags` helper) — returning `400 {"error": ...}`. Valid requests keep their previous behaviour exactly (trim + lowercase tags, 201/200, 404 on unknown id).
- **Verification:** `py -m pytest tests/test_loop_fixes_iter2.py -k note -q` → `5 passed`. Failing-first: all 4 invalid-input tests failed with `500 == 400` before the fix; the 5th (valid create/update/list flow) is a control.

### BUG-7: `/api/health` sleeps 100 ms on every call

- **File:** `orbit/orbit/server.py:1184`
- **Root cause:** `psutil.cpu_percent(interval=0.1)` blocks for the sampling interval, so this polled endpoint could not answer faster than 100 ms. Measured on the live server: `/api/health` p50 **118.6 ms** (min 104.1, max 130.0) versus `/api/notes` p50 ~18 ms and a 404 at ~15 ms; the response header itself reported `X-Response-Time-Ms: 101`. Impact: every frontend health poll holds a worker thread for 100 ms — at the `system:health` bucket's 30 rps that is ~3 threads parked in `sleep` continuously, and it dominated the load run below.
- **Fix:** `psutil.cpu_percent(interval=0)` — non-blocking, compares CPU times since the previous call, the same convention already used at `orbit/orbit/core/system_monitor.py:186`.
- **Verification:** `py -m pytest tests/test_loop_fixes_iter2.py::test_health_endpoint_cpu_sampling_is_non_blocking -q` → passes; failing-first with `AssertionError: health asked psutil for a blocking sample: [0.1]`. The test mocks `psutil.cpu_percent` (reproducing the real sleep) and filters on the test thread so concurrent background monitor samples cannot mask it.
- **After the fix** (in-process Werkzeug server on an ephemeral port, 30 real HTTP requests): p50 **2.9 ms**, mean 3.4 ms, max 18.0 ms — **40× faster** than the 118.6 ms baseline. Accepted trade-off: the first call returns `0.0` (documented psutil non-blocking behaviour, same as `system_monitor`), later calls are accurate.

## Load Test

**Tool:** `tests/load/load_test.py` (new, not collected by pytest — `python_files = test_*.py`). `ThreadPoolExecutor` workers, barrier-aligned start, **one pooled keep-alive `Session` per worker**, optional `--max-rps` pacing gate, `--ramp 10,50,100,...` for multi-level runs. Emits one JSON document to stdout: `rps`, `p50_ms`, `p95_ms`, `p99_ms`, `max_ms`, `requests`, `requests_ok`, `http_2xx`, `http_429`, `errors`, `error_rate`, `error_types`, `error_samples`, `status_counts`. Progress lines go to stderr. Tests: `tests/test_load_tool.py` — 8 hermetic tests against a local `ThreadingHTTPServer` (schema, 5xx counted as errors, `X-API-Key`/`Bearer` header delivery, pacing, percentile math, ramp parsing).

**Why pacing exists:** ORBIT's per-IP token buckets (`orbit/orbit/server.py:447-452`: `global:per_ip` 60 rps / burst 100, `system:health` 30 rps / burst 60, plus `endpoint_rate_limiter` per-path limits) shed unpaced load as 429, so an unpaced run measures the limiter instead of the app. `--max-rps` holds the attempt rate just under the relevant bucket.

### Load run A — `/api/health`, 60 s, concurrency 32, paced 25 rps

| metric | value |
|---|---|
| requests | 1529 (rps 24.97) |
| errors / 429 | **0 / 0** |
| http_2xx | 1529 (100 %) |
| p50 / p95 / p99 / max | 118.6 / 127.7 / 128.7 / 130.0 ms |

Zero errors at the bucket rate. The ~118 ms p50 is BUG-7 measured against the still-running pre-fix process (it is not restarted by design); the same endpoint on fixed code measures p50 2.9 ms.

### Load run B — `/api/notes` (authenticated), 60 s, concurrency 32, paced 50 rps

| metric | value |
|---|---|
| requests | 3031 (rps 50.00) |
| errors / 429 | **0 / 0** |
| http_2xx | 3031 (100 %) |
| p50 / p95 / p99 / max | 18.06 / 26.27 / 27.46 / 28.2 ms |

Steady, error-free, and comfortably under the 60 rps `global:per_ip` bucket.

### Unpaced probe (why pacing is required)

One 60 s unpaced run at concurrency 50 issued 47,226 attempts: 15,364 × 429 (the `system:health` bucket doing its job) and 31,007 transport failures — a 98 % error rate that is an artifact of client connection churn, not an application failure. This motivated both the keep-alive sessions and the pacing gate; without them the tool reports the wrong story.

## Stress Test

Ramp `10 → 50 → 100 → 200 → 400` concurrency, 30 s per level, **unpaced**, `/api/notes` authenticated, against the live server.

| conc | rps | p50 ms | p95 ms | p99 ms | 200 | 429 | ConnectionError |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 693 | 12.3 | 30.5 | 34.7 | 1507 | 14768 | 4524 |
| 50 | 904 | 19.4 | 52.4 | 52.4 | 2 | 0 | 27126 |
| 100 | 977 | 78.1 | 118.5 | 118.5 | 6 | 0 | 29333 |
| 200 | 1092 | 219.0 | 329.6 | 376.5 | 105 | 0 | 32835 |
| 400 | 634 | 513.8 | 1483.4 | 2329.5 | 1878 | 15520 | 1796 |

**Totals:** 129,400 requests issued, peak 1092 rps, worst p95 1483 ms.

**Verdict: the server survived every level.** `status_counts` contains **zero 5xx at all five levels**, no worker died, and `/api/health` returned 200 immediately after the ramp. At level 10 the limiter sheds correctly (1507 successes ≈ 50/s ≈ the 60 rps `global:per_ip` bucket, 14768 × 429).

**Root cause of the ConnectionError column (found, not guessed):** the response headers show `Server: Werkzeug/3.1.8` + `Connection: close`, so every response closes its socket and every request costs a fresh TCP connection. At ~1000 conn/s the Windows dynamic port range (16384 ports, TIME_WAIT ~120 s) is exhausted inside one 30 s level — level 50-200 are almost entirely `NewConnectionError`, and level 400 recovers because ports from levels 10/50 have expired by then. This is a **client/deployment artifact, not an app failure**, and it means genuine concurrency testing of ORBIT needs a keep-alive WSGI server (waitress/gunicorn) instead of Flask's dev server. Switching the production entry point is deliberately **not** part of this iteration (it would change the desktop packaging path) — recorded as follow-up.

## Test Results (Iteration 2)

**Modified / added files:**
- `orbit/orbit/core/relationship_tracker.py` (+15 / -4)
- `orbit/orbit/core/quick_notes_bp.py` (+15 / -3)
- `orbit/orbit/server.py` (+3 / -1)
- `tests/test_loop_fixes_iter2.py` (new, 10 regression tests)
- `tests/test_load_tool.py` (new, 8 tests)
- `tests/load/load_test.py` (new, load/stress tool)

`git diff --numstat` for the three production files -> `33 insertions, 8 deletions`. Diffs reviewed: only bug-fix hunks, no reformatting, no unrelated files touched.

**py_compile:**
```
py -c "import py_compile; [...]" -> COMPILE OK (exit 0)  # 3 source + 3 test/tool files
```

**Lint:**
```
py -m ruff check relationship_tracker.py quick_notes_bp.py server.py test_loop_fixes_iter2.py test_load_tool.py tests/load/load_test.py
-> All checks passed!
```

**Regression batch:**
```
py -m pytest tests/test_stripe_e2e.py tests/test_billing.py tests/test_deploy_probes.py tests/test_api_auth_security.py tests/test_tenancy_isolation.py tests/test_auth.py tests/test_security_headers.py tests/test_security_guard.py tests/test_loop_fixes_iter1.py tests/test_loop_fixes_iter2.py tests/test_load_tool.py -q
-> 142 passed, 13 warnings in 56.88s
```

**Baseline comparison:**

| | passed | failed |
|---|---|---|
| baseline (run start, `run.json` `baseline`) | 112 | 0 |
| after iteration 1 | 124 | 0 |
| after iteration 2 | 142 | 0 |
| delta vs baseline | +30 | **0 new failures** |

Additional verification runs (all green):

| scope | command | result |
|---|---|---|
| iteration-2 regression tests | `py -m pytest tests/test_loop_fixes_iter2.py -q` | 10 passed |
| load tool tests | `py -m pytest tests/test_load_tool.py -q` | 8 passed |
| both loop suites together | `py -m pytest tests/test_loop_fixes_iter{1,2}.py -q` | 22 passed |
| API smoke on the live server | goal/relationship/time probe endpoints | 200s |

**Live-server probe artifacts cleaned up:** `goal_d6949941` deleted, `rel_cdd4d027` deleted, time session `sess_768164` stopped (`POST /api/time/stop`, 200).

Total: **142 tests run, 142 passed, 0 failed** (30 of them new this iteration).
