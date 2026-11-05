# ORBIT Security & Architecture Hardening Plan — P0→P5
> Reviewed against actual code on 2026-10-22 (post `65e7803`). Base = user-proposed plan, verified + improved.
> **Rule (each phase): code audit → targeted tests → full regression → ONE commit per phase. No big-bang.**

---

## PART A — Code review verdicts (assumptions vs reality)

### P0 claims — ALL VERIFIED ✅ (all 5 rows valid)

| Claim | Evidence (verified in code) |
|---|---|
| 5 signals ke baad automatic source deletion | `dead_hand.py:461` `if armed and warnings >= TRIGGER_AT: trigger()` → `:530 _wipe()` unlinks every code file; no human confirm, no risk tier |
| Debugger/RE detection conclusive liya jata hai | `:476-477` — debugger + re_tool = 1 warning each, counted equally toward destruction. False-positive surface: `RE_TOOLS` prefix match (`stem.startswith("ida")` catches non-RE software e.g. IDAutomation; `procdump` = legit admin tool) |
| Identity flagging permanent hai | `_flag()` entries have `flagged_at/reason/warnings` — **no expiry, no review workflow**; recovery = manual local unflag only |
| `os._exit(77)` hard kill | `dead_hand.py:541` in trigger exit-thread; `server.py:1487` auto-starts monitor with `exit_on_trigger=True` (default) → armed boot = hard-exit path live |
| Frozen wipe too broad | `_wipe()` frozen branch (`:549-567`) deletes **everything next to exe except orbit_data/** (docs, config, non-code data included) |

**Additional findings (my review, not in user plan):**
- `dead_hand.py:507-508` — trigger **always self-flags `ip:127.0.0.1` + machine identity** → local machine permanently 403'd on all `/api/*` (recovery path survives, but this is a self-inflicted lockout on every trigger).
- Dev safety claim has a hole: `ORBIT_DEADHAND=1` in `.env` **or** a single local `POST /arm` persists `armed_manual=True` → next boot runs destructive monitor in a dev tree. Env-arm is not build-gated.
- Integrity seal is **in-memory only**, re-sealed at every boot (`start_monitor:589`) → pre-boot tampering is trusted by design; `reseal` endpoint re-trusts current tree with one POST.
- Response model is a single hardcoded action (flag+wipe+exit). No risk tiers, no restricted mode, no configurable profile. (User's required design is the correct fix.)

### P1 claims — MOSTLY VALID, 1 correction ✅⚠️

- **7/8 endpoints are local-only** (`_require_local` on attempts/flagged/arm/disarm/reset/reseal/unflag) — better than plan assumes.
- **`status` is the real leak** — NOT local-only AND it embeds `attempts` (last-10 details) + full `code_root` filesystem path (`dead_hand.py:632,651`). So `/attempts` is protected but the same data ships via `/status` remotely. Inconsistent boundary — VALID.
- **CSRF gap CONFIRMED for auth-disabled mode**: management POSTs have no Origin/Referer check, no token, no confirm body. When `ORBIT_API_AUTH_ENABLED=0` (tests/dev) any local page can cross-origin form-POST `/api/deadhand/disarm|arm|reset|unflag` (no custom header needed → no preflight). With auth ON, `require_api_key` blocks it (custom header required) — so CSRF protection currently *incidentally* depends on one env flag. Deadhand paths are NOT in `ORBIT_API_PUBLIC_PATHS` (config.py:255 — verified) ✓.
- `arm` = bare POST, no explicit confirmation — VALID.
- `reset` clears `attempts` (the only op log) — audit erasure possible — VALID (fix: separate append-only JSONL).
- Loopback check uses `request.remote_addr` only (no XFF trust) ✓; `ORBIT_HOST` default `127.0.0.1` (server.py:1503) ✓. Loopback boundary is sound — plan's "boundary ≠ auth" caveat correct.

### P2 claims — VALID but reality-checked ⚠️✅

- **The 27 MD5→SHA256 changes are ID/fingerprint generation, NOT stored-checksum verification** (verified via `git show 110c9bf`: `audit_trail` entry ids, `skill_learning` step fingerprints, `smart_scheduler` task ids — all `hex[:12]` one-way keys). Same output format (12 hex) → no verification failures; no fail-closed security check broke.
- **Real residual effects:**
  - Persisted fingerprints (skill dedup, anomaly keys) won't match recomputed values → **one-time duplicate entries** after migration (benign, but must be documented/accepted or lazily dual-computed).
  - **`smart_file_watcher.py:189` still MD5** for content-change detection (+ MD5 ids at :118,:210) — left behind.
  - `plugin_system.py:134` stale comment `# path → md5` (actual `_hash_file` = sha256, :146). `file_hash` mismatch path = hot-reload only (plugin_system:423-426), not refusal → benign.
  - `encryption_manager.py` keeps `verify(algorithm="md5")` legacy path (:58) + deprecated `hash_md5` — needs caller audit (secrets vs checksum).
  - Two `.rollback_backup` files (`encryption_manager`, `smart_file_watcher`) = Self-Healer's 2 rolled-back fixes, stale MD5 code sitting in `core/` — cleanup.
- **Plan's critical distinction CONFIRMED**: baseline is runtime seal only; no signed reference → attacker with write access before boot (or local `reseal`) re-trusts. For frozen releases a separately-protected (signed) manifest is the real fix; for dev, in-memory seal is acceptable. Write access to `orbit_data` also lets attacker rewrite flag files (403 deny-list) — separate integrity for `deadhand_flagged.json` not present.

### P3 claims — VALID ✅

- `atomic_write_text` (runtime_paths.py:79-98): tmp + `os.replace` + **cleanup on exception** (better than assumed) but **no `fsync`** before replace → power-loss durability not guaranteed; no `.bak` previous-valid rotation; no disk-full/permission tests (only the static torn-write *scan* test exists). Loaders fall back to "empty state" on corrupted file = silent reset — needs `.bak` recovery.

### P4 claims — VALID ✅

- Self-Healer has: `run_cycle(dry_run)`, apply-with-rollback, `get_history(10)`. Missing: per-finding evidence (file/line/severity/snippet), patch preview artifact, tests/static-checks **before** marking verified, human-approval gate for security-sensitive files, immutable per-fix audit. This run's own incidents prove the need (scanner self-corrupted bugfixer.py → revert; 2 rolled back; torn-write invariant break).

### P5 claims — VALID ✅

- 4348 passed / 24 skipped — skipped inventory captured (below). Fast gate = 48 tests; full suite = release gate; CI workflows exist (lint/tests/build/security, with timeouts). Missing: documented skip rationale, authz/CSRF/recovery drills in gate, release checklist formalized.

### Architecture decision (3 independent layers) — ADOPTED ✅
Current `trigger()` couples detection→flag→wipe→exit in one method — exactly the coupling the plan warns against. Restructure: **Detection → Policy → Enforcement → Recovery** as separate modules with destructive action out of the automatic path.

---

## PART B — Improved execution plan (file-by-file)

### P0 — Dead Hand response model (destructive path removed from auto-trigger)
**Deliverable:** safe response model + recovery design; zero code-deletion in any automatic path.

| # | File | Change |
|---|---|---|
| 0.1 | `orbit/orbit/core/dead_hand.py` | `record_attempt()` → risk scoring (severity map: debugger=1, re_tool=1, integrity=3, state_tamper=3; rolling 10-min window) instead of raw count → `TRIGGER_AT` |
| 0.2 | `orbit/orbit/core/dead_hand.py` | `trigger()` becomes **non-destructive**: flag (quarantined, with evidence refs) + persist + notify + delegate response to policy module. **Delete `_wipe()` call + exit-thread from trigger** |
| 0.3 | NEW `orbit/orbit/core/dead_hand_policy.py` | Response profiles: `audit` (default) → `restricted` (block mutating API) → `lockout` (403 flagged) → `shutdown` (graceful). Config `ORBIT_DEADHAND_RESPONSE`, default `audit`. `destroy` profile **does not exist in this module** |
| 0.4 | `orbit/orbit/core/dead_hand_destroy.py` (new, never auto-imported) | Old wipe logic moved here; callable only via explicit operator action: frozen build + `ORBIT_ALLOW_DESTROY=1` + confirm phrase + audit entry. Dev/test: unreachable by construction |
| 0.5 | `orbit/orbit/core/dead_hand.py` | `shutdown_gracefully()`: flush state → write `orbit_data/security/deadhand_recovery_report.json` (reason, evidence, warnings, restore steps) → flush logs → exit. `os._exit` only after flush, only in shutdown profile |
| 0.6 | `orbit/orbit/core/dead_hand.py` | Quarantine: flag entries gain `expires_at` (default 7d) + `evidence[]`; expiry sweep in `scan_once`; renewal only via reviewed audit |
| 0.7 | `orbit/orbit/server.py` | auto-start block passes profile; log line reports profile; remove wipe wording |
| 0.8 | `tests/test_dead_hand.py` | Rewrite trigger tests: **assert NO file deleted on5 signals** (tmp tree intact), policy escalation, expiry auto-unflag, graceful-shutdown writes recovery report (mock exit), destroy module unreachable without gates |
| — | Gate | targeted tests → ruff/compile → full suite → commit `feat(security): P0 dead hand response model` |

### P1 — Endpoint authorization matrix
**Deliverable:** authorization matrix + negative tests for all 8 endpoints.

| # | File | Change |
|---|---|---|
| 1.1 | `dead_hand_bp.py` | `status` sanitized: `attempts` + `code_root` only when local (remote gets counts/state booleans only) |
| 1.2 | `dead_hand_bp.py` | POST guard: if `Origin`/`Referer` present and host not local → 403 (CSRF); works with auth on AND off |
| 1.3 | `dead_hand_bp.py` | `arm` requires `{"confirm":"ARM"}`; `unflag` requires `reason` (min length); `reset`/`reseal` require `reason` too |
| 1.4 | `dead_hand.py` | `_audit_op(op, actor, result)` → append-only `orbit_data/security/deadhand_audit.jsonl` (atomic append, survives wipe, NOT cleared by reset) |
| 1.5 | `dead_hand_bp.py` | Rate-limit local POSTs via existing scoped limiter (`system:deadhand` bucket) |
| 1.6 | NEW `tests/test_deadhand_authz.py` | Matrix: ×8 remote→403 local_only; ×5 POST cross-origin→403; auth-enabled no-key→401 (create_app fixture); arm w/o confirm→400; unflag w/o reason→400; remote status body lacks attempts/code_root; every op writes audit row; state-file ops don't erase audit |
| — | Gate | per rule → commit `feat(security): P1 deadhand authz matrix` |

### P2 — SHA-256 integrity completion + trust model
**Deliverable:** SHA-256 audit, migration decision documented, signed-manifest path for frozen.

| # | File | Change |
|---|---|---|
| 2.1 | NEW `tests/test_hash_audit.py` | Repo scan: every `hashlib.md5(` must be in allowlist file (text_utils user-tool, encryption_manager legacy verify w/ warning, smart_file_watcher ids) — else fail. Prevents regression |
| 2.2 | `smart_file_watcher.py` | Content hash md5→sha256 with legacy dual-accept one release (store `hash_algo` field, rewrite on next change) |
| 2.3 | `plugin_system.py:134` | Fix stale `# path → md5` comment |
| 2.4 | `encryption_manager.py` | Split `verify(algorithm="md5")` into `verify_legacy()` + warning; audit all callers (grep) → assert no secret/password flow uses it (move secrets to dedicated KDF if found) |
| 2.5 | cleanup | Delete `encryption_manager.py.rollback_backup` + `smart_file_watcher.py.rollback_backup` (untracked stale MD5 code) |
| 2.6 | `dead_hand.py` | Persist sealed manifest `orbit_data/security/deadhand_manifest.json` (rel→sha256) written atomically; integrity compares file **and** manifest vs runtime; unexpected NEW code file during runtime = `integrity_new` warning; frozen builds: manifest signed (HMAC with build key) — reseal in frozen requires signature, dev allows local reseal (documented limitation: local key raises bar + audits, offline release key = P5) |
| 2.7 | Migration note | Skill/anomaly fingerprint mismatch → accept one-time duplicates, documented; test asserts format compat (12-hex both) |
| 2.8 | tests | tampered file / missing file / **new file** / corrupted manifest (fallback+warn) / pre-boot tamper (manifest vs current) / md5-allowlist |
| — | Gate | → commit `fix(security): P2 sha256 integrity completion` |

### P3 — Atomic writes + crash recovery
**Deliverable:** fault-injection tests + previous-valid-state preservation.

| # | File | Change |
|---|---|---|
| 3.1 | `runtime_paths.py` | `atomic_write_text`: `f.flush()+os.fsync(fd)` before `os.replace`; keep exception cleanup; (Windows: dir-fsync unsupported — document in docstring) |
| 3.2 | `runtime_paths.py` | New `atomic_write_text_bak(path, text)`: before replace, rotate current valid content → `.bak` (1 level) for critical state (dead_hand state+flags, kill_switch, immortality state) |
| 3.3 | `dead_hand.py` | Loaders: primary corrupt → auto-recover from `.bak` + log `recovered_from_bak` (test asserts) |
| 3.4 | NEW `tests/test_atomic_write_fault.py` | ENOSPC simulation (patch os.replace→raise) → old file intact + tmp cleaned; permission denied; **crash-before-replace** (orphan tmp ignored by loader + swept); 2 threads × 200 concurrent writes → always-valid JSON; disk-full on flag write → memory state still consistent |
| 3.5 | tests | Recovery consistency: corrupt primary + valid bak → loader returns state + audit line |
| — | Gate | → commit `fix(core): P3 durable state writes` |

### P4 — Self-Healer controlled patching
**Deliverable:** prove fix resolved intended bug, no regression.

| # | File | Change |
|---|---|---|
| 4.1 | `self_healer.py` | Finding record += `file, line, severity, evidence_snippet, rule_id, file_hash_before` |
| 4.2 | `self_healer.py` | Persist patch preview (`orbit_data/self_healer/previews/<cycle>/<file>.patch`) before apply |
| 4.3 | `self_healer.py` | Verification pipeline post-apply: `py_compile` + `ruff` on changed file + targeted pytest (rule→test map, default module smoke) → fail ⇒ auto-rollback (exists) + verdict recorded |
| 4.4 | `self_healer.py` | Approval gate: `SECURITY_SENSITIVE` set (server.py, policy_engine, kill_switch, dead_hand*, guardrails, defense_grid, auth/rate-limit files) → suggest-only unless `ORBIT_HEAL_APPROVE=1` |
| 4.5 | `self_healer.py` | Immutable audit JSONL `orbit_data/self_healer/audit.jsonl`: cycle, file, rule, before/after hashes, preview path, tests run, pass/fail, rolled-back bool |
| 4.6 | NEW `tests/test_self_healer_gate.py` | approval blocks sensitive file; failed verification → byte-identical rollback (hash compare); audit rows complete; preview exists; skip-file list respected |
| — | Gate | → commit `feat(heal): P4 controlled patching` |

### P5 — Release gates + regression net
**Deliverable:** repeatable release checklist (10 + additions below), documented skips, recovery drill.

| # | Item | Change |
|---|---|---|
| 5.1 | `scripts/fast_gate.bat` | Add: `test_deadhand_authz + test_atomic_write_fault + test_api_auth_security` to fast lane |
| 5.2 | `docs/RELEASE_CHECKLIST.md` | User's 10 items + additions: auth-default-on check, CSRF tests pass, quarantine-expiry tests, restricted-mode tests, hash-allowlist test, recovery drill executed |
| 5.3 | `docs/RELEASE_CHECKLIST.md` — skips section | 24 skips inventoried: env-dep (PyGithub ×13, numpy ×2, Ollama ×2, frontend-dist ×3, smoke-server ×2, PyPDF2 ×1, git-unavailable, usage_tracker ×2, tools_audit ×1...) → each tagged `env` or `gap` with action |
| 5.4 | NEW `scripts/recovery_drill.py` | Restore orbit_data from `.bak`/immortality snapshot in a temp dir → verify loaders + deadhand state consistent → print PASS |
| 5.5 | CI | `tests.yml` already runs full suite; ensure new P0-P4 test files included (no markers needed); `security.yml` weekly pip-audit/bandit stays |
| — | Gate | checklist dry-run → commit `chore(release): P5 gates` |

---

## PART C — Layer separation (adopted architecture)

```
core/dead_hand.py        DETECTION: signals, seal, evidence, state  (NO destructive actions)
core/dead_hand_policy.py POLICY:    risk score → response profile (audit|restricted|lockout|shutdown)
server.py before_request ENFORCEMENT: 403 flagged / restricted-mode method block
core/dead_hand_destroy.py RECOVERY-ANTI: manual-only destroy (frozen + env + confirm + audit), never auto-imported
recovery:  deadhand_recovery_report.json + .bak state + ImmortalityEngine snapshots + local /api/deadhand/* path
```
- Detection bug → worst case = wrong risk score, never irreversible action.
- Each layer fail-open independently (existing principle kept).
- Config single source: `ORBIT_DEADHAND_RESPONSE` (+ destroy gates separate).

## Execution order (unchanged from recommendation, refined)
1. **P0** response model (unsafe today → safe)
2. **P1** endpoint authz matrix (exposes P0's new status shape — so after P0)
3. **P2** integrity/trust (independent, pairs with hash tests)
4. **P3** durability (independent)
5. **P4** Self-Healer gates (uses P3 atomic helpers)
6. **P5** release net (aggregates all)

Per-phase gates: audit note → targeted tests green → ruff+compile → **full suite green** → single phase commit → next.

## Out of scope / deferred (honest)
- Offline HSM/release-signing key (needs real release pipeline) → P5 follow-up, documented limitation.
- Real CSP/framing of management API behind separate admin port (overkill now; local+auth+CSRF covers).
- Re-verification of pre-migration skill fingerprints (accept documented one-time dedup).
