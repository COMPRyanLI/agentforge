# AgentForge

A self-hosted, no-code agent platform. Build an AI agent on a canvas, test it with live logs,
publish it to a marketplace, and let others install and run it. LLM inference runs on a local
**Gemma 4 (E4B-it)** model via Ollama.

See `docs/PLAN.md` for the full phased build plan and `CLAUDE.md` for engineering conventions.

---

## Architecture

```
   web (React + Vite + React Flow)
        │  REST + SSE
        ▼
   FastAPI api  ──────────────►  PostgreSQL
        │  enqueue                 (agents, tools, runs,
        ▼                           run_events, LangGraph
   Redis (queue + pub/sub)          checkpoints)
        │
        ▼
   arq worker ──► LangGraph runtime + checkpointer
                        │
                        ▼
                  Ollama → Gemma 4 E4B-it
```

The API enqueues a run to an **arq** worker over Redis and returns immediately; the worker
compiles the agent's `graph_json` into a LangGraph `StateGraph` and executes it. Every node
transition is written to the `run_events` table and published on a Redis channel, which the
`GET /runs/{id}/events` SSE endpoint streams to the canvas live. LangGraph's Postgres
checkpointer persists state after every step, which is what makes resume and replay possible.

## The replay-safety contract

The runtime is durable: a crashed run resumes from its last checkpoint by **replaying**
completed steps. This only works if runtime code (`backend/app/runtime/`) is deterministic:

1. **No nondeterminism** — node handlers never call `datetime.now()`, `random`, or `uuid4()`
   inside control flow. Where a value like "now" is needed, it's captured once as a recorded
   step result, never recomputed on replay.
2. **Idempotent side effects** — every tool call is wrapped with an idempotency key derived
   from `(run_id, node_id, step_index, call_index)`, persisted in `tool_calls`. On resume, a
   completed key returns its stored result; it is never re-executed.
3. **Versioned graphs** — a run always executes against the immutable `agent_versions` row it
   started on, never a published version that's since changed.

The web app stores the JWT in `localStorage` for simplicity — a deliberate tradeoff for this
project's scope. The production-hardened version would use httpOnly cookies plus short-lived
access tokens with a refresh-token rotation, trading some implementation complexity for
immunity to XSS-based token theft (a `localStorage` token is readable by any script running
on the page).

### Resume from crash (the headline demo)

```bash
# start a run, then kill the worker mid-execution
uv run arq app.workers.WorkerSettings   # Ctrl-C while a run is "running"

# restart the worker, then resume the run from its last checkpoint
uv run arq app.workers.WorkerSettings
curl -X POST localhost:8000/runs/{run_id}/resume -H "Authorization: Bearer $TOKEN"
```

The agent finishes from where it stopped — no already-completed LLM call is repeated, no tool
side effect double-fires. *(`docs/img/resume-demo.gif` — TODO: record this.)*

## Run metrics dashboard

Every agent has a run-history page (`/agents/{id}/runs` in the web app) showing success rate,
p95 latency, and average tokens/steps per run — computed over the agent's terminal runs — plus
a per-run timeline view (`/runs/{id}/timeline`) that replays a run's full `run_events` history
with token/latency badges on each LLM step. *(Screenshot: `docs/img/run-timeline.png` — TODO.)*

---

## Phase 0 quickstart

### 0. Verify Gemma tool calling FIRST (the spike)
You need Ollama running locally with the model pulled:
```bash
ollama pull gemma4:e4b
ollama serve
```
Then, from the repo root:
```bash
cd backend && uv sync
uv run python ../scripts/spike_gemma_tools.py
```
Read which path prints `PASS`. `native` (Ollama `/api/chat`) should win — that's the path
`app/llm/provider.py` already uses. If only a different path passes, tell Claude Code so it can
adjust the provider.

### 1. Run the backend
```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload     # http://localhost:8000/health  +  /docs
uv run arq app.workers.WorkerSettings     # the async worker (separate terminal)
```

### 2. Run the frontend
```bash
cd web
npm install
npm run dev                                # http://localhost:5173  (empty canvas + one node)
```

### 3. Or run everything in Docker
Ollama stays on your host; the containers reach it via `host.docker.internal`.
```bash
docker compose -f infra/docker-compose.yml up -d
```

### Quality gate
```bash
cd backend
uv run ruff check . && uv run ruff format --check . && uv run mypy --strict app && uv run pytest
```

---

## Layout
```
backend/   FastAPI app (routers → services → repositories), runtime, llm, workers, tests, alembic
web/       React + Vite + React Flow canvas
infra/     docker-compose
scripts/   spike_gemma_tools.py
docs/      PLAN.md
```

## Status

Phases 0–7 of `docs/PLAN.md` are built: data models & auth, the runtime (compiler, tool
calling, durable execution with resume/replay), async execution with live SSE logs, the
no-code builder UI, the marketplace/templates, and the run-history/metrics dashboard above.
