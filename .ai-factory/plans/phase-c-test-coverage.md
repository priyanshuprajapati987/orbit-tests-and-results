# Implementation Plan: Phase C Test Coverage (Tasks 14-16)

Branch: main
Created: 2026-09-01

## Context
Phase C core implementations are all complete (8/8 systems, 5/5 panels). 
The gap is test coverage: 2 missing test files + 1 thin file.
Current: 2045 tests passing. Target: 2080+ after this batch.

## Source Code Analyzed
- `core/realtime_learning.py` (218 LOC): FeedbackEntry, PatternDetector, RealtimeLearner, singleton
- `core/proactive_assistant.py` (237 LOC): ProactiveAssistant, 5 reminder types, cooldown, singleton
- `core/cross_device_sync.py` (445 LOC): CrossDeviceSync, LocalTransport, NetworkTransport, merge_state

---

## Task 14: Realtime Learning Tests

**File:** `tests/test_realtime_learning.py`
**Target:** 11+ tests

### Tests to Write

| # | Test Name | What It Verifies |
|---|-----------|------------------|
| 1 | `test_feedback_entry_creation` | FeedbackEntry fields populated correctly |
| 2 | `test_feedback_entry_to_dict` | to_dict returns all fields |
| 3 | `test_feedback_entry_from_dict` | from_dict round-trip preserves data |
| 4 | `test_pattern_detector_record` | record() updates query_patterns + topic_scores |
| 5 | `test_pattern_detector_extract_key` | _extract_key takes first 5 words, lowercased |
| 6 | `test_pattern_detector_get_topic_score` | Returns 0.5 default, updated after MIN_FEEDBACK |
| 7 | `test_pattern_detector_top_patterns` | Returns sorted list by score desc |
| 8 | `test_pattern_detector_save_load` | Persistence round-trip preserves patterns |
| 9 | `test_realtime_learner_record_feedback` | High rating no adaptation, low rating triggers adaptation |
| 10 | `test_realtime_learner_adaptation_suggestion` | Returns suggestion when score < 0.3, None otherwise |
| 11 | `test_realtime_learner_stats` | Stats dict has all expected keys |
| 12 | `test_realtime_learner_reset` | Reset clears feedback, patterns, adaptation count |
| 13 | `test_singleton` | get_realtime_learner returns same instance |

### Implementation Notes
- Use `monkeypatch` to redirect LEARNING_DIR to `tmp_path`
- Use `monkeypatch.setattr` for MIN_FEEDBACK_FOR_ADAPT = 2 (speed up tests)
- Mock `threading.Lock` not needed — real locks are fine for tests
- PatternDetector.save/load: write to tmp_path, verify content

---

## Task 15: Proactive Assistant Tests

**File:** `tests/test_proactive_assistant.py`
**Target:** 11+ tests

### Tests to Write

| # | Test Name | What It Verifies |
|---|-----------|------------------|
| 1 | `test_start_stop_lifecycle` | start() sets _running, stop() clears it |
| 2 | `test_start_idempotent` | Double-start doesn't create second thread |
| 3 | `test_can_proact_cooldown` | Returns True initially, False within COOLDOWN_SEC |
| 4 | `test_max_reminders_per_session` | Stops generating after MAX_REMINDERS |
| 5 | `test_generate_reminder_system_alert` | Mock psutil low battery → system_alert type |
| 6 | `test_generate_reminder_news` | Mock NewsTool → news type |
| 7 | `test_generate_reminder_time_based` | Mock datetime hour=7 → time_based type |
| 8 | `test_generate_reminder_idle` | Mock usage_tracker → idle type |
| 9 | `test_generate_reminder_returns_none` | When all sources empty, returns None |
| 10 | `test_get_status` | Status dict has running, reminders_sent, etc. |
| 11 | `test_get_reminders` | Returns last 50 reminders |
| 12 | `test_reset_session` | Clears count, reminders, timestamps |
| 13 | `test_singleton` | get_proactive_assistant returns same instance |

### Implementation Notes
- Mock `psutil.sensors_battery` for system messages
- Mock `psutil.cpu_percent` and `psutil.virtual_memory`
- Mock `NewsTool.fetch_rss` for news messages
- Mock `datetime.now()` for time-based messages (hour control)
- Use `monkeypatch.setattr` for COOLDOWN_SEC = 0 (speed up tests)
- Use `monkeypatch.setattr` for MAX_REMINDERS_PER_SESSION = 3

---

## Task 16: Cross-Device Sync Test Expansion

**File:** `tests/test_cross_device_sync.py` (append to existing)
**Target:** 10+ new tests (5 existing → 15+ total)

### Tests to Add

| # | Test Name | What It Verifies |
|---|-----------|------------------|
| 1 | `test_merge_state_remote_newer` | Remote with newer ts overwrites local |
| 2 | `test_merge_state_equal_ts_kept_local` | Equal ts keeps local value |
| 3 | `test_merge_state_local_missing` | New key from remote added to local |
| 4 | `test_merge_state_returns_conflicts` | Returns conflict list for differing values |
| 5 | `test_queue_change_batches` | Multiple queue_change → pending_changes grows |
| 6 | `test_queue_change_clears_after_sync` | pending_changes cleared after sync() |
| 7 | `test_broadcast_task_update` | Adds task_progress change to queue |
| 8 | `test_broadcast_notification` | Adds task_notification change to queue |
| 9 | `test_export_state_structure` | Returns device_id, updated_at, state |
| 10 | `test_get_state_category` | Returns specific category or all |
| 11 | `test_update_state_timestamps` | Value stored with ISO timestamp |
| 12 | `test_reset_clears_all` | Clears pending, count, state |
| 13 | `test_network_transport_pull_error` | HTTP error → returns ([], []) |
| 14 | `test_get_status_structure` | Status dict has all expected keys |

### Implementation Notes
- Use `monkeypatch` to redirect SYNC_DIR to `tmp_path`
- Use `CrossDeviceSync.__new__` for unit tests (avoid full init)
- Mock NetworkTransport._post/_get for error scenarios
- Existing 5 tests stay untouched

---

## Commit Plan
- **Commit:** "test(phase-c): add missing test coverage for realtime_learning + proactive + sync"

## Verification
1. `py -c "import py_compile; py_compile.compile('tests/test_realtime_learning.py', doraise=True)"`
2. `py -c "import py_compile; py_compile.compile('tests/test_proactive_assistant.py', doraise=True)"`
3. `py -c "import py_compile; py_compile.compile('tests/test_cross_device_sync.py', doraise=True)"`
4. `python -m pytest tests/test_realtime_learning.py tests/test_proactive_assistant.py tests/test_cross_device_sync.py -v`
5. Full suite: `python -m pytest tests/ -q --ignore=tests/e2e` → target 2080+ passing
