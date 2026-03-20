# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

AutoDev automates the software development lifecycle triggered by Zoho Projects tasks. It runs Claude Code (this CLI) as a subprocess to do the actual planning and coding, then creates GitHub/GitLab PRs and updates Zoho task status. Everything runs locally on one machine.

## Running the Stack

**Full stack (recommended):**
```bash
cd /Users/kaushikdevmurari/Documents/one_man_army/autodev
./start.sh
```

**Individual services (PostgreSQL and Redis are via Homebrew, not Docker):**
```bash
# Infrastructure
brew services start postgresql@14
brew services start redis

# Backend (from autodev/backend/)
source venv/bin/activate
uvicorn app.main:app --port 8000 --reload

# rq worker (separate terminal, from autodev/backend/)
source venv/bin/activate
rq worker pipeline:default pipeline:agents

# Frontend (from autodev/frontend/)
npm run dev
```

**Ports:** Frontend → 3000, Backend API → 8000, API docs → http://localhost:8000/docs

## Database

PostgreSQL runs as the local macOS user (no password). The connection string in `.env` is:
```
DATABASE_URL=postgresql+asyncpg://kaushikdevmurari@localhost/autodev_db
```

Schema is managed via `init_db()` on startup (`create_all` from SQLAlchemy models — no Alembic migrations are actively used). To reset the DB:
```bash
psql -c "DROP DATABASE autodev_db; CREATE DATABASE autodev_db;"
```

When adding a new SQLAlchemy model, always import it in `app/workers/pipeline_worker.py` so rq workers can resolve relationship strings.

## Backend Architecture

```
app/
├── main.py          — FastAPI app; mounts api_router at /api/v1, task_assign at /, ws_router at /
├── config.py        — pydantic-settings; reads from backend/.env
├── database.py      — AsyncSessionLocal + init_db()
├── dependencies.py  — get_db, get_current_user (JWT bearer)
├── api/
│   ├── v1/router.py — aggregates all sub-routers
│   ├── task_assign.py — GET/POST /task-assign (Zoho webhook; root-level)
│   └── v1/websocket.py — WS /ws/pipeline/{run_id} (root-level, not under /api/v1)
├── agents/          — one agent per pipeline stage
├── services/        — external API clients + redis + claude subprocess
└── workers/pipeline_worker.py — rq sync wrapper around async orchestrator
```

## Pipeline State Machine

```
task_received → planning → plan_review ⏸ → developing → testing → test_review ⏸ → creating_mr → mr_open ⏸ → completed
                                                                                                    ↕ failed (any stage)
```

**Critical pattern — human gate re-enqueue:** The rq job exits at each `⏸` stage. When a human approves via the UI, the API endpoint must call `enqueue_pipeline(run_id, project_id)` to re-start the rq job. Every endpoint in `plans.py` and `tests.py` that advances the pipeline must include this call. Missing it causes the pipeline to silently stop.

```python
# Every approval/skip endpoint must do this:
from app.services.redis_service import enqueue_pipeline
enqueue_pipeline(str(run.id), str(run.project_id))
```

## Live Log Streaming

Two-layer approach in `services/redis_service.py`:
1. **Redis list** (`pipeline:logbuf:{run_id}`, 2h TTL) — every `publish_log` appends here for replay
2. **Redis pub/sub** (`pipeline:logs:{run_id}`) — live delivery to open WebSocket connections

The WebSocket endpoint (`api/v1/websocket.py`) replays the full buffer on connect, then subscribes to live pub/sub. This means logs appear even if the UI is opened mid-run or after completion.

All agents call `self.publish_log(line)` which routes to `publish_log(run_id, line, agent=self.agent_type)`.

## Claude CLI Subprocess

`services/claude_service.py` invokes `claude --print --dangerously-skip-permissions` as a subprocess. Key non-obvious details:

- **`CLAUDECODE` env var is stripped** — running inside Claude Code sets this env var, which blocks nested `claude` invocations. `_clean_env()` removes it before spawning the subprocess.
- **Prompt is passed via stdin, not as a positional arg** — if the prompt were a positional arg, `--allowedTools` would consume it as a tool name.

## GitHub / GitLab Integration

- **GitConfig model** (`models/git_config.py`) stores OAuth tokens per user per provider. Unique constraint on `(user_id, provider)`.
- **GitHub OAuth**: Client credentials in `.env` as `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET`. Callback URL: `http://localhost:3000/github-callback`.
- **`github_service.push_branch()`** uses token-embedded remote URL (`https://{token}@github.com/{owner}/{repo}.git`) and runs git subprocesses in the target project directory. The project directory must already be a git repo.
- **Orchestrator** fetches `GitConfig` from DB and passes `git_provider`, `git_token`, `repo_full_name` to `PRCreatorAgent`. If neither GitHub nor GitLab is configured, the pipeline skips to `completed`.

## Frontend Architecture

Vite + React 18 + TypeScript + Tailwind CSS. Vite proxies `/api` and `/ws` to `localhost:8000`.

- **`AuthContext`** (`context/AuthContext.tsx`) — JWT token shared across all components. Login state change in `App.tsx` only works if this context is used; per-component `useState` for auth does not propagate.
- **`services/api.ts`** — single axios instance with JWT bearer interceptor. 401 responses redirect to `/login`.
- **LogStream component** — always connects WebSocket on mount (buffer replay shows history even for completed runs). Green pulse dot indicates live connection.

## Environment Variables (backend/.env)

Required non-obvious keys:
```
SECRET_KEY=...                    # JWT signing (min 32 chars)
ZOHO_CLIENT_ID=...
ZOHO_CLIENT_SECRET=...
GITHUB_CLIENT_ID=Ov23ligKpVdwV8TPQEye
GITHUB_CLIENT_SECRET=...
```
