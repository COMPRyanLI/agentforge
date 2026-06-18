"""Run service — orchestrates agent graph execution."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import HTTPException, status
from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import get_engine
from app.llm.provider import LLMProvider
from app.repositories.agent import AgentRepo
from app.repositories.run import RunRepo
from app.repositories.tool import ToolRepo
from app.runtime.checkpointer import fork_thread_at_step
from app.runtime.compiler import GraphCompiler
from app.runtime.errors import AgentRuntimeError
from app.runtime.executor import execute_graph
from app.runtime.registry_builder import build_registry, extract_tool_ids
from app.schemas.run import RunCreate, RunEnqueueResponse, RunRead

logger = logging.getLogger(__name__)

_run_repo = RunRepo()
_agent_repo = AgentRepo()
_tool_repo = ToolRepo()


async def _validate_agent_for_run(
    session: AsyncSession,
    agent_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> tuple[Any, Any, dict[str, str]]:
    """Validate agent ownership + version, return (agent, version, tool_id_to_name)."""
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

    version = await _agent_repo.get_version(session, agent.current_version_id)
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Agent version not found",
        )

    graph_json: dict[str, Any] = version.graph_json
    tool_id_list = extract_tool_ids(graph_json)
    tool_id_to_name: dict[str, str] = {}
    for tid in tool_id_list:
        tool = await _tool_repo.get(session, tid)
        if tool is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tool {tid} not found",
            )
        tool_id_to_name[str(tool.id)] = tool.name

    return agent, version, tool_id_to_name


async def create_pending(
    session: AsyncSession,
    agent_id: uuid.UUID,
    owner_id: uuid.UUID,
    data: RunCreate,
) -> RunEnqueueResponse:
    """Validate the agent, create a pending Run record, return its ID for the worker.

    thread_id is generated here (in the service layer, outside the runtime) so it is
    never generated inside graph execution — satisfying the replay-safety contract.
    """
    _agent, version, _tool_id_to_name = await _validate_agent_for_run(session, agent_id, owner_id)
    thread_id = str(uuid.uuid4())
    run = await _run_repo.create(
        session,
        agent_id=agent_id,
        agent_version_id=version.id,
        thread_id=thread_id,
        input_json={"input": data.input},
    )
    await session.commit()
    return RunEnqueueResponse(run_id=run.id)


async def create_and_execute(
    session: AsyncSession,
    agent_id: uuid.UUID,
    owner_id: uuid.UUID,
    data: RunCreate,
    llm: LLMProvider,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> RunRead:
    """Create a Run record, execute the graph synchronously, persist result.

    Kept for direct use in tests and tooling that want synchronous execution.
    The public API endpoint uses create_pending + arq worker instead.
    """
    agent, version, tool_id_to_name = await _validate_agent_for_run(session, agent_id, owner_id)

    graph_json: dict[str, Any] = version.graph_json

    registry = await build_registry(session, graph_json, agent.owner_id)

    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    compiler = GraphCompiler(
        llm,
        registry,
        session_factory,
        tool_id_to_name=tool_id_to_name,
        checkpointer=checkpointer,
    )
    compile_result = compiler.compile(graph_json)
    compiled = compile_result.graph

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
    await session.commit()

    try:
        result = await execute_graph(
            compiled,
            run_id=str(run.id),
            thread_id=thread_id,
            user_input=data.input,
            recursion_limit=compile_result.recursion_limit,
        )
        ended_at = datetime.now(UTC)
        if result.awaiting_approval is not None:
            run = await _run_repo.update_status(
                session,
                run,
                "interrupted",
                awaiting_approval=True,
                ended_at=ended_at,
            )
        else:
            run = await _run_repo.update_status(
                session,
                run,
                "succeeded",
                output_json={"output": result.output},
                ended_at=ended_at,
            )
    except TimeoutError as exc:
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


_RESUMABLE_STATUSES = {"running", "interrupted"}


async def resume(
    session: AsyncSession,
    run_id: uuid.UUID,
    owner_id: uuid.UUID,
    approval: Literal["approved", "rejected"] | None = None,
) -> RunEnqueueResponse:
    """Validate ownership + resumability, flip status back to "pending".

    Does not execute — the caller re-enqueues "execute_run" with resume=True
    (and resume_value=approval, if given), same enqueue/execute split as
    create_pending.

    "running" is included alongside "interrupted" because a killed worker
    process leaves no code path to ever set "interrupted" — the run just
    stays "running" forever with a valid checkpoint sitting unused. That's
    exactly the crash-recovery case this endpoint exists for.

    Caveat: accepting "running" assumes at most one worker is ever actually
    executing a given run at a time (true for a single arq worker process, or
    for many workers as long as no run_id is ever double-enqueued). There is
    no liveness check or lease here — if the original worker is in fact still
    alive and mid-execution, calling resume re-enqueues a second job against
    the same thread_id, and the two would race on the same checkpoint and the
    same tool_calls idempotency keys. That race is exactly what
    ToolCallAmbiguousError and the tool_calls unique constraint exist to fail
    loudly on rather than silently double-firing a side effect, but it would
    still surface as a confusing error rather than being prevented up front.

    If the run is awaiting a human-in-the-loop decision (awaiting_approval),
    approval must be provided — there's nothing else for resume to do with
    a paused require_approval node.
    """
    run = await _run_repo.get(session, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    agent = await _agent_repo.get(session, run.agent_id)
    if agent is None or agent.owner_id != owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your run")
    if run.status not in _RESUMABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Run is {run.status!r}; only running/interrupted runs can be resumed",
        )
    if run.awaiting_approval and approval is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Run is awaiting a human-in-the-loop decision; provide 'approval'",
        )
    run = await _run_repo.update_status(session, run, "pending", awaiting_approval=False)
    await session.commit()
    return RunEnqueueResponse(run_id=run.id, status="pending")


async def replay(
    session: AsyncSession,
    run_id: uuid.UUID,
    owner_id: uuid.UUID,
    from_step: int,
    checkpointer: BaseCheckpointSaver[Any],
) -> RunEnqueueResponse:
    """Fork a NEW run from an existing run's checkpoint at from_step.

    Copies the checkpoint to a fresh thread_id and creates a new pending Run
    row pinned to the SAME agent_version_id as the original — never the
    agent's current version — so the forked run replays against the exact
    graph definition the original ran on (the replay-safety contract's
    versioned-graphs rule). The caller re-enqueues "execute_run" with
    resume=True so the new run continues forward from the forked checkpoint
    rather than starting from fresh input.
    """
    old_run = await _run_repo.get(session, run_id)
    if old_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    agent = await _agent_repo.get(session, old_run.agent_id)
    if agent is None or agent.owner_id != owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your run")

    new_thread_id = str(uuid.uuid4())
    found = await fork_thread_at_step(checkpointer, old_run.thread_id, new_thread_id, from_step)
    if not found:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No checkpoint found at step {from_step}",
        )

    new_run = await _run_repo.create(
        session,
        agent_id=old_run.agent_id,
        agent_version_id=old_run.agent_version_id,
        thread_id=new_thread_id,
        input_json=old_run.input_json,
    )
    await session.commit()
    return RunEnqueueResponse(run_id=new_run.id, status="pending")


async def get_or_404(
    session: AsyncSession,
    run_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> RunRead:
    """Fetch a run, verifying ownership via the parent agent."""
    run = await _run_repo.get(session, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    agent = await _agent_repo.get(session, run.agent_id)
    if agent is None or agent.owner_id != owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your run")
    return RunRead.model_validate(run)


async def list_by_agent(
    session: AsyncSession,
    agent_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> list[RunRead]:
    """List all runs for an agent, verifying ownership."""
    agent = await _agent_repo.get(session, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    if agent.owner_id != owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your agent")
    runs = await _run_repo.list_by_agent(session, agent_id)
    return [RunRead.model_validate(r) for r in runs]
