# AgentForge

A self-hosted, no-code agent platform. Build an AI agent on a canvas, test it with live logs,
publish it to a marketplace, and let others install and run it. LLM inference runs on a local
**Gemma 4 (E4B-it)** model via Ollama.

See `docs/PLAN.md` for the full phased build plan and `CLAUDE.md` for engineering conventions.

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

Next: in Claude Code, run `/start-phase 1` to build the data models and CRUD.
