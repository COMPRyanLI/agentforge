"""arq worker.

Phase 0: a single ping task proves the queue wiring. Phase 3 adds the real
`execute_run` task that runs an agent graph and streams events to Redis.
Run with:  uv run arq app.workers.WorkerSettings
"""

from typing import Any

from arq.connections import RedisSettings

from app.config import get_settings


async def ping(ctx: dict[str, Any]) -> str:  # justified: arq does not export a typed context
    return "pong"


class WorkerSettings:
    functions = [ping]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
