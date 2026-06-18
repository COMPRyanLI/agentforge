"""Builds the per-run ToolRegistry: builtins plus any DB-backed tool a
graph actually references, replacing the `ToolRegistry() + register_builtins()`
boilerplate previously duplicated in app.services.run and app.workers.worker.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.tool import ToolRepo
from app.runtime.builtins import register_builtins
from app.runtime.http_tool import make_http_tool
from app.runtime.registry import ToolRegistry

_tool_repo = ToolRepo()


def extract_tool_ids(graph_json: dict[str, Any]) -> list[uuid.UUID]:
    """UUID-shaped tool references from standalone `tool` nodes' data.tool_id."""
    ids: list[uuid.UUID] = []
    for node in graph_json.get("nodes", []):
        if node.get("type") == "tool":
            raw_id = (node.get("data") or {}).get("tool_id")
            if raw_id:
                try:
                    ids.append(uuid.UUID(str(raw_id)))
                except ValueError:
                    pass  # non-UUID tool_id — treat as a builtin name, no DB lookup
    return ids


def _extract_llm_tool_names(graph_json: dict[str, Any]) -> list[str]:
    """Tool NAME references from `llm` nodes' data.tools."""
    names: list[str] = []
    for node in graph_json.get("nodes", []):
        if node.get("type") == "llm":
            names.extend(str(n) for n in (node.get("data") or {}).get("tools") or [])
    return names


async def build_registry(
    session: AsyncSession, graph_json: dict[str, Any], owner_id: uuid.UUID
) -> ToolRegistry:
    """Builtins, plus an executor for every `http`-impl_type DB Tool the
    graph references by id (tool node) or by name (llm node's data.tools).

    `impl_type == "python"` tools are intentionally left unregistered — no
    sandboxed code-execution executor exists (CLAUDE.md scope guardrails) —
    so a graph referencing one fails at run time with ToolNotFoundError
    rather than silently doing nothing.
    """
    registry = ToolRegistry()
    register_builtins(registry)

    for tool_id in extract_tool_ids(graph_json):
        tool = await _tool_repo.get(session, tool_id)
        if tool is not None and tool.impl_type == "http" and registry.get(tool.name) is None:
            registry.register(make_http_tool(tool))

    for name in _extract_llm_tool_names(graph_json):
        if registry.get(name) is not None:
            continue
        tool = await _tool_repo.get_by_name(session, owner_id, name)
        if tool is not None and tool.impl_type == "http":
            registry.register(make_http_tool(tool))

    return registry
