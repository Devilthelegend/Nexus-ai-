"""Liveness and readiness endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthStatus(BaseModel):
    """Health probe response payload."""

    status: str
    service: str


@router.get("/healthz", response_model=HealthStatus)
async def healthz() -> HealthStatus:
    """Liveness probe: the process is up and serving requests."""
    return HealthStatus(status="ok", service="nexusai")


@router.get("/readyz", response_model=HealthStatus)
async def readyz() -> HealthStatus:
    """Readiness probe: the service is ready to accept traffic.

    Phase 0 returns a static ready state. Dependency checks (PostgreSQL,
    Redis, Qdrant) are added in later phases as those clients are wired in.
    """
    return HealthStatus(status="ready", service="nexusai")
