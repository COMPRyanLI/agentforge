"""Tool registry: maps tool names to implementations + JSON schemas."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import jsonschema

from app.llm.provider import ToolSchema
from app.runtime.errors import ToolArgValidationError, ToolExecutionError, ToolNotFoundError

ImplFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(slots=True)
class RegisteredTool:
    name: str
    description: str
    json_schema: dict[str, Any]  # justified: JSON Schema is open-ended
    impl_fn: ImplFn


class ToolRegistry:
    """Name-keyed registry of tool definitions and implementations."""

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, tool: RegisteredTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> RegisteredTool | None:
        return self._tools.get(name)

    def get_or_raise(self, name: str) -> RegisteredTool:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolNotFoundError(f"Tool {name!r} is not registered")
        return tool

    def to_llm_schemas(self, names: list[str]) -> list[ToolSchema]:
        """Convert registered tools to the Ollama function-calling schema format."""
        schemas: list[ToolSchema] = []
        for name in names:
            tool = self.get_or_raise(name)
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.json_schema,
                    },
                }
            )
        return schemas

    def validate_args(self, name: str, args: dict[str, Any]) -> None:
        """Validate args against the tool's JSON Schema.

        Raises ToolArgValidationError if validation fails.
        """
        tool = self.get_or_raise(name)
        try:
            jsonschema.validate(instance=args, schema=tool.json_schema)
        except jsonschema.ValidationError as exc:
            raise ToolArgValidationError(
                f"Invalid arguments for tool {name!r}: {exc.message}"
            ) from exc


async def invoke_tool(
    registry: ToolRegistry,
    name: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Validate args and call the tool implementation.

    Raises:
        ToolNotFoundError: if name is not registered.
        ToolArgValidationError: if args fail schema validation.
        ToolExecutionError: if the implementation raises.
    """
    registry.validate_args(name, args)
    tool = registry.get_or_raise(name)
    try:
        return await tool.impl_fn(args)
    except (ToolArgValidationError, ToolNotFoundError):
        raise
    except Exception as exc:
        raise ToolExecutionError(f"Tool {name!r} raised: {exc}") from exc
