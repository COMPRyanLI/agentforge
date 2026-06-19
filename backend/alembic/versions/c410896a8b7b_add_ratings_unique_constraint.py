"""add ratings unique constraint

Revision ID: c410896a8b7b
Revises: 3a58679fe583
Create Date: 2026-06-19 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c410896a8b7b"
down_revision: str | None = "3a58679fe583"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint("uq_ratings_agent_user", "ratings", ["agent_id", "user_id"])


def downgrade() -> None:
    op.drop_constraint("uq_ratings_agent_user", "ratings", type_="unique")
