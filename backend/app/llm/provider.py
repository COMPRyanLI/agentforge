"""LLM provider seam.

ALL model access in the app goes through this interface — never call Ollama
directly from a node handler (see CLAUDE.md). Tool-calling turns use Ollama's
NATIVE /api/chat (the ollama client), which is the reliable path for Gemma 4;
the OpenAI-compatible /v1 streaming path can drop tool_calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ollama import AsyncClient

Message = dict[str, Any]  # justified: Ollama message format is open-ended (role/content/tool_calls)
ToolSchema = dict[str, Any]  # justified: JSON Schema tool definitions are open-ended


@dataclass(slots=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]  # justified: tool arguments are schema-defined at runtime


@dataclass(slots=True)
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMProvider(Protocol):
    async def chat(
        self, messages: list[Message], tools: list[ToolSchema] | None = None
    ) -> LLMResponse: ...


class OllamaProvider:
    """Gemma 4 served by a local Ollama instance via the native API."""

    def __init__(self, base_url: str, model: str) -> None:
        self._client = AsyncClient(host=base_url)
        self._model = model

    async def chat(
        self, messages: list[Message], tools: list[ToolSchema] | None = None
    ) -> LLMResponse:
        resp = await self._client.chat(model=self._model, messages=messages, tools=tools)
        msg = resp.message
        calls: list[ToolCall] = []
        for tc in msg.tool_calls or []:
            calls.append(ToolCall(name=tc.function.name, arguments=dict(tc.function.arguments)))
        return LLMResponse(content=msg.content, tool_calls=calls)
