"""Tool request/response schemas."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

ImplType = Literal["builtin", "http", "python"]


class ToolCreate(BaseModel):
    name: str
    description: str | None = None
    json_schema: dict[str, Any]  # justified: tool parameter schema is open-ended JSON
    impl_type: ImplType
    config_json: dict[str, Any] | None = None  # justified: config shape varies by impl_type


class ToolUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    json_schema: dict[str, Any] | None = None  # justified: tool parameter schema is open-ended JSON
    config_json: dict[str, Any] | None = None  # justified: config shape varies by impl_type


class ToolRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    description: str | None
    json_schema: dict[str, Any]  # justified: tool parameter schema is open-ended JSON
    impl_type: str
    config_json: dict[str, Any] | None  # justified: config shape varies by impl_type
    created_at: datetime
