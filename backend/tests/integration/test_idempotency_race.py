"""Integration test for the tool_calls double-enqueue race.

Uses two genuinely independent sessions/connections (not the single shared,
rolled-back db_session) to reproduce two concurrent processes racing to
create the same idempotency_key row — the scenario services/run.py::resume's
docstring calls out as a known risk if a run is ever double-enqueued.
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.models.agent import Agent, AgentVersion
from app.models.run import Run
from app.models.run import ToolCall as ToolCallRow
from app.models.user import User
from app.runtime.builtins import register_builtins
from app.runtime.errors import ToolCallAmbiguousError
from app.runtime.registry import ToolRegistry, invoke_tool_idempotent

GRAPH: dict[str, object] = {
    "nodes": [{"id": "in", "type": "input"}, {"id": "out", "type": "output"}],
    "edges": [{"source": "in", "target": "out"}],
}


async def _seed_run_id(db_engine: AsyncEngine) -> str:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        user = User(email=f"race_{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
        session.add(user)
        await session.flush()

        agent = Agent(owner_id=user.id, name="race-test-agent")
        session.add(agent)
        await session.flush()

        version = AgentVersion(agent_id=agent.id, version_number=1, graph_json=GRAPH)
        session.add(version)
        await session.flush()
        agent.current_version_id = version.id
        await session.flush()

        run = Run(
            agent_id=agent.id,
            agent_version_id=version.id,
            thread_id=str(uuid.uuid4()),
            status="running",
            input_json={"input": "go"},
        )
        session.add(run)
        await session.flush()
        await session.commit()
        return str(run.id)


async def test_concurrent_invoke_tool_idempotent_loses_race_cleanly(
    db_engine: AsyncEngine,
) -> None:
    """Two callers racing to create the same idempotency key: one wins and
    invokes the tool exactly once; the other gets ToolCallAmbiguousError
    (never IntegrityError) and never invokes the tool itself."""
    run_id = await _seed_run_id(db_engine)
    # NullPool — each session_factory() call below gets its own real connection,
    # so the two invoke_tool_idempotent calls genuinely race at the DB level.
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    registry = ToolRegistry()
    register_builtins(registry)

    common_kwargs: dict[str, object] = dict(run_id=run_id, node_id="t1", step_index=0, call_index=0)

    results = await asyncio.gather(
        invoke_tool_idempotent(
            factory, registry, "calculator", {"expression": "1+1"}, **common_kwargs
        ),
        invoke_tool_idempotent(
            factory, registry, "calculator", {"expression": "1+1"}, **common_kwargs
        ),
        return_exceptions=True,
    )

    outcomes = [r for r in results if not isinstance(r, BaseException)]
    errors = [r for r in results if isinstance(r, BaseException)]

    # Exactly one side wins and gets the real result; the other loses the
    # race cleanly (ToolCallAmbiguousError, never a raw IntegrityError/500).
    assert len(outcomes) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], ToolCallAmbiguousError)
    assert outcomes[0] == {"result": 2.0, "expression": "1+1"}

    async with factory() as session:
        result = await session.execute(
            select(ToolCallRow).where(ToolCallRow.run_id == uuid.UUID(run_id))
        )
        rows = list(result.scalars().all())
    assert len(rows) == 1
    assert rows[0].status == "completed"
