---
name: add-node-type
description: Add a new node type to the agent runtime (the graph executor). Use when extending the canvas/runtime with a new node such as condition, loop, tool, or human-in-the-loop. Enforces the replay-safety contract and adds unit + recovery tests.
---

# Add Node Type

Given a node type name and its behavior, implement it in the runtime. Ask for the node's
config fields and expected state effect if unclear.

Steps:

1. **Config schema.** Define the node's configuration as a Pydantic model in
   `app/runtime/nodes/` (e.g. the system prompt + tool list for an `llm` node, or the
   boolean expression for a `condition` node). This is what the canvas serializes into
   `graph_json.nodes[].data`.

2. **Handler.** Implement an async handler `async def handle(state, config, ctx) -> state`.
   - Read inputs from the shared run state; return the updated state.
   - All LLM access goes through `ctx.llm` (the `LLMProvider`), never Ollama directly.
   - All tool invocation goes through the tool registry with an idempotency key derived from
     `(run_id, node_id, step_index)` — look up `tool_calls` first; only execute if absent.

3. **⚠️ Replay-safety check.** The handler MUST be deterministic on replay. No `datetime.now`,
   `random`, `uuid4`, or external mutable reads in control flow. If the node legitimately
   needs such a value, capture it once as a recorded step result. If you cannot make it
   deterministic, STOP and ask the user before proceeding.

4. **Register** the node type in the graph compiler (`app/runtime/compiler.py`) so
   `graph_json` of this `type` maps to the handler, and add any edge-routing logic
   (for branching nodes like `condition`).

5. **Emit events.** The handler/compiler must emit `node_start`, relevant
   `llm_call`/`tool_call`/`tool_result`, and `node_end` (or `error`/`retry`) events to
   `run_events` so the live log and replay work.

6. **Tests** in `backend/tests/runtime/`:
   - a unit test compiling a tiny `graph_json` that uses the node and asserting the state
     transition;
   - a **recovery test**: inject a failure mid-node, resume, and assert completed LLM/tool
     steps are NOT re-executed (assert on the `tool_calls` idempotency table / call counts).

Then run `/checks`.
