# JARVES Security Audit Report

- **Date:** 2026-08-16
- **Scope:** Desktop app (PyQt5 GUI) + internal Flask API (localhost:5000) + React frontend (`ui_provided/`)
- **Method:** Full re-scan (OpenCode grep + pip-audit + npm audit) following `aif-security-checklist` (OWASP Top 10).
- **Result:** PASS. 2 HIGH + 1 MEDIUM + 1 LOW findings fixed (see Aug 16 findings).

---

## Re-scan 2026-08-16

### H01 — Sandbox-escape RCE in workflow condition eval (HIGH) — FIXED
- `core/workflow_engine.py:318` `_evaluate_condition` used raw `eval(condition, {"__builtins__": safe_builtins, "context": context})`. `().__class__.__mro__[1].__subclasses__()` bypasses the builtins dict → arbitrary code execution. Step conditions are user-settable via `add_step(condition=...)`.
- Fix: replaced with AST-whitelisted evaluator — only constants, comparisons, boolean ops, and `context`-key lookups allowed. Verified `__import__`, `open`, `exec`, `().__class__` chains all return `False`; legit `context["cost"] > 5` conditions still work.
- Regression tests: `tests/test_workflow_condition_security.py` — 20 tests.

### H02 — API auth silently disabled + broken frontend contract (HIGH) — FIXED
- `ORBIT_API_KEY` was never set in `.env`, so `require_api_key` warned "authentication is DISABLED" and allowed everything. Also, even if a key were set, the React SPA never sent `X-API-Key` → every `/api/*` call would 401 → UI broken. Two independent defects.
- Fixes:
  - `.env` now has a generated strong `ORBIT_API_KEY`; `FLASK_DEBUG=true` → `false` (Werkzeug debugger RCE surface on standalone server).
  - `server.py` auth now only guards `/api/*` (SPA shell + static assets stay public so the UI can boot).
  - `server.py` injects the key into the served `index.html` as `window.__ORBIT_API_KEY__` and index.html responses are never CORS-readable (`Access-Control-Allow-Origin` dropped for `text/html`; JS/CSS assets keep `*` for QtWebEngine module scripts).
  - `main.jsx` global fetch wrapper attaches `X-API-Key` to same-origin `/api` calls.
  - `.env.example` synced (`ORBIT_API_KEY`/`ORBIT_API_AUTH_ENABLED`, stale `JARVES_API_KEY` naming removed).
- Regression tests: `tests/test_api_auth_security.py` — 11 tests.
- **Note:** `tests/conftest.py` now pins `ORBIT_API_KEY=""` + `ORBIT_API_AUTH_ENABLED=0` so the suite stays hermetic (no dependence on developer `.env`).

### H03 — npm: nanoid <3.3.18 (HIGH, CWE) — FIXED
- `nanoid@3.3.16` (GHSA-2v37-7h3g-55p8, infinite loop) via postcss. Added `overrides.nanoid ^3.3.18` + bumped direct `postcss` dep to `^8.5.23`. `npm audit`: **0 vulnerabilities**.
- Build verified green (vite build).

### M04 — npm: postcss <=8.5.22 sourceMappingURL (MEDIUM) — FIXED
- GHSA-fxqj-rqcc-2cmp (incomplete fix of GHSA-6g55-p6wh-862q). Bumped `postcss` direct dep to `^8.5.23` (see H03).

### L04 — ORBIT_API_KEY not in `.env.example` / stale naming (LOW) — FIXED
- `.env.example` used `JARVES_API_KEY`/`JARVES_API_AUTH_ENABLED` but code reads `ORBIT_API_KEY`. Synced (see H02).

### Verified clean (no action needed)
- **Secrets in source:** none — only test fixtures (`sk-abc123…`) in `tests/`, `stress_test*.py`.
- **Git hygiene:** `.env` untracked + gitignored; only `.env.example` tracked; no `.env` in git history.
- **Command injection:** no `shell=True`; all `subprocess` calls use list-args. `music_ctrl.py`/`network.py` PowerShell calls use static strings only.
- **XSS:** no `dangerouslySetInnerHTML`/`innerHTML`/`eval`/`new Function` in `ui_provided/src`.
- **eval/exec:** `calculator.py` (AST-restricted, builtins empty), `code_interpreter.py` (documented LOW sandbox), `alert_system.py` (AST-safe) — all reviewed, acceptable.
- **pip-audit** on `requirements.txt` + pyproject deps: **0 vulnerabilities**.
- **Rate limiting:** per-IP scoped buckets + endpoint limiter active (`server.py:306`).
- **Security headers:** CSP/nosniff/DENY/Referrer-Policy via `get_security_headers()` (HSTS skipped on http).

---

## Prior Report 2026-08-02

- **Date:** 2026-08-02
- **Result:** PASS with 3 medium/low findings to fix (see Findings).

---

## Summary

| Check | Status | Notes |
|---|---|---|
| Secrets in source | PASS | No hardcoded keys in `.py`/`.js`/`.jsx`/`.ts`. Only test fixtures (`tests/test_phase1_audit.py:95,100`). |
| `.env` git hygiene | PASS | `.env` gitignored + untracked; only `.env.example`/`.env.n8n.example` tracked; no `.env` in git history. |
| Secrets in git history | PASS | `jarves/OpenMontage/tools/google_credentials.py` (history-only) is an env-var-based OAuth helper; no embedded secrets. |
| Command injection | PASS | All `subprocess` calls use list-args (no `shell=True`); eval sites AST-validated or restricted-builtins. |
| SQL injection | PASS | No raw SQL; data stores are JSON files (jsonlite) via `sqlite3`-free code paths. `input_sanitizer` strips SQL patterns. |
| XSS (React) | PASS | No `dangerouslySetInnerHTML`/`innerHTML`/`eval`/`new Function` in `ui_provided/src`. React escapes by default. |
| XSS (Flask) | PASS | Responses are `jsonify` (JSON) — no HTML rendering server-side. |
| CSRF | PASS | No cookies/sessions; header-based `X-API-Key`/`Bearer` auth + CORS origin allowlist. |
| Auth (fail-closed) | PASS | `JARVES_API_KEY` via `hmac.compare_digest`, public health paths exempt, OPTIONS exempt (`server.py:233`). |
| Rate limiting | PASS | Per-IP scoped buckets enforced (`server.py:263`, `scoped_check`). |
| Input sanitization | PASS | Recursive XSS/SQL/path-traversal sanitizer (`core/input_sanitizer.py`). |
| Prompt injection (LLM) | PASS | QueenAgent escapes `{}` before `.format`; ToolGate gates tool actions; no "ignore previous" patterns found. |
| Race conditions / TOCTOU | PASS | Widespread `threading.Lock`/`RLock`; `policy_engine` RLock on approved sets; atomic writes in stores. |
| Log redaction | PASS | `JSONFormatter` + `SecretRedactor` mask keys/headers in logs. |
| Security headers | FIXED | `get_security_headers()` applied via `after_request` in `create_app()` (HSTS skipped on plain HTTP). |
| Debug mode | FIXED | Standalone server honors `FLASK_DEBUG` env (default off); no hardcoded `debug=True`. |
| Python deps | WARN | `pip-audit` not installed — no CVE scan of `requirements.txt`. |
| npm deps | FIXED | `npm audit`: **0 vulnerabilities** (PrismJS override → 1.30.0; esbuild override → 0.25.12; vite ^5 → ^6.4.3 non-breaking). |

---

## Findings

### M01 — Security headers never applied (MEDIUM) — FIXED
- `core/security_hardening.py:161` defines `get_security_headers()` (CSP, `X-Content-Type-Options`, `X-Frame-Options`, HSTS, Referrer-Policy) but the only `after_request` hooks in `server.py` added just `X-Response-Time-Ms`.
- Impact: no CSP/nosniff/frame-options on API responses. Local-only exposure, but trivial to fix.
- Fix: in `create_app()`, added `after_request` `apply_security_headers` that merges `get_security_headers()` via `setdefault` (preserves `X-Response-Time-Ms`) and skips HSTS when `request.is_secure` is False. Verified: `/api/health` returns nosniff/DENY/CSP/Referrer-Policy, HSTS absent on http.

### M02 — Debug mode enabled on standalone server (MEDIUM) — FIXED
- `server.py:684`: `app.run(host='127.0.0.1', port=5000, debug=True)` — enables Werkzeug debugger (potential RCE surface if ever exposed) + reloader.
- Desktop entry points (`launch_desktop.py:522`, `desktop.py:45`) already use `debug=False`.
- Fix: `debug=os.environ.get("FLASK_DEBUG", "").lower() in ("1","true","yes","on")` — default off, opt-in via env.

### M03 — npm: PrismJS DOM Clobbering (MEDIUM) — FIXED
- `ui_provided/package.json:21` `react-syntax-highlighter@^15.5.0` → `refractor` → `prismjs <1.30.0` (GHSA-x7hr-w5r2-h6wg, CWE-79/94).
- Used only in `ChatMessage.jsx:3-85` to render code blocks (LLM/user content).
- Fix: added npm `overrides` (esbuild `^0.25.0` + `refractor.prismjs ^1.30.0`), bumped `vite ^5.0.0 → ^6.4.3` (non-breaking, plugin-react supports ^6). `npm audit`: **0 vulnerabilities**. Frontend build green (2531 modules).

### L01 — Git option injection (LOW)
- `github_tool.py:623,647`: `git add`/`git push` pass user-provided `files`/`branch` as argv. A value starting with `-` could inject git options (e.g. `--upload-pack`).
- Mitigated by ToolGate: `git_add`/`git_push` are risk-gated (`_gate(...)`, CRITICAL/HIGH). Low residual risk.
- Fix (optional): reject args starting with `-`.

### L02 — Arbitrary-code interpreter endpoint (LOW, by design)
- `/api/code-interpreter/execute` runs Python via `exec` with a restricted sandbox (`core/code_interpreter.py`: banned imports, AST validation, restricted builtins).
- Sandboxed but not a hard boundary; gated behind API key + rate limit. Desktop-only app; acceptable. Note in docs.

### L03 — Auto-updater supply chain (LOW)
- `core/auto_updater.py:111` downloads files from the user's own GitHub repo over HTTPS and writes to the source tree; no signature check. Repo is private/self-owned; acceptable risk.

### I01 — Webhook/notification SSRF (INFO)
- `webhook_system.py:216`, `notification_system.py:205` POST to user-configured URLs. Owner-driven desktop app; acceptable.

---

## Verdict

**PASS.** All M01–M03 findings fixed and verified (2026-08-02, v3.6.0-alpha security round). Remaining L01–L03 are accepted low-risk for a local desktop app; I01 is informational.
