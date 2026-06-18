"""LangGraph Postgres checkpointer wiring.

AsyncPostgresSaver manages its own schema (checkpoints, checkpoint_blobs,
checkpoint_writes) via psycopg, separate from our Alembic-managed tables. It
needs a plain libpq DSN, not the asyncpg-style URL the rest of the app uses.

This module is a lazy singleton per process (mirrors app/db.py's _engine
pattern) — the FastAPI app and the arq worker each get their own connection
pool; pools are never shared across processes.
"""

from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.runnables.config import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

from app.config import get_settings

_pool: AsyncConnectionPool[AsyncConnection[DictRow]] | None = None
_saver: AsyncPostgresSaver | None = None
_lock = asyncio.Lock()


def _to_psycopg_dsn(database_url: str) -> str:
    """Strip the asyncpg driver suffix to get a plain libpq-style DSN."""
    return database_url.replace("postgresql+asyncpg://", "postgresql://")


async def get_checkpointer() -> AsyncPostgresSaver:
    """Return the process-wide AsyncPostgresSaver, creating it on first use."""
    global _pool, _saver
    if _saver is not None:
        return _saver
    async with _lock:
        if _saver is not None:
            return _saver
        dsn = _to_psycopg_dsn(get_settings().database_url)
        pool: AsyncConnectionPool[AsyncConnection[DictRow]] = AsyncConnectionPool(
            dsn,
            open=False,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        )
        await pool.open()
        saver = AsyncPostgresSaver(pool)
        await saver.setup()
        _pool = pool
        _saver = saver
        return _saver


async def close_checkpointer() -> None:
    """Close the process-wide connection pool, if one was created."""
    global _pool, _saver
    if _pool is not None:
        await _pool.close()
    _pool = None
    _saver = None


async def fork_thread_at_step(
    checkpointer: BaseCheckpointSaver[Any],
    old_thread_id: str,
    new_thread_id: str,
    target_step_index: int,
) -> bool:
    """Copy the checkpoint whose post-node step_index == target_step_index from
    old_thread_id to new_thread_id, so a fresh run on new_thread_id can resume
    forward from exactly that point via ainvoke(None, config).

    Returns True if a matching checkpoint was found and copied, False otherwise.

    Note: this must fully drain the `alist` async generator rather than
    `break`-ing out of it early. `alist` holds the saver's connection lock for
    the duration of its underlying cursor; breaking out mid-iteration leaves
    that lock held by a suspended generator frame until it's garbage
    collected, which can deadlock a subsequent call (e.g. `aput`) that needs
    the same lock.
    """
    # checkpoint_ns omitted here (rather than set to ""): alist() defaults a
    # missing checkpoint_ns to matching all namespaces for this thread_id, so
    # it has no filtering effect on old_config. new_config below sets it
    # explicitly to "" (the only namespace this graph ever writes to) because
    # aput() does not default a missing key the same way — omitting it there
    # would write the copy under namespace None instead of "".
    old_config: RunnableConfig = {"configurable": {"thread_id": old_thread_id}}
    match: Any = None
    async for tup in checkpointer.alist(old_config):
        channel_values: dict[str, Any] = tup.checkpoint.get("channel_values", {})
        if channel_values.get("step_index") == target_step_index:
            match = tup
    if match is None:
        return False
    new_config: RunnableConfig = {"configurable": {"thread_id": new_thread_id, "checkpoint_ns": ""}}
    new_metadata = dict(match.metadata)
    new_metadata["source"] = "fork"
    await checkpointer.aput(
        new_config,
        match.checkpoint,
        new_metadata,  # type: ignore[arg-type]
        match.checkpoint.get("channel_versions", {}),
    )
    return True
