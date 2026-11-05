# Test Plan — M3/M4 SaaS Milestones

**Branch:** main
**Date:** 2026-09-29

## 1. Auth System Tests

| ID | Test | Priority | Type |
|----|------|----------|------|
| AUTH-01 | Signup creates user, returns tokens | High | Unit |
| AUTH-02 | Login with valid credentials returns tokens | High | Unit |
| AUTH-03 | Login with invalid credentials returns 401 | High | Unit |
| AUTH-04 | Refresh token rotation works, old token revoked | High | Unit |
| AUTH-05 | Logout revokes refresh token (idempotent) | High | Unit |
| AUTH-06 | /api/auth/me returns current user | High | Unit |
| AUTH-07 | Password reset flow (request → reset → login) | High | Unit |
| AUTH-08 | OAuth state verification (redirect claim) | High | Unit |
| AUTH-09 | OAuth verifier cookie secure flag | Medium | Unit |
| AUTH-10 | Timezone-aware datetime handling in token expiry | High | Unit |

## 2. Per-User Isolation Tests

| ID | Test | Priority | Type |
|----|------|----------|------|
| ISO-01 | Memory: user A cannot read user B's memories | High | Unit |
| ISO-02 | Memory: user A cannot delete user B's memories | High | Unit |
| ISO-03 | Conversations: user A cannot see user B's conversations | High | Unit |
| ISO-04 | Conversations: user A cannot delete user B's conversations | High | Unit |
| ISO-05 | Tasks: user A cannot see user B's tasks | High | Unit |
| ISO-06 | Tasks: user A cannot delete user B's tasks | High | Unit |
| ISO-07 | Engine: session engines are isolated per user | High | Unit |
| ISO-08 | Solo mode: no user_id = "local" behavior unchanged | High | Unit |

## 3. Per-User Budget Tests

| ID | Test | Priority | Type |
|----|------|----------|------|
| BUD-01 | Free plan: 200 calls/day cap enforced | High | Unit |
| BUD-02 | Free plan: $2/day cap enforced | High | Unit |
| BUD-03 | Pro plan: 2000 calls/day cap | Medium | Unit |
| BUD-04 | Quota exceeded returns upgrade nudge | High | Unit |
| BUD-05 | Usage accumulates across multiple calls | High | Unit |
| BUD-06 | Usage resets daily | Medium | Unit |

## 4. Rate Limiting Tests

| ID | Test | Priority | Type |
|----|------|----------|------|
| RATE-01 | Per-user rate limit bucket created | High | Unit |
| RATE-02 | Per-user rate limit enforced | High | Unit |
| RATE-03 | Unauthenticated falls back to per-IP | Medium | Unit |
| RATE-04 | Redis backend: atomic consume | Medium | Unit |
| RATE-05 | Redis fail-open when Redis down | Medium | Unit |

## 5. Billing Tests

| ID | Test | Priority | Type |
|----|------|----------|------|
| BILL-01 | Plans list returns 3 tiers | High | Unit |
| BILL-02 | Get user plan defaults to free | High | Unit |
| BILL-03 | Set user plan (free → pro) | High | Unit |
| BILL-04 | Record usage accumulates | High | Unit |
| BILL-05 | Check quota returns correct remaining | High | Unit |
| BILL-06 | Quota exceeded flag set correctly | High | Unit |
| BILL-07 | Get invoices (empty + with data) | Medium | Unit |
| BILL-08 | Create checkout (Stripe disabled → None) | Medium | Unit |
| BILL-09 | Webhook handling (Stripe disabled → False) | Medium | Unit |
| BILL-10 | Admin stats returns correct counts | Medium | Unit |
| BILL-11 | Thread safety: concurrent writes | High | Unit |
| BILL-12 | Persistence: data survives restart | Medium | Unit |

## 6. Bug Fix Regression Tests

| ID | Test | Priority | Type |
|----|------|----------|------|
| BUG-01 | MemoryEntry dataclass has no duplicate fields | High | Unit |
| BUG-02 | Cloudflare history not dropped without system_prompt | High | Unit |
| BUG-03 | a2a/security nonce pruning uses while (not for) | High | Unit |
| BUG-04 | auth/tokens secret generation uses hex (not decode) | High | Unit |
| BUG-05 | KillSwitch is_active() reads under lock | Medium | Unit |
| BUG-06 | RateLimitQueue _release() returns token | High | Unit |
| BUG-07 | Ground truth: text_ok required for required/any_of items | Medium | Unit |
| BUG-08 | LLM audit reads under _write_lock | Medium | Unit |
| BUG-09 | ProactiveContext _save() reads under lock | Medium | Unit |
| BUG-10 | FallbackChain remaining counter under asyncio.Lock | Medium | Unit |

## 7. Frontend Tests

| ID | Test | Priority | Type |
|----|------|----------|------|
| FE-01 | CopyButton setTimeout cleanup on unmount | Medium | Unit |
| FE-02 | CodeBlock setTimeout cleanup on unmount | Medium | Unit |
| FE-03 | CommandPalette setTimeout cleanup on unmount | Medium | Unit |

## 8. Integration Tests

| ID | Test | Priority | Type |
|----|------|----------|------|
| INT-01 | Full signup → login → chat flow | High | E2E |
| INT-02 | Billing: upgrade → quota check → usage record | High | E2E |
| INT-03 | Isolation: two users, no data leak | High | E2E |
| INT-04 | Rate limit: burst requests → 429 | Medium | E2E |
