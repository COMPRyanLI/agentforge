"""arq worker.

Run with:  uv run arq app.workers.WorkerSettings
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as redis_asyncio
from arq.connections import RedisSettings
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db import get_engine
from app.llm.provider import OllamaProvider
from app.repositories.agent import AgentRepo
from app.repositories.run import RunRepo
from app.repositories.tool import ToolRepo
from app.runtime.builtins import register_builtins
from app.runtime.compiler import GraphCompiler
from app.runtime.errors import AgentRuntimeError
from app.runtime.event_emitter import EventEmitter
from app.runtime.executor import execute_graph
from app.runtime.registry import ToolRegistry

logger = logging.getLogger(__name__)

_run_repo = RunRepo()
_agent_repo = AgentRepo()
_tool_repo = ToolRepo()


def _extract_tool_ids(graph_json: dict[str, Any]) -> list[uuid.UUID]:
    ids: list[uuid.UUID] = []
    for node in graph_json.get("nodes", []):
        if node.get("type") == "tool":
            raw_id = (node.get("data") or {}).get("tool_id")
            if raw_id:
                try:
                    ids.append(uuid.UUID(str(raw_id)))
                except ValueError:
                    pass
    return ids


async def execute_run(  # justified: arq ctx is untyped dict
    ctx: dict[str, Any], run_id_str: str
) -> None:
    """Execute an agent graph run asynchronously.

    Loads the Run record, compiles the graph, emits events to Redis pub/sub,
    and updates run status on completion.
    """
    settings = get_settings()
    redis_client: Redis = redis_asyncio.from_url(  # type: ignore[no-untyped-call]
        settings.redis_url
    )  # justified: redis.asyncio module-level from_url lacks stubs

    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        get_engine(), expire_on_commit=False
    )

    try:
        async with factory() as session:
            run = await _run_repo.get(session, uuid.UUID(run_id_str))
            if run is None:
                logger.error("execute_run: run %s not found", run_id_str)
                return

            agent = await _agent_repo.get(session, run.agent_id)
            if agent is None:
                logger.error("execute_run: agent %s not found for run %s", run.agent_id, run_id_str)
                return

            version = await _agent_repo.get_version(session, run.agent_version_id)
            if version is None:
                logger.error(
                    "execute_run: version %s not found for run %s",
                    run.agent_version_id,
                    run_id_str,
                )
                return

            graph_json: dict[str, Any] = version.graph_json
            tool_id_list = _extract_tool_ids(graph_json)
            tool_id_to_name: dict[str, str] = {}
            for tid in tool_id_list:
                tool = await _tool_repo.get(session, tid)
                if tool is None:
                    logger.error("execute_run: tool %s not found for run %s", tid, run_id_str)
                    await _run_repo.update_status(
                        session,
                        run,
                        "failed",
                        error_json={"error": f"Tool {tid} not found", "type": "ConfigError"},
                        ended_at=datetime.now(UTC),
                    )
                    await session.commit()
                    return
                tool_id_to_name[str(tool.id)] = tool.name

            registry = ToolRegistry()
            register_builtins(registry)

            emitter = EventEmitter(run_id_str, factory, redis_client)
            llm = OllamaProvider(settings.ollama_base_url, settings.ollama_model)
            compiler = GraphCompiler(
                llm, registry, tool_id_to_name=tool_id_to_name, event_emitter=emitter
            )
            compiled = compiler.compile(graph_json)

            started_at = datetime.now(UTC)
            run = await _run_repo.update_status(session, run, "running", started_at=started_at)
            await session.commit()

            user_input: str = run.input_json.get("input", "")
            thread_id: str = run.thread_id

        try:
            output = await execute_graph(
                compiled,
                run_id=run_id_str,
                thread_id=thread_id,
                user_input=user_input,
            )
            ended_at = datetime.now(UTC)
            async with factory() as session:
                run = await _run_repo.get(session, uuid.UUID(run_id_str))
                if run is not None:
                    await _run_repo.update_status(
                        session,
                        run,
                        "succeeded",
                        output_json={"output": output},
                        ended_at=ended_at,
                    )
                    await session.commit()

        except AgentRuntimeError as exc:
            ended_at = datetime.now(UTC)
            logger.warning("execute_run: run %s failed (expected): %s", run_id_str, exc)
            try:
                async with factory() as session:
                    run = await _run_repo.get(session, uuid.UUID(run_id_str))
                    if run is not None:
                        await _run_repo.update_status(
                            session,
                            run,
                            "failed",
                            error_json={"error": str(exc), "type": type(exc).__name__},
                            ended_at=ended_at,
                        )
                        await session.commit()
            except Exception:
                logger.error(
                    "execute_run: could not persist failure status for run %s",
                    run_id_str,
                    exc_info=True,
                )

        except Exception as exc:
            ended_at = datetime.now(UTC)
            logger.error(
                "execute_run: run %s failed (unexpected): %s", run_id_str, exc, exc_info=True
            )
            try:
                async with factory() as session:
                    run = await _run_repo.get(session, uuid.UUID(run_id_str))
                    if run is not None:
                        await _run_repo.update_status(
                            session,
                            run,
                            "failed",
                            error_json={"error": str(exc), "type": type(exc).__name__},
                            ended_at=ended_at,
                        )
                        await session.commit()
            except Exception:
                logger.error(
                    "execute_run: could not persist failure status for run %s",
                    run_id_str,
                    exc_info=True,
                )

    finally:
        await redis_client.aclose()


async def ping(ctx: dict[str, Any]) -> str:  # justified: arq does not export a typed context
    return "pong"


class WorkerSettings:
    functions = [ping, execute_run]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
