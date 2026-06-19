"""Template request/response schemas — platform-provided starter graphs."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class TemplateRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    description: str | None
    category: str
    graph_json: dict[str, Any]  # justified: graph shape is open-ended JSON
    created_at: datetime
