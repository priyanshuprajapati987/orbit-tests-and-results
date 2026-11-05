# ORBIT — AI Operating System

## Tech Stack
- **Backend:** Python 3.11, Flask (internal API on 127.0.0.1:5000), 150 blueprints
- **Frontend:** React 18, Vite, Tailwind CSS, react-icons, framer-motion
- **Desktop:** PyQt5 QWebEngineView loads React SPA from Flask
- **LLM:** OpenRouter, Ollama (local), Gemini, Groq — multi-provider with failover
- **Voice:** Edge-TTS, XTTS v2, Vosk STT, OpenWakeWord
- **Database:** SQLite (procedural memory), JSON files (config, state)
- **Testing:** pytest (1578+ tests), npm test
- **Packaging:** PyInstaller (desktop), npm build (frontend)

## Architecture
- Flask serves as internal API only — never exposed as web server
- React SPA served from `ui_provided/dist/` via Flask static
- PyQt5 desktop wrapper loads `http://127.0.0.1:5000`
- 25 agents, 20 tools, 87+ core systems
- Agent routing: QueenAgent orchestrates → specialized agents → tools
- Auth: ORBIT_API_KEY + ephemeral _UI_TOKEN per boot

## Conventions
- Python: relative imports within `orbit.orbit.*` package
- React: functional components + hooks, no class components
- CSS: Tailwind utility classes + CSS custom properties (`var(--orbit-*)`)
- Error handling: try/except with logging, never bare `pass`
- Flask: `get_json(silent=True) or {}`, never `force=True` without `silent=True`
- Testing: pytest fixtures, mock external services, hermetic tests

## Key Paths
- `orbit/orbit/` — canonical Python package (inner)
- `orbit/` — outer package with re-exports
- `ui_provided/src/` — React frontend
- `orbit/orbit/core/` — 87+ core systems
- `orbit/orbit/agents/` — 25 agents
- `orbit/orbit/tools/` — 20 tools
- `tests/` — pytest test suite
