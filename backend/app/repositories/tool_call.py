"""ToolCallRepo — all DB access for the tool_calls idempotency table."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.run import ToolCall


class ToolCallRepo:
    async def get_by_key(self, session: AsyncSession, idempotency_key: str) -> ToolCall | None:
        result = await session.execute(
            select(ToolCall).where(ToolCall.idempotency_key == idempotency_key)
        )
        return result.scalar_one_or_none()

    async def create_pending(
        self,
        session: AsyncSession,
        run_id: uuid.UUID,
        node_id: str,
        idempotency_key: str,
        args_json: dict[str, Any],  # justified: tool args shape is open-ended
    ) -> ToolCall:
        tool_call = ToolCall(
            run_id=run_id,
            node_id=node_id,
            idempotency_key=idempotency_key,
            status="pending",
            args_json=args_json,
        )
        session.add(tool_call)
        await session.flush()
        await session.refresh(tool_call)
        return tool_call

    async def mark_completed(
        self,
        session: AsyncSession,
        tool_call: ToolCall,
        result_json: dict[str, Any],  # justified: tool result shape is open-ended
    ) -> ToolCall:
        tool_call.status = "completed"
        tool_call.result_json = result_json
        await session.flush()
        await session.refresh(tool_call)
        return tool_call

    async def mark_pending(self, session: AsyncSession, tool_call: ToolCall) -> ToolCall:
        """Reset a previously-failed row to 'pending' before retrying it.

        Keeps the ambiguity-detection window (see ToolCallAmbiguousError)
        active across retries: if the process crashes during this retry too,
        the row is left 'pending' rather than silently looking like a clean
        failure that's safe to retry again.
        """
        tool_call.status = "pending"
        await session.flush()
        await session.refresh(tool_call)
        return tool_call

    async def mark_failed(
        self,
        session: AsyncSession,
        tool_call: ToolCall,
        error_json: dict[str, Any],  # justified: error shape is open-ended
    ) -> ToolCall:
        tool_call.status = "failed"
        tool_call.result_json = error_json
        await session.flush()
        await session.refresh(tool_call)
        return tool_call
