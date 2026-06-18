# CLAUDE.md — AgentForge

> This file is auto-loaded by Claude Code every session. It is the source of truth for
> *how we build*. Read `docs/PLAN.md` for *what we build* (the full phased spec).

## What this is
A self-hosted, **no-code agent platform**: users visually build an AI agent on a canvas,
test it with live logs, publish it to a marketplace, and other users install and run it.
LLM inference runs on a **local Gemma 4 (E4B-it)** model via Ollama. This is a portfolio
project targeting an AI Agent Platform Engineering internship — production-grade execution
concerns (durable state, replay, error recovery) are the point, not an afterthought.

## Tech stack (do not substitute without being asked)
- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0 (typed), Alembic, Pydantic v2.
- **Runtime:** LangGraph for the agent execution graph + checkpointer (durable execution).
- **Async:** `arq` worker on Redis for run execution. Redis also = pub/sub + cache.
- **DB:** PostgreSQL (data models AND LangGraph checkpoints).
- **Inference:** local Gemma 4 E4B via Ollama, behind an `LLMProvider` interface.
- **Frontend:** React + Vite + TypeScript, `@xyflow/react` (React Flow) for the canvas.
- **Infra:** Docker Compose (postgres, redis, ollama, api, worker, web).
- **Tooling:** `uv` for Python deps, `ruff` (lint+format), `mypy --strict`, `pytest`.

## Repository layout
```
backend/
  app/
    routers/         # thin: validation + auth dependency only
    services/        # business logic
    repositories/    # ALL database access goes here
    runtime/         # graph compiler, node handlers, checkpointer wiring
    llm/             # LLMProvider interface + Ollama/Gemma impl
    models/          # SQLAlchemy models
    schemas/         # Pydantic request/response models
    workers/         # arq tasks
  tests/             # mirrors app/ ; unit + integration
  alembic/
web/                 # React + Vite frontend
infra/               # docker-compose.yml, Dockerfiles
docs/PLAN.md         # the full phased build plan — consult before each phase
```

## Architecture rules (non-negotiable)
1. **Layering:** `routers → services → repositories`. Routers never touch the DB session
   directly; services never write raw SQL; repositories never contain business logic.
2. **Typed everywhere.** Full type hints; `mypy --strict` must pass. No bare `Any` without
   a `# justified:` comment.
3. **Pydantic at the boundary.** Every request/response uses a Pydantic schema, never a raw
   dict or a SQLAlchemy model leaking out of a router.
4. **Async I/O.** DB and HTTP calls are `async`. Don't block the event loop.

## ⚠️ The replay-safety contract (applies to everything in `app/runtime/`)
The runtime is durable: a crashed run resumes from its last checkpoint by **replaying**
completed steps. This only works if runtime code is deterministic. Therefore, inside
`app/runtime/` node handlers and graph control flow:
1. **No nondeterminism** — never call `datetime.now()`, `random`, `uuid4()`, or read
   external mutable state inside control flow. If a value like "now" is needed, it must be
   captured once as a recorded step result, never recomputed on replay.
2. **Idempotent side effects** — every side-effecting tool call is wrapped with an
   idempotency key derived from `(run_id, node_id, step_index)` and persisted in the
   `tool_calls` table. On resume, a completed key returns its stored result; it is NEVER
   re-executed.
3. **Versioned graphs** — a run always executes against the immutable `agent_versions` row
   it started on. Never mutate a published version.
If you are about to add randomness or a wall-clock read inside `app/runtime/`, STOP and ask.

## ⚠️ Gemma / Ollama tool-calling gotcha
Gemma 4 returns `tool_calls`, but the Ollama **OpenAI-compatible `/v1` streaming** path can
fail to surface them to client libs. The project standardizes tool-calling turns on Ollama's
**native `/api/chat`** (or the `ollama` python client). All model access goes through
`app/llm/provider.py` (`LLMProvider`) — never call Ollama directly from a node handler.
Keep prompts/tool-result payloads tight: E4B realistically holds ~20K tokens on consumer HW.

## Definition of Done (every change)
- [ ] New/changed behavior has tests in `backend/tests/` (unit + integration where it
      crosses a layer).
- [ ] `ruff check` and `ruff format --check` pass.
- [ ] `mypy --strict app/` passes.
- [ ] `pytest` is green.
- [ ] If a DB model changed → an Alembic migration is generated and named meaningfully.
- [ ] Runtime changes respect the replay-safety contract.
Use the `/checks` skill to run the gate. Don't declare a task done until it passes.

## Workflow expectations
- Work **one phase at a time** (see `docs/PLAN.md`). Use the `/start-phase` skill.
- **Plan before coding** on anything non-trivial: propose a short plan, get confirmation,
  then implement. Prefer test-driven: write the failing test first.
- Keep diffs reviewable. After a logical unit, run `/checks`, then propose a commit message
  (do not auto-push; `git push` is denied).
- For new HTTP endpoints use `/add-endpoint`. For new runtime node types use `/add-node-type`.

## Commands
```bash
# bring up the stack
docker compose -f infra/docker-compose.yml up -d
# backend deps / run
cd backend && uv sync
uv run uvicorn app.main:app --reload
uv run arq app.workers.WorkerSettings        # run the async worker
# quality gate
uv run ruff check . && uv run ruff format --check . && uv run mypy --strict app && uv run pytest
# migrations
uv run alembic revision --autogenerate -m "msg" && uv run alembic upgrade head
# frontend
cd web && npm install && npm run dev
```

## Scope guardrails (do NOT build unless asked)
- No multi-tenant org/RBAC, billing, or payment flows.
- No more than ~6 node types (input, llm, tool, condition, loop, output). Quality > breadth.
- Loop nodes are flat only — a loop node nested inside another loop's body is rejected at
  compile time (`loop_counters` doesn't reset per outer iteration); nested loops are a
  non-goal for this version.
- Don't add new infra services beyond the five above without asking.
- The headline demo is **resume-from-crash**; protect that path above all else.
