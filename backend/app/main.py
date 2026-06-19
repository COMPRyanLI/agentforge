"""FastAPI application entrypoint."""

import asyncio
import sys

# Must run before any event loop is created: psycopg's async mode (used by the
# LangGraph Postgres checkpointer) cannot run on Windows' default
# ProactorEventLoop, only on SelectorEventLoop.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import close_engine
from app.routers import agents, auth, health, marketplace, runs, templates, tools
from app.runtime.checkpointer import close_checkpointer
from app.schemas.health import RootResponse

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    # Both pools are created lazily on first use (possibly never, e.g. in a
    # request-less health check process) — closing is a no-op if so.
    await close_checkpointer()
    await close_engine()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
)

app.include_router(health.router)
app.include_router(auth.router, prefix="/auth")
app.include_router(agents.router, prefix="/agents")
app.include_router(tools.router, prefix="/tools")
app.include_router(runs.router, prefix="/runs")
app.include_router(marketplace.router, prefix="/marketplace")
app.include_router(templates.router, prefix="/templates")


@app.get("/")
async def root() -> RootResponse:
    return RootResponse(app=get_settings().app_name, docs="/docs")
