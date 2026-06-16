"""Agent and AgentVersion request/response schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AgentCreate(BaseModel):
    name: str
    description: str | None = None


class AgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class AgentRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    description: str | None
    current_version_id: uuid.UUID | None
    visibility: str
    install_count: int
    avg_rating: float | None
    created_at: datetime


class AgentVersionCreate(BaseModel):
    graph_json: dict[str, Any]  # justified: graph shape is open-ended JSON


class AgentVersionRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    agent_id: uuid.UUID
    version_number: int
    graph_json: dict[str, Any]  # justified: graph shape is open-ended JSON
    created_at: datetime
