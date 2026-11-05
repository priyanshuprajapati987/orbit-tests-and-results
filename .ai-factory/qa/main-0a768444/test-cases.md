# Test Cases — M3/M4 SaaS Milestones

**Branch:** main
**Date:** 2026-09-29

---

## AUTH-01: Signup creates user, returns tokens

**Preconditions:** Database empty or user does not exist
**Steps:**
1. POST /api/auth/signup with `{email: "test@example.com", password: "SecurePass123!", display_name: "Test User"}`
2. Verify response status 200
3. Verify response contains `access_token`, `refresh_token`
4. Verify token is valid JWT with correct claims (sub, role, type)

**Expected:** 200, valid JWT pair returned
**Priority:** High

---

## AUTH-02: Login with valid credentials

**Preconditions:** User exists with known password
**Steps:**
1. POST /api/auth/login with `{email: "test@example.com", password: "SecurePass123!"}`
2. Verify response status 200
3. Verify access_token + refresh_token present

**Expected:** 200, valid tokens
**Priority:** High

---

## AUTH-03: Login with invalid credentials

**Preconditions:** User exists
**Steps:**
1. POST /api/auth/login with `{email: "test@example.com", password: "wrongpassword"}`
2. Verify response status 401
3. Verify error message does not reveal whether email exists

**Expected:** 401, generic error message
**Priority:** High

---

## AUTH-04: Refresh token rotation

**Preconditions:** User has valid refresh token
**Steps:**
1. POST /api/auth/refresh with refresh token
2. Verify new access_token + refresh_token returned
3. Attempt reuse of old refresh token
4. Verify old token is rejected (401)

**Expected:** New pair works, old token revoked
**Priority:** High

---

## AUTH-05: Logout revokes refresh token (idempotent)

**Preconditions:** User has valid refresh token
**Steps:**
1. POST /api/auth/logout with refresh token
2. Verify response status 200
3. POST /api/auth/logout again with same token
4. Verify second call also returns 200 (idempotent)

**Expected:** Both calls return 200
**Priority:** High

---

## AUTH-06: /api/auth/me returns current user

**Preconditions:** Valid access token
**Steps:**
1. GET /api/auth/me with Bearer access token
2. Verify response contains user email, role, display_name

**Expected:** 200, user profile returned
**Priority:** High

---

## AUTH-07: Password reset flow

**Preconditions:** User exists
**Steps:**
1. POST /api/auth/password/request with email
2. Verify response always returns 200 (no enumeration)
3. Extract reset token (from test hook or DB)
4. POST /api/auth/password/reset with token + new password
5. Login with new password

**Expected:** Full flow works, old password invalid
**Priority:** High

---

## AUTH-08: OAuth state redirect claim verification

**Preconditions:** OAuth provider configured
**Steps:**
1. Create state with redirect_uri = "https://example.com/callback"
2. Attempt to use state with different redirect_uri
3. Verify check_state returns None

**Expected:** State rejected on redirect mismatch
**Priority:** High

---

## ISO-01: Memory isolation between users

**Preconditions:** Two users (alice, bob)
**Steps:**
1. Write memory for alice: namespace="test", key="secret", value="alice-secret"
2. Write memory for bob: namespace="test", key="secret", value="bob-secret"
3. Read memory for alice
4. Read memory for bob
5. Verify alice sees only "alice-secret"
6. Verify bob sees only "bob-secret"

**Expected:** No cross-user data leak
**Priority:** High

---

## ISO-02: Memory delete isolation

**Preconditions:** Two users with memories
**Steps:**
1. Alice writes memory
2. Bob writes memory
3. Alice deletes her memory
4. Verify bob's memory still exists

**Expected:** Bob's data unaffected
**Priority:** High

---

## ISO-03: Conversation isolation

**Preconditions:** Two users
**Steps:**
1. Alice creates conversation "Alice Chat"
2. Bob creates conversation "Bob Chat"
3. Alice lists conversations → only sees hers
4. Bob lists conversations → only sees his
5. Alice tries to get Bob's conversation → 404

**Expected:** No cross-user conversation access
**Priority:** High

---

## ISO-04: Task isolation

**Preconditions:** Two users
**Steps:**
1. Alice adds task "task-a"
2. Bob adds task "task-b"
3. Alice lists tasks → only sees task-a
4. Bob lists tasks → only sees task-b
5. Alice tries to delete Bob's task → fails

**Expected:** No cross-user task access
**Priority:** High

---

## ISO-05: Session engine isolation

**Preconditions:** Two user sessions
**Steps:**
1. Get engine for "u-alice"
2. Get engine for "u-bob"
3. Add message to alice's engine history
4. Verify bob's engine history is empty

**Expected:** Engines are isolated
**Priority:** High

---

## BUD-01: Free plan call cap

**Preconditions:** User on free plan
**Steps:**
1. Record 199 calls (cost=0)
2. Verify quota_exceeded = False
3. Record 1 more call (total 200)
4. Verify quota_exceeded = True

**Expected:** Cap enforced at 200 calls
**Priority:** High

---

## BUD-02: Free plan cost cap

**Preconditions:** User on free plan
**Steps:**
1. Record usage totaling $1.99
2. Verify quota_exceeded = False
3. Record usage of $0.02 (total $2.01)
4. Verify quota_exceeded = True

**Expected:** Cap enforced at $2.00
**Priority:** High

---

## BUD-03: Quota exceeded returns upgrade nudge

**Preconditions:** User exceeds quota
**Steps:**
1. Exceed daily quota
2. Attempt chat generation
3. Verify response contains upgrade message
4. Verify quota_exceeded flag set

**Expected:** User informed to upgrade
**Priority:** High

---

## RATE-01: Per-user rate limit bucket

**Preconditions:** Authenticated user
**Steps:**
1. Make request to rate-limited endpoint
2. Verify per-user bucket created in limiter
3. Verify bucket has correct rate/burst

**Expected:** User-specific bucket exists
**Priority:** High

---

## RATE-02: Per-user rate limit enforced

**Preconditions:** Authenticated user, low burst limit
**Steps:**
1. Make requests exceeding burst limit
2. Verify 429 response returned
3. Verify other user not affected

**Expected:** Rate limit enforced per user
**Priority:** High

---

## BILL-01: Plans list

**Preconditions:** None
**Steps:**
1. GET /api/billing/plans
2. Verify 3 plans returned (free, pro, enterprise)
3. Verify each plan has price, caps, features

**Expected:** 3 plans with correct data
**Priority:** High

---

## BILL-02: Get user plan defaults to free

**Preconditions:** New user (no plan set)
**Steps:**
1. GET /api/billing/subscription
2. Verify plan_id = "free"

**Expected:** Default plan is free
**Priority:** High

---

## BILL-03: Set user plan

**Preconditions:** User exists
**Steps:**
1. POST /api/billing/admin/set-plan with user_id + plan_id="pro"
2. Verify response status 200
3. GET /api/billing/subscription
4. Verify plan_id = "pro"

**Expected:** Plan updated successfully
**Priority:** High

---

## BILL-04: Record usage accumulates

**Preconditions:** User exists
**Steps:**
1. Record usage: $0.50, 100 tokens in, 50 tokens out
2. Record usage: $0.30, 50 tokens in, 25 tokens out
3. GET /api/billing/usage
4. Verify total cost = $0.80, calls = 2

**Expected:** Usage accumulates correctly
**Priority:** High

---

## BILL-05: Check quota

**Preconditions:** User on pro plan
**Steps:**
1. Record usage: $5.00
2. GET /api/billing/usage
3. Verify: plan_id="pro", spent=$5.00, remaining=$15.00, calls_remaining=1999

**Expected:** Correct quota calculations
**Priority:** High

---

## BILL-06: Thread safety

**Preconditions:** Billing manager instance
**Steps:**
1. Spawn 10 threads
2. Each thread records 50 usage entries concurrently
3. Verify no errors
4. Verify total calls = 500

**Expected:** All 500 writes succeed, no corruption
**Priority:** High

---

## BILL-07: Persistence

**Preconditions:** Billing data exists
**Steps:**
1. Set user plan + record usage
2. Create new BillingManager instance (same data dir)
3. Verify plan + usage data loaded correctly

**Expected:** Data survives restart
**Priority:** Medium

---

## BUG-01: MemoryEntry dataclass integrity

**Preconditions:** memory_store module loaded
**Steps:**
1. Import MemoryEntry
2. Verify no duplicate fields
3. Verify user_id field exists with default "local"

**Expected:** Clean dataclass definition
**Priority:** High

---

## BUG-02: Cloudflare history not dropped

**Preconditions:** LLM router loaded
**Steps:**
1. Create LLMRequest with history but no system_prompt
2. Call _call_cloudflare
3. Verify history is included in messages

**Expected:** History always included
**Priority:** High

---

## BUG-03: a2a/security nonce pruning

**Preconditions:** a2a.security module loaded
**Steps:**
1. Import check_replay function
2. Verify it uses while loop (not for)
3. Add nonce, verify replay detection works

**Expected:** No syntax error, replay works
**Priority:** High

---

## BUG-07: Ground truth scoring

**Preconditions:** ground_truth module loaded
**Steps:**
1. Create item with required=["canberra"], number="Canberra"
2. Response = "42" (numeric only, no text match)
3. Verify correct = False (text_ok required)

**Expected:** Numeric-only response rejected
**Priority:** Medium

---

## FE-01: CopyButton setTimeout cleanup

**Preconditions:** ChatMessage component mounted
**Steps:**
1. Click copy button
2. Unmount component within 2 seconds
3. Verify no React warning about state update on unmounted component

**Expected:** No memory leak, no warning
**Priority:** Medium

---

## INT-01: Full signup → login → chat flow

**Preconditions:** Fresh database
**Steps:**
1. Signup new user
2. Login with credentials
3. Send chat message with Bearer token
4. Verify response contains assistant reply

**Expected:** Full flow works end-to-end
**Priority:** High

---

## INT-02: Billing upgrade → quota check

**Preconditions:** User on free plan
**Steps:**
1. Upgrade to pro plan
2. Verify quota reflects pro limits
3. Record usage
4. Verify usage tracked correctly

**Expected:** Plan change affects quota immediately
**Priority:** High

---

## INT-03: Two users, no data leak

**Preconditions:** Two users (alice, bob)
**Steps:**
1. Alice creates conversation + writes memory
2. Bob creates conversation + writes memory
3. Alice lists conversations → only hers
4. Bob lists conversations → only his
5. Alice searches for bob's data → empty

**Expected:** Complete data isolation
**Priority:** High
