"""Run service — orchestrates agent graph execution."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.provider import LLMProvider
from app.repositories.agent import AgentRepo
from app.repositories.run import RunRepo
from app.repositories.tool import ToolRepo
from app.runtime.builtins import register_builtins
from app.runtime.compiler import GraphCompiler
from app.runtime.errors import AgentRuntimeError
from app.runtime.executor import execute_graph
from app.runtime.registry import ToolRegistry
from app.schemas.run import RunCreate, RunRead

logger = logging.getLogger(__name__)

_run_repo = RunRepo()
_agent_repo = AgentRepo()
_tool_repo = ToolRepo()


def _extract_tool_ids(graph_json: dict[str, Any]) -> list[uuid.UUID]:
    """Return all UUID-shaped tool references from tool nodes in graph_json.

    The llm node's data.tools list contains tool NAMES (not UUIDs), so only
    standalone tool nodes (type=="tool") contribute UUIDs here.
    """
    ids: list[uuid.UUID] = []
    for node in graph_json.get("nodes", []):
        if node.get("type") == "tool":
            raw_id = (node.get("data") or {}).get("tool_id")
            if raw_id:
                try:
                    ids.append(uuid.UUID(str(raw_id)))
                except ValueError:
                    pass  # non-UUID tool_id — treat as builtin name, no DB lookup
    return ids


async def create_and_execute(
    session: AsyncSession,
    agent_id: uuid.UUID,
    owner_id: uuid.UUID,
    data: RunCreate,
    llm: LLMProvider,
) -> RunRead:
    """Create a Run record, execute the graph synchronously, persist result."""
    # 1. Load agent + ownership check
    agent = await _agent_repo.get(session, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    if agent.owner_id != owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your agent")
    if agent.current_version_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent has no published version",
        )

    # 2. Load agent version
    version = await _agent_repo.get_version(session, agent.current_version_id)
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Agent version not found",
        )

    graph_json: dict[str, Any] = version.graph_json

    # 3. Load DB tools referenced in graph_json (standalone tool nodes)
    tool_id_list = _extract_tool_ids(graph_json)
    db_tools = []
    tool_id_to_name: dict[str, str] = {}
    for tid in tool_id_list:
        tool = await _tool_repo.get(session, tid)
        if tool is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tool {tid} not found",
            )
        db_tools.append(tool)
        tool_id_to_name[str(tool.id)] = tool.name

    # 4. Build ToolRegistry — builtins always registered first
    registry = ToolRegistry()
    register_builtins(registry)

    # 5. Compile graph
    compiler = GraphCompiler(llm, registry, tool_id_to_name=tool_id_to_name)
    compiled = compiler.compile(graph_json)

    # 6. Create Run record (thread_id and started_at are generated HERE, outside runtime)
    thread_id = str(uuid.uuid4())
    started_at = datetime.now(UTC)
    run = await _run_repo.create(
        session,
        agent_id=agent_id,
        agent_version_id=version.id,
        thread_id=thread_id,
        input_json={"input": data.input},
    )
    run = await _run_repo.update_status(session, run, "running", started_at=started_at)
    # Commit "running" state now so it's visible to concurrent readers and survives
    # a process crash during graph execution.
    await session.commit()

    # 7. Execute graph; catch expected vs unexpected errors differently
    try:
        output = await execute_graph(
            compiled,
            run_id=str(run.id),
            thread_id=thread_id,
            user_input=data.input,
        )
        ended_at = datetime.now(UTC)
        run = await _run_repo.update_status(
            session,
            run,
            "succeeded",
            output_json={"output": output},
            ended_at=ended_at,
        )
    except TimeoutError as exc:
        # Execution deadline exceeded — expected operational failure, not a bug.
        ended_at = datetime.now(UTC)
        run = await _run_repo.update_status(
            session,
            run,
            "failed",
            error_json={"error": "Execution timed out", "type": "TimeoutError"},
            ended_at=ended_at,
        )
        logger.warning("Run %s timed out: %s", run.id, exc, exc_info=True)
    except AgentRuntimeError as exc:
        # Expected runtime failure (bad tool args, LLM error, etc.)
        # Persist the failed run so the caller sees a proper status, then swallow.
        ended_at = datetime.now(UTC)
        run = await _run_repo.update_status(
            session,
            run,
            "failed",
            error_json={"error": str(exc), "type": type(exc).__name__},
            ended_at=ended_at,
        )
        logger.warning("Run %s failed (expected): %s", run.id, exc, exc_info=True)
    except Exception as exc:
        # Unexpected error (DB error, programming bug, etc.) — persist failure AND re-raise.
        # Must commit before re-raising: get_session rolls back on exception, which would
        # erase the "failed" status update without an explicit commit here.
        ended_at = datetime.now(UTC)
        try:
            run = await _run_repo.update_status(
                session,
                run,
                "failed",
                error_json={"error": str(exc), "type": type(exc).__name__},
                ended_at=ended_at,
            )
            await session.commit()
        except Exception:
            logger.error("Could not persist run failure for run %s", run.id, exc_info=True)
        logger.error("Run %s failed (unexpected): %s", run.id, exc, exc_info=True)
        raise

    return RunRead.model_validate(run)


async def get_or_404(
    session: AsyncSession,
    run_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> RunRead:
    """Fetch a run, verifying ownership via the parent agent."""
    run = await _run_repo.get(session, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    # Verify ownership by checking the parent agent
    agent = await _agent_repo.get(session, run.agent_id)
    if agent is None or agent.owner_id != owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your run")
    return RunRead.model_validate(run)
