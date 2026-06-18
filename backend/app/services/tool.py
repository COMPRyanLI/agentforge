"""Tool service — CRUD logic."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tool import Tool
from app.repositories.tool import ToolRepo
from app.runtime.builtins import register_builtins
from app.runtime.errors import AgentRuntimeError, ToolArgValidationError, ToolNotFoundError
from app.runtime.http_tool import make_http_tool
from app.runtime.registry import RegisteredTool, ToolRegistry, invoke_tool
from app.schemas.tool import ToolCreate, ToolTestRequest, ToolTestResponse, ToolUpdate

_repo = ToolRepo()


async def create(session: AsyncSession, owner_id: uuid.UUID, data: ToolCreate) -> Tool:
    return await _repo.create(session, owner_id=owner_id, data=data)


async def get_or_404(
    session: AsyncSession,
    tool_id: uuid.UUID,
    owner_id: uuid.UUID | None = None,
) -> Tool:
    tool = await _repo.get(session, tool_id)
    if tool is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
    if owner_id is not None and tool.owner_id != owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your tool")
    return tool


async def list_mine(session: AsyncSession, owner_id: uuid.UUID) -> list[Tool]:
    return await _repo.list_by_owner(session, owner_id)


async def update(
    session: AsyncSession,
    tool_id: uuid.UUID,
    owner_id: uuid.UUID,
    data: ToolUpdate,
) -> Tool:
    tool = await get_or_404(session, tool_id, owner_id)
    kwargs = data.model_dump(exclude_unset=True)
    if not kwargs:
        return tool
    return await _repo.update(session, tool, **kwargs)


def _build_registered_tool(tool: Tool) -> RegisteredTool:
    """Resolve a DB Tool row to a real executor for a one-off dry run.

    "python" tools have no sandboxed executor (CLAUDE.md scope guardrails),
    so they raise the same ToolNotFoundError a graph run would hit.
    """
    if tool.impl_type == "http":
        return make_http_tool(tool)
    if tool.impl_type == "builtin":
        registry = ToolRegistry()
        register_builtins(registry)
        return registry.get_or_raise(tool.name)
    raise ToolNotFoundError(f"No executor available for impl_type {tool.impl_type!r}")


async def test_tool(
    session: AsyncSession,
    tool_id: uuid.UUID,
    owner_id: uuid.UUID,
    data: ToolTestRequest,
) -> ToolTestResponse:
    """Dry-run a tool with sample args — no idempotency key, no tool_calls row.

    This is a standalone invocation for the tool-builder UI's "test it"
    button, not part of any run, so it intentionally bypasses
    invoke_tool_idempotent (which requires a run_id/node_id/step_index to
    derive a key against).
    """
    tool = await get_or_404(session, tool_id, owner_id)
    try:
        registered = _build_registered_tool(tool)
        registry = ToolRegistry()
        registry.register(registered)
        result = await invoke_tool(registry, tool.name, data.args)
    except ToolArgValidationError as exc:
        # The submitted args don't match the tool's own json_schema — a bad
        # request, not a tool-execution failure the UI should show inline.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except AgentRuntimeError as exc:
        return ToolTestResponse(result=None, error=str(exc))
    return ToolTestResponse(result=result, error=None)
