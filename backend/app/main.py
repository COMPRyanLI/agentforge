"""FastAPI application entrypoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import agents, auth, health, runs, tools
from app.schemas.health import RootResponse

settings = get_settings()

app = FastAPI(title=settings.app_name)

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


@app.get("/")
async def root() -> RootResponse:
    return RootResponse(app=get_settings().app_name, docs="/docs")
