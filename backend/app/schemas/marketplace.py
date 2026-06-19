"""Marketplace request/response schemas: published-agent listing, ratings."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class MarketplaceAgentRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    description: str | None
    install_count: int
    avg_rating: float
    created_at: datetime

    @field_validator("avg_rating", mode="before")
    @classmethod
    def _coalesce_unrated(cls, value: float | None) -> float:
        # An agent with no ratings yet has avg_rating=None at the DB level
        # (only set once recompute_avg_rating runs) — surface 0.0, not null.
        return value if value is not None else 0.0


class RatingCreate(BaseModel):
    score: int = Field(ge=1, le=5)
    comment: str | None = None


class RatingRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    agent_id: uuid.UUID
    user_id: uuid.UUID
    score: int
    comment: str | None
    created_at: datetime
