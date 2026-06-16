"""FastAPI application entrypoint."""

from fastapi import FastAPI

from app.config import settings
from app.routers import health
from app.schemas.health import RootResponse

app = FastAPI(title=settings.app_name)
app.include_router(health.router)


@app.get("/")
async def root() -> RootResponse:
    return RootResponse(app=settings.app_name, docs="/docs")
