"""Unit tests for ToolRegistry."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.runtime.errors import (
    ToolArgValidationError,
    ToolCallAmbiguousError,
    ToolExecutionError,
    ToolNotFoundError,
)
from app.runtime.registry import (
    RegisteredTool,
    ToolRegistry,
    invoke_tool,
    invoke_tool_idempotent,
    make_idempotency_key,
)
from tests.unit.runtime.conftest import FakeToolCall, FakeToolCallRepo, dummy_session_factory


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


# ---------------------------------------------------------------------------
# Idempotency key derivation + invoke_tool_idempotent
# ---------------------------------------------------------------------------


def test_make_idempotency_key_format() -> None:
    key = make_idempotency_key("run-1", "node-a", 3, 0)
    assert key == "run-1:node-a:3:0"


def test_make_idempotency_key_call_index_disambiguates() -> None:
    key0 = make_idempotency_key("run-1", "node-a", 3, 0)
    key1 = make_idempotency_key("run-1", "node-a", 3, 1)
    assert key0 != key1


async def test_invoke_tool_idempotent_invokes_once_on_first_call(
    registry: ToolRegistry, fake_tool_call_repo: FakeToolCallRepo
) -> None:
    result = await invoke_tool_idempotent(
        dummy_session_factory,
        registry,
        "echo",
        {"msg": "hi"},
        run_id=str(uuid.uuid4()),
        node_id="n1",
        step_index=0,
        call_index=0,
    )
    assert result == {"echo": "hi"}
    (row,) = fake_tool_call_repo.rows.values()
    assert row.status == "completed"


async def test_invoke_tool_idempotent_returns_cached_result_without_reinvoking(
    fake_tool_call_repo: FakeToolCallRepo,
) -> None:
    call_count = 0

    async def _impl(args: dict[str, Any]) -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        return {"echo": args.get("msg")}

    registry = ToolRegistry()
    registry.register(
        RegisteredTool(name="echo", description="", json_schema=ECHO_SCHEMA, impl_fn=_impl)
    )

    run_id = str(uuid.uuid4())
    kwargs: dict[str, Any] = dict(run_id=run_id, node_id="n1", step_index=0, call_index=0)

    first = await invoke_tool_idempotent(
        dummy_session_factory, registry, "echo", {"msg": "hi"}, **kwargs
    )
    second = await invoke_tool_idempotent(
        dummy_session_factory, registry, "echo", {"msg": "hi"}, **kwargs
    )

    assert first == second == {"echo": "hi"}
    assert call_count == 1


async def test_invoke_tool_idempotent_pending_row_raises_ambiguous(
    fake_tool_call_repo: FakeToolCallRepo,
) -> None:
    run_id = str(uuid.uuid4())
    key = make_idempotency_key(run_id, "n1", 0, 0)
    fake_tool_call_repo.rows[key] = FakeToolCall(uuid.uuid4(), "n1", key, {"msg": "hi"})
    # left at default status "pending" — simulates a crash mid-call

    registry = ToolRegistry()
    registry.register(ECHO_TOOL)

    with pytest.raises(ToolCallAmbiguousError):
        await invoke_tool_idempotent(
            dummy_session_factory,
            registry,
            "echo",
            {"msg": "hi"},
            run_id=run_id,
            node_id="n1",
            step_index=0,
            call_index=0,
        )


async def test_invoke_tool_idempotent_failed_row_is_retried(
    fake_tool_call_repo: FakeToolCallRepo,
) -> None:
    run_id = str(uuid.uuid4())
    key = make_idempotency_key(run_id, "n1", 0, 0)
    failed_row = FakeToolCall(uuid.uuid4(), "n1", key, {"msg": "hi"})
    failed_row.status = "failed"
    fake_tool_call_repo.rows[key] = failed_row

    registry = ToolRegistry()
    registry.register(ECHO_TOOL)

    result = await invoke_tool_idempotent(
        dummy_session_factory,
        registry,
        "echo",
        {"msg": "hi"},
        run_id=run_id,
        node_id="n1",
        step_index=0,
        call_index=0,
    )
    assert result == {"echo": "hi"}
    assert fake_tool_call_repo.rows[key].status == "completed"


async def test_invoke_tool_idempotent_marks_failed_on_exception(
    fake_tool_call_repo: FakeToolCallRepo,
) -> None:
    async def _boom(args: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("kaboom")

    registry = ToolRegistry()
    registry.register(
        RegisteredTool(name="echo", description="", json_schema=ECHO_SCHEMA, impl_fn=_boom)
    )

    run_id = str(uuid.uuid4())
    with pytest.raises(ToolExecutionError):
        await invoke_tool_idempotent(
            dummy_session_factory,
            registry,
            "echo",
            {"msg": "hi"},
            run_id=run_id,
            node_id="n1",
            step_index=0,
            call_index=0,
        )

    key = make_idempotency_key(run_id, "n1", 0, 0)
    assert fake_tool_call_repo.rows[key].status == "failed"
