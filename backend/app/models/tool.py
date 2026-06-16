"""Tool model."""

import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKey


class Tool(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "tools"

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    json_schema: Mapped[dict[str, Any]] = mapped_column(JSONB)  # justified: open-ended JSON
    impl_type: Mapped[str] = mapped_column(String(20))  # "builtin" | "http" | "python"
    # justified: config shape varies by impl_type
    config_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
