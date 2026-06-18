"""Run, RunEvent, and ToolCall models."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKey


class Run(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "runs"

    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    agent_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_versions.id"))
    thread_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    # status: pending | running | succeeded | failed | interrupted
    status: Mapped[str] = mapped_column(String(20), default="pending")
    input_json: Mapped[dict[str, Any]] = mapped_column(JSONB)  # justified: open-ended JSON
    # justified: output shape varies by agent
    output_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # justified: error shape is open-ended JSON
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # True while status=="interrupted" specifically because a require_approval
    # tool node paused for a human decision — distinguishes that from a
    # crash/transient-failure interruption without re-deriving it from
    # run_events on every resume call.
    awaiting_approval: Mapped[bool] = mapped_column(Boolean, default=False)


class RunEvent(UUIDPrimaryKey, Base):
    __tablename__ = "run_events"

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    step_index: Mapped[int] = mapped_column(Integer)
    node_id: Mapped[str] = mapped_column(String(255))
    # event_type: node_start | llm_call | llm_result | tool_call | tool_result |
    #              node_end | retry | error | interrupt | resume
    event_type: Mapped[str] = mapped_column(String(50))
    # justified: event payload is open-ended JSON
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ToolCall(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "tool_calls"

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[str] = mapped_column(String(255))
    # idempotency_key = (run_id, node_id, step_index, call_index) — call_index disambiguates
    # multiple tool calls within one llm-node iteration; ensures exactly-once side effects on resume
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    # status: pending | completed | failed
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # justified: tool args and result shape are open-ended JSON (match the tool's runtime schema)
    args_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
