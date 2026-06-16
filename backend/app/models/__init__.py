"""SQLAlchemy model registry.

Importing this package pulls in all model classes so that:
- alembic autogenerate can discover every table via Base.metadata
- Any code that imports Base can rely on all tables being registered
"""

from app.models.agent import Agent, AgentVersion
from app.models.base import Base
from app.models.marketplace import Install, Rating
from app.models.run import Run, RunEvent, ToolCall
from app.models.template import Template
from app.models.tool import Tool
from app.models.user import User

__all__ = [
    "Base",
    "User",
    "Agent",
    "AgentVersion",
    "Tool",
    "Template",
    "Run",
    "RunEvent",
    "ToolCall",
    "Rating",
    "Install",
]
