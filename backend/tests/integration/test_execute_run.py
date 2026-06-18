"""Integration tests for the execute_run arq worker task.

Uses a real DB (db_session fixture) but mocks the LLM and Redis so
no live Ollama or Redis is needed in CI.
"""

from __future__ import annotations

import socket
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.runtime.http_tool as http_tool_module
from app.llm.provider import LLMResponse
from app.llm.provider import ToolCall as LLMToolCall
from app.models.agent import Agent, AgentVersion
from app.models.run import Run
from app.models.tool import Tool
from app.models.user import User
from app.repositories.run import RunRepo
from app.workers.worker import execute_run

SIMPLE_GRAPH: dict[str, Any] = {
    "nodes": [
        {"id": "in", "type": "input"},
        {"id": "llm1", "type": "llm", "data": {"system_prompt": "Be helpful.", "tools": []}},
        {"id": "out", "type": "output"},
    ],
    "edges": [
        {"source": "in", "target": "llm1"},
        {"source": "llm1", "target": "out"},
    ],
}


async def _seed_pending_run(
    session: AsyncSession, graph_json: dict[str, Any] = SIMPLE_GRAPH
) -> Run:
    user = User(email=f"worker_{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
    session.add(user)
    await session.flush()

    agent = Agent(owner_id=user.id, name="worker-test-agent")
    session.add(agent)
    await session.flush()

    version = AgentVersion(agent_id=agent.id, version_number=1, graph_json=graph_json)
    session.add(version)
    await session.flush()

    agent.current_version_id = version.id
    await session.flush()

    run = Run(
        agent_id=agent.id,
        agent_version_id=version.id,
        thread_id=str(uuid.uuid4()),
        status="pending",
        input_json={"input": "what is the answer?"},
    )
    session.add(run)
    await session.flush()
    await session.commit()
    return run


def _make_factory(session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    factory: MagicMock = MagicMock(spec=async_sessionmaker)

    class _Ctx:
        async def __aenter__(self) -> AsyncSession:
            return session

        async def __aexit__(self, *_: object) -> None:
            pass

    factory.return_value = _Ctx()
    return factory  # type: ignore[return-value]


async def test_execute_run_sets_succeeded_status(db_session: AsyncSession) -> None:
    run = await _seed_pending_run(db_session)
    run_id_str = str(run.id)

    mock_redis = AsyncMock()
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = LLMResponse(content="42 is the answer.", tool_calls=[])
    factory = _make_factory(db_session)

    with (
        patch("app.workers.worker.redis_asyncio.from_url", return_value=mock_redis),
        patch("app.workers.worker.async_sessionmaker", return_value=factory),
        patch("app.workers.worker.OllamaProvider", return_value=mock_llm),
    ):
        await execute_run({}, run_id_str)

    repo = RunRepo()
    updated = await repo.get(db_session, uuid.UUID(run_id_str))
    assert updated is not None
    assert updated.status == "succeeded"
    assert updated.output_json is not None
    assert "42 is the answer." in updated.output_json.get("output", "")


async def test_execute_run_sets_failed_on_llm_error(db_session: AsyncSession) -> None:
    run = await _seed_pending_run(db_session)
    run_id_str = str(run.id)

    mock_redis = AsyncMock()
    mock_llm = AsyncMock()
    mock_llm.chat.side_effect = RuntimeError("LLM connection refused")
    factory = _make_factory(db_session)

    with (
        patch("app.workers.worker.redis_asyncio.from_url", return_value=mock_redis),
        patch("app.workers.worker.async_sessionmaker", return_value=factory),
        patch("app.workers.worker.OllamaProvider", return_value=mock_llm),
    ):
        await execute_run({}, run_id_str)

    repo = RunRepo()
    updated = await repo.get(db_session, uuid.UUID(run_id_str))
    assert updated is not None
    assert updated.status == "failed"
    assert updated.error_json is not None


FAST_RETRY_GRAPH: dict[str, Any] = {
    "nodes": [
        {"id": "in", "type": "input"},
        {
            "id": "llm1",
            "type": "llm",
            "data": {
                "system_prompt": "Be helpful.",
                "tools": [],
                "retry": {"max_retries": 1, "backoff_seconds": 0},
            },
        },
        {"id": "out", "type": "output"},
    ],
    "edges": [
        {"source": "in", "target": "llm1"},
        {"source": "llm1", "target": "out"},
    ],
}


async def test_execute_run_sets_interrupted_on_transient_error_after_retries(
    db_session: AsyncSession,
) -> None:
    run = await _seed_pending_run(db_session, graph_json=FAST_RETRY_GRAPH)
    run_id_str = str(run.id)

    mock_redis = AsyncMock()
    mock_llm = AsyncMock()
    mock_llm.chat.side_effect = ConnectionError("ollama unreachable")
    factory = _make_factory(db_session)

    with (
        patch("app.workers.worker.redis_asyncio.from_url", return_value=mock_redis),
        patch("app.workers.worker.async_sessionmaker", return_value=factory),
        patch("app.workers.worker.OllamaProvider", return_value=mock_llm),
    ):
        await execute_run({}, run_id_str)

    repo = RunRepo()
    updated = await repo.get(db_session, uuid.UUID(run_id_str))
    assert updated is not None
    assert updated.status == "interrupted"
    assert updated.error_json is not None
    # initial attempt + 1 retry (max_retries=1)
    assert mock_llm.chat.call_count == 2


async def test_execute_run_sets_failed_on_permanent_agent_runtime_error(
    db_session: AsyncSession,
) -> None:
    from app.runtime.errors import ToolArgValidationError

    run = await _seed_pending_run(db_session, graph_json=FAST_RETRY_GRAPH)
    run_id_str = str(run.id)

    mock_redis = AsyncMock()
    mock_llm = AsyncMock()
    mock_llm.chat.side_effect = ToolArgValidationError("bad args")
    factory = _make_factory(db_session)

    with (
        patch("app.workers.worker.redis_asyncio.from_url", return_value=mock_redis),
        patch("app.workers.worker.async_sessionmaker", return_value=factory),
        patch("app.workers.worker.OllamaProvider", return_value=mock_llm),
    ):
        await execute_run({}, run_id_str)

    repo = RunRepo()
    updated = await repo.get(db_session, uuid.UUID(run_id_str))
    assert updated is not None
    assert updated.status == "failed"
    assert updated.error_json is not None
    # permanent error — never retried
    assert mock_llm.chat.call_count == 1


async def test_execute_run_not_found_returns_gracefully() -> None:
    """A missing run_id should log and return without raising."""
    fake_id = str(uuid.uuid4())
    mock_redis = AsyncMock()

    class _EmptyCtx:
        async def __aenter__(self) -> AsyncSession:
            s = AsyncMock(spec=AsyncSession)
            s.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
            return s

        async def __aexit__(self, *_: object) -> None:
            pass

    factory: MagicMock = MagicMock(spec=async_sessionmaker)
    factory.return_value = _EmptyCtx()

    with (
        patch("app.workers.worker.redis_asyncio.from_url", return_value=mock_redis),
        patch("app.workers.worker.async_sessionmaker", return_value=factory),
    ):
        await execute_run({}, fake_id)


async def test_execute_run_publishes_events(db_session: AsyncSession) -> None:
    run = await _seed_pending_run(db_session)
    run_id_str = str(run.id)

    mock_redis = AsyncMock()
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = LLMResponse(content="done", tool_calls=[])
    factory = _make_factory(db_session)

    with (
        patch("app.workers.worker.redis_asyncio.from_url", return_value=mock_redis),
        patch("app.workers.worker.async_sessionmaker", return_value=factory),
        patch("app.workers.worker.OllamaProvider", return_value=mock_llm),
    ):
        await execute_run({}, run_id_str)

    # At least some Redis publishes should have happened (one per node event)
    assert mock_redis.publish.call_count > 0
    # All publishes should be to the correct channel
    for call in mock_redis.publish.call_args_list:
        channel = call.args[0]
        assert channel == f"run:{run_id_str}"


LLM_HTTP_TOOL_GRAPH: dict[str, Any] = {
    "nodes": [
        {"id": "in", "type": "input"},
        {
            "id": "llm1",
            "type": "llm",
            "data": {"system_prompt": "Use the tool.", "tools": ["get_weather"]},
        },
        {"id": "out", "type": "output"},
    ],
    "edges": [
        {"source": "in", "target": "llm1"},
        {"source": "llm1", "target": "out"},
    ],
}


async def test_llm_node_invokes_custom_http_tool_by_name(db_session: AsyncSession) -> None:
    """A graph's llm node references a user-defined HTTP tool by name —
    proves app.runtime.registry_builder.build_registry actually wires a real
    executor in for it, not just builtins."""
    user = User(email=f"httptool_{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
    db_session.add(user)
    await db_session.flush()

    tool = Tool(
        owner_id=user.id,
        name="get_weather",
        description="Get the weather",
        json_schema={
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
        impl_type="http",
        config_json={"url": "https://weather.example/lookup", "method": "GET"},
    )
    db_session.add(tool)
    await db_session.flush()

    agent = Agent(owner_id=user.id, name="weather-agent")
    db_session.add(agent)
    await db_session.flush()

    version = AgentVersion(agent_id=agent.id, version_number=1, graph_json=LLM_HTTP_TOOL_GRAPH)
    db_session.add(version)
    await db_session.flush()
    agent.current_version_id = version.id
    await db_session.flush()

    run = Run(
        agent_id=agent.id,
        agent_version_id=version.id,
        thread_id=str(uuid.uuid4()),
        status="pending",
        input_json={"input": "what's the weather in nyc?"},
    )
    db_session.add(run)
    await db_session.flush()
    await db_session.commit()
    run_id_str = str(run.id)

    captured_query: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_query["q"] = str(request.url.params)
        return httpx.Response(200, json={"forecast": "sunny"})

    async def _fake_resolve(host: str, port: int) -> list[tuple[Any, ...]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

    def _fake_make_client(timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.MockTransport(handler), follow_redirects=False, timeout=timeout
        )

    mock_redis = AsyncMock()
    mock_llm = AsyncMock()
    mock_llm.chat.side_effect = [
        LLMResponse(
            content=None,
            tool_calls=[LLMToolCall(name="get_weather", arguments={"city": "nyc"})],
        ),
        LLMResponse(content="It's sunny in NYC.", tool_calls=[]),
    ]
    factory = _make_factory(db_session)

    with (
        patch("app.workers.worker.redis_asyncio.from_url", return_value=mock_redis),
        patch("app.workers.worker.async_sessionmaker", return_value=factory),
        patch("app.workers.worker.OllamaProvider", return_value=mock_llm),
        pytest.MonkeyPatch().context() as mp,
    ):
        mp.setattr(http_tool_module, "_resolve", _fake_resolve)
        mp.setattr(http_tool_module, "_make_client", _fake_make_client)
        await execute_run({}, run_id_str)

    repo = RunRepo()
    updated = await repo.get(db_session, uuid.UUID(run_id_str))
    assert updated is not None
    assert updated.status == "succeeded"
    assert updated.output_json is not None
    assert updated.output_json.get("output") == "It's sunny in NYC."
    assert "city=nyc" in captured_query["q"]
