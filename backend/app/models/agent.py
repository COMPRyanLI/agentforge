"""Agent and AgentVersion models."""

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKey


class AgentVersion(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "agent_versions"
    __table_args__ = (
        UniqueConstraint("agent_id", "version_number", name="uq_agent_versions_agent_version"),
    )

    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    version_number: Mapped[int] = mapped_column(Integer)
    # justified: graph shape is open-ended JSON
    graph_json: Mapped[dict[str, Any]] = mapped_column(JSONB)

    agent: Mapped["Agent"] = relationship(
        "Agent", back_populates="versions", foreign_keys=[agent_id]
    )


class Agent(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "agents"

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Nullable until the first version is saved
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_versions.id", use_alter=True, name="fk_agents_current_version"),
        nullable=True,
    )
    visibility: Mapped[str] = mapped_column(String(20), default="private")
    install_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_rating: Mapped[float | None] = mapped_column(nullable=True)

    versions: Mapped[list[AgentVersion]] = relationship(
        "AgentVersion",
        back_populates="agent",
        foreign_keys=[AgentVersion.agent_id],
        cascade="all, delete-orphan",
    )
