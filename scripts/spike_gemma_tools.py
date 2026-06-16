#!/usr/bin/env python3
"""Phase 0 spike: verify which Ollama serving path reliably returns tool calls
from your local Gemma 4 model. Run this BEFORE writing any runtime code.

    python scripts/spike_gemma_tools.py

Tests three paths against the same prompt + tool schema and reports which ones
surface a parseable tool call:
  1. native      POST /api/chat                (most reliable for Gemma 4)
  2. v1-nostream POST /v1/chat/completions      (OpenAI-compatible, no stream)
  3. v1-stream   POST /v1/chat/completions      (OpenAI-compatible, streaming — known flaky)

Whichever path wins becomes the contract baked into app/llm/provider.py.
"""

from __future__ import annotations

import json
import os

import httpx

BASE = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:e4b")
PROMPT = "What's the weather in Tokyo right now? Use the tool."

TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the current weather for a city.",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "City name"}},
            "required": ["city"],
        },
    },
}


def _ok(label: str, found: bool, detail: str) -> None:
    mark = "PASS" if found else "FAIL"
    print(f"[{mark}] {label:<12} {detail}")


def try_native() -> None:
    try:
        r = httpx.post(
            f"{BASE}/api/chat",
            json={"model": MODEL, "messages": [{"role": "user", "content": PROMPT}],
                  "tools": [TOOL], "stream": False},
            timeout=120,
        )
        r.raise_for_status()
        calls = r.json().get("message", {}).get("tool_calls") or []
        _ok("native", bool(calls), json.dumps(calls)[:200] if calls else "no tool_calls in message")
    except Exception as e:  # noqa: BLE001
        _ok("native", False, f"error: {e}")


def try_v1_nostream() -> None:
    try:
        r = httpx.post(
            f"{BASE}/v1/chat/completions",
            json={"model": MODEL, "messages": [{"role": "user", "content": PROMPT}],
                  "tools": [TOOL], "stream": False},
            timeout=120,
        )
        r.raise_for_status()
        calls = r.json()["choices"][0]["message"].get("tool_calls") or []
        _ok("v1-nostream", bool(calls), json.dumps(calls)[:200] if calls else "no tool_calls")
    except Exception as e:  # noqa: BLE001
        _ok("v1-nostream", False, f"error: {e}")


def try_v1_stream() -> None:
    try:
        found = False
        names: list[str] = []
        with httpx.stream(
            "POST", f"{BASE}/v1/chat/completions",
            json={"model": MODEL, "messages": [{"role": "user", "content": PROMPT}],
                  "tools": [TOOL], "stream": True},
            timeout=120,
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                payload = line[len("data: "):]
                if payload.strip() == "[DONE]":
                    break
                delta = json.loads(payload)["choices"][0].get("delta", {})
                for tc in delta.get("tool_calls") or []:
                    found = True
                    fn = (tc.get("function") or {}).get("name")
                    if fn:
                        names.append(fn)
        _ok("v1-stream", found, f"names={names}" if found else "no tool_calls in stream")
    except Exception as e:  # noqa: BLE001
        _ok("v1-stream", False, f"error: {e}")


if __name__ == "__main__":
    print(f"Spiking model={MODEL} at {BASE}\n")
    try_native()
    try_v1_nostream()
    try_v1_stream()
    print("\nBake the first PASS path into app/llm/provider.py and tell Claude Code the result.")
