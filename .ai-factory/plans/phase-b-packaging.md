# Phase B — PyInstaller Desktop Packaging

**Status:** done (verified 2026-08-02, frozen smoke green)
**Target:** Jarves onedir folder with `Jarves.exe`
**Branch:** `feature/phase-a-boot-routing`

---

## Decisions (confirmed by user)
1. **Data location:** runtime data (`jarves_data/`, `data/`, `.env`, `.fernet_key`) lives **next to the .exe**.
2. **Bundle size:** **Full build** — include torch + XTTS + vosk (voice cloning + offline STT work).
3. **Format:** **onedir** folder (`dist/Jarves/Jarves.exe`), distributed as zip.

---

## Architecture

### Runtime-path resolver (NEW: `jarves/jarves/core/runtime_paths.py`)
Single source of truth for app paths, frozen-aware:

| Helper | Frozen (onedir) | Dev |
|--------|----------------|-----|
| `is_frozen()` | `True` | `False` |
| `app_root()` | `dirname(sys.executable)` (next to .exe) | repo root (`parents[3]` of this file) |
| `bundle_root()` | `sys._MEIPASS` (`_internal` — read-only bundled assets) | repo root |
| `jarves_data_dir()` | `app_root()/jarves_data` | repo root `jarves_data` |
| `frontend_dist()` | `bundle_root()/ui_provided/dist` | repo root `ui_provided/dist` |

- **Writable data** (jarves_data, data, .env, .fernet_key, voice_samples, models) → `app_root()`
- **Read-only bundled assets** (frontend `dist/`) → `bundle_root()`

### Files that MUST change (frozen-safe)
1. `jarves/jarves/config.py` — `.env` load path + `_FERNET_KEY_PATH` + dir-based defaults → `app_root()`
2. `jarves/jarves/server.py:180` — `static_dir` → `frontend_dist()`
3. `jarves/jarves/core/autonomous_chat.py` — `parents[3]/jarves_data` → `jarves_data_dir()`
4. `jarves/jarves/core/battle.py` — `parents[3]/jarves_data` → `jarves_data_dir()`
5. `jarves/jarves/core/ground_truth.py` — `parents[3]/jarves_data` → `jarves_data_dir()`
6. `jarves/jarves/core/agent_performance_journal.py` — `parent.parent.parent/jarves_data` → `jarves_data_dir()`
7. `jarves/jarves/core/solution_pattern_indexer.py` — `parent.parent.parent/jarves_data` → `jarves_data_dir()`
8. `jarves/jarves/xtts.py` — `CLONING_SAMPLES_DIR` default → `app_root()`
9. `jarves/jarves/core/policy_engine.py` — audit dir default → `jarves_data_dir()/security`
10. ~20 CWD-relative `Path("jarves_data")` modules → `jarves_data_dir()` (deterministic on double-click)

### PyInstaller spec (`jarves/build.spec`)
- Entry: `main.py`
- onedir, `name="Jarves"`, `console=False`
- Data: `ui_provided/dist` → `ui_provided/dist` (under `_internal`)
- Excludes: none (full build)
- Hidden imports: PyQt5.QtWebEngineWidgets, edge_tts, vosk, torch (hooks-contrib)
- `sys._MEIPASS` → `_internal` onedir layout (PyInstaller ≥ 6)

---

## Steps
1. [x] Create plan
2. [x] Install `pyinstaller` + `pyinstaller-hooks-contrib` into system Python
3. [x] Create `core/runtime_paths.py`
4. [x] Wire `config.py` (.env, fernet, dir defaults) to resolver
5. [x] Fix `server.py` static_dir
6. [x] Convert all `jarves_data` hardcoded paths
7. [x] Write `build.spec` + verify with `--clean` build
8. [x] Smoke-test: launch `Jarves.exe`, verify server up + web UI loads + data written next to exe
9. [x] Docs checkpoint (CONTEXT/README/VERSION) + commit

---

## Risks / Mitigations
- **QtWebEngine bundling** — use hooks-contrib; smoke-test `Jarves.exe` before declaring done. Fallback: collect PyQt5.QtWebEngineWidgets data dirs manually.
- **torch size (~14k files)** — build time long; acceptable (user chose full). Use onedir (no re-extract).
- **Path regressions in dev** — resolver returns identical paths in dev; verify by running tests after conversion.
- **WebEngine + onefile temp** — avoided entirely by onedir choice.
