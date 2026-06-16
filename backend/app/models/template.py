"""Template model — platform-provided starter graphs."""

from typing import Any

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKey


class Template(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "templates"

    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(100))
    # justified: graph shape is open-ended JSON
    graph_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
