"""
Pydantic request and response models for API v1.

Routes never return ORM objects; every response is one of these models.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"


class DependencyStatus(StrEnum):
    OK = "ok"
    UNAVAILABLE = "unavailable"


class HealthChecks(BaseModel):
    database: DependencyStatus


class HealthResponse(BaseModel):
    """Liveness (the process answered) and readiness (its dependencies are reachable)."""

    status: HealthStatus
    service: str
    version: str
    checks: HealthChecks
