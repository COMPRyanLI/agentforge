# AgentForge — A Self-Hosted, No-Code Agent Platform
### Detailed build plan for an AI Agent Platform Engineering internship portfolio project

**Author:** Yekun (Ryan) Li
**Inference engine:** Gemma 4 (E4B-it), served locally
**Target role:** AI Agent Platform Engineering Intern (Agent Marketplace + No-Code Agent Builder)

---

## 0. Why this project

The job posting asks for someone who has built: an **agent marketplace**, a **no-code agent builder**, an **agent runtime/harness**, **tool calling**, **state management**, **logging**, **replay**, **error recovery**, and clean **APIs + data models for Agents / Tools / Workflows / Templates**.

Rather than build something *adjacent* to that, this project builds *exactly that system* in miniature — a self-hostable platform where a non-technical user can visually create an agent, test it, publish it to a marketplace, and where another user can install and run it. Every bullet in the posting maps to a concrete component you will have shipped.

The reference projects in this space are **Dify**, **Langflow**, and **Flowise** (all open-source on GitHub). You are building a focused subset of what they do, but with the production-grade execution concerns (durable state, replay, recovery) that most toy clones skip — which is precisely the part that signals platform-engineering maturity.

### Requirement → component map

| Job requirement | Component you build | Where it lives |
|---|---|---|
| Agent Marketplace | Publish / list / install / rate APIs + UI | Phase 6 |
| No-Code builder | React Flow canvas, node palette, config panels | Phase 5 |
| Backend services | FastAPI app, layered services | Phases 1–4 |
| Agent runtime / harness | Graph compiler + LangGraph executor | Phases 2, 4 |
| Tool calling | Tool registry + schema + sandboxed invocation | Phases 2, 5 |
| State management | LangGraph checkpointer (Postgres/Redis) | Phase 4 |
| Logging | `run_events` table + Redis pub/sub + SSE | Phase 3 |
| Replay | Checkpoint history + fork-from-step | Phase 4 |
| Error recovery | Per-node retry + resume-from-checkpoint | Phase 4 |
| Data models (Agents/Tools/Workflows/Templates) | Postgres schema | Phase 1 |
| Async tasks | arq/Celery worker on Redis | Phase 3 |
| Testing | pytest unit + integration | All phases |
| Docker | docker-compose for the full stack | Phase 0 |

---

## 1. Architecture

```
                         ┌─────────────────────────────┐
                         │   React + Vite + React Flow │   ← no-code canvas, marketplace UI
                         │   (TypeScript)               │
                         └───────────────┬─────────────┘
                                         │ REST + SSE
                         ┌───────────────▼─────────────┐
                         │        FastAPI (Python)      │   ← API + auth + services
                         │  agents / tools / runs / mkt │
                         └───┬───────────┬──────────┬───┘
                             │           │          │
            enqueue run      │           │ pub/sub  │ persist
                             ▼           ▼          ▼
                  ┌──────────────┐  ┌─────────┐  ┌──────────────┐
                  │ arq worker   │  │  Redis  │  │  PostgreSQL  │
                  │ (executor)   │◄─┤ queue + │  │ data models  │
                  │              │  │ pub/sub │  │ + checkpoints│
                  └──────┬───────┘  └─────────┘  └──────────────┘
                         │ runs the agent graph
                         ▼
                  ┌──────────────────────────┐
                  │  LangGraph runtime        │
                  │  + checkpointer (durable) │
                  └──────────┬───────────────┘
                             │ LLM node calls
                             ▼
                  ┌──────────────────────────┐
                  │  Ollama → Gemma 4 E4B-it  │   ← local, OpenAI-compatible :11434
                  └──────────────────────────┘
```

**Stack rationale**
- **FastAPI** — async-native, hits the posting's bonus list, plays to your Python/RAG strength.
- **PostgreSQL** — relational data models *and* durable LangGraph checkpoints in one store (the DBOS/Postgres-as-orchestration pattern), so you avoid a second piece of infra.
- **Redis** — three jobs: async task queue, pub/sub channel for live logs, and (optionally) a fast checkpointer. Fills the one real gap in your resume.
- **React + React Flow** — `@xyflow/react` is the exact canvas library Langflow/Flowise/Dify use; reusing it is the industry-standard move, not a shortcut. Reuses your React SPA experience.
- **LangGraph** — gives you durable execution, checkpointing, time-travel/replay, and human-in-the-loop interrupts as first-class primitives, so you spend your time on the *platform* around the runtime instead of reinventing a state machine. You'll still write a thin harness layer on top so you understand (and can talk about) the internals.

---

## 2. ⚠️ Day-one spike: confirm Gemma tool calling BEFORE anything else

Gemma 4 has native function calling (Apache-2.0, all sizes). But there is a **known footgun**: `tool_calls` returned over Ollama's **OpenAI-compatible `/v1` streaming** endpoint are sometimes not recognized by client libraries (the model returns the tool call, the client ignores it and says "I can't do that"). Do not discover this in week 4.

**Spike checklist (half a day):**
1. `ollama pull gemma4:e4b` and `ollama serve`.
2. Write a 30-line Python script that defines one tool (e.g. `get_weather`) with a JSON schema and asks Gemma a question that should trigger it.
3. Test **three** invocation paths and record which reliably returns a parseable tool call:
   - Ollama **native** `/api/chat` with the `ollama` Python client (most reliable for tool calling).
   - OpenAI-compatible `/v1/chat/completions` **non-streaming**.
   - OpenAI-compatible `/v1/chat/completions` **streaming** (the known-flaky path).
4. **Decision:** standardize your LLM-node tool-calling turns on whichever path round-trips a tool call cleanly. Plan to use native `/api/chat` for tool turns and reserve streaming for plain text generation.

**Other Gemma gotchas to bake in now:**
- E4B advertises 256K context but realistically holds ~20K tokens before memory pressure on consumer hardware — keep system prompts and tool-result payloads tight, and truncate aggressively.
- Keep an abstraction seam (`LLMProvider` interface) so you can later swap to a larger Gemma size or a hosted model without touching node code.

---

## 3. Data models (PostgreSQL)

Use SQLAlchemy 2.0 + Alembic migrations. Core tables:

| Table | Key columns | Purpose |
|---|---|---|
| `users` | id, email, password_hash, created_at | auth + ownership |
| `agents` | id, owner_id, name, description, current_version_id, visibility (`private`/`published`), install_count, avg_rating | the marketplace unit |
| `agent_versions` | id, agent_id, version_number, graph_json, created_at | **immutable** snapshots → safe publishing + replay |
| `tools` | id, owner_id, name, description, json_schema, impl_type (`builtin`/`http`/`python`), config_json | reusable tool definitions |
| `templates` | id, name, description, category, graph_json | starter graphs users clone |
| `runs` | id, agent_id, agent_version_id, thread_id, status (`pending`/`running`/`succeeded`/`failed`/`interrupted`), input_json, output_json, started_at, ended_at, error_json | one execution |
| `run_events` | id, run_id, step_index, node_id, event_type, payload_json, ts | the **append-only log** powering live logs + replay |
| `tool_calls` | id, run_id, node_id, idempotency_key (unique), status, args_json, result_json | exactly-once side effects on resume |
| `ratings` | id, agent_id, user_id, score, comment | marketplace ratings |
| `installs` | id, agent_id, user_id, installed_at | marketplace installs |

`event_type` enum: `node_start`, `llm_call`, `llm_result`, `tool_call`, `tool_result`, `node_end`, `retry`, `error`, `interrupt`, `resume`.

**The `graph_json` shape** (what the canvas saves and the runtime compiles):

```json
{
  "nodes": [
    {"id": "in",   "type": "input"},
    {"id": "llm1", "type": "llm",
     "data": {"system_prompt": "...", "tools": ["tool_abc"], "model": "gemma4:e4b"}},
    {"id": "t1",   "type": "tool", "data": {"tool_id": "tool_abc"}},
    {"id": "cond", "type": "condition", "data": {"expr": "state.score > 0.5"}},
    {"id": "out",  "type": "output"}
  ],
  "edges": [
    {"source": "in", "target": "llm1"},
    {"source": "llm1", "target": "cond"},
    {"source": "cond", "target": "t1", "condition": "true"},
    {"source": "cond", "target": "out", "condition": "false"}
  ]
}
```

Keep checkpoints in LangGraph's own checkpointer tables (it manages its schema), keyed by `runs.thread_id`. `run_events` is *yours* and is the human-readable audit log.

---

## 4. API surface (FastAPI)

```
# Auth
POST   /auth/register
POST   /auth/login                       → JWT

# Agents & versions
POST   /agents
GET    /agents                           ?owner=me
GET    /agents/{id}
PATCH  /agents/{id}
POST   /agents/{id}/versions             body: graph_json  → new immutable version
POST   /agents/{id}/publish              flips visibility, pins current_version
POST   /agents/from-template/{template_id}

# Tools
POST   /tools
GET    /tools
POST   /tools/{id}/test                  dry-run a tool with sample args

# Templates
GET    /templates

# Runs (execution)
POST   /agents/{id}/run                  async → 202 {run_id}
GET    /runs/{id}                        status + output
GET    /runs/{id}/events                 SSE live log stream
POST   /runs/{id}/resume                 error recovery: continue from last checkpoint
POST   /runs/{id}/replay                 body: {from_step}  → fork a new run from a checkpoint

# Marketplace
GET    /marketplace                      ?q=&category=&sort=installs
POST   /marketplace/{agent_id}/install
POST   /marketplace/{agent_id}/rate      body: {score, comment}
```

Layer it: `routers/` (thin, validation only) → `services/` (business logic) → `repositories/` (DB access). This separation is itself an interview talking point.

---

## 5. Runtime / harness design (the centerpiece)

This is the part hiring managers will actually probe. Build it in two passes.

**Pass A — compile + execute (Phase 2).**
A `GraphCompiler` turns `graph_json` into a LangGraph `StateGraph`. Each node `type` maps to a handler:

- `input` → seeds run state from the request payload.
- `llm` → calls Gemma via your `LLMProvider`; if the node has tools, runs the tool-calling loop.
- `tool` → looks up the tool in the registry, validates args against its JSON schema, invokes it.
- `condition` → safe-evaluates a boolean expression over run state to pick an edge.
- `loop` → bounded iteration (with a hard max-iterations guard against runaway loops). Flat
  only — a loop nested inside another loop's body is rejected at compile time, not a
  supported pattern in this version.
- `output` → finalizes run output.

The shared **run state** is a typed dict (messages, scratchpad vars, last tool result, step counter).

**Pass B — make it durable (Phase 4).** Attach a checkpointer (`PostgresSaver` or `RedisSaver`) keyed by `thread_id`. This single move gives you:

- **State management** — every node transition (LLM response, tool result, control-flow decision) is checkpointed to durable storage.
- **Error recovery** — on crash or failure, `POST /runs/{id}/resume` re-invokes the graph with the same `thread_id` and `None` input; LangGraph **replays** completed steps from the checkpoint (no re-calling the LLM, no re-paying tokens) and resumes at the failed node.
- **Replay / time-travel** — read checkpoint history, let the user pick a prior step, and **fork** a new run from that checkpoint (`POST /runs/{id}/replay`).
- **Human-in-the-loop** — use LangGraph `interrupt()` so a graph can pause for approval and resume on a signal.

**The replay-safety contract** (state this explicitly in your README — it's a senior-level detail):
1. No nondeterminism in graph code — no `datetime.now()`, no `random` inside node control flow; if you need them, capture them as recorded step results.
2. Wrap every side-effecting tool call with an **idempotency key** derived from `(run_id, node_id, step_index)`, persisted in `tool_calls`. On resume, a completed key returns its stored result instead of re-executing — so resuming never double-sends an email or double-charges an API.
3. Version the graph (`agent_versions`) so a run always replays against the exact graph it started on.

**Per-node retry policy.** Each node carries `{max_retries, backoff}`. Transient failures (LLM timeout, tool HTTP 5xx/429) retry with exponential backoff and emit `retry` events; permanent failures mark the run `interrupted` and persist the checkpoint for later resume.

**Async + logging plumbing.** The `POST /run` endpoint enqueues to an **arq** worker (Redis-backed) and returns `202` immediately. The worker executes the graph, writes each `run_events` row, and `PUBLISH`es each event to Redis channel `run:{id}`. The `GET /runs/{id}/events` SSE endpoint `SUBSCRIBE`s to that channel and streams events to the canvas in real time. (Bonus: make SSE resumable with `Last-Event-ID` mapped to `step_index` so a dropped browser tab can catch up.)

---

## 6. Build plan — week by week

Each phase ends with something demoable. If you run short on time, **Phases 0–4 plus a thin builder and a thin marketplace already hit every requirement** — treat 5–7 as depth, not blockers.

### Phase 0 — Spikes & scaffolding (Week 1)
1. Resolve the **Gemma tool-calling spike** (Section 2). Commit the working invocation path as `llm_provider.py`.
2. `docker-compose.yml` with services: `postgres`, `redis`, `ollama`, `api`, `worker`, `web`. Healthchecks on each.
3. FastAPI skeleton with `/health`; Vite + React + React Flow renders an empty canvas with one draggable node.
4. Wire CI (GitHub Actions): lint (ruff), type-check (mypy), run pytest on push.
**Demo:** `docker compose up` brings up everything; a script calls Gemma and gets a tool call back.

### Phase 1 — Data models & CRUD (Week 2)
1. SQLAlchemy models + Alembic migrations for all Section-3 tables.
2. JWT auth (register/login, password hashing with `passlib`).
3. CRUD for `agents`, `agent_versions`, `tools`; ownership checks.
4. pytest: repository unit tests + API integration tests against a throwaway Postgres (testcontainers or a CI service container).
**Demo:** create an agent, save a `graph_json` version, fetch it back — all authenticated.

### Phase 2 — Runtime v1, synchronous (Week 3)
1. `GraphCompiler` + handlers for `input`, `llm`, `output`.
2. Tool registry + one builtin tool (`http_get` or `calculator`); `tool` node handler with schema validation.
3. Tool-calling loop inside the `llm` node using your spiked provider path.
4. `POST /agents/{id}/run` runs **synchronously** for now and returns the output.
**Demo:** POST a question → Gemma decides to call the tool → you get a grounded answer.

### Phase 3 — Async, logging, live streaming (Week 4)
1. Introduce the **arq** worker; `/run` enqueues and returns `202 {run_id}`.
2. `run_events` writes on every node transition.
3. Redis pub/sub + `GET /runs/{id}/events` **SSE**; render a live step-by-step log panel in the UI.
4. `GET /runs/{id}` returns status/output; basic run history view.
**Demo:** click Run in the UI, watch nodes light up and logs stream live.

### Phase 4 — Durable execution: state, replay, recovery (Week 5) ★
1. Attach LangGraph checkpointer (Postgres) keyed by `thread_id`.
2. Per-node retry with backoff; failures → `interrupted` + persisted checkpoint.
3. `POST /runs/{id}/resume` (replay completed steps, continue from failure).
4. `POST /runs/{id}/replay?from_step=N` (fork a new run from a checkpoint).
5. Idempotency keys for tool calls (`tool_calls` table); prove a resumed run doesn't re-fire a side effect.
6. One human-in-the-loop node using `interrupt()`.
**Demo:** kill the worker mid-run, restart, hit resume — the agent finishes from where it stopped without re-calling the LLM. *This is your headline demo.*

### Phase 5 — No-code builder UX (Week 6)
1. Node palette (input/llm/tool/condition/loop/output), drag-drop, edge wiring.
2. Per-node config panels (system prompt, model, tool selection, condition expr).
3. Graph validation (no orphan nodes, exactly one input/output, no invalid edges) before save.
4. In-canvas **Test** panel that triggers a run and shows the live log inline.
5. Tool-builder UI: define an HTTP tool (URL, method, param schema) with no code.
**Demo:** a non-technical user builds a 4-node agent from scratch and tests it without touching JSON.

### Phase 6 — Marketplace & templates (Week 7)
1. Publish flow (private → published, pins a version).
2. Marketplace list/search/sort by installs & rating; agent detail page.
3. Install (clones the published version into the user's workspace) + ratings.
4. Seed 3–4 templates (e.g. "Research assistant", "Web Q&A", "Data extractor").
**Demo:** User A publishes an agent; User B finds it in the marketplace, installs, runs, and rates it.

### Phase 7 — Observability, polish, ship (Week 8)
1. OpenTelemetry traces across API → worker → LLM; a simple runs dashboard (success rate, p95 latency, token/step counts).
2. Rate limiting (Redis) and structured JSON logging.
3. README with architecture diagram, the replay-safety contract, and a GIF of the resume demo.
4. Record a 3–4 minute walkthrough video; deploy (a small VPS or Fly.io) or provide one-command `docker compose up`.

---

## 7. Testing strategy (don't skip — your ZhongAn QA background is a selling point)

- **Unit:** graph compiler (graph_json → StateGraph), tool schema validation, condition evaluator, idempotency-key derivation.
- **Integration:** full run lifecycle against real Postgres/Redis via testcontainers; assert `run_events` ordering.
- **Recovery tests:** inject a failure at node N, assert resume re-enters at N and that completed LLM/tool steps are *not* re-executed (assert on the idempotency table + call counts).
- **Contract tests:** OpenAPI schema snapshot so the React client and API can't silently drift.
- **A Playwright e2e** (you already know this): build → test → publish → install flow in the browser. Mirrors your ZhongAn automation work and demos beautifully.

---

## 8. Interview talking points (rehearse these)

- *"I built a durable agent runtime: every node transition is checkpointed, so a crashed run resumes from its last checkpoint without re-calling the LLM — and tool side effects are guarded by idempotency keys derived from (run_id, node_id, step)."*
- *"Graphs are versioned and immutable once published, so a run always replays against the exact definition it started on — that's the replay-safety contract."*
- *"Live logs are a Redis pub/sub fan-out to an SSE stream, resumable via Last-Event-ID mapped to the step index."*
- *"Runs are async via an arq worker, so the API stays responsive and long agent runs don't block request threads."*
- *"I ran everything on a local Gemma 4 model — zero API cost, full data privacy — and had to design around its real tool-calling and context-window quirks."*

---

## 9. Scope guardrails (so this stays a portfolio project, not a startup)

- **Don't** build multi-tenant org/RBAC, billing, or a plugin marketplace with payments.
- **Don't** support every node type — 6 well-built node types beat 20 flaky ones.
- **Do** make the **resume-from-crash** demo flawless; it's the one thing toy clones never have.
- **Do** keep a clean `docker compose up` so a reviewer can run it in 2 minutes.

---

## 10. Reference projects to study (read their code, don't copy)

- **Dify** (`langgenius/dify`) — full LLM-app platform; study its workflow engine and node model.
- **Langflow** (`langflow-ai/langflow`) — Python + React Flow canvas; closest to your stack; study how it exports flows to runnable code.
- **Flowise** (`FlowiseAI/Flowise`) — TS/Node take on the same idea; good for the marketplace/templates UX.
- **LangGraph docs → "Durable execution"** — the checkpointer, resume, and time-travel patterns you're implementing.
- **`mmmayo13/gemma_4_tool_calling`** — minimal local Gemma 4 + Ollama tool-calling reference for your Phase 0 spike.

---

*Build order is the point: each phase leaves you with a working, demoable system, and even the first five phases already satisfy every line of the job description.*
