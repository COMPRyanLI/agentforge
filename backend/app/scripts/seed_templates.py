"""Idempotently seed the platform-provided starter templates.

Run with: uv run python -m app.scripts.seed_templates

Every template graph is restricted to input -> llm -> output (optionally
referencing the builtin `calculator` tool by name) — templates have no
owner, so a `tool` node referencing a DB-backed Tool row would be
unresolvable for whoever clones the template (see
app.runtime.registry_builder.graph_references_db_backed_tool, which the
publish-time gate uses for the same reason).
"""

import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db import get_engine
from app.models.template import Template
from app.repositories.template import TemplateRepo

_repo = TemplateRepo()

TEMPLATES: list[dict[str, Any]] = [
    {
        "name": "Research Assistant",
        "description": "Summarizes a topic and surfaces the key facts a user should know.",
        "category": "research",
        "graph_json": {
            "nodes": [
                {"id": "in", "type": "input"},
                {
                    "id": "llm1",
                    "type": "llm",
                    "data": {
                        "system_prompt": (
                            "You are a research assistant. Given a topic or question, "
                            "produce a concise, well-organized summary of the key facts."
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
        "name": "Web Q&A",
        "description": "Answers a user's question directly and concisely.",
        "category": "qa",
        "graph_json": {
            "nodes": [
                {"id": "in", "type": "input"},
                {
                    "id": "llm1",
                    "type": "llm",
                    "data": {
                        "system_prompt": (
                            "You answer questions directly and concisely. If you are not "
                            "sure of an answer, say so rather than guessing."
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
        "name": "Data Extractor",
        "description": "Pulls structured numeric data out of free text and can compute with it.",
        "category": "data",
        "graph_json": {
            "nodes": [
                {"id": "in", "type": "input"},
                {
                    "id": "llm1",
                    "type": "llm",
                    "data": {
                        "system_prompt": (
                            "You extract structured numeric data from the user's text. "
                            "Use the calculator tool for any arithmetic instead of doing "
                            "it yourself, then report the extracted values and results."
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
        "name": "Friendly Chatbot",
        "description": "A general-purpose, friendly conversational assistant.",
        "category": "chat",
        "graph_json": {
            "nodes": [
                {"id": "in", "type": "input"},
                {
                    "id": "llm1",
                    "type": "llm",
                    "data": {
                        "system_prompt": "You are a friendly, helpful assistant.",
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
]


async def seed_templates() -> None:
    factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with factory() as session:
        for spec in TEMPLATES:
            existing = await _repo.get_by_name(session, spec["name"])
            if existing is not None:
                continue
            session.add(
                Template(
                    name=spec["name"],
                    description=spec["description"],
                    category=spec["category"],
                    graph_json=spec["graph_json"],
                )
            )
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed_templates())
