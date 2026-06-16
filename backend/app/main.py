"""FastAPI application entrypoint."""

from fastapi import FastAPI

from app.config import get_settings
from app.routers import agents, auth, health, tools
from app.schemas.health import RootResponse

app = FastAPI(title=get_settings().app_name)

app.include_router(health.router)
app.include_router(auth.router, prefix="/auth")
app.include_router(agents.router, prefix="/agents")
app.include_router(tools.router, prefix="/tools")


@app.get("/")
async def root() -> RootResponse:
    return RootResponse(app=get_settings().app_name, docs="/docs")
