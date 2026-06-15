---
name: start-phase
description: Begin work on a numbered phase of the AgentForge build plan. Use when the user says "start phase N", "let's do phase N", or begins a new milestone. Reads docs/PLAN.md, plans the phase, and drives test-first implementation to the Definition of Done.
---

# Start Phase

When invoked (optionally with a phase number, e.g. `/start-phase 4`):

1. **Load the spec.** Read `docs/PLAN.md` and locate the requested phase under
   "Build plan — week by week". If no number was given, infer the current phase from git
   history and the existing code, then state which phase you believe is next and confirm.

2. **Plan, don't code yet.** Produce a short, ordered task list for *this phase only* using
   the TodoWrite tool. Each task should be independently testable. Surface any decisions or
   ambiguities and ask before proceeding. Respect the scope guardrails in CLAUDE.md.

3. **Implement test-first.** For each task: write the failing test in `backend/tests/` first,
   then the minimal implementation, then make it pass. Follow the `routers → services →
   repositories` layering and the replay-safety contract for anything under `app/runtime/`.

4. **Gate each unit.** After each task, run the `/checks` skill. Do not move on until green.

5. **Wrap up.** When the phase's demo criterion (stated in PLAN.md) is achievable, summarize
   what was built, run the full check gate once more, and propose a single commit message.
   Do not push (push is denied) — leave the commit for the user to make or approve.

Keep the main session focused: if a large independent search or a thorough review is needed,
delegate to the `test-engineer` or `code-reviewer` subagent rather than doing it inline.
