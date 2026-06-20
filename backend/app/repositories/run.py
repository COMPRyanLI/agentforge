"""Run repository — all DB access for the runs table."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.run import Run, RunEvent

_TERMINAL_FOR_STATS = ("succeeded", "failed")
_IN_PROGRESS_FOR_STATS = ("running", "interrupted")


@dataclass(slots=True)
class AgentRunStatsRow:
    total_runs: int
    in_progress_count: int
    success_rate: float | None
    p95_latency_ms: float | None
    avg_prompt_tokens: float | None
    avg_completion_tokens: float | None
    avg_steps_per_run: float | None


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

    async def get_agent_stats(
        self,
        session: AsyncSession,
        agent_id: uuid.UUID,
    ) -> AgentRunStatsRow:
        """Aggregate run statistics for an agent.

        Status semantics: success_rate and p95_latency_ms are computed ONLY over
        runs with status in (succeeded, failed) — runs that actually finished
        with both started_at and ended_at set. `interrupted` (HITL-paused, may
        have no ended_at yet) and `running` are excluded from both and rolled
        into in_progress_count instead, never coerced into either bucket.

        p95 algorithm: nearest-rank on the ascending-sorted list of per-run
        durations in ms — index = ceil(0.95 * N) - 1, clamped to [0, N-1]. For
        N=1 this is index 0, so p95 equals the single duration exactly.

        Token aggregation: prompt_tokens/completion_tokens are optional per
        llm_result event. Each average is computed only over events that carry
        a non-null count for that specific field — missing data is never
        coerced to 0, so a run with no token data never pulls the average
        toward zero. avg_steps_per_run is likewise averaged only over terminal
        runs that have at least one run_event.

        Performance: loads every run for the agent (for total_runs/
        in_progress_count) plus the terminal runs' llm_result events into
        memory and aggregates in Python. Accepted tradeoff at portfolio
        scale — no pagination or DB-side percentile aggregate needed.
        """
        all_runs_result = await session.execute(
            select(Run.id, Run.status, Run.started_at, Run.ended_at).where(Run.agent_id == agent_id)
        )
        all_runs = all_runs_result.all()
        total_runs = len(all_runs)
        in_progress_count = sum(1 for r in all_runs if r.status in _IN_PROGRESS_FOR_STATS)
        terminal_runs = [r for r in all_runs if r.status in _TERMINAL_FOR_STATS]

        success_rate: float | None = None
        p95_latency_ms: float | None = None
        avg_prompt_tokens: float | None = None
        avg_completion_tokens: float | None = None
        avg_steps_per_run: float | None = None

        if terminal_runs:
            succeeded_count = sum(1 for r in terminal_runs if r.status == "succeeded")
            success_rate = succeeded_count / len(terminal_runs)

            durations_ms = sorted(
                (r.ended_at - r.started_at).total_seconds() * 1000
                for r in terminal_runs
                if r.started_at is not None and r.ended_at is not None
            )
            if durations_ms:
                n = len(durations_ms)
                idx = min(max(math.ceil(0.95 * n) - 1, 0), n - 1)
                p95_latency_ms = durations_ms[idx]

            terminal_ids = [r.id for r in terminal_runs]
            events_result = await session.execute(
                select(
                    RunEvent.run_id, RunEvent.step_index, RunEvent.event_type, RunEvent.payload_json
                ).where(RunEvent.run_id.in_(terminal_ids))
            )
            events = events_result.all()

            def _as_int(value: Any) -> int | None:
                # bool is an int subclass — exclude it explicitly since these
                # fields are only ever meant to carry token counts.
                return value if isinstance(value, int) and not isinstance(value, bool) else None

            prompt_values = [
                v
                for e in events
                if e.event_type == "llm_result"
                and (v := _as_int(e.payload_json.get("prompt_tokens"))) is not None
            ]
            completion_values = [
                v
                for e in events
                if e.event_type == "llm_result"
                and (v := _as_int(e.payload_json.get("completion_tokens"))) is not None
            ]
            if prompt_values:
                avg_prompt_tokens = sum(prompt_values) / len(prompt_values)
            if completion_values:
                avg_completion_tokens = sum(completion_values) / len(completion_values)

            max_step_by_run: dict[uuid.UUID, int] = {}
            for e in events:
                current = max_step_by_run.get(e.run_id, -1)
                if e.step_index > current:
                    max_step_by_run[e.run_id] = e.step_index
            if max_step_by_run:
                steps_per_run = [v + 1 for v in max_step_by_run.values()]
                avg_steps_per_run = sum(steps_per_run) / len(steps_per_run)

        return AgentRunStatsRow(
            total_runs=total_runs,
            in_progress_count=in_progress_count,
            success_rate=success_rate,
            p95_latency_ms=p95_latency_ms,
            avg_prompt_tokens=avg_prompt_tokens,
            avg_completion_tokens=avg_completion_tokens,
            avg_steps_per_run=avg_steps_per_run,
        )
