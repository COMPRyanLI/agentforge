# Building AgentForge with Claude Code — Workflow Guide

This guide explains how to drive the whole project with Claude Code using the `.claude/`
scaffold in this package. Read `CLAUDE.md` and `docs/PLAN.md` first — they're the spec.

---

## 0. One-time setup

1. **Install Claude Code** (Node 18+):
   ```bash
   npm install -g @anthropic-ai/claude-code
   ```
2. **Create the repo and drop in the scaffold.** Put `CLAUDE.md`, the `.claude/` folder, and
   `docs/PLAN.md` at the repo root (this package mirrors that layout — just copy it in):
   ```bash
   git init agentforge && cd agentforge
   cp -r /path/to/this/package/. .
   chmod +x .claude/hooks/format.sh
   git add . && git commit -m "chore: bootstrap Claude Code scaffold + plan"
   ```
3. **Start Claude Code** in the repo root:
   ```bash
   claude
   ```
   It auto-loads `CLAUDE.md`. Type `/` to see your skills (`/start-phase`, `/add-endpoint`,
   `/add-node-type`, `/checks`) and `/agents` to see the subagents.

> Tip: run `/reload-skills` after editing any SKILL.md without restarting the session.

---

## 1. The golden loop (per phase)

The project is built phase by phase (see `docs/PLAN.md`). For each phase:

1. **`/clear`** to start with a clean context (do this between phases — stale context makes
   Claude slower and more likely to drift).
2. **`/start-phase N`** — it reads the phase from the plan, proposes a task list, and asks
   before coding.
3. **Use plan mode for anything non-trivial.** Press **Shift+Tab** to enter plan mode so
   Claude proposes an approach *before* touching files. Approve, then let it implement.
4. Let it work **test-first**. For new routes it'll reach for `/add-endpoint`; for runtime
   nodes, `/add-node-type`. You can also invoke those yourself.
5. **`/checks`** runs the quality gate (ruff + mypy + pytest). Don't accept "done" until green.
6. **Review before committing:** ask Claude to *"use the code-reviewer subagent on the diff."*
   It reviews in isolated context against the replay-safety contract and layering rules.
7. **Commit** (Claude will propose a message; committing prompts for your approval, pushing is
   blocked by design). Then `/clear` and move to the next phase.

---

## 2. Do the Gemma spike manually, first (before Phase 0 coding)

Don't let Claude build on an unverified model path. Resolve Section 2 of `docs/PLAN.md`
yourself in ~30 minutes:

```bash
ollama pull gemma4:e4b && ollama serve
```
Then have Claude write a tiny script that defines one tool and tests three invocation paths
(native `/api/chat`, OpenAI `/v1` non-streaming, `/v1` streaming) and **report which reliably
returns a parseable tool call**. Whichever wins becomes the contract baked into
`app/llm/provider.py`. Tell Claude the result so CLAUDE.md's assumption is confirmed, not guessed.

---

## 3. When to use which tool

| Situation | Reach for |
|---|---|
| Starting a milestone | `/start-phase N` |
| New HTTP route | `/add-endpoint` |
| New runtime/canvas node | `/add-node-type` |
| Verifying done-ness | `/checks` |
| "Is this diff safe to commit?" | **code-reviewer** subagent |
| "Add coverage / write the recovery test" | **test-engineer** subagent |
| Big multi-file search or independent investigation | a subagent (keeps main context clean) |
| Anything non-trivial | **plan mode** (Shift+Tab) before editing |

Rule of thumb: **subagents for context isolation** (review, deep search, test authoring),
**skills for repeatable procedures**, **plan mode for design**, **hooks for hard guarantees**
(the format hook runs automatically after every edit).

---

## 4. Habits that keep Claude Code effective

- **One concern per session.** `/clear` between unrelated tasks; long sessions drift.
- **Small, reviewable diffs.** Commit per task, not per phase, where it makes sense.
- **Make it prove durability.** For Phase 4, explicitly ask: *"kill the worker mid-run, then
  resume, and show me the test proving the LLM step wasn't re-called."* That demo is the
  centerpiece — don't let it be hand-waved.
- **Keep the runtime honest.** If Claude ever adds `datetime.now()`/`random`/`uuid4()` inside
  `app/runtime/`, the code-reviewer subagent should flag it; if it slips through, call it out.
- **Tune permissions to taste.** `.claude/settings.json` pre-approves safe commands so you're
  not clicking "allow" constantly. `git push` and `rm -rf` are denied on purpose; widen the
  allowlist only for commands you're comfortable running unattended.
- **Add directory memory if needed.** If the frontend develops its own conventions, drop a
  `web/CLAUDE.md`; Claude merges directory-scoped memory with the root file.

---

## 5. What this scaffold gives you (recap)

```
CLAUDE.md                          # project constitution (auto-loaded)
docs/PLAN.md                       # the full phased spec
.claude/
  settings.json                    # permission allowlist + format hook
  hooks/format.sh                  # auto-ruff after every edit
  skills/
    start-phase/SKILL.md           # /start-phase N
    add-endpoint/SKILL.md          # /add-endpoint
    add-node-type/SKILL.md         # /add-node-type
    checks/SKILL.md                # /checks (quality gate)
  agents/
    code-reviewer.md               # isolated pre-commit review
    test-engineer.md               # isolated test authoring + recovery tests
```

Everything here encodes the *conventions* and the *replay-safety contract* so that across
dozens of Claude Code sessions the project stays coherent instead of drifting. Start with the
Gemma spike, then `/start-phase 0`, and work the golden loop.
