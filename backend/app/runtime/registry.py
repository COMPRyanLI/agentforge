"""Tool registry: maps tool names to implementations + JSON schemas."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import jsonschema
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.llm.provider import ToolSchema
from app.repositories.tool_call import ToolCallRepo
from app.runtime.errors import (
    ToolArgValidationError,
    ToolCallAmbiguousError,
    ToolExecutionError,
    ToolNotFoundError,
)

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


def make_idempotency_key(run_id: str, node_id: str, step_index: int, call_index: int) -> str:
    """Derive a tool_calls idempotency key.

    call_index disambiguates multiple tool invocations made within the same
    step_index — the llm node's tool-calling loop can call several tools in
    one node iteration without incrementing step_index, so (run_id, node_id,
    step_index) alone is not unique. The standalone tool node always uses
    call_index=0 (it invokes exactly one tool per node).
    """
    return f"{run_id}:{node_id}:{step_index}:{call_index}"


_tool_call_repo = ToolCallRepo()


async def invoke_tool_idempotent(
    session_factory: async_sessionmaker[AsyncSession],
    registry: ToolRegistry,
    name: str,
    args: dict[str, Any],
    *,
    run_id: str,
    node_id: str,
    step_index: int,
    call_index: int,
) -> dict[str, Any]:
    """Invoke a tool at most once per idempotency key.

    On resume, a key already marked "completed" returns its stored result
    without re-invoking the tool, guarding against double-firing side effects.
    A key stuck "pending" means a prior attempt's outcome is unknown (the
    process likely crashed mid-call) — re-invoking would risk a double side
    effect, so this raises ToolCallAmbiguousError instead of guessing.

    A unique constraint backs idempotency_key as a defense against the same
    key being inserted twice by two concurrent processes (e.g. a run double-
    enqueued — see services/run.py::resume's docstring on the single-worker
    assumption). If that race is lost, the INSERT fails with IntegrityError
    before invoke_tool() is ever called, so the side effect still can't fire
    twice; this is surfaced as the same ToolCallAmbiguousError rather than an
    opaque DB error, since the practical recovery (verify externally, resolve
    manually) is identical either way.
    """
    key = make_idempotency_key(run_id, node_id, step_index, call_index)
    run_uuid = uuid.UUID(run_id)

    async with session_factory() as session:
        existing = await _tool_call_repo.get_by_key(session, key)
        if existing is not None and existing.status == "completed":
            assert existing.result_json is not None
            return existing.result_json
        if existing is not None and existing.status == "pending":
            raise ToolCallAmbiguousError(
                f"tool_calls row for key {key!r} is stuck 'pending' — a prior attempt's "
                "outcome is unknown; verify the external system before clearing it manually"
            )
        if existing is None:
            try:
                await _tool_call_repo.create_pending(
                    session, run_id=run_uuid, node_id=node_id, idempotency_key=key, args_json=args
                )
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ToolCallAmbiguousError(
                    f"tool_calls row for key {key!r} was created concurrently by another "
                    "process — likely the same run double-enqueued; verify the external "
                    "system before retrying"
                ) from exc
        else:
            # existing.status == "failed": safe to retry — reset to "pending" so a
            # crash during this retry is still detected as ambiguous, not silently
            # treated as another clean failure.
            await _tool_call_repo.mark_pending(session, existing)
            await session.commit()

    try:
        result = await invoke_tool(registry, name, args)
    except Exception:
        async with session_factory() as session:
            tool_call = await _tool_call_repo.get_by_key(session, key)
            if tool_call is not None:
                error_json = {"error": "invocation raised"}
                await _tool_call_repo.mark_failed(session, tool_call, error_json)
                await session.commit()
        raise

    async with session_factory() as session:
        tool_call = await _tool_call_repo.get_by_key(session, key)
        assert tool_call is not None
        await _tool_call_repo.mark_completed(session, tool_call, result)
        await session.commit()
    return result
