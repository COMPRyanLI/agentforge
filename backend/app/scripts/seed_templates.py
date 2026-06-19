"""Idempotently seed the platform-provided starter templates.

Run with: uv run python -m app.scripts.seed_templates

Templates have no owner, so a `tool` node referencing a DB-backed Tool row
(or an `llm` node `data.tools` name resolving to one) would be unresolvable
for whoever clones the template — see
app.runtime.registry_builder.graph_references_db_backed_tool, the same gate
app.services.agent.publish() uses. Every template graph below is therefore
restricted to input/llm/condition/loop/output nodes, optionally referencing
the builtin `calculator` tool by name.

The table always converges to exactly the templates defined in TEMPLATES:
existing rows matching a defined name are updated in place (upsert), and any
row whose name is no longer defined here is deleted (prune). This is safe —
installed/cloned agents are independent copies of a template's graph_json,
so pruning a template never touches agents already created from it.
"""

import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import get_engine
from app.models.template import Template
from app.repositories.template import TemplateRepo

_repo = TemplateRepo()

TEMPLATES: list[dict[str, Any]] = [
    {
        "name": "Friendly Chatbot",
        "description": "A warm, casual conversational assistant for general chat.",
        "category": "chat",
        "graph_json": {
            "nodes": [
                {"id": "in", "type": "input"},
                {
                    "id": "llm1",
                    "type": "llm",
                    "data": {
                        "system_prompt": (
                            "You are a friendly, upbeat assistant. Chat with the user in "
                            "a warm, casual tone and keep replies conversational."
                        ),
                        "tools": [],
                    },
                },
                {"id": "out", "type": "output"},
            ],
            "edges": [
                {"source": "in", "target": "llm1"},
                {"source": "llm1", "target": "out"},
            ],
        },
    },
    {
        "name": "Calculator Assistant",
        "description": "Answers questions and reaches for the calculator tool for any arithmetic.",
        "category": "tools",
        "graph_json": {
            "nodes": [
                {"id": "in", "type": "input"},
                {
                    "id": "llm1",
                    "type": "llm",
                    "data": {
                        "system_prompt": (
                            "You are a helpful assistant. Whenever a question involves "
                            "arithmetic, always call the calculator tool to compute the "
                            "result instead of calculating it yourself, then report the "
                            "answer clearly."
                        ),
                        "tools": ["calculator"],
                    },
                },
                {"id": "out", "type": "output"},
            ],
            "edges": [
                {"source": "in", "target": "llm1"},
                {"source": "llm1", "target": "out"},
            ],
        },
    },
    {
        "name": "Triage Router",
        "description": (
            "Classifies a message as urgent or normal and routes it to a "
            "different response style for each."
        ),
        "category": "routing",
        "graph_json": {
            "nodes": [
                {"id": "in", "type": "input"},
                {
                    "id": "classify",
                    "type": "llm",
                    "data": {
                        "system_prompt": (
                            "Respond with exactly one word: URGENT or NORMAL. No other text."
                        ),
                        "tools": [],
                    },
                },
                {
                    "id": "route",
                    "type": "condition",
                    "data": {"expr": "'URGENT' in output"},
                },
                {
                    "id": "urgent",
                    "type": "llm",
                    "data": {
                        "system_prompt": (
                            "This message has been flagged urgent. Acknowledge it "
                            "immediately, reassure the user it's being handled with "
                            "priority, and ask only for the minimum information needed "
                            "to resolve it fast."
                        ),
                        "tools": [],
                    },
                },
                {
                    "id": "normal",
                    "type": "llm",
                    "data": {
                        "system_prompt": (
                            "Respond helpfully and thoroughly to this standard-priority "
                            "request, at a relaxed pace."
                        ),
                        "tools": [],
                    },
                },
                {"id": "out", "type": "output"},
            ],
            "edges": [
                {"source": "in", "target": "classify"},
                {"source": "classify", "target": "route"},
                {"source": "route", "target": "urgent", "condition": "true"},
                {"source": "route", "target": "normal", "condition": "false"},
                {"source": "urgent", "target": "out"},
                {"source": "normal", "target": "out"},
            ],
        },
    },
    {
        "name": "Iterative Refiner",
        "description": (
            "Runs a bounded loop that refines its own answer a few times before "
            "returning a final response."
        ),
        "category": "loops",
        "graph_json": {
            "nodes": [
                {"id": "in", "type": "input"},
                {
                    "id": "loop",
                    "type": "loop",
                    "data": {"expr": "step_index >= 0", "max_iterations": 3},
                },
                {
                    "id": "llm1",
                    "type": "llm",
                    "data": {
                        "system_prompt": (
                            "Refine and improve your previous answer in this conversation. "
                            "If it is already tight, accurate, and complete, restate it "
                            "unchanged."
                        ),
                        "tools": [],
                    },
                },
                {"id": "out", "type": "output"},
            ],
            "edges": [
                {"source": "in", "target": "loop"},
                {"source": "loop", "target": "llm1", "condition": "true"},
                {"source": "loop", "target": "out", "condition": "false"},
                {"source": "llm1", "target": "loop"},
            ],
        },
    },
]


async def _apply_templates(session: AsyncSession) -> None:
    """Upsert every defined template by name, then delete any row whose name
    is no longer defined — the table always converges to exactly TEMPLATES.
    Split out from seed_templates() so tests can run it against a session
    backed by a test database instead of the production engine."""
    defined_names = {spec["name"] for spec in TEMPLATES}
    for spec in TEMPLATES:
        existing = await _repo.get_by_name(session, spec["name"])
        if existing is not None:
            existing.description = spec["description"]
            existing.category = spec["category"]
            existing.graph_json = spec["graph_json"]
        else:
            session.add(
                Template(
                    name=spec["name"],
                    description=spec["description"],
                    category=spec["category"],
                    graph_json=spec["graph_json"],
                )
            )
    for template in await _repo.list_all(session):
        if template.name not in defined_names:
            await session.delete(template)


async def seed_templates() -> None:
    factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with factory() as session:
        await _apply_templates(session)
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed_templates())
