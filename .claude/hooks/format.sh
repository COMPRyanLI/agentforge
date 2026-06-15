#!/usr/bin/env bash
# Auto-format Python files after Claude Code writes/edits them.
# Runs from the project root. Fails silent so a missing tool never blocks edits.
set -uo pipefail

# Only act if ruff is available.
if ! command -v ruff >/dev/null 2>&1 && ! (command -v uv >/dev/null 2>&1); then
  exit 0
fi

# Format the backend package if it exists; harmless if there's nothing to do.
if [ -d backend ]; then
  if command -v uv >/dev/null 2>&1; then
    uv run --directory backend ruff format . >/dev/null 2>&1 || true
    uv run --directory backend ruff check --fix . >/dev/null 2>&1 || true
  else
    (cd backend && ruff format . >/dev/null 2>&1 || true)
    (cd backend && ruff check --fix . >/dev/null 2>&1 || true)
  fi
fi

exit 0
