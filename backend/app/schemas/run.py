"""Pydantic schemas for run endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class RunCreate(BaseModel):
    input: str


class RunResumeRequest(BaseModel):
    """Optional body for POST /runs/{id}/resume.

    approval is only meaningful when the run is paused awaiting a
    human-in-the-loop decision (RunRead.awaiting_approval is True) — omit it
    for a plain crash-recovery resume.
    """

    approval: Literal["approved", "rejected"] | None = None


class RunRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    agent_id: uuid.UUID
    agent_version_id: uuid.UUID
    thread_id: str
    status: str
    input_json: dict[str, Any]  # justified: open-ended input shape
    output_json: dict[str, Any] | None
    started_at: datetime | None
    ended_at: datetime | None
    error_json: dict[str, Any] | None
    awaiting_approval: bool
    created_at: datetime


class RunEnqueueResponse(BaseModel):
    run_id: uuid.UUID
    status: str = "pending"


class RunEventRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    run_id: uuid.UUID
    step_index: int
    node_id: str
    event_type: str
    payload_json: dict[str, Any]  # justified: event payload is open-ended
    ts: datetime
