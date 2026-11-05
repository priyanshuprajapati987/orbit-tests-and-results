# Implementation Plan: Make ORBIT Smarter

Branch: main
Created: 2026-09-01
Refined: 2026-09-06

## Context
ORBIT has solid infrastructure (25 agents, 20 tools, multi-provider routing) but the intelligence layer has gaps. Most planned improvements were already implemented in prior sessions. This plan reflects the remaining work.

## Current State (Verified)
- ✅ History capped at 50 (`assistant.py:1272`)
- ✅ Disambiguation wired to smart_memory (`assistant.py:1120-1129`)
- ✅ Adaptive prompts with skill level + topics (`prompts.py:63-110`)
- ✅ Orchestrator-informed web grounding (`conversation_engine.py:528-555`)
- ✅ Follow-up detection with word overlap (`conversation_engine.py:244-254`)
- ✅ Personalization context builder (`smart_memory.py:208-242`)
- ✅ Action sequence tracking (`proactive_context.py:120-147`)
- ✅ Quality feedback loop in orchestrator (`orchestrator.py:396-435`)
- ❌ `build_personalization_context()` NOT wired into `context_manager.py:get_context()`

---

## Remaining Work

### Task 1: Wire Personalization into Context Manager
**File:** `core/context_manager.py` (~5 lines)
**What:** Call `smart_memory.build_personalization_context(query)` inside `get_context()` and prepend the result to the context block. This makes user preferences, correction history, and frequent topics visible to every LLM call.
**Implementation:**
```python
# In get_context(), after building parts[]:
try:
    from .smart_memory import get_smart_memory
    personalization = get_smart_memory().build_personalization_context(query)
    if personalization:
        parts.insert(0, personalization)
except Exception:
    pass
```
**Impact:** Model instantly knows user preferences, correction history, and recent topics

### Task 2: Wire Personalization into Router System Prompts
**File:** `core/llm/router.py` (~10 lines)
**What:** When `system_prompt` is None in `generate()`, build a `user_context` dict from smart_memory (skill_level, recent_topics, response_style) and pass it to `system_prompt_for(category, user_context)`. Currently `system_prompt_for()` accepts `user_context` but the router never passes it.
**Implementation:**
```python
# In generate(), when building system_prompt:
if system_prompt is None:
    try:
        from ..smart_memory import get_smart_memory
        mem = get_smart_memory()
        user_ctx = {
            "skill_level": mem._expertise_level,
            "recent_topics": [t[0] for t in mem.get_frequent_topics(3)],
        }
        system_prompt = system_prompt_for(category, user_ctx)
    except Exception:
        system_prompt = system_prompt_for(category)
```
**Impact:** Every LLM call gets adaptive prompts tailored to user expertise

---

## Commit Plan
- **Commit 1:** "feat(intelligence): wire personalization into context manager + router"

## Verification
1. Compile check `context_manager.py` and `router.py`
2. Run existing test suite → 0 regressions
3. Manual test: ask "who am I?" → should know user name from config
4. Manual test: ask technical questions → should get expert-level prompts
5. Full suite: target 2443+ passing
