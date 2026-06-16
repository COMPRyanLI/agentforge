"""Run repository — all DB access for the runs table."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.run import Run


class RunRepo:
    async def create(
        self,
        session: AsyncSession,
        agent_id: uuid.UUID,
        agent_version_id: uuid.UUID,
        thread_id: str,
        input_json: dict[str, Any],  # justified: input shape is open-ended
    ) -> Run:
        run = Run(
            agent_id=agent_id,
            agent_version_id=agent_version_id,
            thread_id=thread_id,
            status="pending",
            input_json=input_json,
        )
        session.add(run)
        await session.flush()
        await session.refresh(run)
        return run

    async def get(self, session: AsyncSession, run_id: uuid.UUID) -> Run | None:
        result = await session.execute(select(Run).where(Run.id == run_id))
        return result.scalar_one_or_none()

    async def update_status(
        self,
        session: AsyncSession,
        run: Run,
        status: str,
        *,
        output_json: dict[str, Any] | None = None,
        error_json: dict[str, Any] | None = None,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
    ) -> Run:
        run.status = status
        if output_json is not None:
            run.output_json = output_json
        if error_json is not None:
            run.error_json = error_json
        if started_at is not None:
            run.started_at = started_at
        if ended_at is not None:
            run.ended_at = ended_at
        await session.flush()
        await session.refresh(run)
        return run
