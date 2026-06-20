"""Runs router — GET /runs/{run_id} and GET /runs/{run_id}/events (SSE)."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session
from app.dependencies import (
    get_arq_pool,
    get_checkpointer,
    get_current_user,
    get_optional_current_user,
    get_redis,
)
from app.models.user import User
from app.repositories.agent import AgentRepo
from app.repositories.run import RunRepo
from app.schemas.run import RunEnqueueResponse, RunEventRead, RunRead, RunResumeRequest
from app.security import decode_access_token
from app.services import run as run_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["runs"])

_run_repo = RunRepo()
_agent_repo = AgentRepo()

_TERMINAL_STATUSES = {"succeeded", "failed", "interrupted"}


@router.get("/{run_id}", response_model=RunRead)
async def get_run(
    run_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RunRead:
    return await run_service.get_or_404(session, run_id, owner_id=current_user.id)


@router.post("/{run_id}/resume", response_model=RunEnqueueResponse)
async def resume_run(
    run_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    arq_pool: Annotated[ArqRedis, Depends(get_arq_pool)],
    body: RunResumeRequest | None = None,
) -> RunEnqueueResponse:
    """Resume a crashed/interrupted run from its last checkpoint.

    Re-invokes the worker with resume=True, so LangGraph continues from the
    last checkpoint on the run's thread_id instead of starting fresh — no
    already-completed LLM call or tool side effect is repeated.

    If the run is paused on a require_approval tool node, body.approval
    carries the human's decision back in via Command(resume=...).
    """
    approval = body.approval if body is not None else None
    response = await run_service.resume(session, run_id, current_user.id, approval)
    await arq_pool.enqueue_job(
        "execute_run", str(response.run_id), resume=True, resume_value=approval
    )
    return response


@router.post("/{run_id}/replay", response_model=RunEnqueueResponse)
async def replay_run(
    run_id: uuid.UUID,
    from_step: Annotated[int, Query(ge=0)],
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    arq_pool: Annotated[ArqRedis, Depends(get_arq_pool)],
    checkpointer: Annotated[AsyncPostgresSaver, Depends(get_checkpointer)],
) -> RunEnqueueResponse:
    """Fork a new run from an existing run's checkpoint at from_step.

    The new run is enqueued with resume=True: its only seed state is the
    forked checkpoint, so execute_graph continues forward from it rather
    than starting from fresh input.
    """
    response = await run_service.replay(session, run_id, current_user.id, from_step, checkpointer)
    await arq_pool.enqueue_job("execute_run", str(response.run_id), resume=True)
    return response


@router.get("/{run_id}/timeline", response_model=list[RunEventRead])
async def get_run_timeline(
    run_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[RunEventRead]:
    """Plain REST counterpart to the SSE /events stream: the full, ordered
    event history of a run, for rendering a static timeline view (no live
    connection needed once the run has finished)."""
    run = await _run_repo.get(session, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    agent = await _agent_repo.get(session, run.agent_id)
    if agent is None or agent.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your run")
    events = await _run_repo.list_events(session, run_id)
    return [RunEventRead.model_validate(e) for e in events]


@router.get("/{run_id}/events")
async def stream_run_events(
    run_id: uuid.UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    settings: Annotated[Settings, Depends(get_settings)],
    opt_user: Annotated[User | None, Depends(get_optional_current_user)] = None,
    token: str | None = Query(default=None),
) -> StreamingResponse:
    """SSE stream of run events.

    Replays persisted run_events from DB first, then subscribes to Redis
    pub/sub for live events. Supports Last-Event-ID for resumable streams.

    Auth: standard Bearer token header OR ?token=<jwt> query param (for browser EventSource).
    Note: the ?token= value will appear in uvicorn access logs; apply log-level filtering or
    short retention for this route in production.
    """
    user: User | None = opt_user

    # Fall back to ?token= query param (EventSource can't send custom headers)
    if user is None and token is not None:
        try:
            subject = decode_access_token(token, settings)
            user_id = uuid.UUID(subject)
        except (HTTPException, ValueError):
            pass
        else:
            from app.repositories.user import UserRepo

            _user_repo = UserRepo()
            user = await _user_repo.get_by_id(session, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Ownership check — do this before starting the stream
    run = await _run_repo.get(session, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    agent = await _agent_repo.get(session, run.agent_id)
    if agent is None or agent.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your run")

    # Parse Last-Event-ID for resumable streams
    last_event_id_header = request.headers.get("Last-Event-ID", "")
    try:
        after_step = int(last_event_id_header)
    except (ValueError, TypeError):
        after_step = -1

    def _done_frame(done_status: str) -> str:
        return f"data: {json.dumps({'type': 'done', 'status': done_status})}\n\n"

    async def _current_status() -> str:
        # Each check is its own short read — committing right after closes
        # out the implicit transaction immediately instead of holding one
        # open (idle-in-transaction) for the entire lifetime of a long SSE
        # connection, which risks the connection being killed by a DB-side
        # idle timeout and the generator dying silently without ever sending
        # a terminal frame (the client would then hang on "running" forever).
        current = await _run_repo.get(session, run_id)
        await session.commit()
        return current.status if current is not None else "unknown"

    async def _generate() -> AsyncIterator[str]:
        # 1. Replay persisted events from DB
        events = await _run_repo.list_events(session, run_id, after_step=after_step)
        for event in events:
            payload = json.dumps(
                {
                    "run_id": str(event.run_id),
                    "step_index": event.step_index,
                    "node_id": event.node_id,
                    "event_type": event.event_type,
                    "payload": event.payload_json,
                    "ts": event.ts.isoformat(),
                }
            )
            yield f"id: {event.step_index}\ndata: {payload}\n\n"

        # 2. If already terminal, yield done frame and stop
        try:
            status_now = await _current_status()
        except Exception:
            logger.exception("stream_run_events: failed to read run %s status", run_id)
            yield _done_frame("unknown")
            return
        if status_now in _TERMINAL_STATUSES:
            yield _done_frame(status_now)
            return

        # 3. Subscribe to Redis pub/sub for live events
        pubsub = redis.pubsub()
        await pubsub.subscribe(f"run:{run_id}")
        try:
            while True:
                # Any failure here (DB or Redis) must still produce a
                # terminal frame rather than silently killing the
                # connection — an EventSource that never sees "done" never
                # closes, and a client relying solely on it would be stuck
                # showing "running" forever even after the run finished.
                try:
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    if message is not None:
                        raw = message.get("data", b"")
                        if isinstance(raw, bytes):
                            raw = raw.decode()
                        try:
                            parsed = json.loads(raw)
                            step_index = parsed.get("step_index", 0)
                            yield f"id: {step_index}\ndata: {raw}\n\n"
                        except (ValueError, TypeError):
                            pass

                    # Re-check terminal state after each message (or timeout)
                    status_now = await _current_status()
                except Exception:
                    logger.exception("stream_run_events: live poll failed for run %s", run_id)
                    yield _done_frame("unknown")
                    return
                if status_now in _TERMINAL_STATUSES:
                    yield _done_frame(status_now)
                    break
        finally:
            await pubsub.unsubscribe(f"run:{run_id}")

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
