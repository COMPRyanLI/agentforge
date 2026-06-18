"""arq worker.

Run with:  uv run arq app.workers.WorkerSettings
"""

from __future__ import annotations

import asyncio
import sys

# Must run before any event loop is created: psycopg's async mode (used by the
# LangGraph Postgres checkpointer) cannot run on Windows' default
# ProactorEventLoop, only on SelectorEventLoop.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

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
from app.runtime.checkpointer import close_checkpointer, get_checkpointer
from app.runtime.compiler import GraphCompiler
from app.runtime.errors import AgentRuntimeError
from app.runtime.event_emitter import EventEmitter
from app.runtime.executor import execute_graph
from app.runtime.registry import ToolRegistry
from app.runtime.retry import TRANSIENT_EXCEPTIONS

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
    ctx: dict[str, Any],
    run_id_str: str,
    resume: bool = False,
    resume_value: Any = None,  # justified: mirrors langgraph.types.Command(resume=...)'s Any
) -> None:
    """Execute an agent graph run asynchronously.

    Loads the Run record, compiles the graph, emits events to Redis pub/sub,
    and updates run status on completion.

    resume=True continues from the last checkpoint on the run's thread_id
    (used by POST /runs/{id}/resume and by replay) instead of starting fresh.
    resume_value carries a human's approval/rejection decision back into a
    paused require_approval tool node (only meaningful alongside resume=True).
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
                llm,
                registry,
                factory,
                tool_id_to_name=tool_id_to_name,
                event_emitter=emitter,
                checkpointer=ctx.get("checkpointer"),
            )
            compiled = compiler.compile(graph_json)

            started_at = datetime.now(UTC)
            run = await _run_repo.update_status(session, run, "running", started_at=started_at)
            await session.commit()

            user_input: str | None = None if resume else run.input_json.get("input", "")
            thread_id: str = run.thread_id

        try:
            result = await execute_graph(
                compiled,
                run_id=run_id_str,
                thread_id=thread_id,
                user_input=user_input,
                resume=resume,
                resume_value=resume_value,
            )
            ended_at = datetime.now(UTC)
            async with factory() as session:
                run = await _run_repo.get(session, uuid.UUID(run_id_str))
                if run is not None:
                    if result.awaiting_approval is not None:
                        snapshot = await compiled.aget_state(
                            {"configurable": {"thread_id": thread_id}}
                        )
                        # Defaults below are not silently masking missing data:
                        # snapshot.values is RunState, always seeded with
                        # step_index by execute_graph; awaiting_approval's
                        # payload is built internally by make_tool_handler's
                        # interrupt() call, which always includes node_id.
                        await emitter.emit(
                            step_index=snapshot.values.get("step_index", 0),
                            node_id=str(result.awaiting_approval.get("node_id", "")),
                            event_type="interrupt",
                            payload=result.awaiting_approval,
                            ts=ended_at,
                        )
                        await _run_repo.update_status(
                            session,
                            run,
                            "interrupted",
                            awaiting_approval=True,
                            ended_at=ended_at,
                        )
                    else:
                        await _run_repo.update_status(
                            session,
                            run,
                            "succeeded",
                            output_json={"output": result.output},
                            awaiting_approval=False,
                            ended_at=ended_at,
                        )
                    await session.commit()

        except TRANSIENT_EXCEPTIONS as exc:
            # Retries (app.runtime.retry) are already exhausted by this point.
            # A checkpoint exists at the last completed node boundary, so this
            # run is resumable — mark "interrupted", not "failed".
            ended_at = datetime.now(UTC)
            logger.warning(
                "execute_run: run %s interrupted (transient, retries exhausted): %s",
                run_id_str,
                exc,
            )
            try:
                async with factory() as session:
                    run = await _run_repo.get(session, uuid.UUID(run_id_str))
                    if run is not None:
                        await _run_repo.update_status(
                            session,
                            run,
                            "interrupted",
                            error_json={"error": str(exc), "type": type(exc).__name__},
                            awaiting_approval=False,
                            ended_at=ended_at,
                        )
                        await session.commit()
            except Exception:
                logger.error(
                    "execute_run: could not persist interrupted status for run %s",
                    run_id_str,
                    exc_info=True,
                )

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
                            awaiting_approval=False,
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
                            awaiting_approval=False,
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


async def startup(ctx: dict[str, Any]) -> None:  # justified: arq ctx is untyped dict
    """Open the checkpointer's connection pool once per worker process."""
    ctx["checkpointer"] = await get_checkpointer()


async def shutdown(ctx: dict[str, Any]) -> None:  # justified: arq ctx is untyped dict
    """Close the checkpointer's connection pool on worker shutdown."""
    await close_checkpointer()


class WorkerSettings:
    functions = [ping, execute_run]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    on_startup = startup
    on_shutdown = shutdown
