"""EventEmitter: persists run_events rows and publishes to Redis pub/sub.

Each emit() opens a fresh DB session so the row is immediately visible to
concurrent SSE readers — not held in a long-lived transaction until run end.

Replay-safety: ts is always passed in by the caller (handler body).
This class never calls datetime.now() or uuid4() internally.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.run import RunRepo

_repo = RunRepo()


class EventEmitter:
    def __init__(
        self,
        run_id: str,
        session_factory: async_sessionmaker[AsyncSession],
        redis_client: Redis,
    ) -> None:
        self._run_id = run_id
        self._factory = session_factory
        self._redis = redis_client

    async def emit(
        self,
        step_index: int,
        node_id: str,
        event_type: str,
        payload: dict[str, Any],  # justified: event payload shape is open-ended
        ts: datetime,
    ) -> None:
        run_uuid = uuid.UUID(self._run_id)
        async with self._factory() as session:
            await _repo.create_event(
                session,
                run_id=run_uuid,
                step_index=step_index,
                node_id=node_id,
                event_type=event_type,
                payload_json=payload,
                ts=ts,
            )
            await session.commit()

        message = json.dumps(
            {
                "run_id": self._run_id,
                "step_index": step_index,
                "node_id": node_id,
                "event_type": event_type,
                "payload": payload,
                "ts": ts.isoformat(),
            }
        )
        await self._redis.publish(f"run:{self._run_id}", message)
