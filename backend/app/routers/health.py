"""Liveness endpoint. Intentionally touches no external service so it works
before any infra (DB/Redis/Ollama) is provisioned."""

from fastapi import APIRouter

from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> HealthResponse:
    return HealthResponse(status="ok")
