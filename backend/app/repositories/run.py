"""Run repository — all DB access for the runs table."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.run import Run, RunEvent


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
        awaiting_approval: bool | None = None,
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
        if awaiting_approval is not None:
            run.awaiting_approval = awaiting_approval
        await session.flush()
        await session.refresh(run)
        return run

    async def create_event(
        self,
        session: AsyncSession,
        run_id: uuid.UUID,
        step_index: int,
        node_id: str,
        event_type: str,
        payload_json: dict[str, Any],  # justified: event payload is open-ended
        ts: datetime,
    ) -> RunEvent:
        event = RunEvent(
            run_id=run_id,
            step_index=step_index,
            node_id=node_id,
            event_type=event_type,
            payload_json=payload_json,
            ts=ts,
        )
        session.add(event)
        await session.flush()
        return event

    async def list_events(
        self,
        session: AsyncSession,
        run_id: uuid.UUID,
        after_step: int = -1,
    ) -> list[RunEvent]:
        result = await session.execute(
            select(RunEvent)
            .where(RunEvent.run_id == run_id, RunEvent.step_index > after_step)
            .order_by(RunEvent.step_index.asc())
        )
        return list(result.scalars().all())

    async def list_by_agent(
        self,
        session: AsyncSession,
        agent_id: uuid.UUID,
    ) -> list[Run]:
        result = await session.execute(
            select(Run).where(Run.agent_id == agent_id).order_by(Run.created_at.desc())
        )
        return list(result.scalars().all())
