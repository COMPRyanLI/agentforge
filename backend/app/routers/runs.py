"""Runs router — GET /runs/{run_id} and GET /runs/{run_id}/events (SSE)."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session
from app.dependencies import get_current_user, get_optional_current_user, get_redis
from app.models.user import User
from app.repositories.agent import AgentRepo
from app.repositories.run import RunRepo
from app.schemas.run import RunRead
from app.security import decode_access_token
from app.services import run as run_service

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
        current_run = await _run_repo.get(session, run_id)
        if current_run is None or current_run.status in _TERMINAL_STATUSES:
            done_status = current_run.status if current_run else "unknown"
            yield f"data: {json.dumps({'type': 'done', 'status': done_status})}\n\n"
            return

        # 3. Subscribe to Redis pub/sub for live events
        pubsub = redis.pubsub()
        await pubsub.subscribe(f"run:{run_id}")
        try:
            while True:
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
                live_run = await _run_repo.get(session, run_id)
                if live_run is None or live_run.status in _TERMINAL_STATUSES:
                    done_status = live_run.status if live_run else "unknown"
                    yield f"data: {json.dumps({'type': 'done', 'status': done_status})}\n\n"
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
