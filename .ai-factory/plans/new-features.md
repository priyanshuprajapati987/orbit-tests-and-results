# ORBIT — New Features Implementation Plan

**Date:** 2026-08-26
**Goal:** Add missing features that don't exist yet

---

## Status: What Already Exists ✅

| Feature | Status |
|---------|--------|
| Voice pipeline (TTS/STT) | ✅ DONE |
| Screen control (pyautogui + CUA) | ✅ DONE |
| Email tool | ✅ DONE |
| Calendar tool | ✅ DONE |
| Social media agent | ✅ DONE (via N8n) |
| File watcher | ✅ DONE |
| Daily briefing | ✅ DONE |
| Knowledge base | ✅ DONE |
| Code generation + review | ✅ DONE |
| Hand gestures | ✅ DONE |
| Proactive assistant | ✅ DONE |
| Background trainer | ✅ DONE |
| Security scanner | ✅ DONE |
| A2A protocol | ✅ DONE |

---

## New Features to Implement 🆕

### Phase 1: Quick Wins (1-2 hours each)

| # | Feature | Description | Files to Create/Modify |
|---|---------|-------------|----------------------|
| 1 | **File Auto-Organize** | "Downloads folder sort kar" — auto-categorize files by type/date | `core/file_organizer.py`, `core/file_organizer_bp.py` |
| 2 | **Email Auto-Draft** | "Priyanshu ko email draft kar" — LLM generates draft, user reviews | Modify `tools/email_tool.py` |
| 3 | **CSV/Excel Analyzer** | "Ye CSV analyze kar" — load, summarize, chart generation | `core/data_analyzer.py`, `core/data_analyzer_bp.py` |
| 4 | **Quick Notes** | "Note le: meeting tomorrow 3pm" — fast note-taking with search | `core/quick_notes.py`, `core/quick_notes_bp.py` |

### Phase 2: Medium Complexity (3-4 hours each)

| # | Feature | Description | Files to Create/Modify |
|---|---------|-------------|----------------------|
| 5 | **Real-time Voice Chat** | Interruptible voice conversation (listen → think → speak loop) | Modify `core/voice_screen.py` |
| 6 | **Screen Click/Type** | "Wo button click kar", "ye type kar" — vision-based desktop control | Modify `tools/cua_computer.py`, `tools/desktop.py` |
| 7 | **Multi-Language** | Tamil/Telugu/Marathi support via config | Modify `core/config.py`, `core/prompts.py` |
| 8 | **Code Debugger** | "Ye error fix kar" — read error, explain fix, apply fix | Modify `agents/specialized.py` (CodeAgent) |

### Phase 3: Advanced (5+ hours each)

| # | Feature | Description | Files to Create/Modify |
|---|---------|-------------|----------------------|
| 9 | **RAG Knowledge Base** | Vector search over documents, not just keyword | Modify `core/knowledge_base.py`, add embeddings |
| 10 | **Trading Monitor** | Stock/crypto price alerts, portfolio tracking | `core/trading_monitor.py`, `core/trading_monitor_bp.py` |

---

## Commit Plan

- **Commit 1:** Phase 1 (4 features)
- **Commit 2:** Phase 2 (4 features)
- **Commit 3:** Phase 3 (2 features)

---

## Settings

- Testing: Yes
- Logging: Verbose
- Docs: No (warn-only)
