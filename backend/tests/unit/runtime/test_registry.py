"""Unit tests for ToolRegistry."""

from __future__ import annotations

from typing import Any

import pytest

from app.runtime.errors import ToolArgValidationError, ToolNotFoundError
from app.runtime.registry import RegisteredTool, ToolRegistry, invoke_tool


async def _echo(args: dict[str, Any]) -> dict[str, Any]:
    return {"echo": args.get("msg")}


ECHO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"msg": {"type": "string"}},
    "required": ["msg"],
    "additionalProperties": False,
}

ECHO_TOOL = RegisteredTool(
    name="echo",
    description="Echoes the message.",
    json_schema=ECHO_SCHEMA,
    impl_fn=_echo,
)


@pytest.fixture
def registry() -> ToolRegistry:
    r = ToolRegistry()
    r.register(ECHO_TOOL)
    return r


def test_register_and_get(registry: ToolRegistry) -> None:
    tool = registry.get("echo")
    assert tool is not None
    assert tool.name == "echo"


def test_get_unknown_returns_none(registry: ToolRegistry) -> None:
    assert registry.get("nonexistent") is None


def test_get_or_raise_raises_for_unknown(registry: ToolRegistry) -> None:
    with pytest.raises(ToolNotFoundError, match="nonexistent"):
        registry.get_or_raise("nonexistent")


def test_to_llm_schemas(registry: ToolRegistry) -> None:
    schemas = registry.to_llm_schemas(["echo"])
    assert len(schemas) == 1
    schema = schemas[0]
    assert schema["type"] == "function"
    fn = schema["function"]
    assert fn["name"] == "echo"
    assert fn["description"] == "Echoes the message."
    assert fn["parameters"] == ECHO_SCHEMA


def test_to_llm_schemas_unknown_raises(registry: ToolRegistry) -> None:
    with pytest.raises(ToolNotFoundError):
        registry.to_llm_schemas(["ghost"])


def test_validate_args_passes(registry: ToolRegistry) -> None:
    registry.validate_args("echo", {"msg": "hello"})  # no exception


def test_validate_args_missing_required(registry: ToolRegistry) -> None:
    with pytest.raises(ToolArgValidationError, match="Invalid arguments"):
        registry.validate_args("echo", {})


def test_validate_args_wrong_type(registry: ToolRegistry) -> None:
    with pytest.raises(ToolArgValidationError):
        registry.validate_args("echo", {"msg": 123})


def test_validate_args_additional_property(registry: ToolRegistry) -> None:
    with pytest.raises(ToolArgValidationError):
        registry.validate_args("echo", {"msg": "hi", "extra": "not allowed"})


async def test_invoke_tool_success(registry: ToolRegistry) -> None:
    result = await invoke_tool(registry, "echo", {"msg": "hello"})
    assert result == {"echo": "hello"}


async def test_invoke_tool_unknown_raises(registry: ToolRegistry) -> None:
    with pytest.raises(ToolNotFoundError):
        await invoke_tool(registry, "ghost", {})


async def test_invoke_tool_validation_error(registry: ToolRegistry) -> None:
    with pytest.raises(ToolArgValidationError):
        await invoke_tool(registry, "echo", {"msg": 999})
