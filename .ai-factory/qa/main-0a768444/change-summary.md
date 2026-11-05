# Change Summary — M3/M4 SaaS Milestones

**Branch:** main
**Commits:** 5 (096d9c0 → 825fbf8)
**Files changed:** 27
**Lines:** +810 / -70

## What Changed

### 1. Auth System (M2 — already shipped, included in diff)
- New `core/auth/` package: models, password (PBKDF2), tokens (JWT), store (SQLAlchemy), oauth (Google/GitHub), service, guards
- `auth_bp.py`: signup, login, refresh, logout, me, password reset, OAuth start/callback
- `server.py`: auth_bp registered, Bearer JWT → g.user_id/g.user_role

### 2. Per-User Isolation (M3.2)
- `memory_store.py`: user_id dimension in MemoryEntry, all read/write paths user-scoped
- `conversation_manager.py`: user_id field, _owned filter, all methods user-scoped
- `task_scheduler.py`: user_id field, _owned filter, add/remove/enable/get/list user-scoped
- `conversation_bp.py`, `task_scheduler_bp.py`, `agentmemory_bp.py`: _request_user_id() wired

### 3. Per-User Budgets (M3.3)
- `kill_switch.py`: USER_PLAN_CAPS (free/pro), user_id in can_act/try_reserve/record_usage/get_usage
- `chat_api.py`: quota gate in _worker (402-style nudge on plan exceed)
- `llm/router.py`: LLMRequest.user_id field, record_usage passes user_id

### 4. Rate Limiting (M3.4)
- `rate_limiter.py`: user_check() for per-user buckets
- `redis_rate_limiter.py`: RedisTokenBucket with Lua atomic consume
- `server.py`: per-user rate limits in check_rate_limit

### 5. Billing & Payments (M4)
- `billing.py`: Plan/Invoice/UsageRecord dataclasses, BillingManager singleton
- `billing_bp.py`: 13 endpoints (plans, subscription, usage, invoices, checkout, webhook, upgrade, downgrade, admin)
- `requirements.txt`: stripe>=10.0.0

### 6. Bug Fixes (22 verified)
- CRITICAL: duplicate user_id field, missing PORTKEY config, Cloudflare history loss, a2a/security for→while, auth/tokens raw.decode()
- HIGH: KillSwitch race, RateLimitQueue token leak
- MEDIUM: duplicate pattern, Cloudflare URL, ground-truth scoring, LLM audit locks, ProactiveContext/FallbackChain/CostOptimizer/SecretRedactor races, dead code

### 7. Frontend
- ChatMessage.jsx: setTimeout cleanup in CopyButton + CodeBlock
- CommandPalette.jsx: setTimeout cleanup for input focus

### 8. CI Pipeline
- Split ci.yml → lint.yml, tests.yml, build.yml, security.yml

## Risk Assessment

| Area | Risk | Reason |
|------|------|--------|
| Auth | HIGH | New JWT/OAuth flow, session management |
| Billing | HIGH | Payment processing, quota enforcement |
| Isolation | HIGH | Multi-tenant data separation |
| Bug fixes | MEDIUM | 22 fixes across core systems |
| Frontend | LOW | setTimeout cleanup only |
| CI | LOW | Config split, no logic change |

## Test Coverage

- 16 new billing tests
- 6 tenancy isolation leak tests
- 135 tests passing in affected suites
- 2886 total passing, 4 failing (pre-existing test-side issues)
