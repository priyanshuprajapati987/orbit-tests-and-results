# ORBIT — Improvement Plan

## 1. Testing
- Add unit tests for Phase 2 & Phase 3 features (voice_screen, cua, multilang, debugger, RAG, trading)
- Target: 0 skips by running Ollama + services in CI
- Add coverage report (pytest-cov), target 80%+

## 2. Performance
- Profile Flask startup (629 modules) — lazy-load heavy systems
- Frontend bundle size audit (Vite build)
- Cache LLM responses (RouteLLM already has cache; verify hit rate)

## 3. Code Quality
- Run ruff + mypy on orbit/orbit; fix warnings
- Remove dead code (DEAD_CODE_EVIDENCE.md follow-up)
- Consolidate duplicate utils

## 4. UX/Frontend
- Rebuild + verify all 138 panels wired
- Add loading states + error boundaries
- Mobile responsiveness check

## 5. Security
- Re-run security checklist before release
- Rotate secrets, verify .env not committed
- Dependency audit (npm + pip)

## 6. Docs
- Update README with v3.7.0 stats
- API docs auto-generation

## Priority Order
P0: Tests (Phase 2/3) → P1: Performance → P2: Code quality → P3: UX → P4: Docs
