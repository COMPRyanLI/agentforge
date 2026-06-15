---
name: checks
description: Run the full quality gate (lint, format check, strict type check, tests) and fix failures. Use before declaring any task done, before proposing a commit, or whenever the user says "run checks".
---

# Checks

Run the project's Definition-of-Done gate from `backend/`:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy --strict app
uv run pytest -q
```

Behavior:
- Run all four. Collect every failure before acting (don't stop at the first).
- **Fix** what you can: lint/format issues, type errors, and genuinely broken tests.
- If a test failure reveals a real behavior bug, fix the code — do not weaken or delete the
  test to make it pass, and do not add blanket `# type: ignore` to silence mypy. If a type
  ignore is truly warranted, scope it narrowly and add a `# justified:` note.
- Re-run until all four are green, then report a one-line summary of what was fixed.

If the frontend changed, also run `npm run build` (or `tsc --noEmit`) in `web/` and fix
type errors there.
