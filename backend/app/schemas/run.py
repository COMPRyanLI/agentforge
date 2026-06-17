"""Pydantic schemas for run endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class RunCreate(BaseModel):
    input: str


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
